import json
import os
from fpdf import FPDF, XPos, YPos

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Everything the PDF prints itself (the report body comes from the pipeline).
_LABELS = {
    "en": {
        "banner": "AUTOMATED DATA ANALYSIS PIPELINE REPORT",
        "page": "Page",
        "query": "User Query:",
        "sql": "Executed SQL Statement",
        "no_sql": "No query found",
        "appendix": "Appendix: Structured Data Reports",
        "metric": "Metric Key",
        "value": "Value / Status",
        "sections": [
            ("Business Context Context", "business_context"),
            ("Data Quality Summary", "quality_interpretation"),
            ("Statistical Insights", "statistics_interpretation"),
            ("Correlation & Relationship Dynamics", "correlation_interpretation"),
            ("Trend Timeline Assessment", "trend_interpretation"),
            ("Outlier Analysis Evaluation", "outlier_interpretation"),
            ("Additional Analysis (Growth, Segmentation, Ranking & More)", "more_analysis_interpretation"),
            ("Exploratory Data Analysis (EDA)", "eda"),
            ("Root Cause Analysis Conclusions", "root_cause"),
            ("Core Insights Generated", "insights"),
            ("Strategic Recommendations", "recommendations"),
        ],
        "reports": [
            ("Quality Metrics Report", "quality_report"),
            ("Descriptive Statistics Calculations", "statistics_report"),
            ("Correlation Vectors Matrix", "correlation_report"),
            ("Time Trend Report Output", "trend_report"),
            ("Identified Outliers Quantiles", "outlier_report"),
            ("Additional Analysis Raw Data (Growth, Segmentation, etc.)", "more_analysis_report"),
        ],
    },
    "ar": {
        "banner": "تقرير التحليل الآلي للبيانات",
        "page": "صفحة",
        "query": "السؤال:",
        "sql": "استعلام SQL المنفَّذ",
        "no_sql": "لم يتم العثور على استعلام",
        "appendix": "ملحق: تقارير البيانات المنظَّمة",
        "metric": "المقياس",
        "value": "القيمة / الحالة",
        "sections": [
            ("سياق العمل", "business_context"),
            ("ملخص جودة البيانات", "quality_interpretation"),
            ("الرؤى الإحصائية", "statistics_interpretation"),
            ("الارتباطات والعلاقات", "correlation_interpretation"),
            ("تقييم الاتجاه الزمني", "trend_interpretation"),
            ("تقييم القيم الشاذة", "outlier_interpretation"),
            ("تحليلات إضافية (النمو والتقسيم والترتيب وغيرها)", "more_analysis_interpretation"),
            ("التحليل الاستكشافي للبيانات (EDA)", "eda"),
            ("استنتاجات السبب الجذري", "root_cause"),
            ("أهم الرؤى المستخلصة", "insights"),
            ("التوصيات الاستراتيجية", "recommendations"),
        ],
        "reports": [
            ("تقرير مقاييس الجودة", "quality_report"),
            ("الحسابات الإحصائية الوصفية", "statistics_report"),
            ("مصفوفة الارتباط", "correlation_report"),
            ("مخرجات الاتجاه الزمني", "trend_report"),
            ("القيم الشاذة المحددة", "outlier_report"),
            ("البيانات الخام للتحليلات الإضافية", "more_analysis_report"),
        ],
    },
}


