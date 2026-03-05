import logging
from typing import Optional
from openai import AsyncOpenAI
from backend.config import get_settings

logger = logging.getLogger(__name__)


def get_ai_client(api_key: Optional[str] = None, base_url: Optional[str] = None, model_name: Optional[str] = None) -> Optional[AsyncOpenAI]:
    settings = get_settings()

    # Use provided config or fallback to settings
    api_key = api_key or settings.openai_api_key
    base_url = base_url or settings.openai_base_url
    model_name = model_name or settings.openai_model

    if not api_key or api_key.startswith("sk-your"):
        return None

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    client._model_name = model_name
    return client
