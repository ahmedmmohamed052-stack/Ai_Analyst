from dotenv import load_dotenv
import contextvars
import json
import re
from huggingface_hub import InferenceClient
from prompts import (
    BusinessQuestionChain_prompt, SQLGenerationChain_prompt, DataQualityInterpretation_prompt,
    StatisticalInterpretation_prompt, CorrelationInterpretation_prompt, TrendInterpretation_prompt,
    OutlierInterpretationEDAChain_prompt, RootCauseChain_prompt, edachain_prompt,
    InsightChain_prompt, RecommendationChain_prompt,
    GrowthInterpretation_prompt, SegmentationInterpretation_prompt, RankingInterpretation_prompt,
    ParetoInterpretation_prompt, DistributionInterpretation_prompt, VarianceInterpretation_prompt,
    ContributionInterpretation_prompt, TimeIntelligenceInterpretation_prompt,
    MissingPeriodInterpretation_prompt, AnomalyInterpretation_prompt,
    render_dialect_sql_template,
)
from config import HF_TOKEN, MODEL_NAME, TEMPERATURE, MAX_NEW_TOKENS

load_dotenv()

client = InferenceClient(model=MODEL_NAME, token=HF_TOKEN, provider="auto")

# Language the human-readable interpretations should be written in. Set once per
# request by pipeline.run_pipeline(); a ContextVar keeps concurrent requests apart.
_output_language = contextvars.ContextVar("output_language", default="en")

def set_output_language(lang):
    """Returns a token; pass it to reset_output_language() when the request ends."""
    return _output_language.set(lang if lang in ("en", "ar") else "en")

def reset_output_language(token):
    _output_language.reset(token)

_ARABIC_DIRECTIVE = (
    "\n\nOUTPUT LANGUAGE (mandatory): write the whole response in clear Modern Standard "
    "Arabic (العربية الفصحى) for an Arabic-speaking business reader. Keep numbers, column "
    "names, table names, metric names, SQL and code exactly as they appear in the data — "
    "never translate identifiers. Do not change the structure or format requested above."
)

# Arabic labels for the assembled 'More analysis' write-up
_MORE_LABELS = {
    "growth": "النمو",
    "segmentation": "التقسيم حسب {d}",
    "ranking": "الترتيب",
    "pareto": "التركّز (باريتو) حسب {d}",
    "distribution": "شكل التوزيع",
    "contribution": "المساهمة حسب {d}",
    "time_intelligence": "الوتيرة الأخيرة",
    "missing_periods": "اكتمال البيانات",
    "anomaly": "الشذوذ",
    "none": "لم يتوفر أي تحليل إضافي بخلاف مراحل المسار الأساسية.",
}

def run_chain(prompt_template, localize=True, **kwargs):

    prompt = prompt_template.format(**kwargs)
    if localize and _output_language.get() == "ar":
        prompt += _ARABIC_DIRECTIVE

    response = client.chat_completion(
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=MAX_NEW_TOKENS,
        temperature=TEMPERATURE
    )

    return response.choices[0].message.content # already a clean string — no prompt echoed back, no [0]["generated_text"] needed

def parse_json_response(text):

    text = text.strip()
    text = text.replace("```json", "")
    text = text.replace("```", "")

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("No JSON found in model response")

    return json.loads(match.group())

# --- one wrapper per prompt, matching the placeholders we defined earlier ---

def businessquestion_chain(question, schema):

    response = run_chain(
        BusinessQuestionChain_prompt,
        localize=False,  # strict JSON — never localized
        question=question,
        schema=schema
    )

    return parse_json_response(response)

def sqlgeneration_chain(question, schema, business_context, latest_date, dialect="postgresql"):

    return run_chain(
        render_dialect_sql_template(dialect),
        localize=False,  # SQL — never localized
        question=question, 
        schema=schema, 
        business_context=business_context,
        latest_date=latest_date
        )

def dataquality_chain(quality_data):
    
    return run_chain(
        DataQualityInterpretation_prompt, 
        quality_data=quality_data)

def statistical_chain(statistics_data):

    return run_chain(
        StatisticalInterpretation_prompt, 
        statistics_data=statistics_data)

def correlation_chain(correlation_data):

    return run_chain(
        CorrelationInterpretation_prompt, 
        correlation_data=correlation_data)

def trend_chain(trend_data):

    return run_chain(
        TrendInterpretation_prompt, 
        trend_data=trend_data)

def outlier_chain(outlier_data):

    return run_chain(
        OutlierInterpretationEDAChain_prompt, 
        outlier_data=outlier_data)


# --- More-analysis sub-chains ---------------------------------------------
# Each of these has its own dedicated, single-purpose prompt (see prompts.py)
# instead of one giant prompt trying to interpret 8+ unrelated analyses at
# once. moreanalysis_chain() below orchestrates them and assembles the
# combined write-up that the rest of the pipeline expects.

