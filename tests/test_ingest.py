"""Ingest tests — acceptance criterion A2.

A2: "Tickets from all four channels are ingested and normalised into one internal
representation." Judged by passing a ticket from each channel and confirming all
four are handled without channel-specific breakage.

Build Specification section 03 additionally requires ingest to:
  - produce one normalised representation regardless of source channel
  - preserve the original text and the channel, because both matter downstream
  - handle missing fields, unusual characters and empty bodies without failing
"""

import pytest

from src.ingest import IngestError, normalise_ticket
from src.models import Channel, CustomerTier, LanguageFluency, NormalisedTicket


def _raw(**overrides):
    """A well-formed raw ticket in the pack's schema, with overrides applied."""
    base = {
        "ticket_id": "DEV-0001",
        "channel": "email",
        "subject": "Cannot log in to the console",
        "body": "I have been trying to sign in since this morning without success.",
        "received_at": "2026-03-14T09:22:00Z",
        "customer_id": "CUST-1042",
        "customer_name": "Priya Sharma",
        "customer_tier": "business",
        "customer_region": "europe",
        "language_fluency": "fluent",
    }
    base.update(overrides)
    return base


# --- A2: all four channels normalise to one representation -------------------


@pytest.mark.parametrize("channel", ["email", "chat", "docs_comment", "forum"])
def test_all_four_channels_normalise_to_the_same_type(channel):
    """Every channel yields a NormalisedTicket — no channel-specific breakage."""
    ticket = normalise_ticket(_raw(channel=channel))

    assert isinstance(ticket, NormalisedTicket)
    assert ticket.channel == Channel(channel)


def test_channel_is_preserved_because_it_matters_downstream():
    ticket = normalise_ticket(_raw(channel="forum"))

    assert ticket.channel is Channel.FORUM


def test_original_text_is_preserved_verbatim():
    """The Build Spec requires the original text to survive normalisation."""
    body = "  Deployment keeps rolling back.  \n\n  Please advise.  "
    ticket = normalise_ticket(_raw(body=body))

    assert ticket.original_body == body


# --- one internal representation ---------------------------------------------


def test_search_text_combines_subject_and_body():
    """Retrieval queries against one field, so ingest must produce one."""
    ticket = normalise_ticket(_raw(subject="Login fails", body="Invalid credentials."))

    assert "Login fails" in ticket.search_text
    assert "Invalid credentials." in ticket.search_text


def test_search_text_is_whitespace_normalised():
    ticket = normalise_ticket(_raw(subject="Login   fails", body="Bad\n\n\ncreds"))

    assert "  " not in ticket.search_text
    assert "\n" not in ticket.search_text


# --- Build Spec 03: handle missing fields and empty bodies without failing ----


def test_empty_subject_is_accepted_because_chat_tickets_have_none():
    """155 of the 500 development tickets have an empty subject."""
    ticket = normalise_ticket(_raw(channel="chat", subject=""))

    assert ticket.subject == ""
    assert ticket.search_text  # body alone still gives us something to retrieve on


def test_missing_subject_key_is_accepted():
    raw = _raw()
    del raw["subject"]

    ticket = normalise_ticket(raw)

    assert ticket.subject == ""


def test_empty_body_does_not_raise():
    """Build Spec 03: 'Handles ... empty bodies without failing.'"""
    ticket = normalise_ticket(_raw(body="", subject="Help"))

    assert ticket.original_body == ""
    assert ticket.is_empty is False  # subject still carries signal


def test_wholly_empty_ticket_is_flagged_rather_than_raising():
    """Nothing to work with must still produce a ticket, marked for escalation."""
    ticket = normalise_ticket(_raw(subject="", body="   "))

    assert ticket.is_empty is True


def test_unusual_characters_survive_normalisation():
    body = "Erreur d'authentification — 認証 失敗 ​ 🚀 <script>alert(1)</script>"
    ticket = normalise_ticket(_raw(body=body))

    assert ticket.original_body == body
    assert "認証" in ticket.search_text


