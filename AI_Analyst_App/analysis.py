"""
analysis.py
Pure computation layer for the AI Analyst pipeline.

Design principle: these functions stay strictly computational. They return
rich pandas/numpy objects so you can still chart, debug, or further process
results in plain Python. The to_json_safe() helper at the bottom is the
ONLY place that knows how to flatten that into clean JSON for an LLM
prompt — call it right before handing a result to run_chain(), not inside
these functions.

Changelog from the original draft:
- Fixed dataquality() crash (was concatenating a string onto a numeric
  Series for missing_values).
- dataquality()/statistics_calculation() output keys now match exactly
  what DataQualityInterpretation_prompt / StatisticalInterpretation_prompt
  expect (rows/duplicates/nulls, p25/p50/p75).
- date_col is now a parameter instead of hardcoded 'order_date'.
- trend_calculation() labels months as "Mar 2024" (not bare "Mar") since
  data spans multiple years; resample('M') -> resample('ME') (pandas
  deprecation).
- flat_threshold default lowered 0.02 -> 0.01: at 0.02, real ~18%/year
  growth in a seasonally noisy monthly series was misclassified as "Flat"
  (measured relative_slope was ~0.0102 on the test dataset). 0.01 reflects
  the actual sensitivity needed for monthly aggregates with heavy
  seasonal swings (Black Friday / Ramadan spikes). Tune per-dataset if
  your revenue is less volatile than this.
- outlier_calculation() gained an optional `display_columns` param so you
  can choose to exclude PII (e.g. customer_name) from what gets sent to
  the LLM, without changing default behavior if you don't pass it.
- Added to_json_safe() so every result here can go straight into
  json.dumps() before hitting a prompt's .format().
"""

from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats


def dataquality(df: pd.DataFrame, date_col: Optional[str] = None) -> dict:
    """
    Profile a dataframe: shape, nulls, duplicates, dtypes, cardinality,
    and (optionally) the date range of a given date column.
    """
    row_count = len(df)
    column_count = len(df.columns)

    missing_counts = df.isnull().sum()
    missing_pct = (
        (missing_counts / row_count * 100).round(2)
        if row_count
        else missing_counts * 0
    )
    nulls = {
        col: {"count": int(missing_counts[col]), "percentage": float(missing_pct[col])}
        for col in df.columns
        if missing_counts[col] > 0  # only report columns that actually have nulls
    }

    duplicate_rows = int(df.duplicated().sum())
    where_duplicated = df[df.duplicated(keep=False)].sort_values(by=list(df.columns))

    datatypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
    unique_values = df.nunique().to_dict()

    data_range = None
    if date_col and date_col in df.columns:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        if dates.notna().any():
            data_range = {"start": str(dates.min()), "end": str(dates.max())}

    return {
        "rows": row_count,
        "column_count": column_count,
        "nulls": nulls,
        "duplicates": duplicate_rows,
        "where_duplicated": where_duplicated,  # debug only — drop before prompting if not needed
        "datatypes": datatypes,
        "unique_values": unique_values,
        "data_range": data_range,
    }


def statistics_calculation(df: pd.DataFrame, col: str) -> Optional[dict]:
    """Descriptive statistics for one numeric column."""
    series = df[col].dropna()

    if series.empty or not pd.api.types.is_numeric_dtype(df[col]):
        return None

    return {
        "sum": series.sum(),
        "mean": series.mean(),
        "median": series.median(),
        "min": series.min(),
        "max": series.max(),
        "std": series.std(),
        "variance": series.var(),
        "quantiles": {
            "p25": series.quantile(0.25),
            "p50": series.quantile(0.50),
            "p75": series.quantile(0.75),
        },
        "skew": series.skew(),
        "kurtosis": series.kurtosis(),
    }


