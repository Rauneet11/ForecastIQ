from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.models import User
from datasets.models import Dataset
from predictions.models import Prediction
from reports.models import Report
from scenarios.models import ScenarioSimulation
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta
import json


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == 'admin':
            predictions = Prediction.objects.all()
            datasets    = Dataset.objects.all()
            reports     = Report.objects.all()
        else:
            predictions = Prediction.objects.filter(user=user)
            datasets    = Dataset.objects.filter(user=user)
            reports     = Report.objects.filter(user=user)

        total_predictions = predictions.count()
        total_datasets    = datasets.count()

        # ── Aggregate metrics ────────────────────────────────────────────
        total_revenue     = 0
        predicted_revenue = 0
        total_sales       = 0
        monthly_growth    = 0
        best_product      = 'N/A'
        worst_product     = 'N/A'
        accuracy_scores   = []
        product_revenues  = {}

        recent_predictions = []
        for pred in predictions.order_by('-created_at')[:5]:
            recent_predictions.append({
                'id':         pred.id,
                'name':       pred.name,
                'model_type': pred.model_type,
                'r2_score':   pred.r2_score,
                'mae':        pred.mae,
                'created_at': pred.created_at.isoformat(),
            })
            if pred.r2_score:
                accuracy_scores.append(pred.r2_score)

        avg_accuracy = 0
        if accuracy_scores:
            avg_accuracy = round(sum(accuracy_scores) / len(accuracy_scores) * 100, 1)

        # ── Revenue: use LATEST prediction only (avoid doubling on re-runs) ─
        latest = predictions.order_by('-created_at').first()
        if latest and latest.result_json:
            result        = latest.result_json
            total_revenue     = result.get('total_actual_revenue', 0)
            predicted_revenue = result.get('total_predicted_revenue', 0)
            total_sales       = result.get('total_actual_sales', 0)

            # Product analysis from latest prediction
            for p in result.get('product_summary', []):
                pname = p.get('product', 'Unknown')
                product_revenues[pname] = product_revenues.get(pname, 0) + p.get('revenue', 0)

            # Monthly growth from latest forecast
            forecast_data = result.get('forecast', {})
            if isinstance(forecast_data, dict):
                future_list = forecast_data.get('future', [])
            elif isinstance(forecast_data, list):
                future_list = forecast_data
            else:
                future_list = []

            if len(future_list) >= 2:
                first_month = future_list[0].get('predicted_revenue', 0)
                last_month  = future_list[-1].get('predicted_revenue', 0)
                if first_month > 0:
                    monthly_growth = round((last_month - first_month) / first_month * 100, 1)

        if product_revenues:
            best_product  = max(product_revenues, key=product_revenues.get)
            worst_product = min(product_revenues, key=product_revenues.get)

        stats = {
            'total_revenue':       round(total_revenue, 2),
            'total_sales':         int(total_sales),
            'predicted_revenue':   round(predicted_revenue, 2),
            'prediction_accuracy': avg_accuracy,
            'total_predictions':   total_predictions,
            'total_datasets':      total_datasets,
            'total_reports':       reports.count(),
            'best_product':        best_product,
            'worst_product':       worst_product,
            'monthly_growth':      monthly_growth,
            'avg_monthly_sales':   round(total_sales / 12, 0) if total_sales else 0,
            'recent_predictions':  recent_predictions,
        }

        if user.role == 'admin':
            stats['total_users']     = User.objects.count()
            stats['total_scenarios'] = ScenarioSimulation.objects.count()

        return Response(stats)
