"""
Add diagnosis decision tracking fields to anomaly table
"""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def upgrade():
    """Add diagnosis decision fields"""
    async with engine.begin() as conn:
        # Check if columns already exist
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'anomalies'
            AND column_name IN ('diagnosis_decision', 'diagnosis_decision_reason', 'diagnosis_decision_at')
        """))
        existing_count = result.scalar()

        if existing_count == 3:
            print("Diagnosis decision fields already exist")
            return

        print("Adding diagnosis decision fields...")

        await conn.execute(text("""
            ALTER TABLE anomalies
            ADD COLUMN IF NOT EXISTS diagnosis_decision VARCHAR(20)
        """))

        await conn.execute(text("""
            ALTER TABLE anomalies
            ADD COLUMN IF NOT EXISTS diagnosis_decision_reason TEXT
        """))

        await conn.execute(text("""
            ALTER TABLE anomalies
            ADD COLUMN IF NOT EXISTS diagnosis_decision_at TIMESTAMP
        """))

        print("Diagnosis decision fields added successfully")


async def downgrade():
    """Remove diagnosis decision fields"""
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE anomalies DROP COLUMN IF EXISTS diagnosis_decision"))
        await conn.execute(text("ALTER TABLE anomalies DROP COLUMN IF EXISTS diagnosis_decision_reason"))
        await conn.execute(text("ALTER TABLE anomalies DROP COLUMN IF EXISTS diagnosis_decision_at"))


if __name__ == "__main__":
    print("Running migration: add_diagnosis_decision_fields")
    asyncio.run(upgrade())
    print("Migration completed!")
