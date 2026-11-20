"""Feedback surveys as a survey purpose (ruling BE29): the second kind of
survey on the survey engine. Importing this module registers it.

Its links point at the engagement (``CEngagement``) or the event (``CEvent``);
its switch is ``FEEDBACK_SURVEYS``; its links last ``FEEDBACK_LINK_DAYS`` and
its refused submits are retried every ``FEEDBACK_RETRY_SECONDS``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from core.espo import EspoError
from surveys import registry
from surveys.definitions import LoaderRules, Survey, SurveyError

from . import config as cfg
from . import service

SURVEY_DIR = Path(__file__).parent / "surveys"


def _check(raw: dict, where: str) -> None:
    """Every feedback survey opens with the recommendation score, required."""
    sections = raw.get("sections") or []
    first = (((sections[0] or {}).get("questions") or [{}])[0]
             if sections and isinstance(sections[0], dict) else {}) or {}
    if first.get("id") != cfg.SCORE_QUESTION or first.get("type") != "score" \
            or first.get("required") is not True:
        raise SurveyError(f"{where}: a feedback survey's first question must be "
                          f"'{cfg.SCORE_QUESTION}', type score, required")
    if raw.get("key") not in cfg.SURVEY_KEYS:
        raise SurveyError(f"{where}: unknown feedback survey {raw.get('key')!r}")


RULES = LoaderRules(check=_check, required_keys=cfg.SURVEY_KEYS)

PAGE = registry.PageText(
    title="Your feedback",
    consent_intro=(
        "<p>Thank you for taking a moment to tell {{org}} how we did. It takes about two\n"
        "        minutes, and only the first question is needed.</p>\n"
        "      <p>Your answers are kept with your record at {{org}} and are read by our staff.\n"
        "        Answers about your mentoring are also read by your mentor.</p>"
    ),
    consent_label="I agree that my answers may be kept with my record at {{org}}, as described above.",
    list_intro="Your survey is below. Your answers are saved as you go.",
    all_done="Thank you. Your answers help us do better.",
    pending=("Your answers are submitted and safe with us. We will pass them on shortly; "
             "there is nothing more you need to do."),
)


def _client(app: Any):
    """The org-wide key, or the dry run: the same factory Business Evaluation's
    submit uses (``core/app.py``)."""
    factory = getattr(app.state, "evaluation_client", None)
    return factory() if factory is not None else None


PURPOSE = registry.register(registry.SurveyPurpose(
    key=cfg.PURPOSE,
    switch="feedback_surveys",
    link_days="feedback_link_days",
    retry_seconds="feedback_retry_seconds",
    definitions_dir=SURVEY_DIR,
    loader=RULES,
    surveys_for=service.survey_keys,
    page=PAGE,
    submit=service.submit,
    client=_client,
    retryable=(EspoError,),
))


def surveys() -> Optional[dict[str, Survey]]:
    """The feedback definitions, read once and kept. None when one is invalid."""
    return registry.definitions(cfg.PURPOSE)
