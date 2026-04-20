import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any, Optional

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)


_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^(\s*)>\s?(.*)$")
MAX_POST_TEXT_LENGTH = 8000


def _feishu_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _markdown_to_feishu_inline(body: str) -> list[dict[str, Any]]:
    parts: list[tuple[int, int, str, Any]] = []
    for match in _MARKDOWN_LINK_RE.finditer(body):
        parts.append((match.start(), match.end(), "link", match))
    for match in _BOLD_RE.finditer(body):
        parts.append((match.start(), match.end(), "bold", match))
    for match in _INLINE_CODE_RE.finditer(body):
        parts.append((match.start(), match.end(), "code", match))
    parts.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    content: list[dict[str, Any]] = []
    cursor = 0
    for start, end, part_type, match in parts:
        if start < cursor:
            continue
        if start > cursor:
            segment = body[cursor:start]
            if segment:
                content.append({"tag": "text", "text": _feishu_escape(segment)})
        if part_type == "link":
            content.append({
                "tag": "a",
                "text": _feishu_escape(match.group(1)),
                "href": match.group(2),
            })
        elif part_type == "bold":
            content.append({
                "tag": "text",
                "text": _feishu_escape(match.group(1)),
                "style": ["bold"],
            })
        elif part_type == "code":
            content.append({
                "tag": "text",
                "text": _feishu_escape(match.group(1)),
                "style": ["code_inline"],
            })
        cursor = end
    if cursor < len(body):
        segment = body[cursor:]
        if segment:
            content.append({"tag": "text", "text": _feishu_escape(segment)})
    return content


def _split_markdown_chunks(text: str, limit: int = MAX_POST_TEXT_LENGTH) -> list[str]:
    normalized = _normalize_markdown_text(text)
    if not normalized:
        return [""]
    if len(normalized) <= limit:
        return [normalized]

    blocks = _parse_markdown_blocks(normalized)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush_current() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n\n".join(current).rstrip())
        current = []
        current_len = 0

    def append_block(block_text: str) -> None:
        nonlocal current_len
        if not block_text.strip():
            return
        if current and current_len + 2 + len(block_text) > limit:
            flush_current()
        if len(block_text) <= limit:
            current.append(block_text)
            current_len = len("\n\n".join(current))
            return

        lines = block_text.splitlines()
        buffer: list[str] = []
        buffer_len = 0
        for line in lines:
            if len(line) > limit:
                if buffer:
                    append_block("\n".join(buffer))
                    buffer = []
                    buffer_len = 0
                start = 0
                while start < len(line):
                    append_block(line[start:start + limit])
                    start += limit
                continue

            extra = len(line) + (1 if buffer else 0)
            if buffer and buffer_len + extra > limit:
                append_block("\n".join(buffer))
                buffer = [line]
                buffer_len = len(line)
            else:
                buffer.append(line)
                buffer_len += extra
        if buffer:
            append_block("\n".join(buffer))

    for block in blocks:
        append_block(block["text"])

    flush_current()
    return chunks or [normalized[:limit]]


def _normalize_markdown_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return ""

    lines = normalized.split("\n")
    compacted: list[str] = []
    blank_count = 0
    in_code_block = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("```"):
            if compacted and compacted[-1] != "":
                compacted.append("")
            compacted.append(line)
            in_code_block = not in_code_block
            blank_count = 0
            continue
        if in_code_block:
            compacted.append(line)
            continue

        if not line.strip():
            blank_count += 1
            if blank_count == 1 and compacted and compacted[-1] != "":
                compacted.append("")
            continue

        blank_count = 0
        compacted.append(line)

    while compacted and compacted[0] == "":
        compacted.pop(0)
    while compacted and compacted[-1] == "":
        compacted.pop()

    return "\n".join(compacted)


def _format_short_text(text: str) -> str:
    compact = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if not compact:
        return ""
    if len(compact) <= 120 and not any(token in text for token in ("#", "- ", "* ", "```", "|", "> ")):
        return compact
    return text


def format_reply_text(text: str) -> str:
    # 先过滤 thinking 标签内容
    filtered = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    filtered = re.sub(r'&lt;think&gt;.*?&lt;/think&gt;', '', filtered, flags=re.DOTALL | re.IGNORECASE)

    normalized = _normalize_markdown_text(filtered)
    if not normalized:
        return ""
    return _format_short_text(normalized)


