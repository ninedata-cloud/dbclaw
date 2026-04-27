from typing import Any, Optional

from pydantic import BaseModel, Field


class FeishuChallengeRequest(BaseModel):
    type: Optional[str] = None
    challenge: Optional[str] = None
    token: Optional[str] = None


class FeishuCardAction(BaseModel):
    tag: Optional[str] = None
    value: Optional[dict[str, Any]] = None
    open_message_id: Optional[str] = None


class FeishuMessageEventBody(BaseModel):
    schema_: Optional[str] = Field(default=None, alias="schema")
    header: Optional[dict[str, Any]] = None
    event: Optional[dict[str, Any]] = None
    action: Optional[FeishuCardAction | dict[str, Any]] = None
    open_message_id: Optional[str] = None
    token: Optional[str] = None
