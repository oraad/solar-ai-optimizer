"""Reset local admin password (invoked from scripts/reset-local-password.sh).

Usage (inside container):
    python -m scripts.reset_local_password [--password PASS] [--username USER]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.local_credentials import (
    generate_password,
    generate_session_secret,
    hash_password,
    local_auth_env_path,
    read_env_value,
    write_local_auth_env,
)


def _data_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("DATA_DIR", "/app/data"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset local admin credentials")
    parser.add_argument("--password", default="", help="New password (auto-generated if omitted)")
    parser.add_argument("--username", default="admin", help="Local admin username")
    parser.add_argument("--data-dir", default="", help="Data directory (default: $DATA_DIR or /app/data)")
    parser.add_argument(
        "--keep-sessions",
        action="store_true",
        help="Do not rotate SESSION_SECRET (existing cookies stay valid)",
    )
    args = parser.parse_args(argv)

    data_dir = _data_dir(args.data_dir or None)
    env_path = local_auth_env_path(data_dir)
    password = args.password or generate_password()
    password_hash = hash_password(password)

    if args.keep_sessions:
        session_secret = read_env_value(env_path, "SESSION_SECRET") or generate_session_secret()
    else:
        session_secret = generate_session_secret()

    write_local_auth_env(
        env_path,
        username=args.username,
        password_hash=password_hash,
        session_secret=session_secret,
    )

    print(f"USERNAME={args.username}")
    print(f"PASSWORD={password}")
    print(f"ENV_FILE={env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