def correlation_calculation(
    df: pd.DataFrame, target_col: Optional[str] = None, threshold: float = 0.7
) -> Optional[dict]:
    """Pearson correlation matrix plus pairs above/below +/- threshold."""
    numeric_df = df.select_dtypes(include="number")

    if numeric_df.shape[1] < 2:
        return None  # need at least 2 numeric columns to correlate

    matrix = numeric_df.corr(numeric_only=True)

    pairs = matrix.unstack()
    pairs = pairs[pairs.index.get_level_values(0) != pairs.index.get_level_values(1)]
    pairs = pairs[~pairs.index.to_series().apply(frozenset).duplicated()]

    strong_positive = pairs[pairs > threshold].sort_values(ascending=False)
    strong_negative = pairs[pairs < -threshold].sort_values()

    feature_ranking = None
    if target_col is not None and target_col in matrix.columns:
        feature_ranking = (
            matrix[target_col]
            .drop(index=target_col)
            .sort_values(key=abs, ascending=False)
        )

    return {
        "matrix": matrix,
        "strong_positive": strong_positive,
        "strong_negative": strong_negative,
        "feature_ranking": feature_ranking,
    }


def trend_calculation(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "revenue",
    flat_threshold: float = 0.01,
) -> Optional[dict]:
    """
    Daily/weekly/monthly aggregation, growth rate, moving average, and an
    overall trend direction (linear-regression slope, not just first-vs-last).
    """
    data = df[[date_col, value_col]].dropna(subset=[date_col, value_col]).copy()

    if data.empty:
        return None

    data[date_col] = pd.to_datetime(data[date_col])
    data = data.set_index(date_col).sort_index()

    daily_revenue = data[value_col].resample("D").sum()
    weekly_revenue = data[value_col].resample("W").sum()
    monthly_revenue = data[value_col].resample("ME").sum()

    growth_rate = monthly_revenue.pct_change() * 100
    moving_average = monthly_revenue.rolling(3).mean()

    peak_month = monthly_revenue.idxmax() if not monthly_revenue.empty else None
    worst_month = monthly_revenue.idxmin() if not monthly_revenue.empty else None

    direction = _trend_direction(monthly_revenue, flat_threshold)

    def _labelled(series: pd.Series) -> pd.Series:
        # "Mar 2024" not bare "Mar" — dataset spans multiple years, bare
        # month names would silently collide across them.
        labelled = series.copy()
        labelled.index = labelled.index.strftime("%b %Y")
        return labelled

    return {
        "daily_revenue": daily_revenue,
        "weekly_revenue": weekly_revenue,
        "monthly_revenue": _labelled(monthly_revenue),
        "growth_rate": _labelled(growth_rate),
        "moving_average": _labelled(moving_average),
        "peak_month": peak_month.strftime("%b %Y") if peak_month is not None else None,
        "worst_month": worst_month.strftime("%b %Y") if worst_month is not None else None,
        "direction": direction,
    }


def _trend_direction(series: pd.Series, flat_threshold: float = 0.01) -> str:
    series = series.dropna()
    if len(series) < 2:
        return "Flat"

    x = np.arange(len(series))
    slope = np.polyfit(x, series.values, 1)[0]
    relative_slope = slope / series.mean() if series.mean() != 0 else 0

    if relative_slope > flat_threshold:
        return "Increasing"
    elif relative_slope < -flat_threshold:
        return "Decreasing"
    else:
        return "Flat"