def _parse_markdown_blocks(text: str) -> list[dict[str, str]]:
    lines = _normalize_markdown_text(text).splitlines()
    if not lines:
        return []

    blocks: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if line.startswith("```"):
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if lines[i].startswith("```"):
                    i += 1
                    break
                i += 1
            blocks.append({"type": "code", "text": "\n".join(code_lines)})
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = [line]
            i += 1
            while i < len(lines):
                current = lines[i].strip()
                if current.startswith("|") and current.endswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                    continue
                break
            blocks.append({"type": "table", "text": "\n".join(table_lines)})
            continue

        paragraph_lines = [line]
        i += 1
        while i < len(lines):
            current = lines[i]
            current_stripped = current.strip()
            if not current_stripped:
                break
            if current.startswith("```"):
                break
            if current_stripped.startswith("|") and current_stripped.endswith("|"):
                break
            if current.lstrip().startswith(("# ", "## ", "### ")) and paragraph_lines:
                break
            if (_BULLET_RE.match(current) or _ORDERED_RE.match(current) or _BLOCKQUOTE_RE.match(current)) and paragraph_lines[-1].strip() and not (_BULLET_RE.match(paragraph_lines[-1]) or _ORDERED_RE.match(paragraph_lines[-1]) or _BLOCKQUOTE_RE.match(paragraph_lines[-1])):
                break
            paragraph_lines.append(current)
            i += 1
        blocks.append({"type": "paragraph", "text": "\n".join(paragraph_lines)})

    return blocks


def _make_text_line(text: str, *, bold: bool = False) -> list[dict[str, Any]]:
    item: dict[str, Any] = {"tag": "text", "text": _feishu_escape(text)}
    if bold:
        item["style"] = ["bold"]
    return [item]


def _blank_post_line() -> list[dict[str, Any]]:
    return [{"tag": "text", "text": " "}]


def _render_table_lines(table_text: str) -> list[list[dict[str, Any]]]:
    raw_rows: list[list[str]] = []
    for raw_line in table_text.splitlines():
        stripped = raw_line.strip()
        if _TABLE_SEPARATOR_RE.match(stripped):
            continue
        inner = stripped.strip("|")
        raw_rows.append([cell.strip() for cell in inner.split("|")])

    if not raw_rows:
        return []

    col_count = max(len(row) for row in raw_rows)
    rows = [row + [""] * (col_count - len(row)) for row in raw_rows]
    widths = [max(len(row[idx]) for row in rows) for idx in range(col_count)]

    rendered: list[list[dict[str, Any]]] = []
    for index, row in enumerate(rows):
        cells = [row[idx].ljust(widths[idx]) for idx in range(col_count)]
        line = " | ".join(cells).rstrip()
        rendered.append(_make_text_line(line, bold=index == 0))
        if index == 0 and len(rows) > 1:
            separator = "-+-".join("-" * max(width, 3) for width in widths)
            rendered.append(_make_text_line(separator))
    return rendered


def _render_code_block_lines(block_text: str) -> list[list[dict[str, Any]]]:
    lines = block_text.splitlines()
    if not lines:
        return []
    language = lines[0][3:].strip()
    code_lines = lines[1:]
    if code_lines and code_lines[-1].startswith("```"):
        code_lines = code_lines[:-1]

    rendered: list[list[dict[str, Any]]] = []
    if language:
        rendered.append(_make_text_line(f"代码块 ({language})", bold=True))
    for line in code_lines or [""]:
        rendered.append(_make_text_line(line))
    return rendered


