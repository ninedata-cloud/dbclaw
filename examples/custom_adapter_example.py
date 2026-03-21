#!/usr/bin/env python3
"""
用户自定义监控适配器脚本示例

此脚本演示如何编写自定义适配器来对接第三方监控系统。

输出格式：JSON 数组，每个元素包含以下字段：
- datasource_id: SmartDBA 数据源 ID（整数）
- metric_name: 指标名称（字符串）
- value: 指标值（数字）
- timestamp: 时间戳（ISO 8601 格式字符串）
- labels: 标签字典（可选）
- unit: 单位（可选）

环境变量：
- ADAPTER_CONFIG: JSON 格式的适配器配置
"""

import json
import sys
import os
from datetime import datetime
import requests


def fetch_from_custom_system():
    """从自定义监控系统拉取数据"""
    # 从环境变量获取配置
    config_str = os.environ.get("ADAPTER_CONFIG", "{}")
    config = json.loads(config_str)

    # 获取自定义参数
    custom_params = config.get("custom_params", {})
    api_url = custom_params.get("api_url")
    api_token = custom_params.get("api_token")

    if not api_url:
        raise ValueError("api_url is required in custom_params")

    # 调用第三方 API
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    response = requests.get(api_url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    # 转换为 SmartDBA 格式
    metrics = []
    datasource_mapping = config.get("datasource_mapping", {})

    for item in data.get("metrics", []):
        # 获取外部数据库 ID
        external_db_id = item.get("db_id") or item.get("instance_id")

        # 映射到 SmartDBA 数据源 ID
        datasource_id = datasource_mapping.get(external_db_id)
        if not datasource_id:
            continue

        # 构造指标数据点
        metric = {
            "datasource_id": datasource_id,
            "metric_name": item["name"],
            "value": float(item["value"]),
            "timestamp": item.get("timestamp", datetime.now().isoformat()),
            "labels": item.get("tags", {}),
            "unit": item.get("unit")
        }
        metrics.append(metric)

    return metrics


def validate():
    """验证连接"""
    try:
        config_str = os.environ.get("ADAPTER_CONFIG", "{}")
        config = json.loads(config_str)

        custom_params = config.get("custom_params", {})
        api_url = custom_params.get("api_url")

        if not api_url:
            return False

        # 简单的健康检查
        response = requests.get(f"{api_url}/health", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return False


def main():
    """主函数"""
    # 检查是否是验证模式
    if "--validate" in sys.argv:
        is_valid = validate()
        sys.exit(0 if is_valid else 1)

    try:
        # 拉取指标
        metrics = fetch_from_custom_system()

        # 输出 JSON
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