def outlier_calculation(
    df: pd.DataFrame,
    col: str,
    method: str = "iqr",
    z_thresh: float = 3,
    top_n: int = 10,
    display_columns: Optional[Sequence[str]] = None,
) -> Optional[dict]:
    """
    Detect outliers in `col` via IQR or z-score. `display_columns` lets you
    limit which columns show up in the largest/smallest records sent
    onward (e.g. exclude customer_name/PII) without changing the
    detection logic itself. Defaults to all columns (original behavior).
    """
    series = df[col].dropna()

    if series.empty or not pd.api.types.is_numeric_dtype(df[col]):
        return None

    if method == "iqr":
        outlier_rows = _iqr_outliers(df, col, series)
    elif method == "zscore":
        outlier_rows = _zscore_outliers(df, col, series, z_thresh)
    else:
        raise ValueError("method must be 'iqr' or 'zscore'")

    count = len(outlier_rows)
    percentage = (count / len(df)) * 100 if len(df) > 0 else 0

    view = outlier_rows[list(display_columns)] if display_columns else outlier_rows

    largest = view.nlargest(top_n, col) if not view.empty else view
    smallest = view.nsmallest(top_n, col) if not view.empty else view

    return {
        "method": method,
        "count": count,
        "percentage": percentage,
        "largest": largest,
        "smallest": smallest,
    }


def _iqr_outliers(df: pd.DataFrame, col: str, series: pd.Series) -> pd.DataFrame:
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1

    upper = q3 + 1.5 * iqr
    lower = q1 - 1.5 * iqr

    return df[(df[col] < lower) | (df[col] > upper)]


def _zscore_outliers(df: pd.DataFrame, col: str, series: pd.Series, z_thresh: float) -> pd.DataFrame:
    z_scores = stats.zscore(series)
    z_series = pd.Series(z_scores, index=series.index)

    flagged_index = z_series[z_series.abs() > z_thresh].index
    return df.loc[flagged_index]

"""
11 analysis types covered:
 1. growth_analysis              - MoM / QoQ / YoY growth
 2. segmentation_analysis        - value by dimension
 3. top_bottom_performers        - top-N / bottom-N
 4. contribution_analysis        - % contribution per category
 5. pareto_analysis              - 80/20 split
 6. ranking_analysis             - top category per dimension
 7. variance_analysis            - actual vs expected (single + grouped)
 8. distribution_analysis        - histogram / percentiles / skew / kurtosis
 9. time_intelligence            - rolling avg/sum, cumulative
10. missing_period_detection     - gaps in a time series
11. anomaly_detection            - statistical outliers + relative spikes
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
_RESAMPLE_FREQ = {"M": "ME", "Q": "QE", "Y": "YE"}


def _require_columns(df: pd.DataFrame, required_cols: list) -> None:
    """
    Raises ValueError for caller mistakes: wrong type, or column names
    that don't exist. Mirrors outlier_calculation's `raise ValueError(...)`
    for an invalid `method` — these are config errors, not data-quality
    issues, so they should fail loud rather than return None silently.
    """
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df must be a pandas DataFrame")
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _require_freq(freq: str) -> str:
    """Raises ValueError for an invalid freq; returns the resample alias."""
    if freq not in _RESAMPLE_FREQ:
        raise ValueError(f"Invalid freq '{freq}'. Use 'M', 'Q', or 'Y'.")
    return _RESAMPLE_FREQ[freq]


def _agg_func(agg: str) -> str:
    mapping = {"sum": "sum", "mean": "mean", "avg": "mean", "count": "count", "median": "median"}
    if agg not in mapping:
        raise ValueError(f"Invalid agg '{agg}'. Use one of: {list(mapping)}")
    return mapping[agg]


def _to_datetime_safe(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Coerces date_col to datetime, dropping rows that fail to parse."""
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    return out.dropna(subset=[date_col])


# ---------------------------------------------------------------------------
# 1. Growth Analysis (MoM / QoQ / YoY)
# ---------------------------------------------------------------------------

