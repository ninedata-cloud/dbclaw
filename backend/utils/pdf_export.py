import io
import logging

logger = logging.getLogger(__name__)


def html_to_pdf(html_content: str) -> bytes:
    try:
        from weasyprint import HTML
        pdf_buffer = io.BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        return pdf_buffer.getvalue()
    except (ImportError, OSError) as e:
        logger.warning(f"WeasyPrint unavailable ({e}), falling back to HTML-as-PDF wrapper")
        # Fallback: return HTML wrapped in a minimal PDF-like format
        # Return the HTML content as a downloadable HTML file instead
        raise RuntimeError(
            "PDF generation requires system libraries (pango, gobject). "
            "Install them with: brew install pango (macOS) or apt install libpango-1.0-0 (Linux). "
            "Use Markdown format as an alternative."
        )
