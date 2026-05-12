"""Load YAML evaluation cases from disk."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

CASES_DIR = Path(__file__).parent / "cases"
DEFAULT_EVAL_DATASOURCE_ID = 900001
DEFAULT_EVAL_HOST_ID = 900101
DEFAULT_PORT_BY_DB_TYPE = {
    "mysql": 3306,
    "tdsql-c-mysql": 3306,
    "postgresql": 5432,
    "oracle": 1521,
    "sqlserver": 1433,
    "opengauss": 5432,
    "hana": 30015,
}


OS_CONTEXT_TOOLS = {
    "get_os_metrics",
    "execute_os_command",
    "execute_any_os_command",
    "diagnose_high_cpu",
    "diagnose_high_memory",
    "diagnose_disk_space",
    "diagnose_disk_io",
    "diagnose_network",
}


@dataclass
class FixtureRule:
    tool: str
    args: Any  # "any" | dict (exact match) | dict with sql_pattern (regex)
    response: Any


@dataclass
class CaseExpected:
    required_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    min_tool_rounds: int = 1
    max_tool_rounds: int = 10
    root_causes: List[str] = field(default_factory=list)
    required_actions: List[Dict[str, Any]] = field(default_factory=list)
    conclusion_must_contain: List[str] = field(default_factory=list)
    conclusion_must_not_contain: List[str] = field(default_factory=list)


@dataclass
class EvalDatasourceContext:
    id: int = DEFAULT_EVAL_DATASOURCE_ID
    name: str = "eval-mysql-primary"
    db_type: str = "mysql"
    host: str = "10.90.0.11"
    port: int = 3306
    database: Optional[str] = "app"
    version: Optional[str] = None
    remark: Optional[str] = "Evaluation-only virtual datasource. Do not assume access to real assets."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "db_type": self.db_type,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "version": self.version,
            "remark": self.remark,
        }


@dataclass
class EvalHostContext:
    id: int = DEFAULT_EVAL_HOST_ID
    name: str = "eval-db-host"
    address: str = "10.90.0.11"
    os_version: Optional[str] = "Linux 5.x"
    ssh_port: int = 22

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "os_version": self.os_version,
            "ssh_port": self.ssh_port,
        }


@dataclass
class EvalContext:
    datasource: EvalDatasourceContext
    host: Optional[EvalHostContext] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasource": self.datasource.to_dict(),
            "host": self.host.to_dict() if self.host else None,
        }


@dataclass
class EvalCase:
    id: str
    category: str
    db_type: str
    title: str
    user_message: str
    fixtures: List[FixtureRule]
    expected: CaseExpected
    description: Optional[str] = None
    difficulty: str = "medium"
    file_path: Optional[str] = None
    context: EvalContext = field(default_factory=lambda: EvalContext(EvalDatasourceContext()))


def _case_needs_host(fixtures: List[FixtureRule], expected: CaseExpected) -> bool:
    tools = {f.tool for f in fixtures}
    tools.update(expected.required_tools)
    return bool(tools.intersection(OS_CONTEXT_TOOLS))


def _parse_context(raw: Dict[str, Any], db_type: str, fixtures: List[FixtureRule], expected: CaseExpected) -> EvalContext:
    ctx_raw = raw.get("context") or {}
    ds_raw = ctx_raw.get("datasource") or {}
    host_raw = ctx_raw.get("host", None)

    datasource = EvalDatasourceContext(
        id=int(ds_raw.get("id", DEFAULT_EVAL_DATASOURCE_ID)),
        name=str(ds_raw.get("name") or f"eval-{db_type}-primary"),
        db_type=str(ds_raw.get("db_type") or db_type),
        host=str(ds_raw.get("host") or "10.90.0.11"),
        port=int(ds_raw.get("port", DEFAULT_PORT_BY_DB_TYPE.get(db_type, 3306))),
        database=ds_raw.get("database", "app"),
        version=ds_raw.get("version"),
        remark=ds_raw.get("remark", "Evaluation-only virtual datasource. Do not assume access to real assets."),
    )

    if host_raw is False or host_raw is None and not _case_needs_host(fixtures, expected):
        host = None
    else:
        host_data = host_raw if isinstance(host_raw, dict) else {}
        host = EvalHostContext(
            id=int(host_data.get("id", DEFAULT_EVAL_HOST_ID)),
            name=str(host_data.get("name") or "eval-db-host"),
            address=str(host_data.get("address") or datasource.host),
            os_version=host_data.get("os_version", "Linux 5.x"),
            ssh_port=int(host_data.get("ssh_port", 22)),
        )

    return EvalContext(datasource=datasource, host=host)


def _parse_case(raw: Dict[str, Any], file_path: Optional[Path]) -> EvalCase:
    fixtures = [
        FixtureRule(
            tool=f["tool"],
            args=f.get("args", "any"),
            response=f.get("response"),
        )
        for f in raw.get("fixtures") or []
    ]
    exp_raw = raw.get("expected") or {}
    expected = CaseExpected(
        required_tools=list(exp_raw.get("required_tools") or []),
        forbidden_tools=list(exp_raw.get("forbidden_tools") or []),
        min_tool_rounds=int(exp_raw.get("min_tool_rounds", 1)),
        max_tool_rounds=int(exp_raw.get("max_tool_rounds", 10)),
        root_causes=list(exp_raw.get("root_causes") or []),
        required_actions=list(exp_raw.get("required_actions") or []),
        conclusion_must_contain=list(exp_raw.get("conclusion_must_contain") or []),
        conclusion_must_not_contain=list(exp_raw.get("conclusion_must_not_contain") or []),
    )
    db_type = raw.get("db_type", "mysql")
    context = _parse_context(raw, db_type, fixtures, expected)
    return EvalCase(
        id=raw["id"],
        category=raw.get("category", "uncategorized"),
        db_type=db_type,
        title=raw.get("title") or raw["id"],
        user_message=raw["user_message"],
        fixtures=fixtures,
        expected=expected,
        description=raw.get("description"),
        difficulty=raw.get("difficulty", "medium"),
        file_path=str(file_path) if file_path else None,
        context=context,
    )


_cache: Optional[Dict[str, EvalCase]] = None


def load_all_cases(force_reload: bool = False) -> Dict[str, EvalCase]:
    """Walk CASES_DIR and parse every *.yaml file. Cached after first load."""
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    cases: Dict[str, EvalCase] = {}
    if not CASES_DIR.exists():
        _cache = cases
        return cases

    for path in sorted(CASES_DIR.rglob("*.yaml")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not raw:
                continue
            case = _parse_case(raw, path)
            if case.id in cases:
                logger.warning("Duplicate case id %s in %s", case.id, path)
            cases[case.id] = case
        except Exception as exc:
            logger.error("Failed to load case %s: %s", path, exc)

    _cache = cases
    return cases


def get_case(case_id: str) -> Optional[EvalCase]:
    return load_all_cases().get(case_id)