def growth_analysis(df: pd.DataFrame, date_col: str = "date", value_col: str = "revenue",
                     freq: str = "M", agg: str = "sum") -> Optional[list]:
    """
    Period-over-period growth. freq: "M" / "Q" / "Y".
    Returns: list of {period, value, prev_value, growth_abs, growth_pct}
    None if there's no valid data or fewer than 2 periods to compare.
    """
    _require_columns(df, [date_col, value_col])
    resample_freq = _require_freq(freq)
    agg_method = _agg_func(agg)

    data = _to_datetime_safe(df, date_col)
    if data.empty:
        return None

    grouped = data.set_index(date_col)[value_col].resample(resample_freq).agg(agg_method).sort_index()
    if len(grouped) < 2:
        return None

    results, prev_value = [], None
    for period, value in grouped.items():
        value = float(value) if pd.notna(value) else None
        record = {
            "period": period.strftime("%Y-%m-%d"),
            "value": value,
            "prev_value": prev_value,
            "growth_abs": None,
            "growth_pct": None,
        }
        if prev_value is not None and value is not None:
            record["growth_abs"] = round(value - prev_value, 4)
            record["growth_pct"] = (
                round((value - prev_value) / abs(prev_value) * 100, 2) if prev_value != 0 else None
            )
        results.append(record)
        prev_value = value

    return results


# ---------------------------------------------------------------------------
# 2. Segmentation Analysis
# ---------------------------------------------------------------------------

def segmentation_analysis(df: pd.DataFrame, group_col: str, value_col: str = "revenue",
                           agg: str = "sum") -> Optional[list]:
    """Aggregates value_col by group_col. Returns sorted list of {category, value}."""
    _require_columns(df, [group_col, value_col])
    agg_method = _agg_func(agg)

    if df.empty:
        return None

    grouped = df.groupby(group_col)[value_col].agg(agg_method).sort_values(ascending=False)
    return [{"category": str(idx), "value": float(val) if pd.notna(val) else None}
            for idx, val in grouped.items()]


# ---------------------------------------------------------------------------
# 3. Top / Bottom Performers
# ---------------------------------------------------------------------------

def top_bottom_analysis(df: pd.DataFrame, group_col: str, value_col: str = "revenue",
                           n: int = 10, agg: str = "sum") -> Optional[dict]:
    """Returns top-N and bottom-N performers by aggregated value_col."""
    _require_columns(df, [group_col, value_col])
    agg_method = _agg_func(agg)

    if df.empty:
        return None

    grouped = df.groupby(group_col)[value_col].agg(agg_method)
    n = min(n, len(grouped))

    top = grouped.nlargest(n)
    bottom = grouped.nsmallest(n)

    return {
        "top": [{"category": str(i), "value": float(v)} for i, v in top.items()],
        "bottom": [{"category": str(i), "value": float(v)} for i, v in bottom.items()],
    }


# ---------------------------------------------------------------------------
# 4. Contribution Analysis
# ---------------------------------------------------------------------------

def contribution_analysis(df: pd.DataFrame, group_col: str, value_col: str = "revenue",
                           agg: str = "sum") -> Optional[list]:
    """Returns each category's % contribution to total value_col. None if total is 0."""
    _require_columns(df, [group_col, value_col])
    agg_method = _agg_func(agg)

    if df.empty:
        return None

    grouped = df.groupby(group_col)[value_col].agg(agg_method).sort_values(ascending=False)
    total = grouped.sum()
    if total == 0:
        return None

    return [
        {"category": str(idx), "value": float(val), "contribution_pct": round(float(val) / total * 100, 2)}
        for idx, val in grouped.items()
    ]


# ---------------------------------------------------------------------------
# 5. Pareto Analysis (80/20)
# ---------------------------------------------------------------------------

