"""CLI entry point for incremental sync.

Usage:
    python -m app.jobs.sync --source jira --since 2024-01-01T00:00:00Z
    python -m app.jobs.sync --source gitlab --since 2024-01-01 --config '{"project_id":"group/repo"}'
    python -m app.jobs.sync --source slack --since 2024-01-01 --config '{"channels":["C0001"]}'
    python -m app.jobs.sync --source notion --since 2024-01-01 --config '{"database_ids":["db-1"]}'
    python -m app.jobs.sync --source confluence --since 2024-01-01 --config '{"base_url":"https://myco.atlassian.net"}'
    python -m app.jobs.sync --source google_meet --since 2024-01-01
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from app.db import async_session
from app.jobs.sync import CONNECTOR_REGISTRY


async def run_sync(
    source: str,
    since: datetime,
    token: str | None = None,
    config: dict | None = None,
) -> int:
    """Execute the sync connector and return exit code."""
    connector_cls = CONNECTOR_REGISTRY.get(source)
    if not connector_cls:
        print(f"Unknown source: {source}")
        print(f"Available: {', '.join(sorted(CONNECTOR_REGISTRY))}")
        return 1

    connector = connector_cls()

    async with async_session() as session:
        # Resolve token: CLI arg > environment > DB lookup (service account)
        resolved_token = token
        if not resolved_token:
            import os
            env_key = f"{source.upper()}_API_TOKEN"
            resolved_token = os.environ.get(env_key, "")

        if not resolved_token:
            # Try DB service-account token
            from sqlalchemy import select
            from app.models.source_token import SourceToken
            from app.crypto import decrypt

            stmt = select(SourceToken).where(
                SourceToken.source == source,
                SourceToken.is_service_account.is_(True),
            ).limit(1)
            result = await session.execute(stmt)
            token_obj = result.scalar_one_or_none()
            if token_obj:
                resolved_token = decrypt(token_obj.encrypted_token)

        if not resolved_token:
            print(
                f"No token found. Provide --token, set {source.upper()}_API_TOKEN env var, "
                f"or configure a service-account token in the DB."
            )
            return 1

        sync_result = await connector.sync(
            session, resolved_token, since, config=config,
        )

    print(f"\n=== Sync Result: {source} ===")
    for k, v in sync_result.summary().items():
        print(f"  {k}: {v}")

    return 0 if sync_result.ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Incremental sync: pull data from external APIs into raw_event.",
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=sorted(CONNECTOR_REGISTRY),
        help="Source connector to run.",
    )
    parser.add_argument(
        "--since",
        required=True,
        help="Fetch data updated since this timestamp (ISO 8601).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="API token (overrides env var and DB lookup).",
    )
    parser.add_argument(
        "--config",
        default="{}",
        help="JSON config for the connector (e.g. board_id, project_id, channels).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    try:
        config = json.loads(args.config)
    except json.JSONDecodeError as exc:
        print(f"Invalid --config JSON: {exc}")
        sys.exit(1)

    exit_code = asyncio.run(run_sync(
        source=args.source,
        since=since,
        token=args.token,
        config=config,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
