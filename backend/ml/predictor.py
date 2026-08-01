"""
Sales Predictor Module
Loads a trained model and generates forecasts.
"""
import pandas as pd
import numpy as np
import joblib
import os
from .preprocessor import DataPreprocessor
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saved_models')


class SalesPredictor:
    """Generate sales and revenue forecasts using trained ML model."""

    def __init__(self, model_path=None, model_type='xgboost'):
        self.model      = None
        self.metadata   = None
        self.model_path = model_path
        self.model_type = model_type
        if model_path and os.path.exists(model_path):
            self.model = joblib.load(model_path)
            meta_path  = model_path.replace('_model.joblib', '_metadata.joblib')
            if os.path.exists(meta_path):
                self.metadata = joblib.load(meta_path)

    def predict(self, file_path: str, forecast_months: int = 6, mapping: dict = None) -> dict:
        """
        Generate predictions and forecasts from a dataset.
        mapping: optional column mapping (see ml.column_mapper). If omitted,
        falls back to the mapping stored in the trained model's metadata, so
        the exact same column mapping used at training time is reused here.
        Returns comprehensive result JSON.
        """
        if mapping is None and self.metadata:
            mapping = self.metadata.get('mapping')

        df = pd.read_csv(file_path)
        preprocessor = DataPreprocessor()
        cleaned_df, clean_report = preprocessor.clean(df, mapping=mapping)
        forecast_mode = clean_report.get('forecast_mode', 'regression')

        if self.model is None:
            raise ValueError('Model not loaded. Please train first.')

        X, y_actual, feature_names = preprocessor.prepare_features(cleaned_df)

        # Align feature columns
        if self.metadata:
            expected_features = self.metadata.get('feature_names', feature_names)
            X_df = pd.DataFrame(X, columns=feature_names)
            for feat in expected_features:
                if feat not in X_df.columns:
                    X_df[feat] = 0
            X_df = X_df[expected_features]
            X = X_df.values

        y_pred = self.model.predict(X)
        y_pred = np.maximum(y_pred, 0)

        total_actual_revenue    = float(np.sum(y_actual))
        total_predicted_revenue = float(np.sum(y_pred))

        forecast          = self._generate_monthly_forecast(cleaned_df, y_actual, y_pred, forecast_months)
        product_summary   = self._get_product_summary(cleaned_df)
        category_analysis = self._get_category_analysis(cleaned_df)
        store_summary      = self._get_store_summary(cleaned_df)

        actual_vs_predicted = [
            {
                'index':     int(i),
                'actual':    round(float(y_actual[i]), 2),
                'predicted': round(float(y_pred[i]), 2),
            }
            for i in range(min(100, len(y_actual)))
        ]

        return {
            'total_actual_revenue':    round(total_actual_revenue, 2),
            'total_predicted_revenue': round(total_predicted_revenue, 2),
            'total_actual_sales':      int(len(y_actual)),
            'forecast':                forecast,
            'product_summary':         product_summary,
            'category_analysis':       category_analysis,
            'store_summary':           store_summary,
            'actual_vs_predicted':     actual_vs_predicted,
            'forecast_months':         forecast_months,
            'forecast_mode':           forecast_mode,
            'columns_used':            list(cleaned_df.columns),
        }

    def _generate_monthly_forecast(self, df, y_actual, y_pred, forecast_months):
        """
        Generate month-by-month historical + future forecast data.
        Uses actual monthly revenue totals as base (not per-row averages).
        """
        monthly_actual = []
        monthly_totals = []
        revenue_col = self._find_col(df, ['sales', 'revenue', 'amount'])

        # Build historical monthly totals
        if 'month' in df.columns and 'year' in df.columns and revenue_col:
            grouped = df.groupby(['year', 'month'])[revenue_col].sum().reset_index()
            grouped = grouped.sort_values(['year', 'month'])
            for _, row in grouped.iterrows():
                monthly_rev = round(float(row[revenue_col]), 2)
                monthly_actual.append({
                    'month':          f"{int(row['year'])}-{int(row['month']):02d}",
                    'actual_revenue': monthly_rev,
                })
                monthly_totals.append(monthly_rev)

        # ── Base revenue: use recent monthly totals, not per-row mean ──────
        if monthly_totals:
            recent = monthly_totals[-6:] if len(monthly_totals) >= 6 else monthly_totals
            base_revenue = float(np.mean(recent))
            # Linear trend per month derived from full history
            if len(monthly_totals) >= 2:
                trend_per_month = (monthly_totals[-1] - monthly_totals[0]) / max(len(monthly_totals) - 1, 1)
            else:
                trend_per_month = base_revenue * 0.02
        else:
            # Fallback: estimate monthly total from row-level sum / num months
            n_months = max(df['month'].nunique(), 1) if 'month' in df.columns else 12
            base_revenue = float(np.sum(y_pred)) / n_months
            trend_per_month = base_revenue * 0.02

        # ── Indian retail seasonal pattern ──────────────────────────────────
        # Peaks: Oct(10) Diwali, Nov(11), Dec(12) Christmas / year-end
        # Troughs: Jan(1) post-festive, Feb(2), Jun(6)-Jul(7) monsoon dip
        SEASONAL = {
            1: -0.08, 2: -0.06, 3:  0.02, 4:  0.04,
            5:  0.05, 6: -0.04, 7: -0.03, 8:  0.03,
            9:  0.06, 10: 0.12, 11: 0.18, 12: 0.15,
        }

        rng          = np.random.default_rng(seed=42)  # reproducible ±noise
        current_date = datetime.now()
        future       = []
        avg_txn      = float(np.mean(y_pred)) if len(y_pred) > 0 else max(base_revenue / 100, 1)

        for i in range(1, forecast_months + 1):
            month_date      = current_date + timedelta(days=30 * i)
            month_num       = month_date.month
            seasonal_factor = 1 + SEASONAL.get(month_num, 0)
            trend_value     = trend_per_month * i
            # ±3% random noise so adjacent months differ visibly
            noise           = 1 + rng.uniform(-0.03, 0.03)
            predicted_rev   = max((base_revenue + trend_value) * seasonal_factor * noise, 0)
            predicted_sales = max(int(predicted_rev / max(avg_txn, 1)), 1)

            future.append({
                'month':             month_date.strftime('%Y-%m'),
                'predicted_revenue': round(float(predicted_rev), 2),
                'predicted_sales':   predicted_sales,
            })

        return {'historical': monthly_actual, 'future': future}

    def _get_product_summary(self, df):
        """Get top products by revenue."""
        product_col = self._find_col(df, ['product', 'product_name', 'item', 'item_name'])
        revenue_col = self._find_col(df, ['sales', 'revenue', 'amount'])
        qty_col     = self._find_col(df, ['quantity', 'qty', 'units'])
        if not product_col or not revenue_col:
            return []
        agg = {revenue_col: 'sum'}
        if qty_col:
            agg[qty_col] = 'sum'
        grouped = df.groupby(product_col).agg(agg).reset_index()
        grouped = grouped.sort_values(revenue_col, ascending=False).head(10)
        result  = []
        for _, row in grouped.iterrows():
            item = {'product': str(row[product_col]), 'revenue': round(float(row[revenue_col]), 2)}
            if qty_col:
                item['quantity'] = int(row[qty_col])
            result.append(item)
        return result

    def _get_category_analysis(self, df):
        """Get category-wise revenue breakdown."""
        cat_col     = self._find_col(df, ['category', 'product_category', 'type', 'department'])
        revenue_col = self._find_col(df, ['sales', 'revenue', 'amount'])
        if not cat_col or not revenue_col:
            return []
        grouped = df.groupby(cat_col)[revenue_col].sum().reset_index()
        grouped = grouped.sort_values(revenue_col, ascending=False)
        return [
            {'category': str(row[cat_col]), 'revenue': round(float(row[revenue_col]), 2)}
            for _, row in grouped.iterrows()
        ]

    def _get_store_summary(self, df):
        """Get store/branch-wise revenue breakdown, if a store column exists."""
        store_col   = self._find_col(df, ['store', 'branch', 'outlet'])
        revenue_col = self._find_col(df, ['sales', 'revenue', 'amount'])
        if not store_col or not revenue_col:
            return []
        grouped = df.groupby(store_col)[revenue_col].sum().reset_index()
        grouped = grouped.sort_values(revenue_col, ascending=False).head(20)
        return [
            {'store': str(row[store_col]), 'revenue': round(float(row[revenue_col]), 2)}
            for _, row in grouped.iterrows()
        ]

    def _find_col(self, df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None
