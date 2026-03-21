#!/usr/bin/env python3
"""
测试时间格式
"""
from datetime import datetime, timedelta

end_time = datetime.utcnow()
start_time = end_time - timedelta(hours=1)

# 方式 1
start_time_str1 = start_time.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
end_time_str1 = end_time.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

print("方式 1 (replace microsecond):")
print(f"  StartTime: {start_time_str1}")
print(f"  EndTime: {end_time_str1}")

# 方式 2
start_time_str2 = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
end_time_str2 = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

print("\n方式 2 (直接 strftime):")
print(f"  StartTime: {start_time_str2}")
print(f"  EndTime: {end_time_str2}")

# 阿里云文档示例
print("\n阿里云文档示例:")
print("  2011-05-30T03:29:00Z")
