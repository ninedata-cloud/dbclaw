import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import get_filtered_tools
from backend.agent.context_builder import execute_tool
from backend.services.ai_agent import get_ai_client

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


async def run_conversation(
    messages: List[Dict[str, Any]],
    connection_id: Optional[int] = None,
    model_id: Optional[int] = None,
    kb_ids: Optional[List[int]] = None,
    db: Optional[Any] = None,
    disabled_tools: Optional[List[str]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run the AI conversation loop with tool calling and streaming."""
    from backend.models.ai_model import AIModel
    from backend.routers.ai_models import decrypt_api_key

    # Get model config
    if model_id and db:
        model = db.query(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True).first()
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

    system_msg = SYSTEM_PROMPT
    if connection_id:
        system_msg += f"\n\nThe user is currently working with database connection ID: {connection_id}. Use this ID when calling tools unless they specify otherwise."

    if kb_ids:
        system_msg += f"\n\nKnowledge bases are enabled for this session (IDs: {kb_ids}). Use search_knowledge_base tool to find relevant documentation when needed."

    # Filter tools based on session's disabled list
    active_tools = get_filtered_tools(disabled_tools)
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
            current_tool_call_index = None

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

                # Server-side guard: block disabled tools even if LLM hallucinates them
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

                # Execute the tool
                tool_result = await execute_tool(tool_name, tool_args)

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
