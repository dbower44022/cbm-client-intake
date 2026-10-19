"""The lead's CRM layouts at the code release (coutreach-lead-model-crm-handoff.md § 7)."""
from scripts.apply_lead_layouts import detail_fields, rewrite_detail, rewrite_list


DETAIL = [
    {"label": "Overview", "rows": [[{"name": "name"}, {"name": "funnelStage"}],
                                   [{"name": "entryStage"}, {"name": "stageChangedAt"}],
                                   [{"name": "entryDoor"}, False]]},
]


def test_detail_replaces_each_retired_field_in_its_place():
    new, changes = rewrite_detail(DETAIL)
    rows = new[0]["rows"]
    assert rows[0] == [{"name": "name"}, {"name": "leadStatus"}]
    assert rows[1] == [{"name": "leadStatusChangedAt"}, False]
    assert rows[2] == [{"name": "leadSource"}, False]
    assert len(new) == 1 and len(changes) == 4
    assert DETAIL[0]["rows"][0][1] == {"name": "funnelStage"}          # the input is not mutated


def test_detail_is_idempotent_and_adds_missing_fields_in_a_panel():
    new, _ = rewrite_detail(DETAIL)
    again, changes = rewrite_detail(new)
    assert again == new and changes == []
    bare, changes = rewrite_detail([{"label": "Overview", "rows": [[{"name": "name"}, False]]}])
    assert bare[-1]["label"] == "Lead"
    assert {"leadStatus", "leadStatusChangedAt", "leadSource"} <= detail_fields(bare)


def test_list_replaces_columns_in_place_and_keeps_the_rest():
    cols = [{"name": "name", "link": True}, {"name": "funnelStage"}, {"name": "entryDoor"},
            {"name": "sideExit"}, {"name": "website"}]
    new, changes = rewrite_list(cols)
    assert [c["name"] for c in new] == ["name", "leadStatus", "leadSource", "sideExit", "website"]
    assert new[0] == {"name": "name", "link": True}
    assert rewrite_list(new) == (new, [])
