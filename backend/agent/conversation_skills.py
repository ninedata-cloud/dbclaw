"""
Updated conversation module to use dynamic skill system
"""
import json
import logging
import re
from typing import AsyncGenerator, List, Dict, Any, Optional

from backend.agent.prompts import DIAGNOSTIC_PROMPT, INFORMATIONAL_PROMPT, ADMINISTRATIVE_PROMPT
from backend.agent.intent_detector import detect_query_intent
from backend.agent.skill_selector import get_available_skills_as_tools
from backend.services.ai_agent import get_ai_client, stream_assistant_turn
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 30

READ_ONLY_SQL_KEYWORDS = {'SELECT', 'SHOW', 'EXPLAIN', 'EXEC', 'EXECUTE', 'DESCRIBE', 'DESC', 'WITH'}
DANGEROUS_SQL_KEYWORDS = {'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE', 'GRANT', 'REVOKE', 'CALL'}
DANGEROUS_COMMAND_PATTERNS = [
    'rm ', 'rmdir', 'del ', 'delete',
    'mv ', 'move',
    'chmod', 'chown', 'chgrp',
    'kill', 'pkill', 'killall',
    'shutdown', 'reboot', 'halt', 'poweroff',
    'mkfs', 'fdisk', 'parted',
    'dd ',
    'iptables', 'firewall',
    'useradd', 'userdel', 'usermod',
    'groupadd', 'groupdel',
    '>>', 'tee',
    'wget', 'curl -o', 'curl -O',
    'apt install', 'yum install', 'dnf install',
    'systemctl stop', 'systemctl start', 'systemctl restart',
    'service stop', 'service start', 'service restart',
]
READ_ONLY_COMMAND_HINTS = [
    'df', 'du', 'free', 'ps', 'top', 'htop', 'iostat', 'vmstat', 'sar', 'ss', 'netstat',
    'journalctl', 'tail', 'cat', 'uptime', 'hostname', 'lsblk', 'mount', 'dmesg', 'sysctl',
]


def _normalize_sql_keyword(sql: str) -> str:
    query = (sql or '').strip().lstrip('(')
    match = re.match(r'([A-Za-z]+)', query)
    return match.group(1).upper() if match else ''


def _get_command_arg(arguments: Dict[str, Any]) -> str:
    return str(arguments.get('command') or arguments.get('cmd') or arguments.get('shell_command') or '').strip()


def build_confirmation_reason(tool_name: str, arguments: Dict[str, Any], risk_level: str) -> str:
    command = _get_command_arg(arguments)
    sql = str(arguments.get('sql') or '').strip()

    if command:
        if risk_level == 'destructive':
            return f"该命令可能直接修改主机状态或中断服务：`{command}`"
        return f"该命令具备修改主机状态的风险，需要确认后再执行：`{command}`"
    if sql:
        if risk_level == 'destructive':
            return f"该 SQL 可能直接修改或破坏数据库对象/数据：`{sql[:120]}`"
        return f"该 SQL 可能修改数据库状态，需要确认后再执行：`{sql[:120]}`"
    return f"技能 `{tool_name}` 具备潜在变更能力，需要确认后再执行。"


