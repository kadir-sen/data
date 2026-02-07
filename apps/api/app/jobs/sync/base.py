"""Base connector with shared HTTP client, rate-limit retries, and cursor state."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent
from app.models.source_state import SourceState

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────────────────

MAX_RETRIES = 5
INITIAL_BACKOFF_S = 1.0
BACKOFF_FACTOR = 2.0
MAX_BACKOFF_S = 60.0
DEFAULT_TIMEOUT_S = 30.0


# ── result dataclass ──────────────────────────────────────────────────


@dataclass
class SyncResult:
    """Tracks statistics for a single connector sync run."""

    source: str
    events_fetched: int = 0
    events_stored: int = 0
    events_skipped_duplicate: int = 0
    errors: list[str] = field(default_factory=list)
    cursor_advanced: bool = False

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> dict[str, object]:
        return {
            "source": self.source,
            "events_fetched": self.events_fetched,
            "events_stored": self.events_stored,
            "events_skipped_duplicate": self.events_skipped_duplicate,
            "errors": self.errors,
            "cursor_advanced": self.cursor_advanced,
        }


# ── HTTP helpers ──────────────────────────────────────────────────────


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = MAX_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF_S,
    **kwargs: object,
) -> httpx.Response:
    """Execute an HTTP request with exponential backoff on rate-limit / transient errors.

    Retries on:
      - 429 Too Many Requests (respects Retry-After header)
      - 5xx Server Errors
      - httpx network errors
    """
    backoff = initial_backoff
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else backoff
                wait = min(wait, MAX_BACKOFF_S)
                logger.warning(
                    "Rate limited (429) on %s %s, retry in %.1fs (attempt %d/%d)",
                    method, url, wait, attempt + 1, max_retries,
                )
                await asyncio.sleep(wait)
                backoff = min(backoff * BACKOFF_FACTOR, MAX_BACKOFF_S)
                continue

            if resp.status_code >= 500:
                logger.warning(
                    "Server error %d on %s %s, retry in %.1fs (attempt %d/%d)",
                    resp.status_code, method, url, backoff, attempt + 1, max_retries,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_FACTOR, MAX_BACKOFF_S)
                continue

            resp.raise_for_status()
            return resp

        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning(
                "Timeout on %s %s, retry in %.1fs (attempt %d/%d)",
                method, url, backoff, attempt + 1, max_retries,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, MAX_BACKOFF_S)

        except httpx.HTTPStatusError:
            raise

        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "HTTP error on %s %s: %s, retry in %.1fs (attempt %d/%d)",
                method, url, exc, backoff, attempt + 1, max_retries,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, MAX_BACKOFF_S)

    raise httpx.HTTPError(
        f"Max retries ({max_retries}) exceeded for {method} {url}"
    ) from last_exc


def compute_content_hash(source: str, entity_type: str, entity_id: str, payload: dict) -> str:
    """SHA-256 hash for idempotent dedup of raw_event rows."""
    canonical = json.dumps(
        {"source": source, "entity_type": entity_type, "entity_id": entity_id, "payload": payload},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── cursor state management ───────────────────────────────────────────


async def load_cursor(
    session: AsyncSession, source: str, entity_type: str
) -> SourceState | None:
    """Load the cursor state for a (source, entity_type) pair."""
    stmt = select(SourceState).where(
        SourceState.source == source,
        SourceState.entity_type == entity_type,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def save_cursor(
    session: AsyncSession,
    source: str,
    entity_type: str,
    last_run: datetime,
    cursor: str | None = None,
    extra: dict | None = None,
) -> None:
    """Upsert the cursor state for a (source, entity_type) pair."""
    stmt = (
        pg_insert(SourceState)
        .values(
            id=uuid.uuid4(),
            source=source,
            entity_type=entity_type,
            last_run=last_run,
            cursor=cursor,
            extra=extra,
        )
        .on_conflict_do_update(
            index_elements=["source", "entity_type"],
            set_={
                "last_run": last_run,
                "cursor": cursor,
                "extra": extra,
                "updated_at": datetime.now(timezone.utc),
            },
        )
    )
    await session.execute(stmt)


async def store_raw_event(
    session: AsyncSession,
    source: str,
    entity_type: str,
    entity_id: str,
    occurred_at: datetime,
    payload: dict,
) -> bool:
    """Store a raw event, returning True if newly inserted, False if duplicate."""
    content_hash = compute_content_hash(source, entity_type, entity_id, payload)
    stmt = (
        pg_insert(RawEvent)
        .values(
            id=uuid.uuid4(),
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            occurred_at=occurred_at,
            content_hash=content_hash,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["content_hash"])
        .returning(RawEvent.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


# ── abstract base connector ──────────────────────────────────────────


class BaseConnector(ABC):
    """Abstract base class for incremental sync connectors.

    Subclasses implement `sync()` which pulls data from an external API
    and stores it as raw_event rows via `store_raw_event()`.
    """

    source: str  # e.g. "jira", "gitlab"

    @abstractmethod
    async def sync(
        self,
        session: AsyncSession,
        token: str,
        since: datetime,
        *,
        config: dict | None = None,
    ) -> SyncResult:
        """Pull new data from the external API and store as raw_events.

        Args:
            session: Async DB session for raw_event storage and cursor state.
            token: Decrypted API token / bearer token.
            since: Only fetch data updated since this timestamp.
            config: Optional connector-specific config (board_id, channels, etc.).

        Returns:
            SyncResult with statistics.
        """

    def _make_client(self, token: str, *, base_url: str = "", **kwargs: object) -> httpx.AsyncClient:
        """Create a pre-configured httpx client with auth and timeout."""
        headers = dict(kwargs.pop("headers", {}))  # type: ignore[arg-type]
        headers.setdefault("Accept", "application/json")
        return httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_S),
            **kwargs,  # type: ignore[arg-type]
        )