def pareto_analysis(df: pd.DataFrame, group_col: str, value_col: str = "revenue",
                     agg: str = "sum", threshold_pct: float = 80.0) -> Optional[dict]:
    """Finds the minimal set of categories that drive `threshold_pct` of total value."""
    _require_columns(df, [group_col, value_col])
    agg_method = _agg_func(agg)

    if df.empty:
        return None

    grouped = df.groupby(group_col)[value_col].agg(agg_method).sort_values(ascending=False)
    total = grouped.sum()
    if total == 0:
        return None

    cum_pct = grouped.cumsum() / total * 100
    cutoff_categories = cum_pct[cum_pct <= threshold_pct].index.tolist()
    if len(cutoff_categories) < len(grouped):
        cutoff_categories.append(cum_pct.index[len(cutoff_categories)])  # include crossing point

    n_categories = len(cutoff_categories)
    total_categories = len(grouped)

    return {
        "categories_driving_threshold": [str(c) for c in cutoff_categories],
        "n_categories": n_categories,
        "total_categories": total_categories,
        "pct_of_categories": round(n_categories / total_categories * 100, 2),
        "threshold_pct": threshold_pct,
        "detail": [
            {"category": str(idx), "value": float(val), "cumulative_pct": round(float(cp), 2)}
            for (idx, val), cp in zip(grouped.items(), cum_pct)
        ],
    }


# ---------------------------------------------------------------------------
# 6. Ranking Analysis (top category across multiple dimensions)
# ---------------------------------------------------------------------------

def ranking_analysis(df: pd.DataFrame, dimensions: list, value_col: str = "revenue",
                      agg: str = "sum") -> Optional[dict]:
    """
    For each dimension (e.g. ["region", "product", "customer"]),
    finds the top-ranked category by value_col.
    Returns: {dimension: {"top_category": ..., "value": ...} | None}
    None overall if df is empty; None per-dimension if that dimension
    has no usable data.
    """
    _require_columns(df, dimensions + [value_col])
    agg_method = _agg_func(agg)

    if df.empty:
        return None

    result = {}
    for dim in dimensions:
        grouped = df.groupby(dim)[value_col].agg(agg_method).sort_values(ascending=False)
        result[dim] = (
            {"top_category": str(grouped.index[0]), "value": float(grouped.iloc[0])}
            if not grouped.empty else None
        )
    return result


# ---------------------------------------------------------------------------
# 7. Variance Analysis (Expected vs Actual / Previous vs Current)
# ---------------------------------------------------------------------------

def variance_analysis(actual: Optional[float], expected: Optional[float], label: str = "Value") -> Optional[dict]:
    """
    Single-value variance: actual vs expected, abs + % + direction.
    None if either value is missing (nothing to compare).
    Raises ValueError if a value is provided but isn't numeric.
    """
    if actual is None or expected is None:
        return None
    try:
        actual, expected = float(actual), float(expected)
    except (TypeError, ValueError):
        raise ValueError("actual and expected must be numeric")

    variance_abs = round(actual - expected, 4)
    variance_pct = round((variance_abs / abs(expected)) * 100, 2) if expected != 0 else None

    return {
        "label": label,
        "expected": expected,
        "actual": actual,
        "variance_abs": variance_abs,
        "variance_pct": variance_pct,
        "direction": "above" if variance_abs > 0 else "below" if variance_abs < 0 else "on target",
    }


def variance_analysis_grouped(df_actual: pd.DataFrame, df_expected: pd.DataFrame,
                               group_col: str, value_col: str = "revenue",
                               agg: str = "sum") -> Optional[list]:
    """Per-category variance (e.g. per Region/Product) between two dataframes."""
    _require_columns(df_actual, [group_col, value_col])
    _require_columns(df_expected, [group_col, value_col])
    agg_method = _agg_func(agg)

    if df_actual.empty or df_expected.empty:
        return None

    actual_agg = df_actual.groupby(group_col)[value_col].agg(agg_method)
    expected_agg = df_expected.groupby(group_col)[value_col].agg(agg_method)

    categories = sorted(set(actual_agg.index) | set(expected_agg.index), key=str)
    return [
        variance_analysis(float(actual_agg.get(cat, 0.0)), float(expected_agg.get(cat, 0.0)), label=str(cat))
        for cat in categories
    ]


# ---------------------------------------------------------------------------
# 8. Distribution Analysis
# ---------------------------------------------------------------------------