def assess_tool_risk(tool_name: str, arguments: Dict[str, Any], permissions: Optional[List[str]] = None) -> Dict[str, Any]:
    permissions = permissions or []
    command = _get_command_arg(arguments)
    sql = str(arguments.get('sql') or '').strip()
    keyword = _normalize_sql_keyword(sql)

    if command:
        command_lower = command.lower()
        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if pattern in command_lower:
                destructive_patterns = {'rm ', 'rmdir', 'del ', 'delete', 'shutdown', 'reboot', 'halt', 'poweroff', 'mkfs', 'fdisk', 'parted', 'dd '}
                level = 'destructive' if pattern in destructive_patterns else 'high'
                return {
                    'level': level,
                    'requires_confirmation': False,
                    'risk_reason': build_confirmation_reason(tool_name, arguments, level),
                    'suppressible': level != 'destructive',
                    'confirmation_key': 'os_destructive' if level == 'destructive' else 'os_write',
                }

        is_read_only_permission = 'execute_any_os_command' not in permissions
        looks_read_only = any(command_lower.startswith(f'{hint} ') or command_lower == hint or f'| {hint}' in command_lower for hint in READ_ONLY_COMMAND_HINTS)
        if is_read_only_permission or looks_read_only:
            return {
                'level': 'safe',
                'requires_confirmation': False,
                'risk_reason': '这是只读 OS 诊断命令，不会修改主机状态。',
                'suppressible': False,
                'confirmation_key': 'os_readonly',
            }

        return {
            'level': 'high',
            'requires_confirmation': False,
            'risk_reason': build_confirmation_reason(tool_name, arguments, 'high'),
            'suppressible': True,
            'confirmation_key': 'os_write',
        }

    if sql:
        if keyword in DANGEROUS_SQL_KEYWORDS:
            level = 'destructive' if keyword in {'DROP', 'TRUNCATE'} else 'high'
            return {
                'level': level,
                'requires_confirmation': False,
                'risk_reason': build_confirmation_reason(tool_name, arguments, level),
                'suppressible': level != 'destructive',
                'confirmation_key': 'sql_destructive' if level == 'destructive' else 'sql_write',
            }

        is_read_only_permission = 'execute_any_sql' not in permissions
        if keyword in READ_ONLY_SQL_KEYWORDS or is_read_only_permission:
            return {
                'level': 'safe',
                'requires_confirmation': False,
                'risk_reason': '这是只读 SQL 诊断查询，不会修改数据库状态。',
                'suppressible': False,
                'confirmation_key': 'sql_readonly',
            }

        return {
            'level': 'high',
            'requires_confirmation': False,
            'risk_reason': build_confirmation_reason(tool_name, arguments, 'high'),
            'suppressible': True,
            'confirmation_key': 'sql_write',
        }

    if 'execute_any_sql' in permissions:
        return {
            'level': 'high',
            'requires_confirmation': False,
            'risk_reason': build_confirmation_reason(tool_name, arguments, 'high'),
            'suppressible': True,
            'confirmation_key': 'sql_write',
        }
    if 'execute_any_os_command' in permissions:
        return {
            'level': 'high',
            'requires_confirmation': False,
            'risk_reason': build_confirmation_reason(tool_name, arguments, 'high'),
            'suppressible': True,
            'confirmation_key': 'os_write',
        }

    return {
        'level': 'safe',
        'requires_confirmation': False,
        'risk_reason': '这是只读诊断步骤。',
        'suppressible': False,
        'confirmation_key': 'generic_readonly',
    }