def _render_paragraph_lines(block_text: str) -> list[list[dict[str, Any]]]:
    rendered: list[list[dict[str, Any]]] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        paragraph_text = " ".join(part.strip() for part in paragraph_buffer if part.strip())
        if paragraph_text:
            inline = _markdown_to_feishu_inline(paragraph_text)
            rendered.append(inline or _make_text_line(paragraph_text))
        paragraph_buffer = []

    for raw_line in block_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()

        if not stripped:
            flush_paragraph()
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            rendered.append(_make_text_line(stripped[4:], bold=True))
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            rendered.append(_make_text_line(stripped[3:], bold=True))
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            rendered.append(_make_text_line(stripped[2:], bold=True))
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            flush_paragraph()
            indent = min(len(bullet_match.group(1)) // 2, 3)
            rendered.append([
                {"tag": "text", "text": "  " * indent + "• "},
                *(_markdown_to_feishu_inline(bullet_match.group(2)) or _make_text_line(bullet_match.group(2))),
            ])
            continue

        ordered_match = _ORDERED_RE.match(line)
        if ordered_match:
            flush_paragraph()
            indent = min(len(ordered_match.group(1)) // 2, 3)
            rendered.append([
                {"tag": "text", "text": "  " * indent + f"{ordered_match.group(2)}. "},
                *(_markdown_to_feishu_inline(ordered_match.group(3)) or _make_text_line(ordered_match.group(3))),
            ])
            continue

        quote_match = _BLOCKQUOTE_RE.match(line)
        if quote_match:
            flush_paragraph()
            body = quote_match.group(2).strip()
            rendered.append([
                {"tag": "text", "text": "│ ", "style": ["bold"]},
                *(_markdown_to_feishu_inline(body) or _make_text_line(body or "")),
            ])
            continue

        paragraph_buffer.append(line)

    flush_paragraph()
    return rendered


def _markdown_to_feishu_rich_text(text: str) -> list[list[dict[str, Any]]]:
    normalized = _normalize_markdown_text(text)
    if not normalized:
        return [_blank_post_line()]

    rendered_lines: list[list[dict[str, Any]]] = []
    blocks = _parse_markdown_blocks(normalized)
    for index, block in enumerate(blocks):
        if block["type"] == "code":
            rendered_lines.extend(_render_code_block_lines(block["text"]))
        elif block["type"] == "table":
            rendered_lines.extend(_render_table_lines(block["text"]))
        else:
            rendered_lines.extend(_render_paragraph_lines(block["text"]))
        if index != len(blocks) - 1:
            rendered_lines.append(_blank_post_line())

    return rendered_lines or [_blank_post_line()]


def _build_post_content(text: str, title: str | None = None) -> dict[str, Any]:
    payload = {
        "content": _markdown_to_feishu_rich_text(text)
    }
    if title:
        payload["title"] = title
    return {
        "zh_cn": payload
    }


class FeishuService:
    def __init__(self):
        self._tenant_token: Optional[str] = None
        self._tenant_token_expire_at: float = 0

    def verify_signature(self, timestamp: str | None, nonce: str | None, body: bytes, signature: str | None, signing_secret: str | None) -> bool:
        if not signing_secret:
            return True
        if not timestamp or not nonce or not signature:
            return False
        payload = f"{timestamp}{nonce}".encode("utf-8") + body
        expected = hmac.new(signing_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def get_tenant_access_token(self, app_id: str, app_secret: str) -> str:
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expire_at:
            return self._tenant_token

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0 or not data.get("tenant_access_token"):
            raise RuntimeError(data.get("msg") or "获取飞书 tenant_access_token 失败")

        self._tenant_token = data["tenant_access_token"]
        expire = int(data.get("expire", 7200))
        self._tenant_token_expire_at = now + max(expire - 60, 60)
        return self._tenant_token

    async def _post_message(self, url: str, payload: dict[str, Any], *, app_id: str, app_secret: str) -> dict[str, Any]:
        token = await self.get_tenant_access_token(app_id, app_secret)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"飞书发送消息失败: HTTP {response.status_code}, body={response.text}")
            data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书发送消息失败: code={data.get('code')}, msg={data.get('msg')}, body={data}")
        return data

    async def send_message(self, receive_id: str, content: dict[str, Any], *, receive_id_type: str, app_id: str, app_secret: str, msg_type: str = "text") -> dict[str, Any]:
        return await self._post_message(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
            {
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
            app_id=app_id,
            app_secret=app_secret,
        )

    async def reply_message(self, message_id: str, content: dict[str, Any], *, app_id: str, app_secret: str, msg_type: str = "text") -> dict[str, Any]:
        return await self._post_message(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            {
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
            app_id=app_id,
            app_secret=app_secret,
        )

    async def reply_text(self, text: str, *, app_id: str, app_secret: str, message_id: str | None = None, chat_id: str | None = None, open_id: str | None = None) -> dict[str, Any]:
        chunks = _split_markdown_chunks(text)
        result = None
        for index, chunk in enumerate(chunks):
            errors: list[str] = []
            post_content = _build_post_content(chunk)
            if message_id and index == 0:
                try:
                    result = await self.reply_message(
                        message_id,
                        post_content,
                        app_id=app_id,
                        app_secret=app_secret,
                        msg_type="post",
                    )
                    continue
                except Exception as exc:
                    errors.append(f"reply_message failed: {exc}")
            if open_id:
                try:
                    result = await self.send_message(
                        open_id,
                        post_content,
                        receive_id_type="open_id",
                        app_id=app_id,
                        app_secret=app_secret,
                        msg_type="post",
                    )
                    continue
                except Exception as exc:
                    errors.append(f"open_id send failed: {exc}")
            if chat_id:
                try:
                    result = await self.send_message(
                        chat_id,
                        post_content,
                        receive_id_type="chat_id",
                        app_id=app_id,
                        app_secret=app_secret,
                        msg_type="post",
                    )
                    continue
                except Exception as exc:
                    errors.append(f"chat_id send failed: {exc}")
            if errors:
                raise RuntimeError("; ".join(errors))
            raise ValueError("message_id、open_id 或 chat_id 必须提供一个")
        return result or {}

    async def send_interactive_card(
        self,
        card: dict[str, Any],
        *,
        app_id: str,
        app_secret: str,
        message_id: str | None = None,
        chat_id: str | None = None,
        open_id: str | None = None,
    ) -> dict[str, Any]:
        errors: list[str] = []
        if message_id:
            try:
                return await self.reply_message(
                    message_id,
                    card,
                    app_id=app_id,
                    app_secret=app_secret,
                    msg_type="interactive",
                )
            except Exception as exc:
                errors.append(f"reply_message failed: {exc}")
        if open_id:
            try:
                return await self.send_message(
                    open_id,
                    card,
                    receive_id_type="open_id",
                    app_id=app_id,
                    app_secret=app_secret,
                    msg_type="interactive",
                )
            except Exception as exc:
                errors.append(f"open_id send failed: {exc}")
        if chat_id:
            try:
                return await self.send_message(
                    chat_id,
                    card,
                    receive_id_type="chat_id",
                    app_id=app_id,
                    app_secret=app_secret,
                    msg_type="interactive",
                )
            except Exception as exc:
                errors.append(f"chat_id send failed: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))
        raise ValueError("message_id、open_id 或 chat_id 必须提供一个")


feishu_service = FeishuService()
