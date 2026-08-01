"""
Column Mapper Module
Makes the platform dataset-agnostic: instead of requiring a fixed CSV schema
(date, product, quantity, revenue, category, region, price, discount), this
module inspects whatever columns a user's file actually has, suggests a
best-guess mapping onto a small set of canonical internal fields, and lets
the rest of the pipeline (preprocessor / model_trainer / predictor) work off
those canonical names no matter what the source dataset calls them.
"""
import difflib
import re

# Canonical internal fields. Only 'date' and 'sales' are required for a
# forecast to run at all - everything else unlocks richer analysis
# (product breakdowns, category analysis, store-level forecasting, etc.)
# but forecasting must still work if they're missing.
CANONICAL_FIELDS = {
    'date': {
        'label': 'Date',
        'required': True,
        'description': 'The transaction/order/period date',
        'aliases': [
            'date', 'invoice date', 'order date', 'sale date', 'sales date',
            'transaction date', 'week', 'week date', 'period', 'ds',
            'order_date', 'invoicedate', 'orderdate',
        ],
    },
    'sales': {
        'label': 'Sales / Revenue',
        'required': True,
        'description': 'The value being forecasted (revenue, total sales, etc.)',
        'aliases': [
            'sales', 'revenue', 'weekly_sales', 'weekly sales', 'total',
            'total sales', 'sales_amount', 'amount', 'turnover', 'y',
            'net sales', 'gross sales', 'order total', 'total_revenue',
        ],
    },
    'product': {
        'label': 'Product',
        'required': False,
        'description': 'Product / item name or SKU',
        'aliases': [
            'product', 'item', 'product name', 'product_name', 'item_name',
            'sku', 'itemid', 'item id', 'product line item', 'description',
        ],
    },
    'quantity': {
        'label': 'Quantity',
        'required': False,
        'description': 'Units sold per row',
        'aliases': [
            'quantity', 'qty', 'units sold', 'units_sold', 'units',
            'unit sold', 'order quantity', 'quantity ordered',
        ],
    },
    'store': {
        'label': 'Store / Branch',
        'required': False,
        'description': 'Store, branch, or outlet identifier',
        'aliases': [
            'store', 'branch', 'outlet', 'store_id', 'store id', 'shop',
            'store number', 'store_nbr', 'location id',
        ],
    },
    'category': {
        'label': 'Category',
        'required': False,
        'description': 'Product category / line / department',
        'aliases': [
            'category', 'product line', 'product_line', 'product category',
            'type', 'department', 'segment', 'productline',
        ],
    },
    'region': {
        'label': 'Region',
        'required': False,
        'description': 'Geographic region, city, or state',
        'aliases': [
            'region', 'city', 'state', 'location', 'area', 'country',
            'zone', 'territory',
        ],
    },
    'price': {
        'label': 'Price',
        'required': False,
        'description': 'Unit price',
        'aliases': [
            'price', 'unit price', 'unit_price', 'cost', 'unit cost',
            'list price', 'mrp',
        ],
    },
    'discount': {
        'label': 'Discount',
        'required': False,
        'description': 'Discount amount or percentage',
        'aliases': [
            'discount', 'discount %', 'discount_percent', 'discount percent',
            'promo', 'promotion', 'markdown',
        ],
    },
}

REQUIRED_FIELDS = [k for k, v in CANONICAL_FIELDS.items() if v['required']]


def _normalize(name: str) -> str:
    """Lowercase, strip, collapse separators to single spaces for comparison."""
    name = str(name).strip().lower()
    name = re.sub(r'[_\-./]+', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def suggest_mapping(columns) -> dict:
    """
    Given the raw column names from an uploaded CSV, suggest which source
    column best fills each canonical field.

    Returns: { canonical_field: source_column_name | None }
    """
    normalized_lookup = {_normalize(c): c for c in columns}
    used_columns = set()
    mapping = {field: None for field in CANONICAL_FIELDS}

    # Pass 1: exact alias match (normalized)
    for field, spec in CANONICAL_FIELDS.items():
        for alias in spec['aliases']:
            norm_alias = _normalize(alias)
            if norm_alias in normalized_lookup:
                col = normalized_lookup[norm_alias]
                if col not in used_columns:
                    mapping[field] = col
                    used_columns.add(col)
                    break

    # Pass 2: fuzzy match remaining unmapped fields against remaining columns
    remaining_columns = [c for c in columns if c not in used_columns]
    for field, spec in CANONICAL_FIELDS.items():
        if mapping[field] is not None:
            continue
        best_col, best_score = None, 0.0
        remaining_norm = {c: _normalize(c) for c in remaining_columns}
        for alias in spec['aliases']:
            norm_alias = _normalize(alias)
            for col, norm_col in remaining_norm.items():
                score = difflib.SequenceMatcher(None, norm_alias, norm_col).ratio()
                if score > best_score:
                    best_score, best_col = score, col
        # 0.72 balances catching real matches (e.g. "Total_Revenue" ~ "revenue")
        # against false positives on unrelated short column names.
        if best_col is not None and best_score >= 0.72:
            mapping[field] = best_col
            used_columns.add(best_col)
            remaining_columns = [c for c in remaining_columns if c != best_col]

    return mapping


def validate_mapping(mapping: dict) -> list:
    """Return a list of human-readable errors if required fields are unmapped."""
    errors = []
    for field in REQUIRED_FIELDS:
        if not mapping.get(field):
            label = CANONICAL_FIELDS[field]['label']
            errors.append(f'{label} is required - please map a column to it.')
    return errors


def get_field_definitions() -> list:
    """Serializable list of canonical field definitions, for the frontend UI."""
    return [
        {
            'field': field,
            'label': spec['label'],
            'required': spec['required'],
            'description': spec['description'],
        }
        for field, spec in CANONICAL_FIELDS.items()
    ]


def determine_forecast_mode(mapping: dict) -> str:
    """
    'timeseries'  -> only date + sales mapped, forecast from trend/seasonality alone.
    'regression'  -> extra features present, train a full ML regression model.
    """
    extra_fields = ['product', 'quantity', 'store', 'category', 'region', 'price', 'discount']
    has_extra = any(mapping.get(f) for f in extra_fields)
    return 'regression' if has_extra else 'timeseries'
