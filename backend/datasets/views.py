from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils import timezone
from .models import Dataset
from .serializers import DatasetSerializer
from ml.preprocessor import DataPreprocessor
from ml.column_mapper import suggest_mapping, validate_mapping, get_field_definitions
import pandas as pd
import logging
import json
import os

logger = logging.getLogger(__name__)

MAX_ROWS = 500_000  # sanity cap independent of raw byte size
MIN_ROWS = 5        # need at least a handful of rows to do anything useful


def validate_csv(df):
    """
    Validate an uploaded CSV for basic structural sanity only.
    This platform is dataset-agnostic, so it no longer requires any fixed
    column names here (that used to hard-require 'product', 'quantity',
    'revenue', 'date'). Column meaning is established afterwards through
    the Column Mapping step, not by name-matching at upload time.
    """
    report = {'errors': [], 'warnings': [], 'stats': {}}
    if len(df.columns) < 2:
        report['errors'].append('CSV must have at least 2 columns to build a forecast.')
    if len(df) < MIN_ROWS:
        report['errors'].append(f'Dataset has only {len(df)} rows; at least {MIN_ROWS} are needed.')
    if len(df) > MAX_ROWS:
        report['errors'].append(f'Dataset has {len(df)} rows, exceeding the {MAX_ROWS} row limit')
    duplicates = df.duplicated().sum()
    if duplicates > 0:
        report['warnings'].append(f'{duplicates} duplicate rows found')
    null_counts = df.isnull().sum().to_dict()
    total_nulls = sum(null_counts.values())
    if total_nulls > 0:
        report['warnings'].append(f'{total_nulls} missing values found')
    report['stats'] = {
        'total_rows': len(df),
        'total_columns': len(df.columns),
        'duplicate_rows': int(duplicates),
        'missing_values': {k: int(v) for k, v in null_counts.items() if v > 0},
        'columns': list(df.columns),
    }
    return report


class DatasetUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=400)
        file = request.FILES['file']
        if not file.name.endswith('.csv'):
            return Response({'error': 'Only CSV files allowed'}, status=400)
        # Belt-and-suspenders: DATA_UPLOAD_MAX_MEMORY_SIZE already rejects
        # oversized bodies at the Django layer, but checking explicitly here
        # gives a clean error instead of a raw request-entity-too-large.
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file.size > max_bytes:
            return Response({'error': f'File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit'}, status=400)
        try:
            df = pd.read_csv(file)
            report = validate_csv(df)
            if report['errors']:
                return Response({'error': 'Validation failed', 'details': report}, status=400)
            file.seek(0)
            columns = list(df.columns)
            suggested = suggest_mapping(columns)
            dataset = Dataset.objects.create(
                user=request.user,
                name=file.name,
                file=file,
                rows=len(df),
                columns=len(df.columns),
                validation_report=report,
                status='uploaded',
                detected_columns=columns,
                suggested_mapping=suggested,
                mapping_status='pending',
            )
            return Response({
                'message': 'Dataset uploaded successfully. Please confirm the column mapping next.',
                'dataset': DatasetSerializer(dataset).data,
            }, status=201)
        except pd.errors.ParserError as e:
            return Response({'error': f'Could not parse CSV: {str(e)}'}, status=400)
        except Exception:
            logger.exception('Dataset upload failed for user %s', request.user.id)
            return Response({'error': 'Failed to process file. Please check the CSV format.'}, status=400)


class DatasetCleanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            if request.user.role == 'admin':
                dataset = Dataset.objects.get(pk=pk)
            else:
                dataset = Dataset.objects.get(pk=pk, user=request.user)
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found'}, status=404)
        if dataset.mapping_status != 'mapped' or not dataset.column_mapping:
            return Response(
                {'error': 'Please confirm the column mapping for this dataset before cleaning it.'},
                status=400,
            )
        try:
            df = pd.read_csv(dataset.file.path)
            preprocessor = DataPreprocessor()
            cleaned_df, cleaning_report = preprocessor.clean(df, mapping=dataset.column_mapping)
            cleaned_path = dataset.file.path.replace('datasets/', 'cleaned_datasets/').replace('.csv', '_cleaned.csv')
            os.makedirs(os.path.dirname(cleaned_path), exist_ok=True)
            cleaned_df.to_csv(cleaned_path, index=False)
            dataset.status = 'cleaned'
            dataset.cleaned_file = cleaned_path.split('media/')[-1]
            dataset.cleaning_report = cleaning_report
            dataset.cleaned_at = timezone.now()
            dataset.rows = len(cleaned_df)
            dataset.save()
            return Response({'message': 'Data cleaned successfully', 'dataset': DatasetSerializer(dataset).data, 'cleaning_report': cleaning_report})
        except Exception:
            logger.exception('Dataset cleaning failed for dataset %s', pk)
            dataset.status = 'error'
            dataset.save()
            return Response({'error': 'Cleaning failed. Please check the dataset format.'}, status=500)


