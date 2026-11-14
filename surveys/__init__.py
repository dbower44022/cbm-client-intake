"""The survey engine (prds/business-evaluation-plan.md, ruling BE23).

What any kind of survey uses: the survey definition format and loader
(``definitions``), answer checking and the readable text (``answers``), the
link store and the saved answers (``store``), the submit retry (``service``),
and the public answer page (``router``, ``frontend/``).

A **survey purpose** is one kind of survey built on the engine. It registers
itself in ``registry`` and decides which surveys a link opens, what the first
screen says, and what happens on submit. Business Evaluation (``evaluation/``)
is the first. **This package holds no code specific to any survey purpose and
never imports one**; ``tests/test_survey_engine.py`` fails if it does. How to
add a survey purpose: ``surveys/CLAUDE.md``.
"""
