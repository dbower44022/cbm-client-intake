"""The chapter information form: one set of questions, read from stage 8 of the
deployment guide, drives the guide, the web page and the values file (09-23-26).

These tests hold the three together: every setting the build scripts read is a
question on the form, the page carries every question, and a page's answers turn
into a values file the settings generator accepts."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "scripts" / "chapter_form"))
form = _load("scripts/chapter_form/fields.py", "fields")
to_values = _load("scripts/chapter_form/to_values.py", "to_values_under_test")
build_page = _load("scripts/chapter_form/build_page.py", "build_page_under_test")

KINDS = {"text", "slug", "url", "email", "domain", "bool", "choice"}

# Every form key a build script reads (render_spec.build_spec, apply_api_half.chapter_settings).
READ_BY_BUILD = {
    "chapter.name", "chapter.slug", "chapter.timezone", "chapter.currency", "chapter.locale",
    "web.app_base_url", "web.website_base_url", "web.docs_site_url", "web.chapter_tokens_url",
    "web.policy_client_conduct_url", "web.policy_mentor_ethics_url", "web.policy_terms_url", "web.policy_privacy_url",
    "google.primary_domain", "google.ops_mailbox", "google.alert_email_from", "google.alert_email_to",
    "google.members_group", "google.mentor_email_domain", "google.delegated_admin", "google.shared_drive_id",
    "google.zoom_host_email", "zoom.account_id", "zoom.client_id",
    "crm.base_url", "crm.application_name", "crm.outbound_from_name", "crm.outbound_from_address",
    "flags.espo_dry_run", "flags.async_delivery", "flags.analytics_enabled", "flags.setup_enabled",
    "flags.events_enabled", "flags.events_public_api", "flags.record_quick_add", "flags.mentor_provision_users",
    "flags.deploy_on_push", "flags.gmail_sync", "flags.gcal_events", "flags.gdrive_docs",
    "flags.google_directory_check", "flags.google_create_mailbox", "flags.gdrive_identity", "flags.zoom_events",
}


def test_every_question_is_complete():
    keys = [f["key"] for f in form.all_fields()]
    assert len(keys) == len(set(keys)), "a question is asked twice"
    for f in form.all_fields():
        for part in ("key", "label", "by", "kind", "meaning", "source", "wrong"):
            assert f.get(part), f"{f.get('key')}: missing {part}"
        assert f["by"] in {"chapter", "central"}, f["key"]
        assert f["kind"] in KINDS, f["key"]
        if f["kind"] == "choice":
            assert f.get("options"), f["key"]
        if f.get("show_if"):
            assert f["show_if"] in keys, f["key"]


def test_every_setting_the_build_reads_is_asked():
    missing = READ_BY_BUILD - {f["key"] for f in form.all_fields()}
    assert not missing, f"the build reads settings the form never asks: {sorted(missing)}"


def test_every_switch_has_a_recommended_answer():
    for f in form.all_fields():
        if f["key"].startswith("flags."):
            assert "default" in f, f["key"]


@pytest.mark.parametrize("kind,good,bad", [
    ("slug", "boston", "Boston MA"),
    ("slug", "boston-mentors", "a" * 26),
    ("slug", "b2", "boston-"),
    ("url", "https://bbmentors.org/privacy/", "bbmentors.org"),
    ("email", "info@bbmentors.org", "info at bbmentors"),
    ("domain", "bbmentors.org", "https://bbmentors.org"),
])
def test_answer_checks(kind, good, bad):
    f = {"kind": kind, "required": True}
    assert form.problem(f, {"value": good}) is None
    assert form.problem(f, {"value": bad})


def test_checks_are_plain_enough_for_the_page():
    # The page runs these patterns in JavaScript; keep them to the shared subset.
    for pattern, _ in form.CHECKS.values():
        assert "(?<" not in pattern and "(?P" not in pattern
        re.compile(pattern)


def _answers(**over):
    a = {}
    for f in form.all_fields():
        if f.get("later"):
            continue
        if "default" in f:
            v = f["default"]
        elif f["kind"] == "url":
            v = "https://bbmentors.org/x/"
        elif f["kind"] == "email":
            v = "info@bbmentors.org"
        elif f["kind"] == "domain":
            v = "bbmentors.org"
        elif f["kind"] == "slug":
            v = "boston"
        else:
            v = "Boston Business Mentors"
        a[f["key"]] = {"value": v, "at": "2026-09-23T12:00:00Z"}
    a["google.shared_drive_id"] = {"value": "0ABCdrive", "at": "2026-09-23T12:00:00Z"}
    for k, v in over.items():
        a[k.replace("__", ".")] = v
    return a


def _block(answers, signoffs=None):
    return form.BLOCK_HEADER + "\n" + json.dumps(
        {"chapter": "Boston Business Mentors", "answers": answers, "signoffs": signoffs or []})


def test_a_complete_page_writes_a_values_file_the_generator_accepts(tmp_path, monkeypatch):
    monkeypatch.setattr(to_values, "CHAPTERS", tmp_path)
    src = tmp_path / "answers.txt"
    src.write_text(_block(_answers(), [{"name": "A One", "date": "09-23-26"}, {"name": "B Two", "date": "09-23-26"}]))
    assert to_values.main(["x", str(src)]) == 0
    out = tmp_path / "boston-values.yaml"
    text = out.read_text()
    assert "reviewed by: A One and B Two" in text
    values = yaml.safe_load(text)
    assert values["web"]["events_public_base_url"] == ""
    assert values["flags"]["gmail_sync"] is True and values["flags"]["deploy_on_push"] is True
    assert "ZOOM_CLIENT_SECRET" not in values["secrets"] and "APP_ENCRYPTION_KEY" in values["secrets"]
    assert to_values.generator_problems(values) == ([], [])


def test_a_missing_answer_is_named_by_its_label(tmp_path, capsys):
    a = _answers()
    del a["web.policy_privacy_url"]
    src = tmp_path / "answers.txt"
    src.write_text(_block(a))
    assert to_values.main(["x", str(src), "--check"]) == 1
    assert "Web address (URL) of your privacy policy page (web.policy_privacy_url): Not answered yet. Answer it, or mark it not known yet." in capsys.readouterr().out


def test_any_question_can_be_marked_not_known_yet_and_is_listed_as_owed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(to_values, "CHAPTERS", tmp_path)
    a = _answers(web__policy_privacy_url={"notYet": True}, crm__base_url={"notYet": True})
    src = tmp_path / "answers.txt"
    src.write_text(_block(a))
    assert to_values.main(["x", str(src)]) == 0
    out = capsys.readouterr().out
    assert "privacy policy page (web.policy_privacy_url): marked not known yet; needed by step 17.3" in out
    assert "(crm.base_url): marked not known yet; needed by step 9.10" in out
    text = (tmp_path / "boston-values.yaml").read_text()
    assert "# OWED" in text and yaml.safe_load(text)["web"]["policy_privacy_url"] == ""


def test_the_short_label_must_be_known_to_write_the_file(tmp_path, capsys):
    src = tmp_path / "answers.txt"
    src.write_text(_block(_answers(chapter__slug={"notYet": True})))
    assert to_values.main(["x", str(src), "--check"]) == 1
    assert "Short label (chapter.slug): must be known" in capsys.readouterr().out


def test_the_shared_drive_is_owed_later_not_a_failure(tmp_path, capsys):
    a = _answers()
    del a["google.shared_drive_id"]
    src = tmp_path / "answers.txt"
    src.write_text(_block(a))
    assert to_values.main(["x", str(src), "--check"]) == 0
    assert "owed later: Shared drive identifier" in capsys.readouterr().out


def test_zoom_questions_count_only_for_a_webinar_chapter(tmp_path):
    a = _answers()
    for k in ("google.zoom_host_email", "zoom.account_id", "zoom.client_id"):
        a.pop(k, None)
    assert to_values.answer_problems(a) == []
    a["flags.zoom_events"] = {"value": True}
    assert len(to_values.answer_problems(a)) == 3
    a.update({"google.zoom_host_email": {"value": "webinars@bbmentors.org"},
              "zoom.account_id": {"value": "acc"}, "zoom.client_id": {"value": "cli"}})
    values = to_values.build_values(a)
    assert "ZOOM_CLIENT_SECRET" in values["secrets"]


def test_a_secret_pasted_into_the_form_is_refused():
    a = _answers(zoom__client_id={"value": "-----BEGIN PRIVATE KEY-----"})
    a["flags.zoom_events"] = {"value": True}
    assert any("looks like a secret" in p for p in to_values.answer_problems(a))


def test_a_block_from_elsewhere_is_refused(tmp_path):
    src = tmp_path / "answers.txt"
    src.write_text("hello\n{}")
    assert to_values.main(["x", str(src)]) == 2


def test_the_page_carries_every_question_and_no_placeholder():
    html = build_page.build("Boston Business Mentors", "Boston Chapter Information")
    assert "{{" not in html
    assert "<title>Boston Chapter Information</title>" in html
    for f in form.all_fields():
        assert f'"{f["key"]}"' in html, f["key"]
    for pattern, _ in form.CHECKS.values():
        assert json.dumps(pattern)[1:-1] in html
