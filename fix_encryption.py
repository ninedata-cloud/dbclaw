"""
Script to fix API key encryption issues.

Option 1: Try to decrypt with old key and re-encrypt with new key
Option 2: Clear encrypted keys and require manual re-entry
"""
import asyncio
import sys
from sqlalchemy import select
from backend.database import async_session
from backend.models.ai_model import AIModel
from backend.utils.encryption import encrypt_value
from cryptography.fernet import Fernet


async def test_decryption():
    """Test if we can decrypt existing keys"""
    async with async_session() as db:
        result = await db.execute(select(AIModel).where(AIModel.is_active == True))
        models = result.scalars().all()

        if not models:
            print("No AI models found")
            return

        print(f"Found {len(models)} AI models")
        print("\nTesting decryption with current ENCRYPTION_KEY...")

        from backend.utils.encryption import decrypt_value

        for model in models:
            try:
                decrypted = decrypt_value(model.api_key_encrypted)
                print(f"✓ Model {model.id} ({model.name}): Successfully decrypted")
            except Exception as e:
                print(f"✗ Model {model.id} ({model.name}): Failed - {type(e).__name__}")


async def clear_and_reset():
    """Clear encrypted API keys - requires manual re-entry via UI"""
    async with async_session() as db:
        result = await db.execute(select(AIModel).where(AIModel.is_active == True))
        models = result.scalars().all()

        print(f"\nClearing {len(models)} encrypted API keys...")
        print("You will need to re-enter API keys via the UI.\n")

        for model in models:
            # Set to empty encrypted value
            model.api_key_encrypted = encrypt_value("")
            print(f"✓ Cleared API key for model {model.id} ({model.name})")

        await db.commit()
        print("\n✓ All API keys cleared. Please re-enter them via the AI Models page.")


async def try_reencrypt_with_key(old_key: str):
    """Try to re-encrypt with a provided old key"""
    try:
        old_cipher = Fernet(old_key.encode())
    except Exception as e:
        print(f"Invalid key format: {e}")
        return

    async with async_session() as db:
        result = await db.execute(select(AIModel).where(AIModel.is_active == True))
        models = result.scalars().all()

        success = 0
        failed = 0

        for model in models:
            try:
                # Decrypt with old key
                decrypted = old_cipher.decrypt(model.api_key_encrypted.encode()).decode()

                # Re-encrypt with new key
                new_encrypted = encrypt_value(decrypted)
                model.api_key_encrypted = new_encrypted

                print(f"✓ Re-encrypted model {model.id} ({model.name})")
                success += 1
            except Exception as e:
                print(f"✗ Failed model {model.id} ({model.name}): {e}")
                failed += 1

        if success > 0:
            await db.commit()
            print(f"\n✓ Successfully re-encrypted {success} API keys")

        if failed > 0:
            print(f"✗ Failed to re-encrypt {failed} API keys")


async def main():
    print("=" * 70)
    print("API Key Encryption Fix Tool")
    print("=" * 70)

    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            await test_decryption()
        elif sys.argv[1] == "clear":
            confirm = input("This will clear all API keys. Type 'yes' to confirm: ")
            if confirm.lower() == 'yes':
                await clear_and_reset()
            else:
                print("Cancelled")
        elif sys.argv[1] == "reencrypt":
            if len(sys.argv) < 3:
                print("Usage: python fix_encryption.py reencrypt <old_encryption_key>")
                return
            await try_reencrypt_with_key(sys.argv[2])
        else:
            print("Unknown command")
    else:
        print("\nUsage:")
        print("  python fix_encryption.py test          - Test current decryption")
        print("  python fix_encryption.py clear         - Clear all API keys (requires re-entry)")
        print("  python fix_encryption.py reencrypt KEY - Re-encrypt with old key")
        print()
        await test_decryption()


if __name__ == "__main__":
    asyncio.run(main())
