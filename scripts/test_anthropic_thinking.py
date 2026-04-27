#!/usr/bin/env python3
"""
最小 Anthropic thinking 测试脚本。

用途：
1. 独立验证 Anthropic 协议是否真的启用了 thinking
2. 观察返回中是否出现 type="thinking" 的内容块

示例：
  export ANTHROPIC_API_KEY="sk-ant-..."
  python scripts/test_anthropic_thinking.py \
    --model claude-opus-4-6 \
    --mode adaptive \
    --effort high \
    --max-tokens 32000
"""

import argparse
import asyncio
import os
from typing import Any, Dict, Optional

from anthropic import AsyncAnthropic


def build_thinking_config(
    mode: str,
    effort: str,
    budget_tokens: int,
) -> Dict[str, Any]:
    if mode == "adaptive":
        return {"type": "adaptive", "effort": effort}
    return {"type": "enabled", "budget_tokens": budget_tokens}


async def run_test(
    api_key: str,
    base_url: Optional[str],
    model: str,
    max_tokens: int,
    mode: str,
    effort: str,
    budget_tokens: int,
    prompt: str,
) -> None:
    client = AsyncAnthropic(api_key=api_key, base_url=base_url or None)
    response =await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=16000,
        thinking={"type": "adaptive"},  # 必须开启自适应思考
        output_config={"effort": "medium"}, # 填入 low, medium, high, max
        messages=[{"role": "user", "content": prompt}],
    )
    print(f"response={response}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Anthropic thinking minimal test")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY", ""), help="Anthropic API key")
    parser.add_argument("--base-url", default=os.getenv("ANTHROPIC_BASE_URL", ""), help="Anthropic base URL")
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6"), help="Model name")
    parser.add_argument("--max-tokens", type=int, default=os.getenv("ANTHROPIC_MAX_TOKENS", 32000), help="Max output tokens")
    parser.add_argument(
        "--mode",
        choices=["adaptive", "enabled"],
        default="adaptive",
        help="Thinking mode",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default="high",
        help="Adaptive effort (adaptive mode only)",
    )
    parser.add_argument(
        "--budget-tokens",
        type=int,
        default=1500,
        help="Budget tokens (enabled mode only, should be >=1024 and < max_tokens)",
    )
    parser.add_argument(
        "--prompt",
        default="1+3=?",
        help="User prompt",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("缺少 API Key：请传 --api-key 或设置环境变量 ANTHROPIC_API_KEY")

    asyncio.run(
        run_test(
            api_key=args.api_key,
            base_url=args.base_url or None,
            model=args.model,
            max_tokens=args.max_tokens,
            mode=args.mode,
            effort=args.effort,
            budget_tokens=args.budget_tokens,
            prompt=args.prompt,
        )
    )


if __name__ == "__main__":
    main()
