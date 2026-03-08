"""
Migration script to re-encrypt API keys with the centralized encryption key.

This script decrypts API keys using the old encryption method and re-encrypts them
using the centralized encryption utility.
"""
import asyncio
import os
from cryptography.fernet import Fernet
from sqlalchemy import select

from backend.database import async_session
from backend.models.ai_model import AIModel
from backend.utils.encryption import encrypt_value


async def migrate_api_keys():
    """Migrate API keys from old encryption to new encryption"""

    # Get old encryption key
    old_key = os.getenv("ENCRYPTION_KEY")
    if not old_key:
        print("ERROR: ENCRYPTION_KEY not found in environment")
        print("Please set the old ENCRYPTION_KEY that was used to encrypt the API keys")
        return

    old_cipher = Fernet(old_key.encode())

    async with async_session() as db:
        # Get all AI models
        result = await db.execute(select(AIModel))
        models = result.scalars().all()

        if not models:
            print("No AI models found in database")
            return

        print(f"Found {len(models)} AI models to migrate")

        migrated = 0
        failed = 0

        for model in models:
            try:
                # Decrypt with old key
                old_encrypted = model.api_key_encrypted
                decrypted_key = old_cipher.decrypt(old_encrypted.encode()).decode()

                # Re-encrypt with new centralized key
                new_encrypted = encrypt_value(decrypted_key)

                # Update in database
                model.api_key_encrypted = new_encrypted

                print(f"✓ Migrated API key for model: {model.name} (ID: {model.id})")
                migrated += 1

            except Exception as e:
                print(f"✗ Failed to migrate model {model.name} (ID: {model.id}): {e}")
                failed += 1

        if migrated > 0:
            await db.commit()
            print(f"\n✓ Successfully migrated {migrated} API keys")

        if failed > 0:
            print(f"✗ Failed to migrate {failed} API keys")

        if migrated == 0 and failed == 0:
            print("No API keys needed migration")


if __name__ == "__main__":
    print("=" * 60)
    print("API Key Migration Script")
    print("=" * 60)
    print()

    asyncio.run(migrate_api_keys())

    print()
    print("=" * 60)
    print("Migration complete")
    print("=" * 60)
