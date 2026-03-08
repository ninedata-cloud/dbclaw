"""
Automatically clear and reset API keys with proper encryption
"""
import asyncio
from sqlalchemy import select
from backend.database import async_session
from backend.models.ai_model import AIModel
from backend.utils.encryption import encrypt_value


async def clear_and_reset():
    """Clear encrypted API keys - requires manual re-entry via UI"""
    async with async_session() as db:
        result = await db.execute(select(AIModel).where(AIModel.is_active == True))
        models = result.scalars().all()

        print(f"Found {len(models)} AI models")
        print("Clearing encrypted API keys...\n")

        for model in models:
            # Set to empty encrypted value
            model.api_key_encrypted = encrypt_value("")
            print(f"✓ Cleared API key for model {model.id} ({model.name})")

        await db.commit()
        print("\n✓ All API keys cleared.")
        print("\nNext steps:")
        print("1. Go to the AI Models page in the UI")
        print("2. Edit each model and re-enter the API key")
        print("3. The keys will be encrypted with the correct encryption key")


if __name__ == "__main__":
    print("=" * 70)
    print("API Key Encryption Reset")
    print("=" * 70)
    print()
    asyncio.run(clear_and_reset())
