"""Simple PDF generator for inspection report using reportlab"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import re


PDF_FONT_NAME = 'STSong-Light'


def _ensure_cjk_font_registered():
    if PDF_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))


def markdown_to_pdf(markdown_text: str, title: str = "Inspection Report") -> bytes:
    """Convert markdown text to PDF"""
    _ensure_cjk_font_registered()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.75*inch, bottomMargin=0.75*inch)

    styles = getSampleStyleSheet()
    styles['Heading1'].fontName = PDF_FONT_NAME
    styles['Heading2'].fontName = PDF_FONT_NAME
    styles['Heading3'].fontName = PDF_FONT_NAME
    styles['Normal'].fontName = PDF_FONT_NAME
    styles['Code'].fontName = PDF_FONT_NAME

    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=PDF_FONT_NAME,
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Parse markdown
    lines = markdown_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            story.append(Spacer(1, 0.1*inch))
            i += 1
            continue
        
        # Headers
        if line.startswith('# '):
            text = line[2:].strip()
            story.append(Paragraph(text, styles['Heading1']))
            story.append(Spacer(1, 0.2*inch))
        elif line.startswith('## '):
            text = line[3:].strip()
            story.append(Paragraph(text, styles['Heading2']))
            story.append(Spacer(1, 0.15*inch))
        elif line.startswith('### '):
            text = line[4:].strip()
            story.append(Paragraph(text, styles['Heading3']))
            story.append(Spacer(1, 0.1*inch))
        
        # Lists
        elif line.startswith('- ') or line.startswith('* '):
            text = line[2:].strip()
            bullet_style = ParagraphStyle('Bullet', parent=styles['Normal'], fontName=PDF_FONT_NAME, leftIndent=20, bulletIndent=10)
            story.append(Paragraph(f"• {text}", bullet_style))
        
        # Tables (simple markdown tables)
        elif '|' in line and i + 1 < len(lines) and '---' in lines[i + 1]:
            # Parse table
            headers = [cell.strip() for cell in line.split('|')[1:-1]]
            i += 2  # Skip separator line
            
            table_data = [headers]
            while i < len(lines) and '|' in lines[i]:
                row = [cell.strip() for cell in lines[i].split('|')[1:-1]]
                table_data.append(row)
                i += 1
            
            if table_data:
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, -1), PDF_FONT_NAME),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
                ]))
                story.append(t)
                story.append(Spacer(1, 0.2*inch))
            continue
        
        # Code blocks
        elif line.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            
            code_text = '\n'.join(code_lines)
            code_style = ParagraphStyle(
                'Code',
                parent=styles['Code'],
                fontName=PDF_FONT_NAME,
                fontSize=9,
                leftIndent=20,
                backgroundColor=colors.HexColor('#f4f4f4'),
                borderPadding=10
            )
            story.append(Paragraph(f"<pre>{code_text}</pre>", code_style))
            story.append(Spacer(1, 0.1*inch))
        
        # Normal paragraph
        else:
            # Simple markdown formatting
            text = line
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)  # Bold
            text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)  # Italic
            text = re.sub(r'`(.*?)`', r'<font face="Courier">\1</font>', text)  # Code
            
            story.append(Paragraph(text, styles['Normal']))
            story.append(Spacer(1, 0.05*inch))
        
        i += 1
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
