"""
Updated conversation module to use dynamic skill system
"""
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from backend.agent.prompts import DIAGNOSTIC_PROMPT, INFORMATIONAL_PROMPT, ADMINISTRATIVE_PROMPT
from backend.agent.intent_detector import detect_query_intent
from backend.agent.skill_selector import get_available_skills_as_tools
from backend.services.ai_agent import get_ai_client
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 30


def is_dashscope_api(client) -> bool:
    """Check if the client is using DashScope (Qwen) API"""
    return client.base_url and "dashscope.aliyuncs.com" in str(client.base_url)


def convert_messages_for_dashscope(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert messages to DashScope-compatible format.
    DashScope doesn't support 'tool' role, convert to 'function' role instead.
    """
    converted = []
    for msg in messages:
        if msg.get("role") == "tool":
            # Convert tool message to function message for DashScope
            converted.append({
                "role": "function",
                "name": msg.get("tool_call_id", "unknown"),
                "content": msg.get("content", "")
            })
        else:
            converted.append(msg)
    return converted


async def execute_skill_call(
    skill_id: str, arguments: Dict[str, Any], db, user_id: int, session_id: Optional[int] = None
) -> tuple[str, int]:
    """Execute a skill and return the result as JSON string and execution time in ms"""
    from backend.skills.registry import SkillRegistry
    from backend.skills.executor import SkillExecutor
    from backend.skills.context import SkillContext
    import time

    start_time = time.time()

    try:
        # Extract timeout from arguments if provided
        timeout = arguments.pop('timeout', None)
        if timeout:
            timeout = max(30, min(int(timeout), 3600))  # Clamp between 30s and 1h

        registry = SkillRegistry(db)
        skill = await registry.get_skill(skill_id)

        if not skill:
            execution_time = int((time.time() - start_time) * 1000)
            return json.dumps({"error": f"Skill '{skill_id}' not found"}), execution_time

        if not skill.is_enabled:
            execution_time = int((time.time() - start_time) * 1000)
            return json.dumps({"error": f"Skill '{skill_id}' is disabled"}), execution_time

        # Determine final timeout (same logic as SkillExecutor)
        # Priority: dynamic timeout > skill timeout > default timeout
        from backend.skills.executor import SkillExecutor
        if timeout is None:
            timeout = skill.timeout if skill.timeout else SkillExecutor.DEFAULT_TIMEOUT
        # Cap at MAX_TIMEOUT for safety
        timeout = min(timeout, SkillExecutor.MAX_TIMEOUT)

        # Create execution context with skill's required permissions and timeout
        context = SkillContext(
            db=db,
            user_id=user_id,
            session_id=session_id,
            permissions=skill.permissions or [],
            timeout=timeout,
        )

        # Execute skill
        executor = SkillExecutor()
        result = await executor.execute(skill, arguments, context, timeout=timeout)

        execution_time = int((time.time() - start_time) * 1000)
        return json.dumps(result, default=str), execution_time

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        logger.error(f"Error executing skill {skill_id}: {e}")
        return json.dumps({"error": str(e)}), execution_time


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

    # Get model config
    from sqlalchemy import select
    client = None
    if model_id and db:
        result = await db.execute(select(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True))
        model = result.scalar_one_or_none()
        if model:
            client = get_ai_client(
                api_key=decrypt_api_key(model.api_key_encrypted),
                base_url=model.base_url,
                model_name=model.model_name
            )
    # Fallback: use first active model from DB
    if not client and db:
        result = await db.execute(select(AIModel).filter(AIModel.is_active == True))
        model = result.scalars().first()
        if model:
            client = get_ai_client(
                api_key=decrypt_api_key(model.api_key_encrypted),
                base_url=model.base_url,
                model_name=model.model_name
            )
    # Last resort: env var
    if not client:
        client = get_ai_client()

    if not client:
        yield {"type": "error", "message": "AI model not configured. Please add an AI model in the AI Model Management page."}
        return

    # Detect intent from first user message
    first_user_message = next((msg['content'] for msg in messages if msg['role'] == 'user'), '')
    # first_user_message.content may be a list (multimodal with attachments)
    if isinstance(first_user_message, list):
        intent_text = " ".join(p.get("text", "") for p in first_user_message if isinstance(p, dict) and p.get("type") == "text")
    else:
        intent_text = first_user_message
    intent = detect_query_intent(intent_text)

    # Select appropriate prompt based on intent (or use override)
    if system_prompt_override:
        system_msg = system_prompt_override
    elif intent == 'diagnostic':
        system_msg = DIAGNOSTIC_PROMPT
    elif intent == 'administrative':
        system_msg = ADMINISTRATIVE_PROMPT
    else:  # informational
        system_msg = INFORMATIONAL_PROMPT

    if datasource_id and db:
        # Get datasource info to determine database type
        from backend.models.datasource import Datasource
        from backend.models.host import Host
        from sqlalchemy import select
        result = await db.execute(select(Datasource).filter(Datasource.id == datasource_id))
        datasource = result.scalar_one_or_none()
        if datasource:
            # Map db_type to skill prefix
            skill_prefix_map = {
                'mysql': 'mysql',
                'postgresql': 'pg',
                'sqlserver': 'mssql',
                'oracle': 'oracle'
            }
            skill_prefix = skill_prefix_map.get(datasource.db_type, datasource.db_type)

            system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id} (Type: {datasource.db_type.upper()}, Name: {datasource.name}). Use this ID when calling tools unless they specify otherwise."
            system_msg += f"\n\nIMPORTANT: This is a {datasource.db_type.upper()} database. You MUST use {skill_prefix}_* skills (e.g., {skill_prefix}_get_db_status, {skill_prefix}_get_slow_queries, {skill_prefix}_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type."

            # Pass host configuration status for OS-level diagnosis
            if datasource.host_id:
                host_result = await db.execute(select(Host).filter(Host.id == datasource.host_id))
                host = host_result.scalar_one_or_none()
                host_info = f" (Host: {host.name or host.host})" if host else ""
                system_msg += f"\n\n**主机连接已配置**：该数据源已关联主机{host_info}，你可以使用 OS 层面的诊断技能（get_os_metrics、diagnose_high_cpu、diagnose_high_memory、diagnose_disk_space、diagnose_disk_io、diagnose_network）进行操作系统级别的深度分析。遇到性能问题时，应同时从数据库和操作系统两个层面进行诊断。"
            else:
                system_msg += "\n\n**注意**：该数据源未配置主机连接，无法进行操作系统层面的诊断（如 CPU、内存、磁盘、网络分析）。如需 OS 级别诊断，请建议用户在数据源配置中关联主机。"
        else:
            system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id}. Use this ID when calling tools unless they specify otherwise."
    elif datasource_id:
        system_msg += f"\n\nThe user is currently working with datasource ID: {datasource_id}. Use this ID when calling tools unless they specify otherwise."

    if kb_ids:
        system_msg += f"\n\nKnowledge bases are enabled for this session (IDs: {kb_ids}). Use search_knowledge_base tool to find relevant documentation when needed."

    # Get dynamic skills as tools
    active_tools = await get_available_skills_as_tools(db, disabled_tools)
    disabled_set = set(disabled_tools) if disabled_tools else set()

    full_messages = [{"role": "system", "content": system_msg}] + messages

    # Detect if using DashScope (通义千问) API
    is_dashscope = client.base_url and "dashscope.aliyuncs.com" in str(client.base_url)

    for round_num in range(MAX_TOOL_ROUNDS):
        try:

            response = await client.chat.completions.create(
                model=client._model_name,
                messages=full_messages,
                tools=active_tools,
                tool_choice="auto",
                stream=True,
            )

            collected_content = ""
            collected_tool_calls = {}

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Stream text content
                if delta.content:
                    collected_content += delta.content
                    yield {"type": "content", "content": delta.content}

                # Collect tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": tc.id or "",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.id:
                            collected_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                collected_tool_calls[idx]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                collected_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

                # Check finish reason
                finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                if finish_reason == "stop":
                    yield {"type": "done", "content": collected_content}
                    return
                elif finish_reason == "tool_calls":
                    break

            # Process tool calls
            if not collected_tool_calls:
                yield {"type": "done", "content": collected_content}
                return

            # Build assistant message with tool calls
            assistant_msg = {"role": "assistant", "content": collected_content or None}
            tool_calls_list = []
            for idx in sorted(collected_tool_calls.keys()):
                tc = collected_tool_calls[idx]
                tool_calls_list.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    }
                })
            assistant_msg["tool_calls"] = tool_calls_list
            full_messages.append(assistant_msg)

            # Execute each tool call
            for tc in tool_calls_list:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                # Server-side guard: block disabled tools
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

                yield {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_call_id": tc["id"],
                }

                # Execute the skill
                tool_result, execution_time_ms = await execute_skill_call(
                    tool_name, tool_args, db, user_id, session_id
                )

                yield {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": tc["id"],
                    "result": tool_result[:10000],  # Truncate for display
                    "execution_time_ms": execution_time_ms,
                }

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

            # Loop back to get LLM response after tool results

        except Exception as e:
            logger.error(f"Conversation error at round {round_num}: {e}")
            yield {"type": "error", "message": f"Error: {str(e)}"}
            return

    yield {
        "type": "error",
        "content": f"Maximum tool execution rounds ({MAX_TOOL_ROUNDS}) reached. The diagnosis may be too complex or requires manual intervention. Please try breaking down your question into smaller parts."
    }


async def generate_report_with_skills(
    datasource_id: int,
    datasource_name: str,
    datasource_type: str,
    trigger_reason: str,
    system_prompt: str,
    db: Any,
    user_id: int = 1,
    model_id: Optional[int] = None,
    timeout_seconds: int = 300
) -> tuple[str, list]:
    """Generate inspection report using AI with skill calls. Returns (markdown, skill_executions)."""
    import asyncio
    from datetime import datetime

    skill_executions = []
    collected_content = ""

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
                if event["type"] == "content":
                    collected_content += event["content"]
                elif event["type"] == "tool_call":
                    skill_executions.append({
                        "skill_id": event["tool_name"],
                        "arguments": event["tool_args"],
                        "timestamp": now().isoformat()
                    })
                elif event["type"] == "done":
                    break

    except asyncio.TimeoutError:
        if collected_content.strip():
            collected_content += "\n\n⚠️ 报告生成超时，以上为部分结果"
        else:
            collected_content = "⚠️ 报告生成超时，未能获取到任何内容。请检查 AI 模型配置是否正确，或稍后重试。"
    except Exception as e:
        if collected_content.strip():
            collected_content += f"\n\n⚠️ 报告生成过程中出错: {str(e)}"
        else:
            collected_content = f"⚠️ 报告生成失败: {str(e)}"

    return collected_content or "⚠️ 未生成任何内容，请检查 AI 模型配置。", skill_executions
