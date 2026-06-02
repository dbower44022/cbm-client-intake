"""Tests for the volunteer application -> Contact (Mentor) + CMentorProfile."""

from __future__ import annotations

import pytest

from forms.volunteer.orchestrator import (
    CONTACT,
    CONTACT_TYPE_MENTOR,
    MENTOR_PROFILE,
    submit_application,
)
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
        att_id = f"attachment-{self._n}"
        self.uploads.append(
            {"id": att_id, "filename": filename, "related_type": related_type, "field": field}
        )
        return att_id


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
        industry_experience=["Information Technology", "Manufacturing"],
        fluent_languages=["English"],
        currently_employed="No",
        terms_accepted=True,
        submission_token="tok-volunteer1",
    )
    base.update(overrides)
    return VolunteerApplication(**base)


async def test_creates_contact_and_mentor_profile():
    client = CapturingClient()
    ids = await submit_application(_application(), client)

    assert set(ids) == {"contactId", "mentorProfileId"}
    entities = [e for e, _ in client.creates]
    assert entities == [CONTACT, MENTOR_PROFILE]

    _, contact = client.creates[0]
    assert contact["cContactType"] == [CONTACT_TYPE_MENTOR]  # array, not string

    _, profile = client.creates[1]
    assert profile["name"] == "Grace Hopper"
    assert profile["contactRecordId"] == ids["contactId"]
    assert profile["mentorStatus"] == "Candidate"
    assert profile["mentorType"] == "Mentor"
    assert profile["termsAccepted"] is True
    assert profile["mentoringFocusAreas"] == ["Marketing", "Sales"]
    # Multi-select industry stored into a single enum -> first value only.
    assert profile["industrySector"] == "Information Technology"


async def test_matched_contact_is_reused_profile_still_created():
    client = CapturingClient(existing_contact="contact-existing-9")
    ids = await submit_application(_application(), client)

    assert ids["contactId"] == "contact-existing-9"
    entities = [e for e, _ in client.creates]
    assert entities == [MENTOR_PROFILE]  # contact reused, profile still created
    _, profile = client.creates[0]
    assert profile["contactRecordId"] == "contact-existing-9"


async def test_max_six_areas_enforced():
    with pytest.raises(ValueError):
        _application(areas_of_expertise=["a", "b", "c", "d", "e", "f", "g"])


async def test_terms_required():
    with pytest.raises(ValueError):
        _application(terms_accepted=False)


async def test_resume_uploaded_and_linked_on_profile():
    client = CapturingClient()
    sub = _application(
        resume={
            "filename": "resume.pdf",
            "content_type": "application/pdf",
            "data_base64": "aGVsbG8=",
        }
    )
    ids = await submit_application(sub, client)

    # The file is uploaded as an Attachment bound to the resumeUpload field...
    assert len(client.uploads) == 1
    up = client.uploads[0]
    assert up["filename"] == "resume.pdf"
    assert up["related_type"] == MENTOR_PROFILE
    assert up["field"] == "resumeUpload"
    # ...and its id is set on the profile so the file links on create.
    _, profile = client.creates[1]
    assert profile["resumeUploadId"] == up["id"]
    assert set(ids) == {"contactId", "mentorProfileId"}


async def test_no_resume_means_no_upload():
    client = CapturingClient()
    await submit_application(_application(), client)
    assert client.uploads == []
    _, profile = client.creates[1]
    assert "resumeUploadId" not in profile


async def test_unsupported_resume_type_rejected():
    with pytest.raises(ValueError):
        _application(
            resume={
                "filename": "malware.exe",
                "content_type": "application/x-msdownload",
                "data_base64": "AAAA",
            }
        )
