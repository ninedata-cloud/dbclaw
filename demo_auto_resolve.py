"""
示例：告警自动恢复功能演示

这个脚本演示了告警自动恢复功能的工作流程。
"""

import asyncio
from datetime import datetime


async def simulate_alert_lifecycle():
    """模拟告警的完整生命周期"""

    print("=" * 60)
    print("告警自动恢复功能演示")
    print("=" * 60)

    # 场景 1: CPU 使用率告警
    print("\n场景 1: CPU 使用率告警")
    print("-" * 60)

    print("\n时间 10:00 - CPU 使用率: 85%")
    print("  → 超过阈值 80%")
    print("  → 创建告警 (ID: 1, status: active)")
    print("  → 触发 AI 诊断")

    await asyncio.sleep(1)

    print("\n时间 10:01 - CPU 使用率: 88%")
    print("  → 仍然超过阈值")
    print("  → 告警保持活跃 (去重保护，不创建新告警)")

    await asyncio.sleep(1)

    print("\n时间 10:02 - CPU 使用率: 65%")
    print("  → 低于阈值 80%")
    print("  → 自动解除告警 (ID: 1, status: resolved)")
    print("  ✓ 告警已自动恢复")

    # 场景 2: 数据库连接失败
    print("\n\n场景 2: 数据库连接失败")
    print("-" * 60)

    print("\n时间 10:05 - 数据库连接失败")
    print("  → 错误: Connection refused")
    print("  → 创建严重告警 (ID: 2, severity: critical)")
    print("  → 触发连接失败诊断")

    await asyncio.sleep(1)

    print("\n时间 10:06 - 数据库连接失败")
    print("  → 仍然无法连接")
    print("  → 告警保持活跃 (去重保护，不创建新告警)")

    await asyncio.sleep(1)

    print("\n时间 10:07 - 数据库连接成功")
    print("  → 连接已恢复")
    print("  → 自动解除告警 (ID: 2, status: resolved)")
    print("  ✓ 连接告警已自动恢复")

    # 场景 3: 多指标同时恢复
    print("\n\n场景 3: 多指标同时恢复")
    print("-" * 60)

    print("\n时间 10:10 - 多个指标异常")
    print("  → CPU: 90%, Memory: 95%, Disk: 88%")
    print("  → 创建 3 个告警 (ID: 3, 4, 5)")

    await asyncio.sleep(1)

    print("\n时间 10:11 - 部分指标恢复")
    print("  → CPU: 70%, Memory: 92%, Disk: 75%")
    print("  → 自动解除告警 ID: 3 (CPU)")
    print("  → 自动解除告警 ID: 5 (Disk)")
    print("  → 告警 ID: 4 (Memory) 保持活跃")
    print("  ✓ 已恢复的指标告警自动解除")

    await asyncio.sleep(1)

    print("\n时间 10:12 - 所有指标恢复")
    print("  → CPU: 70%, Memory: 80%, Disk: 75%")
    print("  → 自动解除告警 ID: 4 (Memory)")
    print("  ✓ 所有告警已自动恢复")

    # 总结
    print("\n\n" + "=" * 60)
    print("功能特点总结")
    print("=" * 60)
    print("✓ 指标恢复正常时自动解除告警")
    print("✓ 连接恢复时自动解除连接失败告警")
    print("✓ 支持多指标独立恢复")
    print("✓ 保留去重保护，避免重复告警")
    print("✓ 记录详细的恢复日志")
    print("=" * 60)


async def show_api_usage():
    """展示 API 使用示例"""

    print("\n\nAPI 使用示例")
    print("=" * 60)

    print("\n1. 查询告警（包含已恢复的告警）")
    print("""
GET /api/alerts?status=all&datasource_ids=1

响应示例：
{
  "alerts": [
    {
      "id": 1,
      "status": "resolved",
      "metric_name": "cpu_usage",
      "metric_value": 85.0,
      "threshold_value": 80.0,
      "created_at": "2026-03-16T10:00:00",
      "resolved_at": "2026-03-16T10:02:00"
    }
  ],
  "total": 1
}
    """)

    print("\n2. 查询活跃告警（排除已恢复）")
    print("""
GET /api/alerts?status=active&datasource_ids=1

响应示例：
{
  "alerts": [],
  "total": 0
}
    """)

    print("\n3. 手动解除告警（如果需要）")
    print("""
POST /api/alerts/1/resolve

响应示例：
{
  "id": 1,
  "status": "resolved",
  "resolved_at": "2026-03-16T10:02:00"
}
    """)


async def main():
    """主函数"""
    await simulate_alert_lifecycle()
    await show_api_usage()

    print("\n\n提示：")
    print("- 自动恢复功能默认启用，无需配置")
    print("- 监控采集周期默认 15 秒")
    print("- 查看详细文档：AUTO_RESOLVE_ALERTS.md")
    print()


if __name__ == "__main__":
    asyncio.run(main())
