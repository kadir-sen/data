"""Cross-system entity linker.

Resolves references between canonical entities and maintains the external_link
mapping table. Uses both exact ID matching and URL-based heuristics.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_link import ExternalLink

logger = logging.getLogger(__name__)

# Known URL patterns for cross-system linking
URL_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # Jira: https://foo.atlassian.net/browse/PROJ-123
    ("jira", "work_item", re.compile(r"https?://[^/]+/browse/([A-Z][A-Z0-9]+-\d+)")),
    # GitLab issue: https://gitlab.com/group/project/-/issues/42
    ("gitlab", "work_item", re.compile(r"https?://[^/]+/([^/]+/[^/]+)/-/issues/(\d+)")),
    # GitLab MR: https://gitlab.com/group/project/-/merge_requests/42
    ("gitlab", "work_item", re.compile(r"https?://[^/]+/([^/]+/[^/]+)/-/merge_requests/(\d+)")),
    # Notion page: https://www.notion.so/page-title-<32-hex-id>
    ("notion", "work_item", re.compile(r"https?://(?:www\.)?notion\.so/(?:[^/]+/)?[^/]*?([0-9a-f]{32})")),
    # Confluence: https://foo.atlassian.net/wiki/spaces/SPACE/pages/12345/Title
    ("confluence", "doc_entry", re.compile(r"https?://[^/]+/wiki/spaces/[^/]+/pages/(\d+)")),
]


async def upsert_external_link(
    session: AsyncSession,
    canonical_table: str,
    canonical_id: uuid.UUID,
    source: str,
    external_id: str,
    external_url: str | None = None,
    link_type: str = "auto",
    confidence: float | None = None,
) -> None:
    """Insert or update an external link (idempotent on source+external_id+canonical_table)."""
    stmt = pg_insert(ExternalLink).values(
        id=uuid.uuid4(),
        canonical_table=canonical_table,
        canonical_id=canonical_id,
        source=source,
        external_id=external_id,
        external_url=external_url,
        link_type=link_type,
        confidence=confidence,
    ).on_conflict_do_update(
        index_elements=["source", "external_id", "canonical_table"],
        set_={
            "canonical_id": canonical_id,
            "external_url": external_url,
            "link_type": link_type,
            "confidence": confidence,
        },
    )
    await session.execute(stmt)


async def resolve_external_id(
    session: AsyncSession,
    source: str,
    external_id: str,
    canonical_table: str,
) -> uuid.UUID | None:
    """Look up the canonical ID for a given source + external_id."""
    stmt = select(ExternalLink.canonical_id).where(
        ExternalLink.source == source,
        ExternalLink.external_id == external_id,
        ExternalLink.canonical_table == canonical_table,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row


def extract_links_from_text(text: str) -> list[dict[str, Any]]:
    """Scan text for known URLs and return potential cross-system links.

    Returns a list of dicts with keys: source, canonical_table, external_id, url.
    """
    if not text:
        return []

    links: list[dict[str, Any]] = []
    for source, table, pattern in URL_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if source == "gitlab" and table == "work_item":
                # GitLab: project#iid or project!iid
                project = groups[0]
                iid = groups[1]
                sep = "#" if "/issues/" in match.group() else "!"
                external_id = f"{project}{sep}{iid}"
            elif source == "notion":
                # Notion: 32-char hex -> add dashes for UUID
                hex_id = groups[0]
                external_id = hex_id
            else:
                external_id = groups[0]

            links.append({
                "source": source,
                "canonical_table": table,
                "external_id": external_id,
                "url": match.group(),
                "confidence": 0.9,
            })

    return links


async def auto_link_from_text(
    session: AsyncSession,
    text: str,
    referring_table: str,
    referring_id: uuid.UUID,
) -> int:
    """Scan text for cross-system URLs and create external_link records.

    Returns the number of new links created.
    """
    found = extract_links_from_text(text)
    created = 0
    for link_info in found:
        existing = await resolve_external_id(
            session,
            link_info["source"],
            link_info["external_id"],
            link_info["canonical_table"],
        )
        if existing:
            # Link already exists — skip
            continue
        # Store the heuristic link for later manual confirmation
        await upsert_external_link(
            session,
            canonical_table=referring_table,
            canonical_id=referring_id,
            source=link_info["source"],
            external_id=link_info["external_id"],
            external_url=link_info["url"],
            link_type="auto",
            confidence=link_info.get("confidence", 0.8),
        )
        created += 1
    return created
