#!/usr/bin/env python3
"""Test script to verify Chinese report generation prompts"""

import sys
sys.path.insert(0, '.')

from backend.agent.prompts import REPORT_GENERATION_PROMPT

# Check if the prompt contains Chinese instructions
chinese_keywords = [
    "必须使用中文",
    "数据库巡检报告",
    "执行摘要",
    "数据库状态概览",
    "性能分析",
    "问题与建议",
    "行动计划"
]

print("检查 REPORT_GENERATION_PROMPT 是否包含中文关键词：\n")

all_found = True
for keyword in chinese_keywords:
    if keyword in REPORT_GENERATION_PROMPT:
        print(f"✓ 找到关键词：{keyword}")
    else:
        print(f"✗ 未找到关键词：{keyword}")
        all_found = False

print("\n" + "="*60)
if all_found:
    print("✓ 所有中文关键词都已找到！")
    print("✓ 报告生成 prompt 已成功中文化")
else:
    print("✗ 部分关键词未找到，请检查配置")
    sys.exit(1)

# Show a sample of the prompt
print("\n" + "="*60)
print("Prompt 示例（前 500 字符）：")
print("="*60)
print(REPORT_GENERATION_PROMPT[:500])
print("...")