def test_missing_fairness_segment_fields_become_unknown_not_the_majority_segment():
    """A defaulted ticket must never be indistinguishable from a genuine one.

    customer_tier and language_fluency are fairness-audit segments. Silently
    coercing them to `standard`/`fluent` would move tickets into the majority
    segment (50.6% and 76.0% of dev respectively), which is exactly where the
    pre-registered baseline of design section 2.4 is computed.
    """
    raw = _raw()
    for key in ("customer_tier", "customer_region", "language_fluency", "customer_name"):
        del raw[key]

    ticket = normalise_ticket(raw)

    assert ticket.customer_tier is CustomerTier.UNKNOWN
    assert ticket.language_fluency is LanguageFluency.UNKNOWN


def test_unknown_channel_falls_back_rather_than_raising():
    """The hidden set uses the same schema, but defensive ingest never crashes a run."""
    ticket = normalise_ticket(_raw(channel="carrier_pigeon"))

    assert ticket.channel is Channel.UNKNOWN


def test_unrecognised_tier_becomes_unknown_rather_than_a_real_segment():
    ticket = normalise_ticket(_raw(customer_tier="platinum"))

    assert ticket.customer_tier is CustomerTier.UNKNOWN


def test_unrecognised_fluency_becomes_unknown_rather_than_fluent():
    ticket = normalise_ticket(_raw(language_fluency="partial"))

    assert ticket.language_fluency is LanguageFluency.UNKNOWN


# --- degradation is recorded, so coercion is auditable after ingest ----------


def test_a_clean_ticket_records_no_degradation():
    ticket = normalise_ticket(_raw())

    assert ticket.degraded_fields == ()


def test_an_unrecognised_segment_value_is_recorded_as_degraded():
    """Without this residue the coercion is unrecoverable, and a widened or
    narrowed fairness gap cannot be told apart from silent segment migration."""
    ticket = normalise_ticket(_raw(customer_tier="platinum", language_fluency="partial"))

    assert "customer_tier" in ticket.degraded_fields
    assert "language_fluency" in ticket.degraded_fields


def test_an_unrecognised_channel_is_recorded_as_degraded():
    ticket = normalise_ticket(_raw(channel="carrier_pigeon"))

    assert "channel" in ticket.degraded_fields


def test_a_malformed_timestamp_is_recorded_as_degraded():
    ticket = normalise_ticket(_raw(received_at="not-a-timestamp"))

    assert "received_at" in ticket.degraded_fields


def test_a_missing_field_is_recorded_as_degraded():
    raw = _raw()
    del raw["customer_tier"]

    ticket = normalise_ticket(raw)

    assert "customer_tier" in ticket.degraded_fields


def test_degradation_of_one_field_does_not_implicate_another():
    ticket = normalise_ticket(_raw(customer_tier="platinum"))

    assert "customer_tier" in ticket.degraded_fields
    assert "customer_region" not in ticket.degraded_fields


# --- ticket_id is the one field we cannot invent -----------------------------


def test_missing_ticket_id_raises_because_decisions_could_not_be_reconciled():
    """A8 reconciles logged decisions against tickets by id. No id, no reconciliation."""
    raw = _raw()
    del raw["ticket_id"]

    with pytest.raises(IngestError, match="ticket_id"):
        normalise_ticket(raw)


def test_non_mapping_input_raises_ingest_error():
    with pytest.raises(IngestError):
        normalise_ticket("not a ticket")


# --- labels and history are optional: the hidden set may omit them -----------


def test_labels_are_optional_because_the_hidden_set_may_not_carry_them():
    raw = _raw()
    ticket = normalise_ticket(raw)

    assert ticket.labels is None


def test_labels_are_captured_when_present_for_evaluation():
    raw = _raw()
    raw["labels"] = {
        "intent": "authentication_failure",
        "urgency": "high",
        "expected_route": "auto_respond",
        "answerable_from_docs": True,
        "expected_doc_ids": ["DOC-AUTH-001"],
        "must_not_auto_respond": False,
    }

    ticket = normalise_ticket(raw)

    assert ticket.labels is not None
    assert ticket.labels.intent == "authentication_failure"
    assert ticket.labels.expected_doc_ids == ["DOC-AUTH-001"]
    assert ticket.labels.must_not_auto_respond is False


def test_malformed_received_at_falls_back_rather_than_crashing_the_run():
    """A11: malformed input must degrade, not stop the run."""
    ticket = normalise_ticket(_raw(received_at="not-a-timestamp"))

    assert ticket.received_at is None
    assert ticket.ticket_id == "DEV-0001"
