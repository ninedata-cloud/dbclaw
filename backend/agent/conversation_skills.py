"""
Updated conversation module to use dynamic skill system
"""
import asyncio
import json
import logging
import re
import uuid
from typing import AsyncGenerator, List, Dict, Any, Optional

from backend.agent.prompts import DIAGNOSTIC_PROMPT, INFORMATIONAL_PROMPT, ADMINISTRATIVE_PROMPT
from backend.agent.intent_detector import detect_query_intent
from backend.agent.skill_selector import get_available_skills_as_tools
from backend.agent.tools import get_filtered_tools
from backend.agent.context_builder import execute_tool
from backend.services.ai_agent import get_ai_client, stream_assistant_turn, request_text_response
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 1000
# 单轮 AI API 调用超时（秒），防止 LLM 提供商 API 挂起导致会话卡死
STREAM_ROUND_TIMEOUT = 600
KB_TOOL_NAMES = {"list_documents", "read_document"}

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


_RISK_ASSESS_SYSTEM_PROMPT = """你是一个数据库运维安全审计专家。你的任务是判断给定的 SQL 语句或 OS 命令的风险等级。

风险等级定义：
- safe: 只读操作，不会修改任何数据或系统状态。例如 SELECT 查询、SHOW 命令、df/ps/top 等诊断命令。
- high: 可能修改数据或系统状态，但不会造成不可逆的破坏。例如 INSERT/UPDATE/DELETE、systemctl restart、chmod 等。
- destructive: 可能造成不可逆的数据丢失或系统破坏。例如 DROP TABLE、TRUNCATE、rm -rf、mkfs、shutdown 等。

判断规则：
1. 关注语句的实际语义，而非简单的关键词匹配。例如 `SELECT * FROM delete_log` 是安全的只读查询，虽然包含 "delete" 一词。
2. 存储过程/函数调用（CALL/EXEC）如果无法确定其内部行为，应判定为 high。
3. 带 WHERE 条件的 UPDATE/DELETE 比不带条件的风险更低，但仍为 high。
4. 不带 WHERE 的 DELETE/UPDATE 应判定为 destructive。

请严格以 JSON 格式返回，不要包含任何其他文字：
{"level": "safe|high|destructive", "reason": "简短的中文原因说明"}"""


async def _llm_assess_risk(client, sql: str = "", command: str = "") -> Optional[Dict[str, Any]]:
    """调用 LLM 判定 SQL/OS 命令的风险等级，返回 None 表示判定失败需 fallback。"""
    if not client:
        return None

    content_parts = []
    if sql:
        content_parts.append(f"SQL 语句：{sql[:500]}")
    if command:
        content_parts.append(f"OS 命令：{command[:500]}")
    if not content_parts:
        return None

    messages = [
        {"role": "system", "content": _RISK_ASSESS_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(content_parts)},
    ]

    try:
        response = await request_text_response(client, messages, temperature=0, max_tokens=128)
        # 提取 JSON（兼容 LLM 可能在 JSON 前后添加多余文字的情况）
        text = response.strip()
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            logger.warning(f"LLM risk assess response not valid JSON: {text[:200]}")
            return None
        parsed = json.loads(text[start:end + 1])
        level = parsed.get("level", "").lower()
        if level not in ("safe", "high", "destructive"):
            logger.warning(f"LLM risk assess returned unknown level: {level}")
            return None
        return {"level": level, "reason": parsed.get("reason", "")}
    except Exception as e:
        logger.warning(f"LLM risk assess failed, will fallback to keyword matching: {e}")
        return None


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


def _keyword_assess_risk(tool_name: str, arguments: Dict[str, Any], permissions: Optional[List[str]] = None) -> Dict[str, Any]:
    """基于关键词匹配的风险判定（fallback 方案）。"""
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


