import json
from fpdf import FPDF, XPos, YPos

class ExecutiveReportPDF(FPDF):
    def header(self):
        # Top banner styling
        self.set_fill_color(31, 41, 55)  # Dark Slate Blue/Gray
        self.rect(0, 0, 210, 25, 'F')
        
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, -5, "AUTOMATED DATA ANALYSIS PIPELINE REPORT", align="C")
        self.ln(12)

    def footer(self):
        # Bottom page numbering
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(156, 163, 175)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def add_section_header(self, title):
        self.ln(6)
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(243, 244, 246)  # Light gray background row
        self.set_text_color(29, 78, 216)    # Deep Accent Blue
        self.cell(0, 8, f"  {title.upper()}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def add_text_block(self, content):
        self.set_font("Helvetica", size=10)
        self.set_text_color(55, 65, 81)     # Dark Charcoal Text
        # Automatic Multi-cell wrapping
        self.multi_cell(0, 5, str(content))
        self.ln(2)

    def add_data_table(self, data_dict):
        """Formats flat dictionaries/metrics neatly into a clean two-column grid."""
        if not isinstance(data_dict, dict):
            self.add_text_block(str(data_dict))
            return
            
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(229, 231, 235)
        self.set_text_color(0, 0, 0)
        
        # Table Headers
        self.cell(70, 6, "Metric Key", border=1, fill=True)
        self.cell(120, 6, "Value / Status", border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        self.set_font("Helvetica", size=9)
        self.set_text_color(75, 85, 99)
        
        for key, value in data_dict.items():
            # Check if inner data is complex nested dict
            val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            
            # Key Column
            self.cell(70, 6, str(key)[:35], border=1)
            # Value Column
            self.cell(120, 6, val_str[:65], border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)


def generate_pipeline_pdf(result_data, filename="Pipeline_Analysis_Report.pdf"):
    # Ensure data is parsed into a Python Dict if passed as JSON string
    if isinstance(result_data, str):
        data = json.loads(result_data)
    else:
        data = result_data

    pdf = ExecutiveReportPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_margins(10, 25, 10)
    pdf.set_auto_page_break(auto=True, margin=20)

    # 1. Primary Metadata
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(30, 6, "User Query:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Helvetica", "I", 11)
    pdf.multi_cell(0, 6, f'"{data.get("question", "N/A")}"')
    pdf.ln(2)

    # 2. SQL Query Box
    pdf.add_section_header("Executed SQL Statement")
    pdf.set_font("Courier", size=9)
    pdf.set_fill_color(249, 250, 251)
    pdf.set_text_color(5, 150, 105) # Greenish slate text for code
    pdf.multi_cell(0, 5, data.get("sql_query", "No query found"), border=1, fill=True)

    # 3. Core Interpretations & Insights
    interpretations = [
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
    ]

    for title, key in interpretations:
        if key in data:
            pdf.add_section_header(title)
            pdf.add_text_block(data[key])

    # 4. Appendix: Raw Technical Reports Data
    pdf.add_page() # Start a clean page for raw tables
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 10, "Appendix: Structured Data Reports", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    reports = [
        ("Quality Metrics Report", "quality_report"),
        ("Descriptive Statistics Calculations", "statistics_report"),
        ("Correlation Vectors Matrix", "correlation_report"),
        ("Time Trend Report Output", "trend_report"),
        ("Identified Outliers Quantiles", "outlier_report"),
        ("Additional Analysis Raw Data (Growth, Segmentation, etc.)", "more_analysis_report"),
    ]

    for title, key in reports:
        if key in data:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            pdf.add_data_table(data[key])

    pdf.output(filename)
    print(f"Professional PDF Report successfully generated: {filename}")