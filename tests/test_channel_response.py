#!/usr/bin/env python3
"""
重现 422 错误
"""
from backend.schemas.integration import AlertChannelResponse
from datetime import datetime

# 模拟数据
data = {
    "id": 1,
    "name": "飞书webhook",
    "description": "",
    "integration_id": 2,
    "params": {"webhook_url": "https://example.com", "secret": ""},
    "enabled": True,
    "created_at": datetime.now(),
    "updated_at": datetime.now(),
    "integration_name": "飞书 Webhook 通知",
    "integration_type": "outbound_notification",
    "integration_category": "im"
}

try:
    response = AlertChannelResponse(**data)
    print("✓ 验证通过")
    print(response.model_dump_json(indent=2))
except Exception as e:
    print(f"✗ 验证失败: {e}")
