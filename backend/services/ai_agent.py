import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import anthropic
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
THINK_START_TAG = "<think>"
THINK_END_TAG = "</think>"


def _normalize_usage(input_tokens: Optional[int] = None, output_tokens: Optional[int] = None) -> Dict[str, int]:
    input_value = int(input_tokens or 0)
    output_value = int(output_tokens or 0)
    return {
        "input_tokens": input_value,
        "output_tokens": output_value,
        "total_tokens": input_value + output_value,
    }


def _coerce_stream_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_coerce_stream_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "reasoning", "thinking", "reasoning_content"):
            if key in value:
                return _coerce_stream_text(value.get(key))
        return ""

    for attr in ("text", "content", "reasoning", "thinking", "reasoning_content"):
        attr_value = getattr(value, attr, None)
        if attr_value is not None:
            return _coerce_stream_text(attr_value)
    return ""


def _extract_openai_reasoning_text(delta: Any) -> str:
    for attr in ("reasoning_content", "reasoning"):
        text = _coerce_stream_text(getattr(delta, attr, None))
        if text:
            return text
    return ""


def _extract_anthropic_reasoning_text(delta: Any) -> str:
    delta_type = getattr(delta, "type", None)
    if delta_type not in {"thinking_delta", "reasoning_delta"}:
        return ""
    for attr in ("thinking", "text", "reasoning", "content"):
        text = _coerce_stream_text(getattr(delta, attr, None))
        if text:
            return text
    return ""


OPENAI_PROTOCOL = "openai"
ANTHROPIC_PROTOCOL = "anthropic"
DEFAULT_MODEL = "claude-opus-4-6"


@dataclass
class AIClient:
    protocol: str
    client: Any
    model_name: str
    base_url: Optional[str] = None
    reasoning_effort: Optional[str] = None


def get_ai_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    protocol: str = OPENAI_PROTOCOL,
    reasoning_effort: Optional[str] = None,
) -> Optional[AIClient]:
    protocol = protocol or OPENAI_PROTOCOL

    if not api_key or api_key.startswith("sk-your"):
        return None

    if protocol == ANTHROPIC_PROTOCOL:
        client = AsyncAnthropic(api_key=api_key, base_url=base_url or None)
        return AIClient(
            protocol=ANTHROPIC_PROTOCOL,
            client=client,
            model_name=model_name or DEFAULT_MODEL,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
        )

    if not model_name:
        return None

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return AIClient(
        protocol=OPENAI_PROTOCOL,
        client=client,
        model_name=model_name,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
    )


def _get_anthropic_reasoning_payload(reasoning_effort: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    effort = (reasoning_effort or "").strip().lower()
    if effort not in {"low", "medium", "high", "max"}:
        return None, None
    # Keep Anthropic path simple and aligned with verified sample:
    # thinking uses adaptive mode, effort is carried in output_config.
    return {"type": "adaptive"}, {"effort": effort}


def _extract_system_message(messages: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    system_parts: List[str] = []
    filtered: List[Dict[str, Any]] = []

    for message in messages:
        if message.get("role") == "system":
            content = message.get("content")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_parts.append(block.get("text", ""))
            continue
        filtered.append(message)

    system = "\n\n".join(part for part in system_parts if part)
    return system or None, filtered


def _parse_data_url(data_url: str) -> Optional[Tuple[str, str]]:
    if not data_url.startswith("data:") or ";base64," not in data_url:
        return None
    header, data = data_url.split(",", 1)
    media_type = header[5:].split(";", 1)[0] or "image/jpeg"
    return media_type, data


def _to_anthropic_content_blocks(content: Any) -> List[Dict[str, Any]]:
    if content is None:
        return []

    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    blocks: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                blocks.append({"type": "text", "text": item.get("text", "")})
            elif item_type == "image_url":
                image_url = item.get("image_url", {}).get("url")
                if not image_url:
                    continue
                parsed = _parse_data_url(image_url)
                if not parsed:
                    continue
                media_type, data = parsed
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                })
    return blocks


