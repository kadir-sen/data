"""Google Meet mapper: raw_event payload -> doc_entry, person."""

from __future__ import annotations

import logging
from typing import Any

from app.jobs.mappers.base import BaseMapper, MapperResult

logger = logging.getLogger(__name__)


class GoogleMeetMapper(BaseMapper):
    """Maps Google Meet transcript / recording data to canonical entities.

    Handles entity_types: transcript, recording.

    Typically ingested from Google Drive API (transcript doc) or
    Calendar API (event with Meet link).
    """

    source = "google_meet"

    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        dispatch = {
            "transcript": self._map_transcript,
            "recording": self._map_recording,
        }
        handler = dispatch.get(entity_type)
        if not handler:
            return MapperResult(errors=[f"Unsupported Google Meet entity_type: {entity_type}"])
        try:
            return handler(entity_id, payload)
        except Exception as exc:
            logger.exception("Google Meet mapper error for %s/%s", entity_type, entity_id)
            return MapperResult(errors=[f"Google Meet mapper error: {exc}"])

    def _map_transcript(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()

        # Participants
        participants = payload.get("participants", [])
        for p in participants:
            if p.get("email") or p.get("id"):
                result.persons.append({
                    "source": "google_meet",
                    "source_id": p.get("id", p.get("email", "")),
                    "display_name": p.get("displayName", p.get("email", "Unknown")),
                    "email": p.get("email"),
                })

        # Organizer
        organizer = payload.get("organizer", {})
        author_source_id = None
        if organizer.get("email") or organizer.get("id"):
            author_source_id = organizer.get("id", organizer.get("email", ""))
            result.persons.append({
                "source": "google_meet",
                "source_id": author_source_id,
                "display_name": organizer.get("displayName", organizer.get("email", "Unknown")),
                "email": organizer.get("email"),
            })

        # Transcript text
        transcript_entries = payload.get("transcript", [])
        body_text = "\n".join(
            f"[{entry.get('speaker', 'Unknown')}] {entry.get('text', '')}"
            for entry in transcript_entries
        ) if isinstance(transcript_entries, list) else str(transcript_entries)

        meeting_title = payload.get("title", payload.get("summary", "Untitled Meeting"))

        result.doc_entries.append({
            "source": "google_meet",
            "source_id": entity_id,
            "title": f"Transcript: {meeting_title}",
            "doc_type": "transcript",
            "url": payload.get("meetingUrl") or payload.get("hangoutLink"),
            "body_text": body_text or None,
            "author_source": "google_meet" if author_source_id else None,
            "author_source_id": author_source_id,
            "space_or_parent": None,
            "labels": ["meeting", "transcript"],
            "occurred_at": payload.get("startTime") or payload.get("start", {}).get("dateTime"),
            "extra": {
                "meeting_id": payload.get("meetingId") or payload.get("conferenceId"),
                "end_time": payload.get("endTime") or payload.get("end", {}).get("dateTime"),
                "duration_minutes": payload.get("durationMinutes"),
                "participant_count": len(participants),
                "calendar_event_id": payload.get("calendarEventId"),
                "recording_url": payload.get("recordingUrl"),
            },
        })

        result.external_links.append({
            "canonical_table": "doc_entry",
            "source": "google_meet",
            "external_id": entity_id,
            "external_url": payload.get("meetingUrl") or payload.get("hangoutLink"),
            "link_type": "auto",
            "confidence": 1.0,
        })

        return result

    def _map_recording(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()

        meeting_title = payload.get("title", payload.get("summary", "Untitled Recording"))

        result.doc_entries.append({
            "source": "google_meet",
            "source_id": entity_id,
            "title": f"Recording: {meeting_title}",
            "doc_type": "meeting_notes",
            "url": payload.get("recordingUrl") or payload.get("webViewLink"),
            "body_text": None,
            "author_source": None,
            "author_source_id": None,
            "space_or_parent": None,
            "labels": ["meeting", "recording"],
            "occurred_at": payload.get("startTime"),
            "extra": {
                "meeting_id": payload.get("meetingId"),
                "file_id": payload.get("fileId"),
                "mime_type": payload.get("mimeType"),
                "size_bytes": payload.get("size"),
            },
        })

        return result
