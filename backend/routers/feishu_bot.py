import json
import logging

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.i18n.errors import ApiError
from backend.schemas.feishu import FeishuChallengeRequest, FeishuMessageEventBody
from backend.services.feishu_bot_service import FeishuBotService, _extract_feishu_bot_config
from backend.services.feishu_service import feishu_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feishu-bot"])


@router.post("/api/feishu/bot/events")
async def handle_feishu_events(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_lark_request_timestamp: str | None = Header(default=None),
    x_lark_request_nonce: str | None = Header(default=None),
    x_lark_signature: str | None = Header(default=None),
):
    body = await request.body()
    payload = json.loads(body.decode("utf-8") or "{}")

    challenge_req = FeishuChallengeRequest.model_validate(payload)
    if challenge_req.challenge:
        return {"challenge": challenge_req.challenge}

    integration = await FeishuBotService.get_bot_integration(db)
    config = _extract_feishu_bot_config(integration)
    signing_secret = (config.get("signing_secret") or "").strip()

    if not feishu_service.verify_signature(
        x_lark_request_timestamp,
        x_lark_request_nonce,
        body,
        x_lark_signature,
        signing_secret,
    ):
        raise ApiError(401, "auth.invalid_credentials")

    event_body = FeishuMessageEventBody.model_validate(payload)
    header = event_body.header or {}
    event_type = header.get("event_type")

    if event_type == "im.message.receive_v1":
        return await FeishuBotService.handle_message_event(db, payload)

    if event_type in {"card.action.trigger", "card.action.trigger_v1"}:
        logger.info("Received Feishu card callback: event_type=%s", event_type)
        return await FeishuBotService.handle_action_event(db, payload)

    if event_body.action:
        logger.info("Received a Feishu card callback with an undeclared type; handling in compatibility mode: event_type=%s", event_type)
        return await FeishuBotService.handle_action_event(db, payload)

    logger.info("Ignoring unhandled Feishu event: event_type=%s", event_type)
    return {"ok": True, "ignored": True}
