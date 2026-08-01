from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Prediction
from .serializers import PredictionSerializer
from datasets.models import Dataset
from ml.model_trainer import ModelTrainer
from ml.predictor import SalesPredictor
from ml.recommender import RecommendationEngine
import logging

logger = logging.getLogger(__name__)


class RunPredictionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        dataset_id = request.data.get('dataset_id')
        model_type = request.data.get('model_type', 'xgboost')
        try:
            forecast_months = int(request.data.get('forecast_months', 6))
        except (TypeError, ValueError):
            return Response({'error': 'forecast_months must be an integer'}, status=400)
        if not 1 <= forecast_months <= 24:
            return Response({'error': 'forecast_months must be between 1 and 24'}, status=400)
        if model_type not in dict(Prediction.MODEL_CHOICES):
            return Response({'error': 'Invalid model_type'}, status=400)

        prediction_name = request.data.get('name') or f'Prediction {Prediction.objects.filter(user=request.user).count() + 1}'

        try:
            # Previously this was Dataset.objects.get(pk=dataset_id) with no
            # ownership check - any authenticated user could run a prediction
            # (and consume compute) against another user's private dataset.
            if request.user.role == 'admin':
                dataset = Dataset.objects.get(pk=dataset_id)
            else:
                dataset = Dataset.objects.get(pk=dataset_id, user=request.user)
        except Dataset.DoesNotExist:
            return Response({'error': 'Dataset not found'}, status=404)

        try:
            file_path = dataset.cleaned_file.path if dataset.cleaned_file else dataset.file.path
            mapping = dataset.column_mapping or None
            trainer = ModelTrainer(model_type=model_type)
            metrics, model_path = trainer.train(file_path, mapping=mapping)
            predictor = SalesPredictor(model_path=model_path)
            results = predictor.predict(file_path, forecast_months=forecast_months, mapping=mapping)
            engine = RecommendationEngine()
            recommendations = engine.generate(results)
            feature_imp = trainer.get_feature_importance()
            prediction = Prediction.objects.create(
                user=request.user,
                dataset=dataset,
                name=prediction_name,
                model_type=model_type,
                forecast_months=forecast_months,
                mae=metrics.get('mae'),
                rmse=metrics.get('rmse'),
                r2_score=metrics.get('r2'),
                mape=metrics.get('mape'),
                result_json=results,
                feature_importance=feature_imp,
                recommendations=recommendations,
                status='completed'
            )
            return Response({'message': 'Prediction completed', 'prediction': PredictionSerializer(prediction).data}, status=201)
        except ValueError as e:
            # e.g. "Not enough data" from ModelTrainer - safe, user-facing message
            return Response({'error': str(e)}, status=400)
        except Exception:
            # Full traceback used to be returned in the API response, which
            # leaks file paths, library versions, and internal structure to
            # any client. Log it server-side only; return a generic message.
            logger.exception('Prediction failed for dataset %s', dataset_id)
            return Response({'error': 'Prediction failed. Please check the dataset and try again.'}, status=500)


class PredictionListView(generics.ListAPIView):
    serializer_class = PredictionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # select_related avoids a separate query per row for the
        # serializer's username/dataset_name lookups (N+1 fix).
        base = Prediction.objects.select_related('user', 'dataset')
        qs = base.all() if self.request.user.role == 'admin' else base.filter(user=self.request.user)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(model_type__icontains=search))
        return qs


class PredictionDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = PredictionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        base = Prediction.objects.select_related('user', 'dataset')
        if self.request.user.role == 'admin':
            return base.all()
        return base.filter(user=self.request.user)
