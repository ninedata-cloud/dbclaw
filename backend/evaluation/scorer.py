"""Programmatic scoring dimensions for an evaluation case run.

The semantic dimensions (root cause, action quality) come from `judge.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.evaluation.case_loader import EvalCase
from backend.evaluation.mock_executor import CallRecorder

# Dimension weights (sum = 100)
WEIGHT_ROOT_CAUSE = 30      # judge
WEIGHT_TOOL_SELECTION = 20  # programmatic
WEIGHT_ACTION = 15          # judge + keyword
WEIGHT_STRUCTURE = 10       # programmatic
WEIGHT_EVIDENCE = 10        # programmatic (heuristic)
WEIGHT_EFFICIENCY = 10      # programmatic
WEIGHT_LATENCY = 5          # programmatic


@dataclass
class DimensionScore:
    name: str
    score: float
    max_score: float
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 2),
            "max_score": self.max_score,
            "detail": self.detail,
        }


@dataclass
class ProgrammaticBreakdown:
    tool_selection: DimensionScore
    structure: DimensionScore
    evidence: DimensionScore
    efficiency: DimensionScore
    latency: DimensionScore
    keyword_action_hits: int
    forbidden_tool_hits: List[str] = field(default_factory=list)
    missing_required_tools: List[str] = field(default_factory=list)


def score_tool_selection(case: EvalCase, recorder: CallRecorder) -> tuple[DimensionScore, List[str], List[str]]:
    called = set(recorder.tool_names_called())
    valid_matched_called = {
        c.tool_name for c in recorder.calls
        if c.matched and c.argument_valid
    }
    required = case.expected.required_tools
    forbidden = case.expected.forbidden_tools

    if required:
        hit = sum(1 for t in required if t in valid_matched_called)
        missing = [t for t in required if t not in valid_matched_called]
        recall = hit / len(required)
    else:
        missing = []
        recall = 1.0

    forbidden_hits = [t for t in forbidden if t in called]
    penalty_per_hit = 0.5  # half the dimension per forbidden call (capped to 1.0)
    penalty = min(1.0, len(forbidden_hits) * penalty_per_hit)

    score_ratio = max(0.0, recall - penalty)
    score = score_ratio * WEIGHT_TOOL_SELECTION
    detail = (
        f"required={len(required)}, hit={len(required) - len(missing)}, "
        f"missing={missing or '∅'}, forbidden_hits={forbidden_hits or '∅'}, "
        f"invalid_args={recorder.invalid_argument_count()}"
    )
    return DimensionScore("tool_selection", score, WEIGHT_TOOL_SELECTION, detail), missing, forbidden_hits


def score_structure(case: EvalCase, conclusion_md: str) -> DimensionScore:
    text = conclusion_md or ""
    must = case.expected.conclusion_must_contain
    must_not = case.expected.conclusion_must_not_contain

    if must:
        hits = sum(1 for s in must if s in text)
        ratio = hits / len(must)
    else:
        ratio = 1.0

    forbidden_hits = [s for s in must_not if s in text]
    penalty = min(1.0, len(forbidden_hits) * 0.34)
    ratio = max(0.0, ratio - penalty)
    score = ratio * WEIGHT_STRUCTURE
    detail = (
        f"must_contain hits={hits if must else 0}/{len(must)}, "
        f"must_not_contain hits={forbidden_hits or '∅'}"
    )
    return DimensionScore("structure", score, WEIGHT_STRUCTURE, detail)


def score_evidence(recorder: CallRecorder, conclusion_md: str) -> DimensionScore:
    """Heuristic: check whether the conclusion references data that came back from
    tools. We look for at least 3 numeric tokens or quoted strings, plus that
    the AI made >=1 tool call. This is a coarse check — real evidence_refs
    structure isn't always populated for streaming sessions.
    """
    if not recorder.calls:
        return DimensionScore("evidence", 0.0, WEIGHT_EVIDENCE, "no tool calls made")

    text = conclusion_md or ""
    import re as _re
    numeric_tokens = _re.findall(r"\b\d{2,}(?:[.,]\d+)?\b", text)
    quoted_tokens = _re.findall(r"`[^`]+`", text)
    sql_tokens = _re.findall(r"```[\s\S]*?```", text)
    signal = len(numeric_tokens) + len(quoted_tokens) * 2 + len(sql_tokens) * 3
    ratio = min(1.0, signal / 8.0)
    return DimensionScore(
        "evidence", ratio * WEIGHT_EVIDENCE, WEIGHT_EVIDENCE,
        f"signals={signal} (numeric={len(numeric_tokens)}, quoted={len(quoted_tokens)}, sql={len(sql_tokens)})",
    )


def score_efficiency(case: EvalCase, recorder: CallRecorder) -> DimensionScore:
    rounds = len(recorder.calls)
    min_r = case.expected.min_tool_rounds
    max_r = case.expected.max_tool_rounds

    if rounds < min_r:
        # too few — likely not enough investigation
        ratio = max(0.0, rounds / max(1, min_r)) * 0.6
        detail = f"only {rounds} tool calls, expected at least {min_r}"
    elif rounds <= max_r:
        ratio = 1.0
        detail = f"{rounds} tool calls (within {min_r}-{max_r})"
    else:
        # over budget — linearly degrade until 2x max
        overage = rounds - max_r
        ratio = max(0.2, 1.0 - overage / max(1, max_r))
        detail = f"{rounds} tool calls, exceeded max {max_r} (overage={overage})"

    return DimensionScore("efficiency", ratio * WEIGHT_EFFICIENCY, WEIGHT_EFFICIENCY, detail)


def score_latency(latency_ms: int) -> DimensionScore:
    # 60s = full marks; 180s = zero. Linear in between.
    seconds = latency_ms / 1000.0
    if seconds <= 60:
        ratio = 1.0
    elif seconds >= 180:
        ratio = 0.0
    else:
        ratio = 1.0 - (seconds - 60) / 120.0
    return DimensionScore("latency", ratio * WEIGHT_LATENCY, WEIGHT_LATENCY, f"{seconds:.1f}s")


def score_action_keywords(case: EvalCase, conclusion_md: str) -> tuple[int, int, str]:
    """Returns (hits, total, detail). Used to gate judge-action-score."""
    text = conclusion_md or ""
    total = len(case.expected.required_actions)
    hits = 0
    detail_parts = []
    for entry in case.expected.required_actions:
        keywords = entry.get("keywords") or []
        if not keywords:
            continue
        if all(kw.lower() in text.lower() for kw in keywords):
            hits += 1
            detail_parts.append(f"✓ {keywords}")
        else:
            detail_parts.append(f"✗ {keywords}")
    return hits, total, "; ".join(detail_parts) if detail_parts else "no required_actions"


def compute_programmatic(
    case: EvalCase,
    recorder: CallRecorder,
    conclusion_md: str,
    latency_ms: int,
) -> ProgrammaticBreakdown:
    tool_dim, missing, forbidden_hits = score_tool_selection(case, recorder)
    structure_dim = score_structure(case, conclusion_md)
    evidence_dim = score_evidence(recorder, conclusion_md)
    efficiency_dim = score_efficiency(case, recorder)
    latency_dim = score_latency(latency_ms)
    kw_hits, _, _ = score_action_keywords(case, conclusion_md)
    return ProgrammaticBreakdown(
        tool_selection=tool_dim,
        structure=structure_dim,
        evidence=evidence_dim,
        efficiency=efficiency_dim,
        latency=latency_dim,
        keyword_action_hits=kw_hits,
        forbidden_tool_hits=forbidden_hits,
        missing_required_tools=missing,
    )


def combine_scores(
    programmatic: ProgrammaticBreakdown,
    judge_root_cause: float,    # 0..WEIGHT_ROOT_CAUSE
    judge_action: float,        # 0..WEIGHT_ACTION
) -> tuple[float, List[Dict[str, Any]]]:
    dims = [
        DimensionScore("root_cause", judge_root_cause, WEIGHT_ROOT_CAUSE, "LLM judge"),
        programmatic.tool_selection,
        DimensionScore("action_quality", judge_action, WEIGHT_ACTION, "LLM judge + keyword gate"),
        programmatic.structure,
        programmatic.evidence,
        programmatic.efficiency,
        programmatic.latency,
    ]
    total = sum(d.score for d in dims)
    return round(total, 2), [d.to_dict() for d in dims]
