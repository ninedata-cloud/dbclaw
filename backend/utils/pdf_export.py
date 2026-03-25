import io
import logging
from html.parser import HTMLParser
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

logger = logging.getLogger(__name__)

PDF_FONT_NAME = 'STSong-Light'


def _ensure_cjk_font_registered():
    if PDF_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))


class HTMLToPDFParser(HTMLParser):
    """Simple HTML parser to extract text content for PDF generation"""
    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_text = []
        self.in_heading = None
        self.in_paragraph = False
        self.in_list = False
        self.in_table = False
        self.table_rows = []
        self.current_row = []
        self.in_code = False

    def handle_starttag(self, tag, attrs):
        if tag in ['h1', 'h2', 'h3', 'h4']:
            self.in_heading = tag
        elif tag == 'p':
            self.in_paragraph = True
        elif tag in ['ul', 'ol']:
            self.in_list = True
        elif tag == 'table':
            self.in_table = True
            self.table_rows = []
        elif tag == 'tr':
            self.current_row = []
        elif tag in ['code', 'pre']:
            self.in_code = True

    def handle_endtag(self, tag):
        if tag in ['h1', 'h2', 'h3', 'h4']:
            text = ''.join(self.current_text).strip()
            if text:
                self.elements.append(('heading', tag, text))
            self.current_text = []
            self.in_heading = None
        elif tag == 'p':
            text = ''.join(self.current_text).strip()
            if text:
                self.elements.append(('paragraph', text))
            self.current_text = []
            self.in_paragraph = False
        elif tag in ['ul', 'ol']:
            self.in_list = False
        elif tag == 'li':
            text = ''.join(self.current_text).strip()
            if text:
                self.elements.append(('list_item', text))
            self.current_text = []
        elif tag == 'table':
            if self.table_rows:
                self.elements.append(('table', self.table_rows))
            self.in_table = False
            self.table_rows = []
        elif tag == 'tr':
            if self.current_row:
                self.table_rows.append(self.current_row)
            self.current_row = []
        elif tag in ['td', 'th']:
            text = ''.join(self.current_text).strip()
            self.current_row.append(text)
            self.current_text = []
        elif tag in ['code', 'pre']:
            self.in_code = False

    def handle_data(self, data):
        if self.in_heading or self.in_paragraph or self.in_list or self.in_table:
            self.current_text.append(data)


def html_to_pdf(html_content: str) -> bytes:
    """Convert HTML content to PDF using reportlab (pure Python, no system dependencies)"""
    try:
        _ensure_cjk_font_registered()

        # Parse HTML
        parser = HTMLToPDFParser()
        parser.feed(html_content)

        # Create PDF
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, topMargin=0.75*inch, bottomMargin=0.75*inch)

        # Styles
        styles = getSampleStyleSheet()
        styles['Heading1'].fontName = PDF_FONT_NAME
        styles['Heading2'].fontName = PDF_FONT_NAME
        styles['Heading3'].fontName = PDF_FONT_NAME
        styles['BodyText'].fontName = PDF_FONT_NAME
        styles.add(ParagraphStyle(name='CustomHeading1', parent=styles['Heading1'], fontName=PDF_FONT_NAME, fontSize=24, spaceAfter=12))
        styles.add(ParagraphStyle(name='CustomHeading2', parent=styles['Heading2'], fontName=PDF_FONT_NAME, fontSize=18, spaceAfter=10))
        styles.add(ParagraphStyle(name='CustomHeading3', parent=styles['Heading3'], fontName=PDF_FONT_NAME, fontSize=14, spaceAfter=8))
        styles.add(ParagraphStyle(name='CustomBody', parent=styles['BodyText'], fontName=PDF_FONT_NAME, fontSize=10, spaceAfter=6))
        styles.add(ParagraphStyle(name='ListItem', parent=styles['BodyText'], fontName=PDF_FONT_NAME, fontSize=10, leftIndent=20, spaceAfter=4))

        # Build PDF content
        story = []

        for element in parser.elements:
            if element[0] == 'heading':
                _, tag, text = element
                style_map = {'h1': 'CustomHeading1', 'h2': 'CustomHeading2', 'h3': 'CustomHeading3', 'h4': 'CustomHeading3'}
                story.append(Paragraph(text, styles[style_map.get(tag, 'CustomHeading3')]))
                story.append(Spacer(1, 0.1*inch))
            elif element[0] == 'paragraph':
                _, text = element
                story.append(Paragraph(text, styles['CustomBody']))
            elif element[0] == 'list_item':
                _, text = element
                story.append(Paragraph(f"• {text}", styles['ListItem']))
            elif element[0] == 'table':
                _, rows = element
                if rows:
                    # Create table
                    table = Table(rows)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, -1), PDF_FONT_NAME),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 0.2*inch))

        # Build PDF
        doc.build(story)
        return pdf_buffer.getvalue()

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise RuntimeError(f"PDF generation failed: {str(e)}")
