"""Generate a rich multi-page demo HR handbook for upload testing.
Usage: python scripts/make_demo_policy.py  ->  sample_docs/Acme_Employee_Handbook_2026.pdf
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

OUT = Path(__file__).resolve().parents[1] / "sample_docs" / "Acme_Employee_Handbook_2026.pdf"

styles = getSampleStyleSheet()
h1 = styles["Heading1"]
h2 = styles["Heading2"]
body = styles["BodyText"]

story = [
    Paragraph("Acme Technologies — Employee Handbook 2026", h1),
    Paragraph("Effective 1 January 2026 · Applies to all full-time employees in India", body),
    Spacer(1, 0.6 * cm),
    Paragraph("1. Leave Policy", h2),
    Paragraph("All full-time employees receive 22 days of annual leave per calendar year. "
              "Unused leave up to 5 days may be carried forward to the next year.", body),
    Paragraph("Sick leave is 10 days per year. A medical certificate is required for absences "
              "longer than 2 consecutive days.", body),
    Paragraph("Maternity leave is 26 weeks for India-based employees, and paternity leave is "
              "20 days to be availed within 6 months of childbirth.", body),
    PageBreak(),
    Paragraph("2. Separation and Notice Period", h2),
    Paragraph("The notice period depends on tenure and seniority, as summarised below.", body),
    Spacer(1, 0.3 * cm),
    Table(
        [["Tenure", "Individual Contributors", "Managers and above"],
         ["Less than 1 year", "30 days", "30 days"],
         ["1 to 3 years", "45 days", "60 days"],
         ["More than 3 years", "60 days", "90 days"]],
        colWidths=[5 * cm, 5 * cm, 5 * cm],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                          ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]),
    ),
    Spacer(1, 0.4 * cm),
    Paragraph("Garden leave may apply to senior leadership at the company's discretion.", body),
    PageBreak(),
    Paragraph("3. Work From Home and Conduct", h2),
    Paragraph("Employees may work from home up to 3 days per week with prior manager approval. "
              "Core collaboration hours are 11 AM to 4 PM IST.", body),
    Paragraph("All employees must complete the annual Code of Conduct training by 31 March. "
              "Grievances must be reported to HR within 10 working days of the incident.", body),
    PageBreak(),
    Paragraph("4. Benefits and POSH", h2),
    Paragraph("Health insurance covers the employee, spouse, and up to two children with a "
              "family floater of Rs. 5,00,000 per annum.", body),
    Paragraph("As per Article 12.3 of the POSH policy, every office with 10 or more employees "
              "must constitute an Internal Committee. Complaints must be filed in writing within "
              "3 months, and the inquiry completed within 90 days.", body),
    Paragraph("Employees are entitled to 12 company holidays per year, published each December.", body),
]

SimpleDocTemplate(str(OUT), pagesize=A4,
                  title="Acme Employee Handbook 2026").build(story)
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
