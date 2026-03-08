"""
Test script to debug report generation logic
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from backend.database import get_db
from backend.services.ai_report_generator import generate_ai_report
from sqlalchemy import select
from backend.models.datasource import Datasource
from backend.models.report import Report
import json


async def test_report_generation():
    """Test the report generation flow"""
    async for db in get_db():
        # Get a datasource
        result = await db.execute(select(Datasource).limit(1))
        datasource = result.scalar_one_or_none()

        if not datasource:
            print("No datasource found")
            return

        print(f"Testing with datasource: {datasource.name} (ID: {datasource.id}, Type: {datasource.db_type})")

        # Create a test report
        report = Report(
            datasource_id=datasource.id,
            title=f"Test Report - {datasource.name}",
            report_type="comprehensive",
            status="generating",
            generation_method="ai"
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        print(f"Created report ID: {report.id}")
        print("\n" + "="*80)
        print("Starting report generation...")
        print("="*80 + "\n")

        # Generate report and collect events
        events = []
        async for event in generate_ai_report(
            report_id=report.id,
            datasource_id=datasource.id,
            report_type="comprehensive",
            model_id=None,
            kb_ids=None,
            db=db,
            user_id=1
        ):
            events.append(event)
            event_type = event.get("type")

            if event_type == "status":
                print(f"[STATUS] {event.get('message')}")
            elif event_type == "content":
                print(f"[CONTENT] {event.get('content')[:100]}...")
            elif event_type == "tool_call":
                print(f"[TOOL_CALL] {event.get('tool_name')} with args: {event.get('tool_args')}")
            elif event_type == "tool_result":
                result_str = event.get('result', '')[:200]
                print(f"[TOOL_RESULT] {event.get('tool_name')} -> {result_str}... ({event.get('execution_time_ms')}ms)")
            elif event_type == "finding":
                print(f"[FINDING] {event.get('severity')} - {event.get('title')}")
            elif event_type == "error":
                print(f"[ERROR] {event.get('message')}")
            elif event_type == "done":
                print(f"[DONE]")
            elif event_type == "report_complete":
                print(f"[REPORT_COMPLETE] {event.get('summary')}")

        print("\n" + "="*80)
        print("Event Summary:")
        print("="*80)

        # Count events by type
        event_counts = {}
        for event in events:
            event_type = event.get("type")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        for event_type, count in sorted(event_counts.items()):
            print(f"{event_type}: {count}")

        # Check tool results
        print("\n" + "="*80)
        print("Tool Results Analysis:")
        print("="*80)

        tool_results = [e for e in events if e.get("type") == "tool_result"]
        for tr in tool_results:
            tool_name = tr.get("tool_name")
            result = tr.get("result", "")
            try:
                result_data = json.loads(result)
                if isinstance(result_data, dict):
                    print(f"\n{tool_name}:")
                    print(f"  Keys: {list(result_data.keys())}")
                    if "error" in result_data:
                        print(f"  ERROR: {result_data['error']}")
                    if "metrics" in result_data:
                        print(f"  Metrics keys: {list(result_data['metrics'].keys()) if isinstance(result_data['metrics'], dict) else 'not a dict'}")
                elif isinstance(result_data, list):
                    print(f"\n{tool_name}:")
                    print(f"  List length: {len(result_data)}")
                    if result_data and isinstance(result_data[0], dict):
                        print(f"  First item keys: {list(result_data[0].keys())}")
            except:
                print(f"\n{tool_name}: (non-JSON result)")

        # Debug: Check what data was collected for diagnostic engine
        print("\n" + "="*80)
        print("Collected Data for Diagnostic Engine:")
        print("="*80)

        # We need to simulate the data collection logic
        collected_data_debug = {}
        for tr in tool_results:
            tool_name = tr.get("tool_name")
            result = tr.get("result", "")
            try:
                result_data = json.loads(result)

                # Extract actual data from wrapped response
                if isinstance(result_data, dict) and result_data.get("success"):
                    if "metrics" in result_data:
                        actual_data = result_data["metrics"]
                    elif "data" in result_data:
                        actual_data = result_data["data"]
                    elif "tables" in result_data:
                        actual_data = result_data["tables"]
                    else:
                        actual_data = result_data
                else:
                    actual_data = result_data

                if "get_db_status" in tool_name:
                    collected_data_debug["status"] = actual_data
                    print(f"\nStatus data: {actual_data}")
                elif "get_slow_queries" in tool_name:
                    if isinstance(result_data, dict) and not result_data.get("extension_enabled", True):
                        collected_data_debug["slow_queries"] = []
                    else:
                        collected_data_debug["slow_queries"] = actual_data
                    print(f"\nSlow queries data: {collected_data_debug.get('slow_queries')}")
                elif "get_table_stats" in tool_name:
                    collected_data_debug["table_stats"] = actual_data
                    print(f"\nTable stats data type: {type(actual_data)}, length: {len(actual_data) if isinstance(actual_data, list) else 'N/A'}")
                elif "get_os_metrics" in tool_name:
                    collected_data_debug["os_metrics"] = actual_data
                    print(f"\nOS metrics data: {actual_data}")
            except Exception as e:
                print(f"\nError processing {tool_name}: {e}")

        # Check final report
        print("\n" + "="*80)
        print("Final Report:")
        print("="*80)

        await db.refresh(report)
        print(f"Status: {report.status}")
        print(f"Summary: {report.summary}")
        print(f"AI Analysis length: {len(report.ai_analysis or '')}")
        print(f"Content MD length: {len(report.content_md or '')}")
        print(f"Content HTML length: {len(report.content_html or '')}")
        print(f"Findings: {report.findings}")

        if report.error_message:
            print(f"Error: {report.error_message}")


if __name__ == "__main__":
    asyncio.run(test_report_generation())
