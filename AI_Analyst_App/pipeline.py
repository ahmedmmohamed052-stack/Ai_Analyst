from chains import (
    businessquestion_chain, sqlgeneration_chain, dataquality_chain, statistical_chain,
    correlation_chain, trend_chain, outlier_chain, rootcause_chain, eda_chain, insight_chain,
    recommendation_chain, moreanalysis_chain
)
from analysis import (
    dataquality, statistics_calculation, correlation_calculation, trend_calculation,
    outlier_calculation, to_json_safe, more_analysis_calculation
)
from security import sanitize_sql, validate_sql

def run_pipeline(question, data_source):
    """data_source is any object with get_schema(), get_latest_date(table, col),
    and execute_sql(query) — see datasources.py. It points at whichever
    dataset (uploaded file or external DB) the user picked for this
    question, not a single app-wide database."""

    schema = data_source.get_schema()

    business_context = businessquestion_chain(
        question,
        schema
    )

    latest_date = data_source.get_latest_date(
    business_context["tables"][0],
    business_context["date_column"]
    )

    target_metric = business_context["target_metric"]
    date_column = business_context["date_column"]

    dialect = "sqlite" if getattr(data_source, "dialect_note", None) == "sqlite" else "postgresql"

    sql_query = sqlgeneration_chain(
        question=question,
        schema=schema,
        business_context=business_context,
        latest_date=latest_date,
        dialect=dialect,
    )

    sql_query = sanitize_sql(sql_query)
    print("\nSQL RESPONSE:")
    print(sql_query)
    validate_sql(sql_query)

    df = data_source.execute_sql(sql_query)
    if df.empty:
        raise ValueError(
            'Query returned no Data'
        )

    quality_report = dataquality(df)

    quality_interpretation = dataquality_chain(
        quality_report
    )

    statistics_report = statistics_calculation(
        df,
        target_metric
    )

    statistics_interpretation = statistical_chain(
        statistics_report
    )

    correlation_report = correlation_calculation(
        df,
        target_metric
    )

    correlation_interpretation = correlation_chain(
        correlation_report
    )

    if (
        date_column in df.columns
        and target_metric in df.columns
    ):
        trend_report = trend_calculation(
            df,
            date_column,
            target_metric
        )
    else:
        trend_report = {
            "status": "skipped",
            "reason": "required columns not found"
        }

    trend_interpretation = trend_chain(
        trend_report
    )

    outlier_report = outlier_calculation(
        df,
        target_metric
    )

    outlier_interpretation = outlier_chain(
        outlier_report
    )

    # ── More Analysis ─────────────────────────────────────────────────────────
    more_analysis_report = more_analysis_calculation(df, business_context)

    more_analysis_interpretation = moreanalysis_chain(
        more_analysis_report
    )
    # ─────────────────────────────────────────────────────────────────────────

    eda_report = eda_chain({
        "quality": quality_report,
        "statistics": statistics_report,
        "correlations": correlation_report,
        "trends": trend_report,
        "outliers": outlier_report,
        "more_analysis": more_analysis_report       # ← fed into EDA as well
    })

    root_cause_report = rootcause_chain({
        "eda": eda_report,
        "quality": quality_report,
        "statistics": statistics_report,
        "correlations": correlation_report,
        "trends": trend_report,
        "outliers": outlier_report,
        "more_analysis": more_analysis_report       # ← available for root-cause
    })

    insights = insight_chain({
        "eda": eda_report,
        "root_cause": root_cause_report
    })

    recommendations = recommendation_chain({
        "insights": insights,
        "root_cause": root_cause_report
    })

    result = {
        "question": question,

        "business_context": business_context,

        "sql_query": sql_query,

        "quality_report": quality_report,
        "quality_interpretation": quality_interpretation,

        "statistics_report": statistics_report,
        "statistics_interpretation": statistics_interpretation,

        "correlation_report": correlation_report,
        "correlation_interpretation": correlation_interpretation,

        "trend_report": trend_report,
        "trend_interpretation": trend_interpretation,

        "outlier_report": outlier_report,
        "outlier_interpretation": outlier_interpretation,

        "more_analysis_report": more_analysis_report,               # ← new
        "more_analysis_interpretation": more_analysis_interpretation, # ← new

        "eda": eda_report,

        "root_cause": root_cause_report,

        "insights": insights,

        "recommendations": recommendations
    }

    return to_json_safe(result)


if __name__ == "__main__":
    # Manual/local test run: `python pipeline.py` — points at whatever
    # Postgres DB_HOST/DB_* env vars resolve to, purely for local smoke
    # testing of the pipeline; the real app builds a data_source per user
    # dataset instead (see datasources.py).
    from datasources import build_external_datasource
    import os
    ds = build_external_datasource({
        "db_type": "postgres",
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "ai"),
        "user": os.getenv("DB_USER", "postgres"),
        "encrypted_password": "",
    })
    question = "Why did revenue decrease last quarter?"
    result = run_pipeline(question, ds)
    print(result)