class ExecutiveReportPDF(FPDF):
    def __init__(self, lang="en"):
        super().__init__()
        self.lang = lang if lang in _LABELS else "en"
        self.L = _LABELS[self.lang]
        self.rtl = self.lang == "ar"
        if self.rtl:
            # Tajawal covers Arabic AND Latin, so mixed text (SQL names, numbers) renders.
            self.add_font("Tajawal", "", os.path.join(_FONT_DIR, "Tajawal-Regular.ttf"))
            self.add_font("Tajawal", "B", os.path.join(_FONT_DIR, "Tajawal-Bold.ttf"))
            self.add_font("Tajawal", "I", os.path.join(_FONT_DIR, "Tajawal-Regular.ttf"))
            self.set_text_shaping(True)  # joins Arabic letters + bidi ordering (needs uharfbuzz)
            self.font_name = "Tajawal"
        else:
            self.font_name = "Helvetica"

    def header(self):
        # Top banner styling
        self.set_fill_color(31, 41, 55)  # Dark Slate Blue/Gray
        self.rect(0, 0, 210, 25, 'F')

        self.set_text_color(255, 255, 255)
        self.set_font(self.font_name, "B", 14)
        self.cell(0, -5, self.L["banner"], align="C")
        self.ln(12)

    def footer(self):
        # Bottom page numbering
        self.set_y(-15)
        self.set_font(self.font_name, "I", 8)
        self.set_text_color(156, 163, 175)
        if self.rtl:
            # Arabic + the {nb} alias in one shaped string breaks the alias substitution,
            # so the number and the word are separate cells.
            self.set_x(self.l_margin)
            half = (self.w - self.l_margin - self.r_margin) / 2
            self.cell(half, 10, f"{self.page_no()}/{{nb}}", align="R")
            self.cell(half, 10, " " + self.L["page"], align="L")
        else:
            self.cell(0, 10, f"{self.L['page']} {self.page_no()}/{{nb}}", align="C")

    def add_section_header(self, title):
        self.ln(6)
        self.set_font(self.font_name, "B", 12)
        self.set_fill_color(243, 244, 246)  # Light gray background row
        self.set_text_color(29, 78, 216)    # Deep Accent Blue
        if self.rtl:
            self.cell(0, 8, f"{title}  ", fill=True, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            self.cell(0, 8, f"  {title.upper()}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def add_text_block(self, content):
        self.set_font(self.font_name, size=10)
        self.set_text_color(55, 65, 81)     # Dark Charcoal Text
        # Prose is right-aligned in Arabic; raw dict/list dumps are Latin, so they stay left.
        align = "R" if (self.rtl and isinstance(content, str)) else "L"
        self.multi_cell(0, 5, str(content), align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def add_data_table(self, data_dict):
        """Formats flat dictionaries/metrics neatly into a clean two-column grid."""
        if not isinstance(data_dict, dict):
            self.add_text_block(str(data_dict))
            return

        self.set_font(self.font_name, "B", 9)
        self.set_fill_color(229, 231, 235)
        self.set_text_color(0, 0, 0)

        # Table Headers (metric keys are identifiers, so the grid stays left-to-right)
        self.cell(70, 6, self.L["metric"], border=1, fill=True)
        self.cell(120, 6, self.L["value"], border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font(self.font_name, size=9)
        self.set_text_color(75, 85, 99)

        for key, value in data_dict.items():
            # Check if inner data is complex nested dict
            val_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

            # Key Column
            self.cell(70, 6, str(key)[:35], border=1)
            # Value Column
            self.cell(120, 6, val_str[:65], border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)


def generate_pipeline_pdf(result_data, filename="Pipeline_Analysis_Report.pdf", language=None):
    # Ensure data is parsed into a Python Dict if passed as JSON string
    if isinstance(result_data, str):
        data = json.loads(result_data)
    else:
        data = result_data

    # The report remembers the language it was generated in (pipeline adds "language").
    lang = language or data.get("language", "en")
    pdf = ExecutiveReportPDF(lang)
    L = pdf.L
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_margins(10, 25, 10)
    pdf.set_auto_page_break(auto=True, margin=20)
    f = pdf.font_name

    # 1. Primary Metadata
    pdf.ln(10)
    pdf.set_font(f, "B", 11)
    pdf.set_text_color(0, 0, 0)
    question = f'"{data.get("question", "N/A")}"'
    if pdf.rtl:
        pdf.multi_cell(0, 6, L["query"], align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(f, "I", 11)
        pdf.multi_cell(0, 6, question, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(30, 6, L["query"], new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font(f, "I", 11)
        pdf.multi_cell(0, 6, question)
    pdf.ln(2)

    # 2. SQL Query Box (always left-to-right, monospace)
    pdf.add_section_header(L["sql"])
    pdf.set_font("Courier", size=9)
    pdf.set_fill_color(249, 250, 251)
    pdf.set_text_color(5, 150, 105) # Greenish slate text for code
    pdf.multi_cell(0, 5, data.get("sql_query", L["no_sql"]), border=1, fill=True, align="L")

    # 3. Core Interpretations & Insights
    for title, key in L["sections"]:
        if key in data:
            pdf.add_section_header(title)
            pdf.add_text_block(data[key])

    # 4. Appendix: Raw Technical Reports Data
    pdf.add_page() # Start a clean page for raw tables
    pdf.set_font(f, "B", 14)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 10, L["appendix"], align="R" if pdf.rtl else "L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    for title, key in L["reports"]:
        if key in data:
            pdf.set_font(f, "B", 10)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 6, title, align="R" if pdf.rtl else "L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            pdf.add_data_table(data[key])

    pdf.output(filename)
    print(f"Professional PDF Report successfully generated: {filename}")