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

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


async def execute_skill_call(
    skill_id: str, arguments: Dict[str, Any], db, user_id: int, session_id: Optional[int] = None
) -> str:
    """Execute a skill and return the result as JSON string"""
    from backend.skills.registry import SkillRegistry
    from backend.skills.executor import SkillExecutor
    from backend.skills.context import SkillContext

    try:
        registry = SkillRegistry(db)
        skill = await registry.get_skill(skill_id)

        if not skill:
            return json.dumps({"error": f"Skill '{skill_id}' not found"})

        if not skill.is_enabled:
            return json.dumps({"error": f"Skill '{skill_id}' is disabled"})

        # Create execution context with skill's required permissions
        context = SkillContext(
            db=db,
            user_id=user_id,
            session_id=session_id,
            permissions=skill.permissions or [],
        )

        # Execute skill
        executor = SkillExecutor()
        result = await executor.execute(skill, arguments, context)

        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error executing skill {skill_id}: {e}")
        return json.dumps({"error": str(e)})


async def run_conversation_with_skills(
    messages: List[Dict[str, Any]],
    connection_id: Optional[int] = None,
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
    if model_id and db:
        from sqlalchemy import select
        result = await db.execute(select(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True))
        model = result.scalar_one_or_none()
        if model:
            client = get_ai_client(
                api_key=decrypt_api_key(model.api_key_encrypted),
                base_url=model.base_url,
                model_name=model.model_name
            )
        else:
            client = get_ai_client()
    else:
        client = get_ai_client()

    if not client:
        yield {"type": "error", "content": "AI client not configured. Set OPENAI_API_KEY in .env"}
        return

    # Detect intent from first user message
    first_user_message = next((msg['content'] for msg in messages if msg['role'] == 'user'), '')
    intent = detect_query_intent(first_user_message)

    # Select appropriate prompt based on intent
    if intent == 'diagnostic':
        system_msg = DIAGNOSTIC_PROMPT
    elif intent == 'administrative':
        system_msg = ADMINISTRATIVE_PROMPT
    else:  # informational
        system_msg = INFORMATIONAL_PROMPT

    if connection_id and db:
        # Get connection info to determine database type
        from backend.models.connection import Connection
        from sqlalchemy import select
        result = await db.execute(select(Connection).filter(Connection.id == connection_id))
        conn = result.scalar_one_or_none()
        if conn:
            # Map db_type to skill prefix
            skill_prefix_map = {
                'mysql': 'mysql',
                'postgresql': 'pg',
                'sqlserver': 'mssql',
                'oracle': 'oracle'
            }
            skill_prefix = skill_prefix_map.get(conn.db_type, conn.db_type)

            system_msg += f"\n\nThe user is currently working with database connection ID: {connection_id} (Type: {conn.db_type.upper()}, Name: {conn.name}). Use this ID when calling tools unless they specify otherwise."
            system_msg += f"\n\nIMPORTANT: This is a {conn.db_type.upper()} database. You MUST use {skill_prefix}_* skills (e.g., {skill_prefix}_get_db_status, {skill_prefix}_get_slow_queries, {skill_prefix}_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type."
        else:
            system_msg += f"\n\nThe user is currently working with database connection ID: {connection_id}. Use this ID when calling tools unless they specify otherwise."
    elif connection_id:
        system_msg += f"\n\nThe user is currently working with database connection ID: {connection_id}. Use this ID when calling tools unless they specify otherwise."

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
                tool_result = await execute_skill_call(
                    tool_name, tool_args, db, user_id, session_id
                )

                yield {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": tc["id"],
                    "result": tool_result[:2000],  # Truncate for display
                }

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

            # Loop back to get LLM response after tool results

        except Exception as e:
            logger.error(f"Conversation error at round {round_num}: {e}")
            yield {"type": "error", "content": f"Error: {str(e)}"}
            return

    yield {"type": "error", "content": "Maximum tool call rounds reached. Please try a more specific question."}
