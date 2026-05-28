"""Tests for the volunteer application -> single Contact (Mentor)."""

from __future__ import annotations

import pytest

from forms.volunteer.orchestrator import CONTACT, MENTOR, submit_application
from forms.volunteer.schemas import VolunteerApplication


class CapturingClient:
    def __init__(self, existing_contact=None):
        self.creates: list[tuple[str, dict]] = []
        self.uploads: list[dict] = []
        self._existing_contact = existing_contact
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def find_one(self, entity, attribute, value):
        if entity == CONTACT and self._existing_contact:
            return {"id": self._existing_contact}
        return None

    async def upload_attachment(self, *, filename, content_type, data_base64, related_type, field):
        self._n += 1
        self.uploads.append(
            {"filename": filename, "related_type": related_type, "field": field}
        )
        return f"attachment-{self._n}"


def _application(**overrides) -> VolunteerApplication:
    base = dict(
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        confirm_email="grace@example.com",
        zip_code="44113",
        phone="216-555-0144",
        why_volunteer="I want to give back to small businesses.",
        areas_of_expertise=["Marketing", "Sales"],
        industry_experience=["Information Technology"],
        currently_employed="No",
        terms_accepted=True,
        submission_token="tok-volunteer1",
    )
    base.update(overrides)
    return VolunteerApplication(**base)


async def test_creates_single_mentor_contact():
    client = CapturingClient()
    ids = await submit_application(_application(), client)

    assert set(ids) == {"contactId"}
    assert len(client.creates) == 1
    entity, payload = client.creates[0]
    assert entity == CONTACT
    assert payload["cContactType"] == MENTOR
    assert payload["cMentorStatus"] == "Submitted"
    assert payload["currentlyEmployed"] is False  # "No" -> not employed


async def test_matched_contact_is_reused():
    client = CapturingClient(existing_contact="mentor-existing-9")
    ids = await submit_application(_application(), client)

    assert ids["contactId"] == "mentor-existing-9"
    assert client.creates == []


async def test_max_six_areas_enforced():
    with pytest.raises(ValueError):
        _application(areas_of_expertise=["a", "b", "c", "d", "e", "f", "g"])


async def test_terms_required():
    with pytest.raises(ValueError):
        _application(terms_accepted=False)


async def test_resume_uploaded_and_attached():
    client = CapturingClient()
    sub = _application(
        resume={
            "filename": "resume.pdf",
            "content_type": "application/pdf",
            "data_base64": "aGVsbG8=",
        }
    )
    await submit_application(sub, client)

    assert len(client.uploads) == 1
    assert client.uploads[0]["related_type"] == CONTACT
    _, payload = client.creates[0]
    assert payload["cResumeIds"] == ["attachment-1"]


async def test_unsupported_resume_type_rejected():
    with pytest.raises(ValueError):
        _application(
            resume={
                "filename": "malware.exe",
                "content_type": "application/x-msdownload",
                "data_base64": "AAAA",
            }
        )


async def test_no_resume_means_no_upload():
    client = CapturingClient()
    await submit_application(_application(), client)
    assert client.uploads == []
    _, payload = client.creates[0]
    assert "cResumeIds" not in payload
