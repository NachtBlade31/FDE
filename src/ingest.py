"""Ingest — normalise tickets from all four channels (A2, FR-01 to FR-03).

Build Specification section 03 requires ingest to produce one representation
regardless of channel, preserve the original text and the channel, and handle
missing fields, unusual characters and empty bodies without failing.

The design principle here is that ingest is *defensive by default and strict in
exactly one place*. Every field except `ticket_id` degrades to a documented
fallback, because a run that stops on the fortieth ticket fails A9. `ticket_id`
is the exception: without it, decisions cannot be reconciled against tickets
(A8), so a ticket that lacks one is rejected rather than given a fabricated id.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from src.models import (
    Channel,
    CustomerRegion,
    CustomerTier,
    LanguageFluency,
    NormalisedTicket,
    TicketHistory,
    TicketLabels,
)


class IngestError(ValueError):
    """Raised only when a ticket cannot be given an identity."""


def _text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp, returning None rather than raising (A11)."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _submodel(raw: Mapping[str, Any], key: str, model: type) -> Any:
    """Build an optional nested model, tolerating absence or the wrong shape."""
    value = raw.get(key)
    if not isinstance(value, Mapping):
        return None
    try:
        return model(**value)
    except (TypeError, ValueError):
        return None


def normalise_ticket(raw: Any) -> NormalisedTicket:
    """Convert one raw ticket into the single internal representation.

    Unknown enum values (channel, tier, region, fluency) resolve to a documented
    fallback rather than raising, so an unfamiliar value in the hidden set cannot
    stop the run.
    """
    if not isinstance(raw, Mapping):
        raise IngestError(f"ticket must be a mapping, got {type(raw).__name__}")

    ticket_id = _text(raw, "ticket_id").strip()
    if not ticket_id:
        raise IngestError("ticket_id is required: decisions cannot be reconciled without it")

    degraded: list[str] = []

    def enum_field(key: str, enum_cls: type) -> Any:
        """Coerce an enum field, recording the coercion when it was not exact."""
        raw_value = _text(raw, key)
        member = enum_cls(raw_value)
        if member.value != raw_value:
            degraded.append(key)
        return member

    received_at = _parse_timestamp(raw.get("received_at"))
    if received_at is None:
        degraded.append("received_at")

    return NormalisedTicket(
        ticket_id=ticket_id,
        channel=enum_field("channel", Channel),
        subject=_text(raw, "subject"),
        original_body=_text(raw, "body"),
        received_at=received_at,
        customer_id=_text(raw, "customer_id"),
        customer_name=_text(raw, "customer_name"),
        customer_tier=enum_field("customer_tier", CustomerTier),
        customer_region=enum_field("customer_region", CustomerRegion),
        language_fluency=enum_field("language_fluency", LanguageFluency),
        labels=_submodel(raw, "labels", TicketLabels),
        history=_submodel(raw, "history", TicketHistory),
        degraded_fields=tuple(degraded),
    )


def normalise_batch(raws: list[Any]) -> tuple[list[NormalisedTicket], list[dict[str, Any]]]:
    """Normalise many tickets, collecting rejections instead of raising.

    A9 requires that no ticket is silently dropped. Returning rejections
    alongside the tickets lets the harness account for every input record.
    """
    tickets: list[NormalisedTicket] = []
    rejected: list[dict[str, Any]] = []

    for index, raw in enumerate(raws):
        try:
            tickets.append(normalise_ticket(raw))
        except IngestError as exc:
            rejected.append({"index": index, "reason": str(exc)})

    return tickets, rejected
