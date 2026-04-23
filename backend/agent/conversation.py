import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from sqlalchemy import select

from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import get_filtered_tools
from backend.agent.context_builder import execute_tool
from backend.services.ai_agent import get_ai_client, stream_assistant_turn

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 1000


async def run_conversation(
    messages: List[Dict[str, Any]],
    datasource_id: Optional[int] = None,
    model_id: Optional[int] = None,
    kb_ids: Optional[List[int]] = None,
    db: Optional[Any] = None,
    disabled_tools: Optional[List[str]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run the AI conversation loop with tool calling and streaming."""

    # Get model config
    from backend.models.ai_model import AIModel
    from backend.routers.ai_models import decrypt_api_key
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
                reasoning_effort=getattr(model, "reasoning_effort", None),
            )
    # Fallback: use default model, or first active model by ID
    if not client and db:
        result = await db.execute(
            select(AIModel)
            .filter(AIModel.is_active == True)
            .order_by(AIModel.is_default.desc(), AIModel.id.asc())
        )
        model = result.scalars().first()
        if model:
            client = get_ai_client(
                api_key=decrypt_api_key(model.api_key_encrypted),
                base_url=model.base_url,
                model_name=model.model_name,
                protocol=getattr(model, "protocol", "openai"),
                reasoning_effort=getattr(model, "reasoning_effort", None),
            )
    if not client:
        yield {"type": "error", "content": "AI model not configured. Please add an AI model in the AI Model Management page."}
        return

    system_msg = SYSTEM_PROMPT
    if datasource_id:
        system_msg += f"\n\nThe user is currently working with database datasource ID: {datasource_id}. Use this ID when calling tools unless they specify otherwise."

    if kb_ids:
        system_msg += f"\n\nKnowledge bases are enabled for this session (IDs: {kb_ids}). Use list_documents tool to browse available documentation, then read_document to fetch full content."

    active_tools = get_filtered_tools(disabled_tools)
    disabled_set = set(disabled_tools) if disabled_tools else set()

    full_messages = [{"role": "system", "content": system_msg}] + messages

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            collected_content = ""
            collected_tool_calls = []

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

                tool_result = await execute_tool(tool_name, tool_args)

                yield {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": tc["id"],
                    "result": tool_result[:2000],
                }

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        except Exception as e:
            logger.error(f"Conversation error at round {round_num}: {e}")
            yield {"type": "error", "content": f"Error: {str(e)}"}
            return

    yield {"type": "error", "content": "Maximum tool call rounds reached. Please try a more specific question."}