def _assistant_tool_calls_to_blocks(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks = _to_anthropic_content_blocks(message.get("content"))
    for tool_call in message.get("tool_calls", []) or []:
        function = tool_call.get("function", {})
        arguments = function.get("arguments") or "{}"
        try:
            parsed_args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            parsed_args = {}
        blocks.append({
            "type": "tool_use",
            "id": tool_call.get("id", ""),
            "name": function.get("name", ""),
            "input": parsed_args or {},
        })
    return blocks


def convert_messages_for_anthropic(messages: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    system, non_system_messages = _extract_system_message(messages)
    converted: List[Dict[str, Any]] = []

    for message in non_system_messages:
        role = message.get("role")

        if role == "tool":
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": message.get("tool_call_id", ""),
                    "content": message.get("content", ""),
                }],
            })
            continue

        if role == "assistant":
            assistant_blocks = _assistant_tool_calls_to_blocks(message)
            converted.append({
                "role": "assistant",
                "content": assistant_blocks or [{"type": "text", "text": ""}],
            })
            continue

        if role == "user":
            converted.append({
                "role": "user",
                "content": _to_anthropic_content_blocks(message.get("content")) or [{"type": "text", "text": ""}],
            })
            continue

    merged: List[Dict[str, Any]] = []
    for message in converted:
        if merged and merged[-1]["role"] == message["role"]:
            merged[-1]["content"].extend(message["content"])
        else:
            merged.append({"role": message["role"], "content": list(message["content"])})

    return system, merged