async def execute_skill_call(
    skill_id: str, arguments: Dict[str, Any], db, user_id: int, session_id: Optional[int] = None
) -> tuple[str, int, Optional[int]]:
    """Execute a skill and return JSON result, execution time, and skill_execution_id."""
    from backend.skills.registry import SkillRegistry
    from backend.skills.executor import SkillExecutor
    from backend.skills.context import SkillContext
    from backend.skills.models import SkillExecution
    from sqlalchemy import select
    import time

    start_time = time.time()

    async def _get_latest_execution_id() -> Optional[int]:
        if not db:
            return None
        query = (
            select(SkillExecution.id)
            .where(SkillExecution.skill_id == skill_id)
            .order_by(SkillExecution.id.desc())
            .limit(1)
        )
        if session_id is not None:
            query = query.where(SkillExecution.session_id == session_id)
        if user_id is not None:
            query = query.where(SkillExecution.user_id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    try:
        timeout = arguments.pop('timeout', None)
        if timeout:
            timeout = max(30, min(int(timeout), 3600))

        registry = SkillRegistry(db)
        skill = await registry.get_skill(skill_id)

        if not skill:
            execution_time = int((time.time() - start_time) * 1000)
            return json.dumps({"error": f"Skill '{skill_id}' not found"}), execution_time, None

        if not skill.is_enabled:
            execution_time = int((time.time() - start_time) * 1000)
            return json.dumps({"error": f"Skill '{skill_id}' is disabled"}), execution_time, None

        from backend.skills.executor import SkillExecutor
        if timeout is None:
            timeout = skill.timeout if skill.timeout else SkillExecutor.DEFAULT_TIMEOUT
        timeout = min(timeout, SkillExecutor.MAX_TIMEOUT)

        context = SkillContext(
            db=db,
            user_id=user_id,
            session_id=session_id,
            permissions=skill.permissions or [],
            timeout=timeout,
        )

        executor = SkillExecutor()
        result = await executor.execute(skill, arguments, context, timeout=timeout)

        execution_time = int((time.time() - start_time) * 1000)
        execution_id = await _get_latest_execution_id()
        return json.dumps(result, default=str), execution_time, execution_id

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        logger.error(f"Error executing skill {skill_id}: {e}")
        execution_id = await _get_latest_execution_id()
        return json.dumps({"error": str(e)}), execution_time, execution_id


async def run_conversation_with_skills(
    messages: List[Dict[str, Any]],
    datasource_id: Optional[int] = None,
    model_id: Optional[int] = None,
    kb_ids: Optional[List[int]] = None,
    db: Optional[Any] = None,
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
    disabled_tools: Optional[List[str]] = None,
    system_prompt_override: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run the AI conversation loop with dynamic skill calling and streaming."""
    from backend.models.ai_model import AIModel
    from backend.routers.ai_models import decrypt_api_key

    from sqlalchemy import select
    client = None
    if model_id and db:
        result = await db.execute(select(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True))
        model = result.scalar_one_or_none()
        if model:
            client = get_ai_client(
                api_key=decrypt_api_key(model.api_key_encrypted),
                base_url=model.base_url,
                model_name=model.model_name,
                protocol=getattr(model, "protocol", "openai"),
            )
    if not client and db:
        result = await db.execute(select(AIModel).filter(AIModel.is_active == True))
        model = result.scalars().first()
        if model:
            client = get_ai_client(
                api_key=decrypt_api_key(model.api_key_encrypted),
                base_url=model.base_url,
                model_name=model.model_name,
                protocol=getattr(model, "protocol", "openai"),
            )
    if not client:
        client = get_ai_client()

    if not client:
        yield {"type": "error", "message": "AI model not configured. Please add an AI model in the AI Model Management page."}
        return

    first_user_message = next((msg['content'] for msg in messages if msg['role'] == 'user'), '')
    if isinstance(first_user_message, list):
        intent_text = " ".join(p.get("text", "") for p in first_user_message if isinstance(p, dict) and p.get("type") == "text")
    else:
        intent_text = first_user_message
    intent = detect_query_intent(intent_text)

    if system_prompt_override:
        system_msg = system_prompt_override
    elif intent == 'diagnostic':
        system_msg = DIAGNOSTIC_PROMPT
    elif intent == 'administrative':
        system_msg = ADMINISTRATIVE_PROMPT
    else:
        system_msg = INFORMATIONAL_PROMPT

    datasource_db_type = None
    host_configured_for_tools = None

    if datasource_id and db:
        from backend.models.datasource import Datasource
        from backend.models.host import Host
        from sqlalchemy import select
        result = await db.execute(select(Datasource).filter(Datasource.id == datasource_id))
        datasource = result.scalar_one_or_none()
        if datasource:
            datasource_db_type = datasource.db_type
            host_id = datasource.host_id
            host_configured = host_id is not None
            host_configured_for_tools = host_configured

            skill_prefix_map = {
                'mysql': 'mysql',
                'postgresql': 'pg',
                'sqlserver': 'mssql',
                'oracle': 'oracle',
                'opengauss': 'opengauss',
                'tidb': 'tidb',
                'dm': 'dm',
                'oceanbase': 'oceanbase',
                'oceanbase_mysql': 'oceanbase',
            }
            skill_prefix = skill_prefix_map.get(datasource.db_type, datasource.db_type)

            system_msg += (
                "\n\nCurrent conversation datasource context (stable unless the user explicitly asks to switch):"
                f"\n- datasource_id: {datasource_id}"
                f"\n- datasource_type: {datasource.db_type}"
                f"\n- datasource_name: {datasource.name}"
                f"\n- host_id: {host_id if host_id is not None else 'None'}"
                f"\n- host_configured: {str(host_configured).lower()}"
            )
            system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id} (Type: {datasource.db_type.upper()}, Name: {datasource.name}). Use this ID when calling tools unless they specify otherwise."
            system_msg += f"\n\nIMPORTANT: This is a {datasource.db_type.upper()} database. You MUST use {skill_prefix}_* skills (e.g., {skill_prefix}_get_db_status, {skill_prefix}_get_slow_queries, {skill_prefix}_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type. Unless the user explicitly asks to switch datasources, keep all diagnosis and tool calls scoped to this datasource."

            if datasource.remark:
                system_msg += (
                    f"\n\n**数据源备注**：{datasource.remark}"
                    "\n此备注包含该数据源的业务背景、特殊配置或已知问题等重要上下文信息，诊断时请结合此备注进行分析。"
                )

            if host_id:
                host_result = await db.execute(select(Host).filter(Host.id == host_id))
                host = host_result.scalar_one_or_none()
                host_info = f" (Host: {host.name or host.host})" if host else ""
                system_msg += f"\n\n**主机连接已配置**：该数据源已关联主机{host_info}，host_id={host_id}。你可以使用 OS 层面的诊断技能（get_os_metrics、diagnose_high_cpu、diagnose_high_memory、diagnose_disk_space、diagnose_disk_io、diagnose_network）进行操作系统级别的深度分析。遇到性能问题时，应同时从数据库和操作系统两个层面进行诊断。"
            else:
                system_msg += "\n\n**注意**：该数据源未配置主机连接，host_id=None，无法进行操作系统层面的诊断（如 CPU、内存、磁盘、网络分析）。如需 OS 级别诊断，请建议用户在数据源配置中关联主机。"
        else:
            system_msg += (
                f"\n\nCurrent conversation datasource context (stable unless the user explicitly asks to switch):"
                f"\n- datasource_id: {datasource_id}"
                f"\n- datasource_type: unknown"
                f"\n- host_id: unknown"
                f"\n- host_configured: unknown"
            )
            system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id}. Use this ID when calling tools unless they specify otherwise."
    elif datasource_id:
        system_msg += (
            f"\n\nCurrent conversation datasource context (stable unless the user explicitly asks to switch):"
            f"\n- datasource_id: {datasource_id}"
            f"\n- datasource_type: unknown"
            f"\n- host_id: unknown"
            f"\n- host_configured: unknown"
        )
        system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id}. Use this ID when calling tools unless they specify otherwise."

    if kb_ids:
        system_msg += f"\n\nKnowledge bases are enabled for this session (IDs: {kb_ids}). Use list_documents tool to browse available documentation, then read_document to fetch full content."

    active_tools = await get_available_skills_as_tools(
        db,
        disabled_tools,
        datasource_db_type=datasource_db_type,
        host_configured=host_configured_for_tools,
    )
    disabled_set = set(disabled_tools) if disabled_tools else set()
    full_messages = [{"role": "system", "content": system_msg}] + messages

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            collected_content = ""
            collected_tool_calls = []
            round_usage = None

            async for event in stream_assistant_turn(
                client,
                full_messages,
                tools=active_tools,
                tool_choice="auto",
            ):
                if event["type"] == "content":
                    collected_content += event["content"]
                    yield {"type": "content", "content": event["content"]}
                elif event["type"] == "message_complete":
                    collected_tool_calls = event.get("tool_calls", [])
                    round_usage = event.get("usage")
                    if round_usage:
                        yield {"type": "usage", "usage": round_usage}
                    if event.get("stop_reason") == "end_turn" and not collected_tool_calls:
                        yield {"type": "done", "content": collected_content}
                        return

            if not collected_tool_calls:
                yield {"type": "done", "content": collected_content}
                return

            assistant_msg = {"role": "assistant", "content": collected_content or None, "tool_calls": collected_tool_calls}
            full_messages.append(assistant_msg)

            for tc in collected_tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                if tool_name in disabled_set:
                    tool_result = json.dumps({"error": f"Tool '{tool_name}' is disabled for this session by the user."})
                    yield {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_call_id": tc["id"],
                    }
                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "tool_call_id": tc["id"],
                        "result": tool_result,
                        "execution_time_ms": 0,
                    }
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })
                    continue

                from backend.skills.registry import SkillRegistry
                skill = await SkillRegistry(db).get_skill(tool_name) if db else None
                risk = assess_tool_risk(tool_name, tool_args, getattr(skill, 'permissions', None))

                yield {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_call_id": tc["id"],
                }

                tool_result, execution_time_ms, skill_execution_id = await execute_skill_call(
                    tool_name, tool_args, db, user_id, session_id
                )

                yield {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": tc["id"],
                    "result": tool_result[:10000],
                    "execution_time_ms": execution_time_ms,
                    "skill_execution_id": skill_execution_id,
                }

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        except Exception as e:
            logger.error(f"Conversation error at round {round_num}: {e}")
            yield {"type": "error", "message": f"Error: {str(e)}"}
            return

    yield {
        "type": "error",
        "message": (
            f"Maximum tool execution rounds ({MAX_TOOL_ROUNDS}) reached. "
            "The diagnosis may be too complex or requires manual intervention. "
            "Please try breaking down your question into smaller parts."
        ),
    }


def _strip_markdown_for_summary(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"```[\s\S]*?```", " ", text)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _sanitize_report_markdown(content_md: str) -> str:
    if not content_md:
        return ""

    normalized = content_md.replace("\r\n", "\n").strip()
    if not normalized:
        return ""

    report_heading_markers = [
        "# 数据库巡检报告",
        "# 数据库诊断报告",
        "# 数据库连接失败诊断报告",
        "## 一、执行摘要",
        "## 执行摘要",
    ]

    start_index = -1
    for marker in report_heading_markers:
        idx = normalized.find(marker)
        if idx >= 0 and (start_index < 0 or idx < start_index):
            start_index = idx

    if start_index > 0:
        normalized = normalized[start_index:].lstrip()

    filtered_lines = []
    process_line_patterns = [
        r"^我将为.+生成.+报告",
        r"^让我先",
        r"^我先收集",
        r"^继续收集",
        r"^现在我已经收集了足够的数据",
        r"^现在我已经收集了足够的诊断数据",
        r"^下面(开始)?生成",
        r"^接下来我将",
        r"^继续调用",
    ]

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            filtered_lines.append(raw_line)
            continue
        if any(re.match(pattern, line) for pattern in process_line_patterns):
            continue
        filtered_lines.append(raw_line)

    sanitized = "\n".join(filtered_lines).strip()
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    return sanitized


def _has_meaningful_report_content(content_md: str) -> bool:
    plain = _strip_markdown_for_summary(_sanitize_report_markdown(content_md))
    if not plain:
        return False

    if plain.startswith("⚠️"):
        return False

    lower_plain = plain.lower()
    for fragment in ["未生成任何内容", "报告生成超时", "报告生成失败", "需要人工确认"]:
        if fragment in plain:
            return False
    if "timeout" in lower_plain and len(plain) < 120:
        return False

    return len(plain) >= 40


def _build_report_summary(content_md: str) -> str:
    plain = _strip_markdown_for_summary(_sanitize_report_markdown(content_md))
    return plain[:220].strip() if plain else ""


async def generate_report_with_skills(
    datasource_id: int,
    datasource_name: str,
    datasource_type: str,
    trigger_reason: str,
    system_prompt: str,
    db: Any,
    user_id: int = 1,
    model_id: Optional[int] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Generate inspection report using AI with skill calls.

    Returns a structured result:
    {
      status: completed|partial|timed_out|awaiting_confirm|failed,
      content_md,
      summary,
      error_message,
      skill_executions,
    }
    """
    import asyncio

    skill_executions: list[dict[str, Any]] = []
    collected_content = ""

    error_message: Optional[str] = None

    # Check if datasource has host configured for OS-level analysis
    host_info_msg = ""
    try:
        from backend.models.datasource import Datasource
        from backend.models.host import Host
        from sqlalchemy import select

        ds_result = await db.execute(select(Datasource).filter(Datasource.id == datasource_id))
        ds = ds_result.scalar_one_or_none()
        if ds and ds.host_id:
            host_result = await db.execute(select(Host).filter(Host.id == ds.host_id))
            host = host_result.scalar_one_or_none()
            host_name = host.name or host.host if host else "unknown"
            host_info_msg = f"""
- 主机连接：已配置（主机：{host_name}）
- **重要**：该数据源已关联主机，请务必使用 OS 诊断技能（get_os_metrics、diagnose_high_cpu、diagnose_high_memory、diagnose_disk_space、diagnose_disk_io、diagnose_network）收集操作系统层面数据，并在报告中包含完整的"操作系统资源分析"章节。"""
        else:
            host_info_msg = "\n- 主机连接：未配置（无法进行操作系统层面分析，请在报告中注明）"
    except Exception as e:
        logger.warning(f"Failed to check host config for report: {e}")

    initial_message = f"""请为以下数据库生成一份全面的巡检报告：
- 数据库名称：{datasource_name} ({datasource_type})
- 数据源 ID：{datasource_id}
- 触发原因：{trigger_reason}{host_info_msg}

请使用技能收集数据，并按照专业 DBA 报告的标准格式撰写完整的中文报告。"""

    messages = [{"role": "user", "content": initial_message}]

    saw_done = False
    saw_error = False

    try:
        async with asyncio.timeout(timeout_seconds):
            async for event in run_conversation_with_skills(
                messages=messages,
                datasource_id=datasource_id,
                model_id=model_id,
                db=db,
                user_id=user_id,
                system_prompt_override=system_prompt,
            ):
                etype = event.get("type")

                if etype == "content":
                    collected_content += event.get("content") or ""
                    continue

                if etype == "tool_call":
                    skill_executions.append({
                        "skill_id": event.get("tool_name"),
                        "arguments": event.get("tool_args"),
                        "timestamp": now().isoformat(),
                    })
                    continue

                if etype == "error":
                    saw_error = True
                    error_message = str(event.get("message") or event.get("content") or "Unknown error")
                    break

                if etype == "done":
                    saw_done = True
                    break

    except asyncio.TimeoutError:
        status = "timed_out"
        sanitized_content = _sanitize_report_markdown(collected_content)
        if sanitized_content.strip() and _has_meaningful_report_content(sanitized_content):
            summary = _build_report_summary(sanitized_content)
            error_message = f"报告生成超时（{timeout_seconds}s），以上为部分结果。"
            return {
                "status": status,
                "content_md": sanitized_content,
                "summary": summary or "报告生成超时（部分结果）",
                "error_message": error_message,
                "skill_executions": skill_executions,
            }

        return {
            "status": status,
            "content_md": "",
            "summary": "报告生成超时，未产出正文。",
            "error_message": f"报告生成超时（{timeout_seconds}s），未能获取到任何内容。",
            "skill_executions": skill_executions,
        }

    except Exception as e:
        error_message = f"{type(e).__name__}: {str(e)}"
        saw_error = True

    if saw_error:
        sanitized_content = _sanitize_report_markdown(collected_content)
        if sanitized_content.strip() and _has_meaningful_report_content(sanitized_content):
            return {
                "status": "partial",
                "content_md": sanitized_content,
                "summary": _build_report_summary(sanitized_content) or "报告生成部分成功",
                "error_message": error_message or "报告生成过程中出错，已返回部分内容。",
                "skill_executions": skill_executions,
            }

        return {
            "status": "failed",
            "content_md": "",
            "summary": "报告生成失败，未产出有效内容。",
            "error_message": error_message or "报告生成失败（未产出有效内容）。",
            "skill_executions": skill_executions,
        }

    # Normal completion
    sanitized_content = _sanitize_report_markdown(collected_content)

    if not saw_done:
        # Defensive: stream ended without done/error/confirm
        if sanitized_content.strip() and _has_meaningful_report_content(sanitized_content):
            return {
                "status": "partial",
                "content_md": sanitized_content,
                "summary": _build_report_summary(sanitized_content) or "报告生成部分成功",
                "error_message": "对话流提前结束，已返回部分内容。",
                "skill_executions": skill_executions,
            }
        return {
            "status": "failed",
            "content_md": "",
            "summary": "报告生成失败，未产出有效内容。",
            "error_message": "对话流提前结束，未生成任何有效内容。",
            "skill_executions": skill_executions,
        }

    if not sanitized_content.strip() or not _has_meaningful_report_content(sanitized_content):
        return {
            "status": "failed",
            "content_md": "",
            "summary": "报告生成失败，未产出有效内容。",
            "error_message": "AI 未生成任何有效报告内容。",
            "skill_executions": skill_executions,
        }

    return {
        "status": "completed",
        "content_md": sanitized_content,
        "summary": _build_report_summary(sanitized_content) or "报告生成完成",
        "error_message": None,
        "skill_executions": skill_executions,
    }
