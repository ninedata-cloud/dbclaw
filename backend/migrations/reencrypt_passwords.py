"""
Re-encrypt all passwords with the current encryption key.

This migration is needed when upgrading from an older version that used
a different encryption key. It will:
1. Decrypt passwords using legacy keys (if configured)
2. Re-encrypt them with the current key
3. Update the database

Run this after setting LEGACY_ENCRYPTION_KEYS environment variable.
"""
import asyncio
from sqlalchemy import text
from backend.database import async_engine
from backend.utils.encryption import decrypt_value, encrypt_value
from cryptography.fernet import InvalidToken


async def run_migration():
    """Re-encrypt all encrypted passwords in the database."""
    async with async_engine.begin() as conn:
        # Get all datasources with passwords
        result = await conn.execute(
            text("SELECT id, password FROM datasources WHERE password IS NOT NULL AND password != ''")
        )
        datasources = result.fetchall()

        # Get all hosts with passwords
        result = await conn.execute(
            text("SELECT id, password FROM hosts WHERE password IS NOT NULL AND password != ''")
        )
        hosts = result.fetchall()

        total_updated = 0
        failed = []

        # Re-encrypt datasource passwords
        for ds_id, encrypted_password in datasources:
            try:
                # Decrypt with current or legacy key
                plain_password = decrypt_value(encrypted_password)
                # Re-encrypt with current key
                new_encrypted = encrypt_value(plain_password)

                # Only update if different (means it was encrypted with legacy key)
                if new_encrypted != encrypted_password:
                    await conn.execute(
                        text("UPDATE datasources SET password = :password WHERE id = :id"),
                        {"password": new_encrypted, "id": ds_id}
                    )
                    total_updated += 1
            except InvalidToken:
                failed.append(("datasource", ds_id))

        # Re-encrypt host passwords
        for host_id, encrypted_password in hosts:
            try:
                plain_password = decrypt_value(encrypted_password)
                new_encrypted = encrypt_value(plain_password)

                if new_encrypted != encrypted_password:
                    await conn.execute(
                        text("UPDATE hosts SET password = :password WHERE id = :id"),
                        {"password": new_encrypted, "id": host_id}
                    )
                    total_updated += 1
            except InvalidToken:
                failed.append(("host", host_id))

        if failed:
            print(f"Warning: Failed to decrypt {len(failed)} records:")
            for record_type, record_id in failed:
                print(f"  - {record_type} id={record_id}")
            print("These records may need manual intervention.")

        print(f"Re-encryption complete: {total_updated} records updated")


if __name__ == "__main__":
    asyncio.run(run_migration())
