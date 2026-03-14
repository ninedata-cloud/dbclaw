#!/usr/bin/env python3
"""Simple verification of export feature implementation"""

print("=" * 80)
print("SmartDBA Export Feature Verification")
print("=" * 80)

# 1. Check Chinese prompt
print("\n1. Checking INSPECTION_REPORT_PROMPT...")
from backend.agent.prompts import INSPECTION_REPORT_PROMPT
chinese_keywords = ["数据库", "配置", "负载", "中文"]
found = sum(1 for kw in chinese_keywords if kw in INSPECTION_REPORT_PROMPT)
print(f"   Found {found}/{len(chinese_keywords)} Chinese keywords: {'✅ PASS' if found >= 3 else '❌ FAIL'}")

# 2. Check export endpoints
print("\n2. Checking export endpoints...")
with open('backend/routers/inspections.py', 'r') as f:
    content = f.read()
    has_markdown = 'export/{report_id}/markdown' in content
    has_pdf = 'export/{report_id}/pdf' in content
    print(f"   Markdown endpoint: {'✅ PASS' if has_markdown else '❌ FAIL'}")
    print(f"   PDF endpoint: {'✅ PASS' if has_pdf else '❌ FAIL'}")

# 3. Check HTML generation in report_generator
print("\n3. Checking HTML generation...")
with open('backend/services/report_generator.py', 'r') as f:
    content = f.read()
    has_html_gen = 'content_html =' in content and 'MarkdownIt' in content
    print(f"   HTML generation: {'✅ PASS' if has_html_gen else '❌ FAIL'}")

# 4. Check frontend export buttons
print("\n4. Checking frontend export buttons...")
with open('frontend/js/pages/inspection-dashboard.js', 'r') as f:
    content = f.read()
    has_export_md = 'exportMarkdown' in content
    has_export_pdf = 'exportPDF' in content
    print(f"   Markdown button: {'✅ PASS' if has_export_md else '❌ FAIL'}")
    print(f"   PDF button: {'✅ PASS' if has_export_pdf else '❌ FAIL'}")

# 5. Check weasyprint (optional)
print("\n5. Checking weasyprint (optional)...")
try:
    import weasyprint
    print(f"   ✅ Installed (version {weasyprint.__version__})")
except ImportError:
    print("   ⚠️  Not installed (optional - install with: pip install weasyprint)")
except Exception as e:
    print(f"   ⚠️  Import error: {str(e)[:50]}...")
    print("   Note: System dependencies may be required")

print("\n" + "=" * 80)
print("Verification complete!")
print("=" * 80)