def growth_chain(growth_data):
    return run_chain(GrowthInterpretation_prompt, growth_data=growth_data)

def segmentation_chain(segmentation_data):
    return run_chain(SegmentationInterpretation_prompt, segmentation_data=segmentation_data)

def ranking_chain(ranking_data):
    return run_chain(RankingInterpretation_prompt, ranking_data=ranking_data)

def pareto_chain(pareto_data):
    return run_chain(ParetoInterpretation_prompt, pareto_data=pareto_data)

def distribution_chain(distribution_data):
    return run_chain(DistributionInterpretation_prompt, distribution_data=distribution_data)

def variance_chain(variance_data):
    return run_chain(VarianceInterpretation_prompt, variance_data=variance_data)

def contribution_chain(contribution_data):
    return run_chain(ContributionInterpretation_prompt, contribution_data=contribution_data)

def time_intelligence_chain(time_intelligence_data):
    return run_chain(TimeIntelligenceInterpretation_prompt, time_intelligence_data=time_intelligence_data)

def missing_period_chain(missing_period_data):
    return run_chain(MissingPeriodInterpretation_prompt, missing_period_data=missing_period_data)

def anomaly_chain(anomaly_data):
    return run_chain(AnomalyInterpretation_prompt, anomaly_data=anomaly_data)


def _skip(value) -> bool:
    """True if a sub-report has nothing worth sending to the LLM."""
    if value is None:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def moreanalysis_chain(more_analysis_data):
    """
    Orchestrates the per-analysis-type interpreters over the dict produced
    by analysis.more_analysis_calculation(), then assembles one labeled
    write-up. Every piece gets its own focused prompt instead of dumping
    everything into a single oversized call — cheaper per call, and each
    interpretation stays on-topic instead of blending eight analyses
    together.

    `segmentation`, `pareto`, and `contribution` are dicts keyed by business
    dimension (one sub-report per dimension) — each dimension is
    interpreted separately and labeled by name.
    """
    sections = []
    ar = _output_language.get() == "ar"

    def label(en_label, key, dimension=None):
        if not ar:
            return en_label
        return _MORE_LABELS[key].format(d=dimension) if dimension is not None else _MORE_LABELS[key]

    growth_data = more_analysis_data.get("growth")
    if not _skip(growth_data):
        sections.append((label("Growth", "growth"), growth_chain(growth_data)))

    segmentation_data = more_analysis_data.get("segmentation") or {}
    for dimension, data in segmentation_data.items():
        if not _skip(data):
            sections.append((label(f"Segmentation by {dimension}", "segmentation", dimension), segmentation_chain(data)))

    ranking_data = more_analysis_data.get("ranking")
    if not _skip(ranking_data):
        sections.append((label("Ranking", "ranking"), ranking_chain(ranking_data)))

    pareto_data = more_analysis_data.get("pareto") or {}
    for dimension, data in pareto_data.items():
        if not _skip(data):
            sections.append((label(f"Concentration (Pareto) by {dimension}", "pareto", dimension), pareto_chain(data)))

    distribution_data = more_analysis_data.get("distribution")
    if not _skip(distribution_data):
        sections.append((label("Distribution shape", "distribution"), distribution_chain(distribution_data)))

    contribution_data = more_analysis_data.get("contribution") or {}
    for dimension, data in contribution_data.items():
        if not _skip(data):
            sections.append((label(f"Contribution by {dimension}", "contribution", dimension), contribution_chain(data)))

    time_intelligence_data = more_analysis_data.get("time_intelligence")
    if not _skip(time_intelligence_data):
        sections.append((label("Recent pace", "time_intelligence"), time_intelligence_chain(time_intelligence_data)))

    missing_period_data = more_analysis_data.get("missing_periods")
    if not _skip(missing_period_data):
        sections.append((label("Data completeness", "missing_periods"), missing_period_chain(missing_period_data)))

    anomaly_data = more_analysis_data.get("anomaly")
    if not _skip(anomaly_data):
        sections.append((label("Anomalies", "anomaly"), anomaly_chain(anomaly_data)))

    # variance_analysis isn't wired into more_analysis_calculation() yet
    # (no budget/target data source in the pipeline) — variance_chain is
    # ready to use the moment that data becomes available.

    if not sections:
        return _MORE_LABELS["none"] if ar else "No additional analysis was available beyond the core pipeline stages."

    return "\n\n".join(f"{label}: {text.strip()}" for label, text in sections)


def rootcause_chain(pipeline_state):

    return run_chain(
        RootCauseChain_prompt, 
        pipeline_state=pipeline_state)

def eda_chain(pipeline_state):

    return run_chain(
        edachain_prompt, 
        pipeline_state=pipeline_state)

def insight_chain(pipeline_state):

    return run_chain(
        InsightChain_prompt, 
        pipeline_state=pipeline_state)

def recommendation_chain(pipeline_state):

    return run_chain(
        RecommendationChain_prompt, 
        pipeline_state=pipeline_state)