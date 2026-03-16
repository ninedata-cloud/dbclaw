"""
One-time data migration script: SQLite -> PostgreSQL

Usage:
    python backend/migrations/sqlite_to_postgres.py \\
        --sqlite ./data/smartdba.db \\
        --postgres postgresql://smartdba:smartdba@localhost:5432/smartdba

This script reads all data from the SQLite database and inserts it into
an already-initialized PostgreSQL database (tables must exist first).
Run `python run.py` once to let SQLAlchemy create_all, then stop and run this script.
"""

import argparse
import sqlite3
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2-binary is required: pip install psycopg2-binary")
    sys.exit(1)


# Tables in dependency order (parents before children)
TABLES = [
    "users",
    "ai_models",
    "datasources",
    "hosts",
    "knowledge_bases",
    "metric_snapshots",
    "diagnostic_sessions",
    "chat_messages",
    "skills",
    "skill_executions",
    "reports",
    "inspection_configs",
    "inspection_triggers",
    "alert_messages",
    "alert_events",
    "alert_subscriptions",
    "alert_delivery_log",
    "system_configs",
    "login_logs",
]


def get_sqlite_tables(sqlite_conn: sqlite3.Connection) -> set:
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def get_pg_columns(pg_conn, table: str) -> list:
    cursor = pg_conn.cursor()
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (table,))
    return [row[0] for row in cursor.fetchall()]


def get_sqlite_columns(sqlite_conn: sqlite3.Connection, table: str) -> list:
    cursor = sqlite_conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str, batch_size: int = 500) -> int:
    sqlite_cols = set(get_sqlite_columns(sqlite_conn, table))
    pg_cols = get_pg_columns(pg_conn, table)

    # Use only columns that exist in both databases
    common_cols = [c for c in pg_cols if c in sqlite_cols]
    if not common_cols:
        print(f"  {table}: no common columns, skipping")
        return 0

    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
    total = sqlite_cursor.fetchone()[0]
    if total == 0:
        print(f"  {table}: empty, skipping")
        return 0

    cols_sql = ", ".join(common_cols)
    placeholders = ", ".join(["%s"] * len(common_cols))
    insert_sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    pg_cursor = pg_conn.cursor()
    sqlite_cursor.execute(f"SELECT {cols_sql} FROM {table}")

    inserted = 0
    while True:
        rows = sqlite_cursor.fetchmany(batch_size)
        if not rows:
            break
        psycopg2.extras.execute_batch(pg_cursor, insert_sql, rows)
        pg_conn.commit()
        inserted += len(rows)
        print(f"  {table}: {inserted}/{total} rows migrated", end="\r")

    print(f"  {table}: {inserted} rows migrated    ")
    return inserted


def reset_sequences(pg_conn, tables: list):
    """Reset PostgreSQL SERIAL sequences to max id + 1 for each table"""
    print("\nResetting PostgreSQL sequences...")
    cursor = pg_conn.cursor()
    for table in tables:
        # Check if table has an id column with a sequence
        cursor.execute("""
            SELECT pg_get_serial_sequence(%s, 'id')
        """, (table,))
        row = cursor.fetchone()
        if row and row[0]:
            sequence = row[0]
            cursor.execute(f"SELECT MAX(id) FROM {table}")
            max_id = cursor.fetchone()[0]
            if max_id is not None:
                cursor.execute(f"SELECT setval(%s, %s)", (sequence, max_id))
                print(f"  {table}: sequence reset to {max_id}")
    pg_conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Path to SQLite database file")
    parser.add_argument("--postgres", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch (default: 500)")
    args = parser.parse_args()

    print(f"Connecting to SQLite: {args.sqlite}")
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row

    print(f"Connecting to PostgreSQL: {args.postgres}")
    pg_conn = psycopg2.connect(args.postgres)

    sqlite_tables = get_sqlite_tables(sqlite_conn)
    print(f"\nFound {len(sqlite_tables)} tables in SQLite")

    total_rows = 0
    skipped_tables = []
    migrated_tables = []

    # Disable FK checks during bulk insert
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute("SET session_replication_role = 'replica'")
    pg_conn.commit()

    print("\nMigrating tables...")
    for table in TABLES:
        if table not in sqlite_tables:
            print(f"  {table}: not found in SQLite, skipping")
            skipped_tables.append(table)
            continue
        rows = migrate_table(sqlite_conn, pg_conn, table, args.batch_size)
        if rows > 0:
            migrated_tables.append(table)
            total_rows += rows

    # Re-enable FK checks
    pg_cursor.execute("SET session_replication_role = 'origin'")
    pg_conn.commit()

    # Reset sequences
    reset_sequences(pg_conn, migrated_tables)

    sqlite_conn.close()
    pg_conn.close()

    print(f"\nMigration complete!")
    print(f"  Tables migrated: {len(migrated_tables)}")
    print(f"  Total rows:      {total_rows}")
    if skipped_tables:
        print(f"  Tables skipped:  {', '.join(skipped_tables)}")


if __name__ == "__main__":
    main()
