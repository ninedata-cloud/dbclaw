#!/usr/bin/env python3
"""
Test script for inspection report export feature
"""
import asyncio
from backend.agent.prompts import INSPECTION_REPORT_PROMPT

def test_chinese_prompt():
    """Test that the inspection prompt is in Chinese"""
    print("Testing INSPECTION_REPORT_PROMPT...")
    print("-" * 80)
    print(INSPECTION_REPORT_PROMPT)
    print("-" * 80)
    
    # Check for Chinese characters
    chinese_keywords = ["数据库", "配置", "负载", "指标", "空间", "使用", "中文"]
    found_keywords = [kw for kw in chinese_keywords if kw in INSPECTION_REPORT_PROMPT]
    
    print(f"\nFound Chinese keywords: {found_keywords}")
    print(f"Total: {len(found_keywords)}/{len(chinese_keywords)}")
    
    if len(found_keywords) >= 5:
        print("✅ PASS: Prompt is in Chinese")
        return True
    else:
        print("❌ FAIL: Prompt is not in Chinese")
        return False

def test_export_endpoints():
    """Test that export endpoints are defined"""
    print("\nTesting export endpoints...")
    
    try:
        from backend.routers.inspections import router
        
        # Get all routes
        routes = [route.path for route in router.routes]
        
        markdown_export = "/reports/export/{report_id}/markdown" in routes
        pdf_export = "/reports/export/{report_id}/pdf" in routes
        
        print(f"Markdown export endpoint: {'✅' if markdown_export else '❌'}")
        print(f"PDF export endpoint: {'✅' if pdf_export else '❌'}")
        
        if markdown_export and pdf_export:
            print("✅ PASS: Export endpoints are defined")
            return True
        else:
            print("❌ FAIL: Export endpoints are missing")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_weasyprint_availability():
    """Test if weasyprint is available"""
    print("\nTesting weasyprint availability...")
    
    try:
        import weasyprint
        print(f"✅ weasyprint is installed (version: {weasyprint.__version__})")
        return True
    except ImportError:
        print("⚠️  weasyprint is not installed")
        print("   Install with: pip install weasyprint")
        print("   Note: System dependencies may be required")
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("SmartDBA Export Feature Test")
    print("=" * 80)
    
    results = []
    results.append(("Chinese Prompt", test_chinese_prompt()))
    results.append(("Export Endpoints", test_export_endpoints()))
    results.append(("WeasyPrint", test_weasyprint_availability()))
    
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")
    
    total_passed = sum(1 for _, passed in results if passed)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")
    
    if total_passed == len(results):
        print("\n🎉 All tests passed!")
    elif total_passed >= len(results) - 1:
        print("\n⚠️  Most tests passed (weasyprint is optional)")
    else:
        print("\n❌ Some tests failed")
