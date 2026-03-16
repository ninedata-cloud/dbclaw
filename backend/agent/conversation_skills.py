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

    # Select appropriate prompt based on intent
    if intent == 'diagnostic':
        system_msg = DIAGNOSTIC_PROMPT
    elif intent == 'administrative':
        system_msg = ADMINISTRATIVE_PROMPT
    else:  # informational
        system_msg = INFORMATIONAL_PROMPT

    if datasource_id and db:
        # Get datasource info to determine database type
        from backend.models.datasource import Datasource
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
                    "result": tool_result[:2000],  # Truncate for display
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

    initial_message = f"""请为以下数据库生成一份全面的巡检报告：
- 数据库名称：{datasource_name} ({datasource_type})
- 数据源 ID：{datasource_id}
- 触发原因：{trigger_reason}

请使用技能收集数据，并按照专业 DBA 报告的标准格式撰写完整的中文报告。"""

    messages = [{"role": "user", "content": initial_message}]

    try:
        async with asyncio.timeout(timeout_seconds):
            async for event in run_conversation_with_skills(
                messages=messages,
                datasource_id=datasource_id,
                model_id=model_id,
                db=db,
                user_id=user_id
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
        collected_content += "\n\n⚠️ Report generation timed out - showing partial results"
    except Exception as e:
        collected_content += f"\n\n⚠️ Error during generation: {str(e)}"

    return collected_content or "⚠️ No content generated", skill_executions
