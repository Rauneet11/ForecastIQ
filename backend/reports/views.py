from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from django.conf import settings
from .models import Report
from .serializers import ReportSerializer
from predictions.models import Prediction
from ml.report_generator import generate_pdf_report
import logging
import os

logger = logging.getLogger(__name__)


class GenerateReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        prediction_id = request.data.get('prediction_id')
        company_name = request.data.get('company_name', request.user.company or 'Sales Analytics Institute')
        try:
            # Previously Prediction.objects.get(pk=prediction_id) had no
            # ownership check - any authenticated user could generate (and
            # thus read) a full PDF report off another user's prediction.
            if request.user.role == 'admin':
                prediction = Prediction.objects.get(pk=prediction_id)
            else:
                prediction = Prediction.objects.get(pk=prediction_id, user=request.user)
        except Prediction.DoesNotExist:
            return Response({'error': 'Prediction not found'}, status=404)
        try:
            reports_dir = os.path.join(settings.MEDIA_ROOT, 'reports')
            os.makedirs(reports_dir, exist_ok=True)
            filename = f'report_{prediction.id}_{request.user.id}.pdf'
            filepath = os.path.join(reports_dir, filename)
            generate_pdf_report(prediction, company_name, filepath)
            file_size = os.path.getsize(filepath)
            relative_path = f'reports/{filename}'
            report = Report.objects.create(
                user=request.user,
                prediction=prediction,
                title=f'Sales Report - {prediction.name}',
                file=relative_path,
                file_size=file_size
            )
            return Response({'message': 'Report generated', 'report': ReportSerializer(report, context={'request': request}).data}, status=201)
        except Exception:
            logger.exception('Report generation failed for prediction %s', prediction_id)
            return Response({'error': 'Report generation failed. Please try again.'}, status=500)


class ReportListView(generics.ListAPIView):
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        base = Report.objects.select_related('user', 'prediction')
        if self.request.user.role == 'admin':
            return base.all()
        return base.filter(user=self.request.user)

    def get_serializer_context(self):
        return {'request': self.request}


class ReportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            # Previously Report.objects.get(pk=pk) had no ownership check -
            # any authenticated user could download any other user's report
            # PDF (which contains that user's real revenue/sales figures)
            # just by guessing the numeric id.
            if request.user.role == 'admin':
                report = Report.objects.get(pk=pk)
            else:
                report = Report.objects.get(pk=pk, user=request.user)
            response = FileResponse(open(report.file.path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(report.file.name)}"'
            return response
        except Report.DoesNotExist:
            return Response({'error': 'Report not found'}, status=404)
        except FileNotFoundError:
            return Response({'error': 'Report file not found on disk'}, status=404)


class ReportDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == 'admin':
            return Report.objects.all()
        return Report.objects.filter(user=self.request.user)
