"""Business Evaluation as a survey purpose (ruling BE23): the first kind of
survey on the survey engine. Importing this module registers it.

Its links point at the engagement (``CEngagement``); its switch is
``BUSINESS_EVALUATION``; its links last ``EVALUATION_LINK_DAYS`` and its
refused submits are retried every ``EVALUATION_RETRY_SECONDS`` (both settings
kept their names, prompt for phase 2b item 7). The page's words below are the
phase 1 page's, unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

from core.espo import EspoError
from surveys import registry

from . import service
from .surveys import RULES, SURVEY_DIR, Survey

PAGE = registry.PageText(
    title="Business Evaluation",
    consent_intro=(
        "<p>Your mentor has offered you a free evaluation of your business. You will answer a\n"
        "        few short surveys. There are no right or wrong answers, and you can stop at any\n"
        "        time and come back to this page later: your answers are saved as you go.</p>\n"
        "      <p>When you submit a survey, your answers are processed by an AI service to prepare\n"
        "        a draft report. Your mentor reviews and corrects that draft before you see any of it.\n"
        "        Your answers and the report are kept with your record at {{org}}.</p>"
    ),
    consent_label=(
        "I agree that my answers may be processed by an AI service and kept with my\n"
        "            record at {{org}}, as described above."
    ),
    list_intro=(
        "Start with the first survey. You can stop at any time and come back\n"
        "        to this page later; your answers are saved as you go."
    ),
    all_done=(
        "Thank you. You have submitted every\n"
        "        survey. Your mentor will be in touch to go through the results with you."
    ),
)


def _client(app: Any):
    """The CRM client the submit writes through: the org-wide key, or the
    dry run (``app.state.evaluation_client``, set by ``core/app.py``)."""
    factory = getattr(app.state, "evaluation_client", None)
    return factory() if factory is not None else None


PURPOSE = registry.register(registry.SurveyPurpose(
    key=service.PURPOSE,
    switch="business_evaluation",
    link_days="evaluation_link_days",
    retry_seconds="evaluation_retry_seconds",
    definitions_dir=SURVEY_DIR,
    loader=RULES,
    surveys_for=service.survey_keys,
    page=PAGE,
    submit=service.submit,
    first_save=service.first_save,
    client=_client,
    retryable=(EspoError,),
))


def load_surveys() -> Optional[dict[str, Survey]]:
    """Read and check Business Evaluation's definitions now (start-up)."""
    return registry.load_definitions(service.PURPOSE)


def surveys() -> Optional[dict[str, Survey]]:
    """Business Evaluation's definitions, read once and kept. None when one
    is invalid (logged as an ERROR)."""
    return registry.definitions(service.PURPOSE)
