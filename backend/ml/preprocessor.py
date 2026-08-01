"""
Data Preprocessor Module
Handles all data cleaning and feature engineering for the ML pipeline.

Dataset-agnostic by design: callers pass in a `mapping` (built by
ml.column_mapper from the user-confirmed Column Mapping screen) that says
which source column plays each canonical role (date, sales, product, ...).
Everything downstream works off those canonical names, so a Walmart-style
"Weekly_Sales" file and a Rossmann-style "Sales" file both end up looking
identical to the rest of the pipeline. If no mapping is supplied, the
preprocessor falls back to guessing column names directly (legacy behavior),
so it still works for pre-mapped / already-standard files.
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler
from .column_mapper import CANONICAL_FIELDS, determine_forecast_mode
import warnings
warnings.filterwarnings('ignore')


class DataPreprocessor:
    """Complete data cleaning and feature engineering pipeline."""

    def __init__(self):
        self.label_encoders = {}
        self.scaler = StandardScaler()

    def clean(self, df: pd.DataFrame, mapping: dict = None) -> tuple:
        """
        Main cleaning pipeline.
        mapping: optional dict from ml.column_mapper, e.g.
            {'date': 'Order Date', 'sales': 'Total', 'product': 'Item', ...}
        Returns: (cleaned_df, cleaning_report)
        """
        report = {'original_rows': len(df), 'steps': []}
        df = df.copy()

        if mapping:
            df, applied = self._apply_mapping(df, mapping)
            report['column_mapping_applied'] = applied
            report['forecast_mode'] = determine_forecast_mode(mapping)
        else:
            # Legacy path: no mapping given, standardize names and let the
            # _find_column heuristics below guess based on common aliases.
            df.columns = [str(c).lower().strip().replace(' ', '_') for c in df.columns]
            report['forecast_mode'] = 'regression'

        # 2. Remove duplicates
        before = len(df)
        df = df.drop_duplicates()
        removed_dupes = before - len(df)
        report['steps'].append({'step': 'Remove Duplicates', 'rows_removed': removed_dupes})

        # 3. Handle date column
        date_col = self._find_column(df, ['date', 'sale_date', 'order_date', 'transaction_date'])
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df = df.dropna(subset=[date_col])
            df['month']      = df[date_col].dt.month
            df['year']       = df[date_col].dt.year
            df['quarter']    = df[date_col].dt.quarter
            df['day_of_week']= df[date_col].dt.dayofweek
            df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
            report['steps'].append({
                'step': 'Date Features Extracted',
                'columns_added': ['month', 'year', 'quarter', 'day_of_week', 'is_weekend']
            })

        # 4. Handle missing numerical values with median
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        nulls_filled = 0
        for col in num_cols:
            nulls = df[col].isnull().sum()
            if nulls > 0:
                df[col] = df[col].fillna(df[col].median())
                nulls_filled += nulls
        if nulls_filled:
            report['steps'].append({'step': 'Fill Missing Numerical Values', 'values_filled': int(nulls_filled)})

        # 5. Handle missing categorical values with mode
        cat_cols = df.select_dtypes(include=['object']).columns.tolist()
        for col in cat_cols:
            if col != date_col:
                mode_val = df[col].mode()
                fill_val = mode_val[0] if not mode_val.empty else 'Unknown'
                df[col] = df[col].fillna(fill_val)

        # 6. Remove outliers using IQR on sales/revenue/quantity
        outlier_col = self._find_column(df, ['sales', 'revenue', 'quantity', 'amount'])
        if outlier_col:
            before = len(df)
            Q1  = df[outlier_col].quantile(0.25)
            Q3  = df[outlier_col].quantile(0.75)
            IQR = Q3 - Q1
            df = df[(df[outlier_col] >= Q1 - 3 * IQR) & (df[outlier_col] <= Q3 + 3 * IQR)]
            removed_outliers = before - len(df)
            report['steps'].append({
                'step': 'Remove Outliers',
                'rows_removed': removed_outliers,
                'column': outlier_col
            })

        # 7. Ensure non-negative values for numeric business fields
        for col in ['quantity', 'revenue', 'price', 'amount', 'sales', 'discount']:
            if col in df.columns:
                df[col] = df[col].abs()

        report['cleaned_rows']    = len(df)
        report['columns_final']   = list(df.columns)
        report['status']          = 'success'

        return df, report

    def _find_column(self, df, candidates):
        """Find a column by checking multiple possible names."""
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
        return None

    def _apply_mapping(self, df, mapping):
        """
        Rename the user-confirmed source columns onto canonical names
        (date, sales, product, quantity, store, category, region, price,
        discount), and standardize the names of any leftover, unmapped
        columns so the rest of the pipeline never sees raw dataset-specific
        headers.
        Returns: (renamed_df, applied) where applied is {canonical: source}.
        """
        df = df.copy()
        applied = {}
        rename_map = {}
        for field in CANONICAL_FIELDS:
            source_col = mapping.get(field)
            if source_col and source_col in df.columns:
                rename_map[source_col] = field
                applied[field] = source_col
        df = df.rename(columns=rename_map)

        # Standardize any remaining, unmapped columns too (lowercase,
        # underscored) so downstream code has predictable names for them.
        mapped_targets = set(rename_map.values())
        new_columns = []
        for c in df.columns:
            if c in mapped_targets:
                new_columns.append(c)
            else:
                new_columns.append(str(c).lower().strip().replace(' ', '_'))
        df.columns = new_columns
        return df, applied

    def prepare_features(self, df: pd.DataFrame, target_col: str = 'sales'):
        """Prepare feature matrix and target vector for ML training."""
        df = df.copy()
        # Drop date columns (keep extracted features)
        date_cols = [c for c in df.columns if 'date' in c.lower()]
        df = df.drop(columns=date_cols, errors='ignore')

        # Encode categorical columns
        cat_cols = df.select_dtypes(include=['object']).columns.tolist()
        for col in cat_cols:
            le = LabelEncoder()
            df[col] = le.fit_transform(df[col].astype(str))
            self.label_encoders[col] = le

        # Separate target from features
        if target_col not in df.columns:
            for alt in ['sales', 'revenue', 'amount', 'total', 'revenue_amount']:
                if alt in df.columns:
                    target_col = alt
                    break

        if target_col in df.columns:
            y = df[target_col].values
            X = df.drop(columns=[target_col])
        else:
            y = df.iloc[:, -1].values
            X = df.iloc[:, :-1]

        return X, y, list(X.columns)
