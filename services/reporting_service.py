from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch

def generate_clinic_report_pdf(clinic_name: str, stats: dict) -> BytesIO:
    """
    Generates a professional clinical institution performance report.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'ClinicTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#0052CC"), # Superhumanly Blue
        spaceAfter=30
    )
    
    header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor("#333333"),
        spaceBefore=20,
        spaceAfter=10
    )

    elements = []

    # 1. Header
    elements.append(Paragraph(f"{clinic_name}", title_style))
    elements.append(Paragraph(f"Monthly Clinical Performance Report", styles['Heading2']))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
    elements.append(Spacer(1, 0.5 * inch))

    # 2. Executive Summary
    elements.append(Paragraph("Executive Summary", header_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total Clinical Encounters", str(stats.get("total_encounters", 0))],
        ["Unique Patients Registered", str(stats.get("total_patients", 0))],
        ["Active Physician Staff", str(stats.get("team_size", 0))],
    ]
    
    t = Table(summary_data, colWidths=[3 * inch, 2 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F0F4F8")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#0052CC")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3 * inch))

    # 3. Staff Performance
    elements.append(Paragraph("Physician Productivity", header_style))
    staff_data = [["Physician Name", "Encounters"]]
    for staff in stats.get("staff_performance", []):
        staff_data.append([staff["name"], str(staff["encounters"])])
    
    st = Table(staff_data, colWidths=[3 * inch, 2 * inch])
    st.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F0F4F8")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (1, -1), 'CENTER')
    ]))
    elements.append(st)
    elements.append(Spacer(1, 0.3 * inch))

    # 4. Clinical Focus (Top Diagnoses)
    elements.append(Paragraph("Primary Clinical Focus (Top Diagnoses)", header_style))
    diag_data = [["Diagnosis", "Frequency"]]
    for diag in stats.get("top_diagnoses", []):
        diag_data.append([diag["name"], str(diag["count"])])
    
    dt = Table(diag_data, colWidths=[4 * inch, 1 * inch])
    dt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F0F4F8")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    elements.append(dt)

    # Footer
    elements.append(Spacer(1, 1 * inch))
    elements.append(Paragraph("Superhumanly Doctors - Sovereign Clinical Intelligence Platform", styles['Italic']))
    elements.append(Paragraph("Confidential - For Institutional Use Only", styles['Italic']))

    doc.build(elements)
    buffer.seek(0)
    return buffer
