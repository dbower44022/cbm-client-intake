"""The lead model's value move (ruling 45): the per-lead rules."""
from scripts.migrate_lead_model_values import STAGE_MOVES, lead_changes


def test_converted_wins_over_stage_and_exit():
    out, note = lead_changes({"funnelStage": "Lead", "sideExit": "Already known",
                              "promotedContactId": "c1", "entryDoor": "List"})
    assert out == {"leadStatus": "Converted", "sideExit": "Duplicate", "leadSource": "List"}
    assert note is None


def test_unqualified_exit_becomes_disqualified_status():
    out, _ = lead_changes({"funnelStage": "Unverified", "sideExit": "Unqualified"})
    assert out == {"leadStatus": "Disqualified", "sideExit": ""}


def test_early_stages_map_and_default_is_not_rewritten():
    assert lead_changes({"funnelStage": "Qualified"})[0] == {"leadStatus": "Qualified"}
    assert lead_changes({"funnelStage": "Unverified"})[0] == {"leadStatus": "Unqualified"}
    assert lead_changes({"funnelStage": "Unverified", "leadStatus": "Unqualified"})[0] == {}


def test_a_status_the_application_set_is_never_lowered():
    out, _ = lead_changes({"funnelStage": "Unverified", "leadStatus": "Disqualified"})
    assert "leadStatus" not in out


def test_contact_without_a_converted_record_needs_a_human():
    out, note = lead_changes({"funnelStage": "Warm Lead"})
    assert "leadStatus" not in out
    assert note and "ruling 42" in note


def test_lead_source_is_never_overwritten():
    assert "leadSource" not in lead_changes({"entryDoor": "List", "leadSource": "State filing"})[0]


def test_stage_moves():
    assert STAGE_MOVES == {"Unverified": "Prospect", "Qualified": "Prospect",
                           "Lead": "Prospect", "Warm Lead": "Engaged"}
