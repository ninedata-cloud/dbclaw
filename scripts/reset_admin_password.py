#!/usr/bin/env python3
"""Reset a user's password from the server shell (no Web login, no manual SQL).

Uses the same rules as POST /api/users/{id}/reset-password: bcrypt hash,
password_changed_at, session_version bump, and session revocation.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from backend.database import get_db
from backend.models.soft_delete import alive_filter
from backend.models.user import User
from backend.services.session_service import SessionService
from backend.utils.security import hash_password


def _resolve_new_password(args: argparse.Namespace) -> str:
    if args.password is not None:
        return args.password
    env_pw = os.environ.get("DBCLAW_RESET_PASSWORD")
    if env_pw is not None:
        return env_pw
    if not sys.stdin.isatty():
        print(
            "Non-interactive mode: set DBCLAW_RESET_PASSWORD or pass --password.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    while True:
        a = getpass.getpass("New password: ")
        b = getpass.getpass("Confirm new password: ")
        if a != b:
            print("Passwords do not match, try again.", file=sys.stderr)
            continue
        if not a:
            print("Password must not be empty.", file=sys.stderr)
            continue
        return a


async def _run(username: str, new_password: str) -> None:
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.username == username, alive_filter(User))
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"User not found (or deleted): {username}", file=sys.stderr)
            raise SystemExit(1)

        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(timezone.utc)
        user.session_version += 1
        await SessionService.revoke_user_session(db, user.id, "password_reset")
        await db.commit()
        print(f"Password reset for user {username!r}.")
        break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset DBClaw user password using DATABASE_URL from .env or environment.",
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="Username to reset (default: admin)",
    )
    parser.add_argument(
        "--password",
        default=None,
        metavar="PASSWORD",
        help="New password (avoid: visible in shell history; prefer interactive or DBCLAW_RESET_PASSWORD)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    new_password = _resolve_new_password(args)
    asyncio.run(_run(args.username, new_password))


if __name__ == "__main__":
    main()