def _build_risk_dict_from_llm(llm_result: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """将 LLM 返回的风险判定结果转换为标准 risk dict。"""
    level = llm_result["level"]
    command = _get_command_arg(arguments)
    sql = str(arguments.get('sql') or '').strip()

    if command:
        if level == 'destructive':
            key = 'os_destructive'
        elif level == 'high':
            key = 'os_write'
        else:
            key = 'os_readonly'
    elif sql:
        if level == 'destructive':
            key = 'sql_destructive'
        elif level == 'high':
            key = 'sql_write'
        else:
            key = 'sql_readonly'
    else:
        key = 'generic_readonly'

    reason = llm_result.get("reason") or build_confirmation_reason(tool_name, arguments, level)

    return {
        'level': level,
        'requires_confirmation': False,
        'risk_reason': reason,
        'suppressible': level not in ('safe', 'destructive'),
        'confirmation_key': key,
    }


async def assess_tool_risk(tool_name: str, arguments: Dict[str, Any], permissions: Optional[List[str]] = None, client=None) -> Dict[str, Any]:
    """评估工具调用的风险等级。优先使用 LLM 判定，失败时 fallback 到关键词匹配。"""
    command = _get_command_arg(arguments)
    sql = str(arguments.get('sql') or '').strip()

    # 有 client 且存在 sql/command 时，优先走 LLM 判定
    if client and (sql or command):
        llm_result = await _llm_assess_risk(client, sql=sql, command=command)
        if llm_result:
            return _build_risk_dict_from_llm(llm_result, tool_name, arguments)
        logger.info("LLM risk assessment unavailable, falling back to keyword matching")

    return _keyword_assess_risk(tool_name, arguments, permissions)


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
    skip_approval: bool = False,
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

    # 阶段1: 意图检测
    yield {"type": "thinking_phase", "phase": "intent_detection", "message": "正在分析您的问题..."}
    intent = detect_query_intent(intent_text)

    intent_message_map = {
        "diagnostic": "检测到诊断意图，正在分析数据库问题...",
        "informational": "检测到查询意图，正在准备信息检索...",
        "administrative": "检测到操作意图，正在准备执行任务...",
    }
    yield {"type": "thinking_phase", "phase": "intent_detection", "message": intent_message_map.get(intent, "正在分析..."), "intent": intent}

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
        from backend.models.soft_delete import alive_filter
        from sqlalchemy import select
        result = await db.execute(select(Datasource).filter(Datasource.id == datasource_id, alive_filter(Datasource)))
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

            # 获取数据库版本信息
            db_version_info = ""
            if datasource.db_version:
                db_version_info = f"\n- db_version: {datasource.db_version}"

            # 获取主机详情
            host_os_info = ""
            host_ssh_port = ""
            host_name_for_display = ""
            if host_id:
                host_result = await db.execute(select(Host).filter(Host.id == host_id))
                host = host_result.scalar_one_or_none()
                if host:
                    host_name_for_display = host.name or host.host
                    if host.os_version:
                        host_os_info = f"\n- host_os_version: {host.os_version}"
                    if host.port:
                        host_ssh_port = f"\n- host_ssh_port: {host.port}"

            system_msg += (
                "\n\nCurrent conversation datasource context (stable unless the user explicitly asks to switch):"
                f"\n- datasource_id: {datasource_id}"
                f"\n- datasource_type: {datasource.db_type}"
                f"\n- datasource_name: {datasource.name}"
                f"\n- host_id: {host_id if host_id is not None else 'None'}"
                f"\n- host_configured: {str(host_configured).lower()}"
                f"\n- datasource_host: {datasource.host}"
                f"\n- datasource_port: {datasource.port}"
                f"{db_version_info}"
                f"{host_os_info}"
                f"{host_ssh_port}"
            )
            system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id} (Type: {datasource.db_type.upper()}, Name: {datasource.name}). Use this ID when calling tools unless they specify otherwise."
            system_msg += f"\n\nIMPORTANT: This is a {datasource.db_type.upper()} database. You MUST use {skill_prefix}_* skills (e.g., {skill_prefix}_get_db_status, {skill_prefix}_get_slow_queries, {skill_prefix}_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type. Unless the user explicitly asks to switch datasources, keep all diagnosis and tool calls scoped to this datasource."

            if datasource.remark:
                system_msg += (
                    f"\n\n**数据源备注**：{datasource.remark}"
                    "\n此备注包含该数据源的业务背景、特殊配置或已知问题等重要上下文信息，诊断时请结合此备注进行分析。"
                )

            if host_id and host_name_for_display:
                host_info_parts = [f"主机名: {host_name_for_display}"]
                if host and host.os_version:
                    host_info_parts.append(f"OS版本: {host.os_version}")
                if host and host.port:
                    host_info_parts.append(f"SSH端口: {host.port}")
                host_detail = "，".join(host_info_parts)
                system_msg += f"\n\n**主机连接已配置**：该数据源已关联主机（{host_detail}），host_id={host_id}。你可以使用 OS 层面的诊断技能（get_os_metrics、diagnose_high_cpu、diagnose_high_memory、diagnose_disk_space、diagnose_disk_io、diagnose_network）进行操作系统级别的深度分析。遇到性能问题时，应同时从数据库和操作系统两个层面进行诊断。"
            elif host_id:
                system_msg += f"\n\n**主机连接已配置**：该数据源已关联主机，host_id={host_id}。你可以使用 OS 层面的诊断技能（get_os_metrics、diagnose_high_cpu、diagnose_high_memory、diagnose_disk_space、diagnose_disk_io、diagnose_network）进行操作系统级别的深度分析。遇到性能问题时，应同时从数据库和操作系统两个层面进行诊断。"
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

    # 阶段2: 数据源上下文构建完成
    datasource_info = ""
    datasource_ctx = None
    if datasource_id and db:
        from backend.models.datasource import Datasource
        from backend.models.soft_delete import alive_filter
        from sqlalchemy import select
        result = await db.execute(select(Datasource).filter(Datasource.id == datasource_id, alive_filter(Datasource)))
        datasource_ctx = result.scalar_one_or_none()
        if datasource_ctx:
            datasource_info = f"数据源: {datasource_ctx.name} ({datasource_ctx.db_type})"
            if datasource_ctx.host_id:
                datasource_info += " · 已关联主机"
            else:
                datasource_info += " · 未关联主机"
    yield {
        "type": "thinking_phase",
        "phase": "context_building",
        "message": f"正在构建诊断上下文... {datasource_info}" if datasource_info else "正在构建诊断上下文...",
        "datasource_name": datasource_ctx.name if datasource_ctx else None,
        "datasource_type": datasource_ctx.db_type if datasource_ctx else None,
        "host_configured": bool(datasource_ctx.host_id) if datasource_ctx else False,
    }

    active_tools = await get_available_skills_as_tools(
        db,
        disabled_tools,
        datasource_db_type=datasource_db_type,
        host_configured=host_configured_for_tools,
    )
    static_kb_tools = [tool for tool in get_filtered_tools(disabled_tools) if tool.get("function", {}).get("name") in KB_TOOL_NAMES]
    active_tools = active_tools + static_kb_tools
    disabled_set = set(disabled_tools) if disabled_tools else set()

    # 阶段3: 技能选择完成
    skill_count = len(active_tools)
    yield {
        "type": "thinking_phase",
        "phase": "skill_selection",
        "message": f"已选中 {skill_count} 个诊断技能",
        "skill_count": skill_count,
    }

    # 阶段4: 准备开始输出
    yield {"type": "thinking_complete", "message": "开始诊断..."}

    full_messages = [{"role": "system", "content": system_msg}] + messages
    emitted_plan = False
    emitted_kb_hint = False

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            collected_content = ""
            collected_tool_calls = []
            round_usage = None

            try:
                async with asyncio.timeout(STREAM_ROUND_TIMEOUT):
                    async for event in stream_assistant_turn(
                        client,
                        full_messages,
                        tools=active_tools,
                        tool_choice="auto",
                    ):
                        if not emitted_plan and round_num == 0:
                            emitted_plan = True
                            yield {
                                "type": "plan_created",
                                "summary": "诊断计划已启动：理解问题、必要时阅读知识库、调用诊断技能收集证据、输出结论。",
                            }
                        if kb_ids and not emitted_kb_hint and round_num == 0:
                            emitted_kb_hint = True
                            yield {
                                "type": "kb_document_selected",
                                "title": f"当前会话启用了 {len(kb_ids)} 个知识库，将优先结合文档诊断。",
                            }
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
            except TimeoutError:
                logger.error(f"AI API stream timed out at round {round_num} after {STREAM_ROUND_TIMEOUT}s")
                if collected_content:
                    yield {"type": "content", "content": "\n\n[AI 响应超时，以上为部分结果]"}
                    yield {"type": "done", "content": collected_content + "\n\n[AI 响应超时，以上为部分结果]"}
                else:
                    yield {"type": "error", "message": f"AI 响应超时（{STREAM_ROUND_TIMEOUT}秒），请稍后重试或简化问题。"}
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
                    yield {
                        "type": "plan_step_status",
                        "step_id": tc["id"],
                        "tool_name": tool_name,
                        "status": "failed",
                        "title": f"尝试调用技能 {tool_name}",
                        "summary": f"技能 {tool_name} 已被用户在当前会话中禁用。",
                        "error": f"Tool '{tool_name}' is disabled for this session by the user.",
                    }
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

                if tool_name in KB_TOOL_NAMES:
                    yield {
                        "type": "plan_step_status",
                        "step_id": tc["id"],
                        "tool_name": tool_name,
                        "status": "running",
                        "title": f"读取知识库 {tool_name}",
                        "summary": f"正在调用 {tool_name}...",
                    }
                    yield {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_call_id": tc["id"],
                    }
                    tool_result = await execute_tool(tool_name, tool_args)
                    if tool_name == "list_documents":
                        try:
                            docs = json.loads(tool_result)
                            first_doc = docs[0] if isinstance(docs, list) and docs else None
                            if first_doc:
                                yield {
                                    "type": "kb_document_selected",
                                    "title": first_doc.get("title") or f"已找到 {len(docs)} 篇候选文档",
                                    "document_id": first_doc.get("id"),
                                }
                        except Exception:
                            pass
                    elif tool_name == "read_document":
                        yield {
                            "type": "kb_document_read",
                            "document_id": tool_args.get("doc_id"),
                            "title": f"已读取文档 #{tool_args.get('doc_id')}",
                        }
                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "tool_call_id": tc["id"],
                        "result": tool_result[:10000],
                        "execution_time_ms": 0,
                    }
                    yield {
                        "type": "plan_step_status",
                        "step_id": tc["id"],
                        "tool_name": tool_name,
                        "status": "completed",
                        "title": f"知识库工具 {tool_name} 执行完成",
                        "summary": f"知识库 {tool_name} 执行完成。",
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
                risk = await assess_tool_risk(tool_name, tool_args, getattr(skill, 'permissions', None), client=client)

                yield {
                    "type": "plan_step_status",
                    "step_id": tc["id"],
                    "tool_name": tool_name,
                    "status": "running",
                    "title": f"执行技能 {tool_name}",
                    "summary": f"正在执行 {tool_name}...",
                }

                if risk.get("level") in {"high", "destructive"} and not skip_approval:
                    approval_id = f"approval_{uuid.uuid4().hex}"
                    yield {
                        "type": "approval_request",
                        "approval_id": approval_id,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_call_id": tc["id"],
                        "summary": f"技能 {tool_name} 可能带来数据库或主机状态变更，需要确认后再执行。",
                        "plan_markdown": f"1. 执行技能 `{tool_name}`\n2. 观察执行结果\n3. 继续完成本轮诊断",
                        "risk_level": risk.get("level", "high"),
                        "risk_reason": risk.get("risk_reason"),
                        "suppressible": risk.get("suppressible", False),
                        "confirmation_key": risk.get("confirmation_key"),
                    }
                    yield {
                        "type": "plan_step_status",
                        "step_id": tc["id"],
                        "tool_name": tool_name,
                        "status": "waiting_approval",
                        "title": f"等待确认 {tool_name}",
                        "summary": f"技能 {tool_name} 已提交，等待用户批准后执行。",
                    }
                    return

                yield {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_call_id": tc["id"],
                }

                tool_result, execution_time_ms, skill_execution_id = await execute_skill_call(
                    tool_name, tool_args, db, user_id, session_id
                )

                try:
                    result_data = json.loads(tool_result)
                    if isinstance(result_data, dict) and result_data.get("success") is False:
                        step_status = "failed"
                        step_summary = f"技能 {tool_name} 执行失败：{result_data.get('error', 'unknown')}"
                        step_error = result_data.get("error")
                    else:
                        step_status = "completed"
                        step_summary = f"技能 {tool_name} 执行完成"
                        step_error = None
                except Exception:
                    step_status = "completed"
                    step_summary = f"技能 {tool_name} 执行完成"
                    step_error = None

                yield {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": tc["id"],
                    "result": tool_result[:10000],
                    "execution_time_ms": execution_time_ms,
                    "skill_execution_id": skill_execution_id,
                }
                yield {
                    "type": "plan_step_status",
                    "step_id": tc["id"],
                    "tool_name": tool_name,
                    "status": step_status,
                    "title": f"执行技能 {tool_name}",
                    "summary": step_summary,
                    "execution_time_ms": execution_time_ms,
                    "error": step_error,
                }

                # Truncate result for AI model to avoid token limit issues
                ai_result = tool_result
                if len(tool_result) > 30000:
                    ai_result = tool_result[:30000] + "\n\n... [数据过长，已截断。请基于以上数据进行分析]"
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": ai_result,
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
    timeout_seconds: int = 600
) -> tuple[str, list]:
    """Generate inspection report using AI with skill calls. Returns (markdown, skill_executions)."""
    import asyncio

    skill_executions: list[dict[str, Any]] = []
    collected_content = ""

    error_message: Optional[str] = None

    # Check if datasource has host configured for OS-level analysis
    host_info_msg = ""
    try:
        from backend.models.datasource import Datasource
        from backend.models.host import Host
        from backend.models.soft_delete import alive_filter
        from sqlalchemy import select

        ds_result = await db.execute(select(Datasource).filter(Datasource.id == datasource_id, alive_filter(Datasource)))
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
