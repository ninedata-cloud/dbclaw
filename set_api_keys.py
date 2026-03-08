"""
Script to set API keys directly with proper encryption
"""
import asyncio
from sqlalchemy import select
from backend.database import async_session
from backend.models.ai_model import AIModel
from backend.utils.encryption import encrypt_value


async def set_api_keys():
    """Set API keys for models"""

    # Define your API keys here
    api_keys = {
        "qwen-plus": "sk-156b463e041340f781305dec2e254dd3",  # Replace with actual key
        "qwen3.5-plus": "sk-56d9e30b5236471099cbc3a8c63c7821",  # Replace with actual key
    }

    async with async_session() as db:
        result = await db.execute(select(AIModel).where(AIModel.is_active == True))
        models = result.scalars().all()

        print(f"Found {len(models)} AI models")
        print("Setting API keys...\n")

        for model in models:
            if model.name in api_keys:
                api_key = api_keys[model.name]
                model.api_key_encrypted = encrypt_value(api_key)
                print(f"✓ Set API key for model {model.id} ({model.name})")
            else:
                print(f"⚠ No API key defined for model {model.id} ({model.name})")

        await db.commit()
        print("\n✓ API keys updated successfully")


if __name__ == "__main__":
    print("=" * 70)
    print("Set API Keys with Proper Encryption")
    print("=" * 70)
    print()
    asyncio.run(set_api_keys())