class DatasetColumnsView(APIView):
    """
    Step 2 of the upload flow: report the raw columns detected in the file,
    a sample preview, and an auto-suggested mapping onto canonical fields,
    so the frontend can render the Column Mapping screen.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            if request.user.role == 'admin':
                dataset = Dataset.objects.get(pk=pk)
            else:
                dataset = Dataset.objects.get(pk=pk, user=request.user)
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found'}, status=404)
        try:
            df = pd.read_csv(dataset.file.path)
            sample_rows = df.head(5).fillna('').to_dict(orient='records')
            # Re-suggest live in case detected_columns/suggested_mapping predate
            # this feature (e.g. datasets uploaded before mapping existed).
            columns = dataset.detected_columns or list(df.columns)
            suggested = dataset.suggested_mapping or suggest_mapping(columns)
            current = dataset.column_mapping or suggested
            return Response({
                'columns': columns,
                'sample_rows': sample_rows,
                'suggested_mapping': suggested,
                'current_mapping': current,
                'mapping_status': dataset.mapping_status,
                'fields': get_field_definitions(),
            })
        except Exception:
            logger.exception('Failed to inspect columns for dataset %s', pk)
            return Response({'error': 'Failed to read dataset columns'}, status=500)


class DatasetMappingView(APIView):
    """
    Accepts the user-confirmed (or edited) column mapping and stores it on
    the dataset. Required fields (date, sales) must be mapped; every other
    field is genuinely optional - the pipeline adapts to whatever is present.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            if request.user.role == 'admin':
                dataset = Dataset.objects.get(pk=pk)
            else:
                dataset = Dataset.objects.get(pk=pk, user=request.user)
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found'}, status=404)

        mapping = request.data.get('mapping')
        if not isinstance(mapping, dict):
            return Response({'error': 'mapping must be an object of {field: column_name}'}, status=400)

        # Only accept columns that actually exist in the uploaded file, and
        # only known canonical fields, to avoid ever pushing arbitrary keys
        # into downstream renaming logic.
        valid_columns = set(dataset.detected_columns or [])
        cleaned_mapping = {}
        for field, col in mapping.items():
            if not col:
                continue
            if valid_columns and col not in valid_columns:
                return Response({'error': f"Column '{col}' was not found in this dataset."}, status=400)
            cleaned_mapping[field] = col

        errors = validate_mapping(cleaned_mapping)
        if errors:
            return Response({'error': 'Invalid mapping', 'details': errors}, status=400)

        dataset.column_mapping = cleaned_mapping
        dataset.mapping_status = 'mapped'
        dataset.save()
        return Response({
            'message': 'Column mapping confirmed',
            'dataset': DatasetSerializer(dataset).data,
        })


class DatasetListView(generics.ListAPIView):
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == 'admin':
            return Dataset.objects.select_related('user').all()
        return Dataset.objects.filter(user=self.request.user)


class DatasetDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == 'admin':
            return Dataset.objects.all()
        return Dataset.objects.filter(user=self.request.user)


class DatasetPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            # Previously this was Dataset.objects.get(pk=pk) with no owner
            # check at all - any authenticated user could preview any other
            # user's uploaded sales data just by iterating ids.
            if request.user.role == 'admin':
                dataset = Dataset.objects.get(pk=pk)
            else:
                dataset = Dataset.objects.get(pk=pk, user=request.user)
            file_to_read = dataset.cleaned_file if dataset.cleaned_file else dataset.file
            df = pd.read_csv(file_to_read.path)
            preview_data = df.head(50).fillna('').to_dict(orient='records')
            numeric_df = df.select_dtypes(include='number')
            stats = {
                'rows': len(df),
                'columns': len(df.columns),
                'column_names': list(df.columns),
                'dtypes': {k: str(v) for k, v in df.dtypes.items()},
                'describe': json.loads(numeric_df.describe().to_json()) if not numeric_df.empty else {},
            }
            return Response({'preview': preview_data, 'stats': stats})
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found'}, status=404)
        except Exception:
            logger.exception('Dataset preview failed for dataset %s', pk)
            return Response({'error': 'Failed to generate preview'}, status=500)
