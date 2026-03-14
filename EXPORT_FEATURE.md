# Inspection Report Export Feature

## Overview
The inspection report system now supports exporting reports in two formats:
- **Markdown (.md)**: Plain text format with markdown formatting
- **PDF (.pdf)**: Professional formatted PDF document

## Features

### Markdown Export
- Direct download of the report's markdown content
- Preserves all formatting, tables, and code blocks
- Filename format: `inspection_report_{id}_{timestamp}.md`

### PDF Export
- Converts markdown to professionally formatted PDF
- Includes:
  - Styled headers and sections
  - Tables with alternating row colors
  - Code blocks with syntax highlighting
  - Bullet lists and formatting
- Uses reportlab (pure Python, no system dependencies)
- Filename format: `inspection_report_{id}_{timestamp}.pdf`

## Usage

### From Web UI
1. Navigate to the Inspection page
2. Click on any completed report to view details
3. Use the export buttons in the top-right corner:
   - **📄 Export Markdown**: Download as .md file
   - **📑 Export PDF**: Download as .pdf file

### API Endpoints

#### Export Markdown
```bash
GET /api/inspections/reports/export/{report_id}/markdown
```

Example:
```bash
curl -O http://localhost:8000/api/inspections/reports/export/1/markdown
```

#### Export PDF
```bash
GET /api/inspections/reports/export/{report_id}/pdf
```

Example:
```bash
curl -O http://localhost:8000/api/inspections/reports/export/1/pdf
```

## Implementation Details

### Backend
- **Markdown Export**: [backend/routers/inspections.py:272](backend/routers/inspections.py#L272)
  - Returns raw markdown content from `Report.content_md`
  - Sets appropriate content-type and download headers

- **PDF Export**: [backend/routers/inspections.py:297](backend/routers/inspections.py#L297)
  - Uses custom PDF generator: `backend/utils/pdf_generator.py`
  - Converts markdown to PDF using reportlab
  - Handles tables, code blocks, headers, lists, and formatting

### Frontend
- **Export Buttons**: [frontend/js/pages/inspection.js:219](frontend/js/pages/inspection.js#L219)
  - Added to report detail view
  - Uses Fetch API to download files
  - Shows toast notifications for success/error

### Dependencies
- `reportlab>=4.0.0`: PDF generation (pure Python, no system dependencies)
- `markdown-it-py>=3.0.0`: Already used for markdown rendering

## Testing

Run the test script to verify export functionality:
```bash
python test_export_endpoints.py
```

This will:
1. Find or create a test report
2. Display export URLs
3. Provide curl commands for testing

## Error Handling

### Markdown Export
- Returns 404 if report not found
- Returns 400 if report has no markdown content

### PDF Export
- Returns 404 if report not found
- Returns 400 if report has no markdown content
- Returns 500 if PDF generation fails (with error details)

## Future Enhancements

Possible improvements:
1. Add HTML export option
2. Support batch export (multiple reports)
3. Add email delivery option
4. Include charts and graphs in PDF
5. Custom PDF templates/themes
6. Export scheduling (auto-export on report completion)

## Files Modified

1. `backend/routers/inspections.py`: Added export endpoints
2. `frontend/js/pages/inspection.js`: Added export buttons and handlers
3. `backend/utils/pdf_generator.py`: New PDF generation utility
4. `requirements.txt`: Added reportlab dependency
5. `test_export_endpoints.py`: Test script for export functionality
