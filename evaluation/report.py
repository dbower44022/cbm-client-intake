"""The Business Evaluation report (ruling BE16): one schema for the Claude
API's structured output, and one template that renders it as the
``draftReport`` HTML.

Every report has the same sections, in this order: summary; a score per
rubric dimension with the reason; strengths; gaps; recommended action items
(title, reason, priority, time horizon); information the client did not give,
headed "Questions to explore" (Doug, 11-14-26);
and the points the analysis is unsure of. The last section is for reviewers
only: it carries ``data-internal="true"`` so the client version (ruling BE19,
phase 5) can leave it out.

The HTML uses only headings, paragraphs, lists and tables, which the CRM's
wysiwyg field and the shared ``CBMRichText`` editor keep as they are.
Template version: ``TEMPLATE_VERSION``.
"""

from __future__ import annotations

import html
from typing import Literal, Optional

from pydantic import BaseModel, Field

TEMPLATE_VERSION = "report.v1"

Priority = Literal["High", "Medium", "Low"]
Horizon = Literal["Next 30 days", "Next 90 days", "Next 12 months"]


class DimensionScore(BaseModel):
    dimension_id: str = Field(description="The rubric dimension's id.")
    score: Optional[int] = Field(
        description="1 to 5, or null when the answers give too little to score it "
                    "or it cannot apply yet.")
    reason: str = Field(description="One or two sentences naming the answers the score rests on.")


class Point(BaseModel):
    point: str = Field(description="The strength or gap, in one sentence.")
    evidence: str = Field(description="The answers it rests on, in plain words.")


class ActionItem(BaseModel):
    title: str = Field(description="Starts with a verb.")
    reason: str = Field(description="Links the item to a gap and to the owner's goals.")
    priority: Priority
    time_horizon: Horizon


class Report(BaseModel):
    """The structured output the Claude API returns for one evaluation area."""

    summary: str
    scores: list[DimensionScore]
    strengths: list[Point]
    gaps: list[Point]
    action_items: list[ActionItem]
    missing_information: list[str]
    points_to_check: list[str]


def _e(text: object) -> str:
    return html.escape(str(text or ""), quote=False)


def _points(items: list[Point]) -> str:
    if not items:
        return "<p>None.</p>"
    rows = "".join(f"<li><strong>{_e(p.point)}</strong> {_e(p.evidence)}</li>" for p in items)
    return f"<ul>{rows}</ul>"


def _plain_list(items: list[str], empty: str) -> str:
    if not items:
        return f"<p>{_e(empty)}</p>"
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>"


def render(report: Report, *, area: str, company: str,
           dimension_names: dict[str, str]) -> str:
    """The draft report as HTML. ``dimension_names`` maps each rubric
    dimension id to its name, in the rubric's order; a score for an id the
    rubric does not have is shown under the id itself."""
    score_rows = "".join(
        "<tr>"
        f"<td>{_e(dimension_names.get(s.dimension_id, s.dimension_id))}</td>"
        f"<td>{_e(f'{s.score} of 5') if s.score else 'Not scored'}</td>"
        f"<td>{_e(s.reason)}</td>"
        "</tr>"
        for s in report.scores
    )
    action_rows = "".join(
        "<tr>"
        f"<td>{n}</td>"
        f"<td><strong>{_e(a.title)}</strong><br>{_e(a.reason)}</td>"
        f"<td>{_e(a.priority)}</td>"
        f"<td>{_e(a.time_horizon)}</td>"
        "</tr>"
        for n, a in enumerate(report.action_items, start=1)
    )
    return (
        f"<h2>{_e(area)} evaluation: {_e(company)}</h2>"
        "<h3>Summary</h3>"
        f"<p>{_e(report.summary)}</p>"
        "<h3>Scores</h3>"
        "<table><thead><tr><th>Area</th><th>Score</th><th>Why</th></tr></thead>"
        f"<tbody>{score_rows}</tbody></table>"
        "<h3>Strengths</h3>"
        f"{_points(report.strengths)}"
        "<h3>Gaps</h3>"
        f"{_points(report.gaps)}"
        "<h3>Recommended action items</h3>"
        "<table><thead><tr><th>#</th><th>Action</th><th>Priority</th><th>When</th></tr></thead>"
        f"<tbody>{action_rows}</tbody></table>"
        "<h3>Questions to explore</h3>"
        f"{_plain_list(report.missing_information, 'No open questions.')}"
        '<div data-internal="true">'
        "<h3>Points to check (for reviewers only)</h3>"
        f"{_plain_list(report.points_to_check, 'Nothing to check.')}"
        "</div>"
    )
