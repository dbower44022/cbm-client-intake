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
    def __init__(self, existing_contact=None, enum_options=None):
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self.uploads: list[dict] = []
        self._existing_contact = existing_contact
        # {field: [valid options]}; a field absent here returns None => "keep all".
        self._enum_options = enum_options or {}
        self._n = 0

    async def metadata_enum_options(self, entity, field):
        return self._enum_options.get(field)

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}

    async def find_one(self, entity, attribute, value, select="id"):
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
        areas_of_expertise=["Marketing & Branding", "Sales & Business Development"],
        industry_experience=["Technology & Software", "Manufacturing & Industrial"],
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
    # The single consent checkbox sets all three Contact bools.
    assert contact["cTermsOfUseAccepted"] is True
    assert contact["cPrivacyPolicyAccepted"] is True
    assert contact["cCodeOfConductAccepted"] is True

    _, profile = client.creates[1]
    assert profile["name"] == "Grace Hopper"
    assert profile["contactRecordId"] == ids["contactId"]
    assert profile["mentorStatus"] == "Candidate"
    assert profile["mentorType"] == "Mentor"
    assert profile["termsAccepted"] is True
    assert profile["mentorCodeAccepted"] is True  # mentor-specific code-of-conduct
    # Accepting the Code of Conduct IS the mentor code of ethics — sets the flag
    # /mentoradmin's completeness rule requires.
    assert profile["ethicsAgreementAccepted"] is True
    assert profile["areaOfExpertise"] == ["Marketing & Branding", "Sales & Business Development"]
    # Multi-select industry stored as a multiEnum -> all selections kept.
    assert profile["industryExperience"] == ["Technology & Software", "Manufacturing & Industrial"]


async def test_contact_method_and_employment_written_to_contact():
    """Pass A: 'how should we contact you' + employment status land on the
    Contact as cPreferredContactMethod / cEmploymentStatus."""
    client = CapturingClient()
    await submit_application(
        _application(contact_preference="Email", currently_employed="No"), client
    )
    _, contact = client.creates[0]
    assert contact["cPreferredContactMethod"] == "Email"
    assert contact["cEmploymentStatus"] == "No"


async def test_invalid_enum_values_dropped_record_still_created():
    """A drifted industry/language value is dropped (not fatal); the profile is
    created with the valid data + a note, so contact info is always captured."""
    client = CapturingClient(enum_options={
        "industryExperience": ["Technology & Software", "Healthcare & Medical"],
        "fluentLanguages": ["English", "Spanish"],
        # areaOfExpertise absent => not validated (kept as-is).
    })
    sub = _application(
        industry_experience=["Utilities"],          # not in the live enum
        fluent_languages=["English", "Klingon"],     # Klingon invalid
    )
    ids = await submit_application(sub, client)

    assert set(ids) == {"contactId", "mentorProfileId"}
    _, profile = client.creates[1]
    # Invalid industry omitted entirely; invalid language filtered out.
    assert "industryExperience" not in profile
    assert profile["fluentLanguages"] == ["English"]
    # A note records what was dropped, for staff follow-up.
    assert "industryExperience" in profile["description"]
    assert "Utilities" in profile["description"]
    assert "Klingon" in profile["description"]


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