def distribution_analysis(df: pd.DataFrame, value_col: str = "revenue", bins: int = 10) -> Optional[dict]:
    """Histogram, percentiles, spread, skewness, kurtosis for value_col."""
    _require_columns(df, [value_col])

    series = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if series.empty:
        return None

    counts, edges = np.histogram(series, bins=bins)
    percentile_levels = [5, 25, 50, 75, 90, 95, 99]
    percentiles = {f"p{p}": round(float(np.percentile(series, p)), 4) for p in percentile_levels}

    return {
        "count": int(series.count()),
        "mean": round(float(series.mean()), 4),
        "std": round(float(series.std()), 4),
        "min": round(float(series.min()), 4),
        "max": round(float(series.max()), 4),
        "range": round(float(series.max() - series.min()), 4),
        "iqr": round(float(np.percentile(series, 75) - np.percentile(series, 25)), 4),
        "percentiles": percentiles,
        "skewness": round(float(scipy_stats.skew(series)), 4),
        "kurtosis": round(float(scipy_stats.kurtosis(series)), 4),
        "histogram": {
            "bucket_edges": [round(float(e), 4) for e in edges],
            "bucket_counts": [int(c) for c in counts],
        },
    }


# ---------------------------------------------------------------------------
# 9. Time Intelligence (rolling / cumulative metrics)
# ---------------------------------------------------------------------------

def time_intelligence(df: pd.DataFrame, date_col: str = "date", value_col: str = "revenue",
                       freq: str = "M", agg: str = "sum",
                       rolling_window: int = 3) -> Optional[list]:
    """Time-aggregated table with rolling avg, rolling sum, cumulative value."""
    _require_columns(df, [date_col, value_col])
    resample_freq = _require_freq(freq)
    agg_method = _agg_func(agg)

    data = _to_datetime_safe(df, date_col)
    if data.empty:
        return None

    series = data.set_index(date_col)[value_col].resample(resample_freq).agg(agg_method).sort_index()

    rolling_avg = series.rolling(window=rolling_window, min_periods=1).mean()
    rolling_sum = series.rolling(window=rolling_window, min_periods=1).sum()
    cumulative = series.cumsum()

    results = []
    for period in series.index:
        results.append({
            "period": period.strftime("%Y-%m-%d"),
            "value": round(float(series[period]), 4) if pd.notna(series[period]) else None,
            "rolling_avg": round(float(rolling_avg[period]), 4) if pd.notna(rolling_avg[period]) else None,
            "rolling_sum": round(float(rolling_sum[period]), 4) if pd.notna(rolling_sum[period]) else None,
            "cumulative": round(float(cumulative[period]), 4) if pd.notna(cumulative[period]) else None,
        })

    if results:
        results[-1]["is_current_period"] = True
    if len(results) >= 2:
        results[-2]["is_last_period"] = True

    return results


# ---------------------------------------------------------------------------
# 10. Missing Period Detection
# ---------------------------------------------------------------------------

def missing_period_detection(df: pd.DataFrame, date_col: str = "date", freq: str = "M") -> Optional[dict]:
    """Detects gaps in a time series between the min and max date present."""
    _require_columns(df, [date_col])
    if freq not in _RESAMPLE_FREQ:
        raise ValueError(f"Invalid freq '{freq}'. Use 'M', 'Q', or 'Y'.")

    data = _to_datetime_safe(df, date_col)
    if data.empty:
        return None

    present_periods = set(data[date_col].dt.to_period(freq))  # Period objects need the short code
    full_range = pd.period_range(start=min(present_periods), end=max(present_periods), freq=freq)
    missing = sorted(set(full_range) - present_periods)

    return {
        "expected_periods": len(full_range),
        "present_periods": len(present_periods),
        "missing_periods": [str(p) for p in missing],
        "has_gaps": len(missing) > 0,
    }


# ---------------------------------------------------------------------------
# 11. Anomaly Detection (statistical outliers + relative spikes)
# ---------------------------------------------------------------------------