def convert_tools_for_anthropic(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None

    converted = []
    for tool in tools:
        function = tool.get("function", {})
        converted.append({
            "name": function.get("name", ""),
            "description": function.get("description", ""),
            "input_schema": function.get("parameters", {"type": "object", "properties": {}}),
        })
    return converted


async def request_text_response(
    ai_client: AIClient,
    messages: List[Dict[str, Any]],
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    if ai_client.protocol == ANTHROPIC_PROTOCOL:
        system, anthropic_messages = convert_messages_for_anthropic(messages)
        request_kwargs: Dict[str, Any] = {
            "model": ai_client.model_name or DEFAULT_MODEL,
            "system": system,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        thinking_config, output_config = _get_anthropic_reasoning_payload(ai_client.reasoning_effort)
        if thinking_config:
            request_kwargs["thinking"] = thinking_config
        if output_config:
            request_kwargs["output_config"] = output_config
        if thinking_config or output_config:
            logger.info(
                "Anthropic reasoning enabled for model=%s thinking=%s effort=%s",
                ai_client.model_name,
                (thinking_config or {}).get("type"),
                (output_config or {}).get("effort"),
            )
        response = await ai_client.client.messages.create(**request_kwargs)
        texts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        return "".join(texts).strip()

    request_kwargs: Dict[str, Any] = {
        "model": ai_client.model_name,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        request_kwargs["temperature"] = float(temperature)
    if ai_client.reasoning_effort:
        request_kwargs["reasoning_effort"] = ai_client.reasoning_effort

    response = await ai_client.client.chat.completions.create(**request_kwargs)
    return (response.choices[0].message.content if response.choices else "") or ""


async def request_text_response_with_usage(
    ai_client: AIClient,
    messages: List[Dict[str, Any]],
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> Tuple[str, Dict[str, int]]:
    if ai_client.protocol == ANTHROPIC_PROTOCOL:
        system, anthropic_messages = convert_messages_for_anthropic(messages)
        request_kwargs: Dict[str, Any] = {
            "model": ai_client.model_name or DEFAULT_MODEL,
            "system": system,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        thinking_config, output_config = _get_anthropic_reasoning_payload(ai_client.reasoning_effort)
        if thinking_config:
            request_kwargs["thinking"] = thinking_config
        if output_config:
            request_kwargs["output_config"] = output_config
        if thinking_config or output_config:
            logger.info(
                "Anthropic reasoning enabled for model=%s thinking=%s effort=%s",
                ai_client.model_name,
                (thinking_config or {}).get("type"),
                (output_config or {}).get("effort"),
            )
        response = await ai_client.client.messages.create(**request_kwargs)
        texts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        usage = _normalize_usage(
            getattr(getattr(response, "usage", None), "input_tokens", None),
            getattr(getattr(response, "usage", None), "output_tokens", None),
        )
        return "".join(texts).strip(), usage

    request_kwargs: Dict[str, Any] = {
        "model": ai_client.model_name,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        request_kwargs["temperature"] = float(temperature)
    if ai_client.reasoning_effort:
        request_kwargs["reasoning_effort"] = ai_client.reasoning_effort

    response = await ai_client.client.chat.completions.create(**request_kwargs)
    usage = _normalize_usage(
        getattr(getattr(response, "usage", None), "prompt_tokens", None),
        getattr(getattr(response, "usage", None), "completion_tokens", None),
    )
    return (response.choices[0].message.content if response.choices else "") or "", usage


async def stream_assistant_turn(
    ai_client: AIClient,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    temperature: Optional[float] = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[Dict[str, Any], None]:
    if ai_client.protocol == ANTHROPIC_PROTOCOL:
        async for event in _stream_anthropic_turn(
            ai_client,
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield event
        return

    async for event in _stream_openai_turn(
        ai_client,
        messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield event


async def _stream_openai_turn(
    ai_client: AIClient,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    temperature: Optional[float] = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[Dict[str, Any], None]:
    request_kwargs: Dict[str, Any] = {
        "model": ai_client.model_name,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        request_kwargs["temperature"] = float(temperature)
    if ai_client.reasoning_effort:
        request_kwargs["reasoning_effort"] = ai_client.reasoning_effort

    response = await ai_client.client.chat.completions.create(**request_kwargs)

    collected_content = ""
    collected_tool_calls: Dict[int, Dict[str, Any]] = {}
    final_stop_reason = "end_turn"
    usage = _normalize_usage()

    async for chunk in response:
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage:
            usage = _normalize_usage(
                getattr(chunk_usage, "prompt_tokens", None),
                getattr(chunk_usage, "completion_tokens", None),
            )

        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue

        if delta.content:
            collected_content += delta.content
            yield {"type": "content", "content": delta.content}

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in collected_tool_calls:
                    collected_tool_calls[idx] = {
                        "id": tc.id or "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc.id:
                    collected_tool_calls[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        collected_tool_calls[idx]["function"]["name"] = tc.function.name
                    if tc.function.arguments:
                        collected_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

        finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
        if finish_reason == "tool_calls":
            final_stop_reason = "tool_calls"
        elif finish_reason == "stop":
            final_stop_reason = "end_turn"

    tool_calls = [collected_tool_calls[idx] for idx in sorted(collected_tool_calls.keys())]
    yield {
        "type": "message_complete",
        "content": collected_content,
        "tool_calls": tool_calls,
        "stop_reason": final_stop_reason if tool_calls else "end_turn",
        "usage": usage,
    }


async def _stream_anthropic_turn(
    ai_client: AIClient,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    temperature: Optional[float] = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[Dict[str, Any], None]:
    system, anthropic_messages = convert_messages_for_anthropic(messages)
    anthropic_tools = convert_tools_for_anthropic(tools)

    request_kwargs: Dict[str, Any] = {
        "model": ai_client.model_name or DEFAULT_MODEL,
        "messages": anthropic_messages,
        "system": system,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    thinking_config, output_config = _get_anthropic_reasoning_payload(ai_client.reasoning_effort)
    if thinking_config:
        request_kwargs["thinking"] = thinking_config
    if output_config:
        request_kwargs["output_config"] = output_config
    if thinking_config or output_config:
        logger.info(
            "Anthropic reasoning enabled for model=%s thinking=%s effort=%s",
            ai_client.model_name,
            (thinking_config or {}).get("type"),
            (output_config or {}).get("effort"),
        )
    if anthropic_tools:
        request_kwargs["tools"] = anthropic_tools
        request_kwargs["tool_choice"] = {"type": "auto"} if tool_choice == "auto" else {"type": "any"}

    collected_content = ""
    collected_tool_calls: Dict[int, Dict[str, Any]] = {}
    current_tool_index: Optional[int] = None
    final_stop_reason = "end_turn"
    usage = _normalize_usage()

    async with ai_client.client.messages.stream(**request_kwargs) as stream:
        async for event in stream:
            if event.type == "content_block_start":
                block = event.content_block
                if getattr(block, "type", None) == "tool_use":
                    current_tool_index = event.index
                    collected_tool_calls[event.index] = {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": "",
                        },
                    }
            elif event.type == "content_block_delta":
                delta = event.delta
                if getattr(delta, "type", None) == "text_delta":
                    collected_content += delta.text
                    yield {"type": "content", "content": delta.text}
                elif getattr(delta, "type", None) == "input_json_delta":
                    idx = event.index if hasattr(event, "index") else current_tool_index
                    if idx is not None and idx in collected_tool_calls:
                        collected_tool_calls[idx]["function"]["arguments"] += delta.partial_json
            elif event.type == "message_delta":
                stop_reason = getattr(event.delta, "stop_reason", None)
                if stop_reason == "tool_use":
                    final_stop_reason = "tool_calls"
                elif stop_reason == "end_turn":
                    final_stop_reason = "end_turn"

        final_message = await stream.get_final_message()
        if getattr(final_message, "stop_reason", None) == "tool_use":
            final_stop_reason = "tool_calls"
        elif getattr(final_message, "stop_reason", None) == "end_turn":
            final_stop_reason = "end_turn"

        final_usage = getattr(final_message, "usage", None)
        if final_usage:
            usage = _normalize_usage(
                getattr(final_usage, "input_tokens", None),
                getattr(final_usage, "output_tokens", None),
            )

    tool_calls = [collected_tool_calls[idx] for idx in sorted(collected_tool_calls.keys())]
    yield {
        "type": "message_complete",
        "content": collected_content,
        "tool_calls": tool_calls,
        "stop_reason": final_stop_reason if tool_calls else "end_turn",
        "usage": usage,
    }
