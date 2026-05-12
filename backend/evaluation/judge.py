"""LLM-as-judge for semantic dimensions (root cause, action quality)."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.evaluation.case_loader import EvalCase
from backend.evaluation.scorer import (
    WEIGHT_ACTION,
    WEIGHT_ROOT_CAUSE,
    score_action_keywords,
)

logger = logging.getLogger(__name__)


@dataclass
class JudgeResult:
    root_cause_score: float          # 0..WEIGHT_ROOT_CAUSE
    action_score: float              # 0..WEIGHT_ACTION
    root_cause_feedback: str
    action_feedback: str
    raw_response: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_cause_score": round(self.root_cause_score, 2),
            "action_score": round(self.action_score, 2),
            "root_cause_feedback": self.root_cause_feedback,
            "action_feedback": self.action_feedback,
            "error": self.error,
        }


JUDGE_SYSTEM = (
    "You are an expert DBA evaluator scoring an AI database-diagnosis agent's "
    "output against a known-good answer key. Respond with strict JSON only — "
    "no markdown, no commentary outside the JSON object."
)

JUDGE_PROMPT = """Evaluate the AI agent's diagnostic conclusion against the expected answer.

# Case
Title: {title}
Category: {category}
DB type: {db_type}
User question: {user_message}

# Expected root causes (reference)
{expected_root_causes}

# Expected actions (must include these recommendations or equivalent)
{expected_actions}

# Agent's conclusion (markdown)
<<<
{conclusion_md}
>>>

# Scoring rules
Return JSON with these exact keys:
{{
  "root_cause_score": <number 0..{root_cause_max}>,
  "root_cause_feedback": "<short Chinese explanation>",
  "action_score": <number 0..{action_max}>,
  "action_feedback": "<short Chinese explanation>"
}}

Rubric:
- root_cause_score: how well the conclusion identifies the SAME root cause as the expected list. Full marks only if every expected root cause is correctly identified with supporting evidence. Half marks for partial overlap. Zero if root cause is wrong or missing.
- action_score: how concrete and correct the recommended actions are vs the expected actions. Reward specific, executable suggestions (SQL/DDL/commands). Penalize vague advice or actions that don't address the root cause.

Be strict. Do not award points for verbose but incorrect content."""


def _format_list(items: List[str]) -> str:
    if not items:
        return "(none)"
    return "\n".join(f"- {x}" for x in items)


def _format_actions(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return "(none)"
    parts = []
    for a in actions:
        kws = a.get("keywords") or []
        parts.append(f"- keywords: {kws}")
    return "\n".join(parts)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    # Try direct
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try to find first {...} block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


async def run_judge(
    case: EvalCase,
    conclusion_md: str,
    judge_client,
) -> JudgeResult:
    """Call the judge LLM and parse a score JSON.

    `judge_client` must be the result of `services.ai_agent.get_ai_client(...)`.
    """
    if not conclusion_md or not conclusion_md.strip():
        # Apply keyword gate even with no conclusion
        return JudgeResult(
            root_cause_score=0.0,
            action_score=0.0,
            root_cause_feedback="结论为空，无法评估根因。",
            action_feedback="结论为空，无可执行建议。",
            error="empty_conclusion",
        )

    prompt = JUDGE_PROMPT.format(
        title=case.title,
        category=case.category,
        db_type=case.db_type,
        user_message=case.user_message,
        expected_root_causes=_format_list(case.expected.root_causes),
        expected_actions=_format_actions(case.expected.required_actions),
        conclusion_md=conclusion_md[:8000],
        root_cause_max=WEIGHT_ROOT_CAUSE,
        action_max=WEIGHT_ACTION,
    )

    try:
        from backend.services.ai_agent import request_text_response
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        text = await request_text_response(
            judge_client,
            messages,
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.exception("Judge LLM call failed")
        return JudgeResult(
            root_cause_score=0.0,
            action_score=0.0,
            root_cause_feedback="",
            action_feedback="",
            error=f"judge_call_failed: {exc}",
        )

    parsed = _extract_json(text or "")
    if not parsed:
        return JudgeResult(
            root_cause_score=0.0,
            action_score=0.0,
            root_cause_feedback="",
            action_feedback="",
            raw_response=text or "",
            error="judge_response_unparseable",
        )

    rc = float(parsed.get("root_cause_score", 0))
    ac = float(parsed.get("action_score", 0))
    rc = max(0.0, min(WEIGHT_ROOT_CAUSE, rc))
    ac = max(0.0, min(WEIGHT_ACTION, ac))

    # Keyword gate: action requires required-keyword hits to award full marks
    kw_hits, kw_total, _ = score_action_keywords(case, conclusion_md)
    if kw_total > 0 and kw_hits < kw_total:
        # cap at proportion of keywords actually hit
        max_allowed = WEIGHT_ACTION * (kw_hits / kw_total)
        if ac > max_allowed:
            ac = max_allowed

    return JudgeResult(
        root_cause_score=rc,
        action_score=ac,
        root_cause_feedback=str(parsed.get("root_cause_feedback", ""))[:500],
        action_feedback=str(parsed.get("action_feedback", ""))[:500],
        raw_response=(text or "")[:2000],
    )