def anomaly_detection(df: pd.DataFrame, date_col: str = "date", value_col: str = "revenue",
                       freq: Optional[str] = None, agg: str = "sum",
                       zscore_threshold: float = 3.0,
                       spike_multiplier: float = 3.0,
                       rolling_window: int = 5) -> Optional[dict]:
    """
    Flags anomalies via two complementary methods:
    1. Statistical outliers — |z-score| > zscore_threshold
    2. Relative spikes — value > spike_multiplier x rolling median,
       which catches sudden jumps even when they're NOT statistical
       outliers across the whole series (e.g. one freak 12M day in
       an otherwise low-volume series).
    `freq=None` runs on the raw rows as-is — pass a freq to aggregate
    first if your rows aren't already one-value-per-timestamp.
    """
    _require_columns(df, [date_col, value_col])

    data = _to_datetime_safe(df, date_col)
    if data.empty:
        return None

    if freq:
        resample_freq = _require_freq(freq)
        agg_method = _agg_func(agg)
        series = data.set_index(date_col)[value_col].resample(resample_freq).agg(agg_method).sort_index()
    else:
        series = data.set_index(date_col)[value_col].sort_index()

    series = series.dropna()
    if len(series) < 3:
        return None

    mean, std = series.mean(), series.std()
    zscores = (series - mean) / std if std != 0 else pd.Series(0, index=series.index)
    rolling_median = series.rolling(window=rolling_window, min_periods=1).median()

    anomalies = []
    for ts, value, z, med in zip(series.index, series.values, zscores.values, rolling_median.values):
        z = float(z)
        med = float(med) if pd.notna(med) else None
        reasons = []
        if abs(z) > zscore_threshold:
            reasons.append(f"statistical outlier (z-score={round(z, 2)})")
        if med and med != 0 and value > med * spike_multiplier:
            reasons.append(f"spike vs rolling median (value={round(float(value), 2)} vs median={round(med, 2)})")
        if reasons:
            anomalies.append({
                "date": ts.strftime("%Y-%m-%d"),
                "value": round(float(value), 4),
                "zscore": round(z, 2),
                "rolling_median": round(med, 4) if med is not None else None,
                "reasons": reasons,
            })

    return {
        "total_points": len(series),
        "anomalies_found": len(anomalies),
        "anomalies": anomalies,
    }


def more_analysis_calculation(df, business_context):

    target_metric = business_context["target_metric"]
    date_column = business_context["date_column"]
    dimensions = business_context["dimensions"]

    return {

        "growth": growth_analysis(
            df,
            date_col=date_column,
            value_col=target_metric
        ),

        "segmentation": {
            dimension: segmentation_analysis(
                df,
                group_col=dimension,
                value_col=target_metric
            )
            for dimension in dimensions
        },

        "ranking": ranking_analysis(
            df,
            dimensions=dimensions,
            value_col=target_metric
        ),

        "pareto": {
            dimension: pareto_analysis(
                df,
                group_col=dimension,
                value_col=target_metric
            )
            for dimension in dimensions
        },

        "distribution": distribution_analysis(
            df,
            value_col=target_metric
        ),

        "contribution": {
            dimension: contribution_analysis(
                df,
                group_col=dimension,
                value_col=target_metric
            )
            for dimension in dimensions
        },

        "time_intelligence": time_intelligence(
            df,
            date_col=date_column,
            value_col=target_metric
        ),

        "missing_periods": missing_period_detection(
            df,
            date_col=date_column
        ),

        "anomaly": anomaly_detection(
            df,
            date_col=date_column,
            value_col=target_metric
        )
    }


# ---------------------------------------------------------------------------
# JSON-safety layer — call this right before passing any dict above into a
# prompt's .format(). Keeps the analysis functions themselves pure/computational.
# ---------------------------------------------------------------------------

def to_json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, pd.Series):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj) if not np.isnan(obj) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if obj is pd.NaT:
        return None
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj