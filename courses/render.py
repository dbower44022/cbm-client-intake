"""The one reader of a training course's Markdown (prds/training-app-plan.md,
decision 4). ``scripts/build_runbook.py`` imports it to make the Claude page,
and the course page in the application draws from it, so the two can never
read a course differently.

The Markdown's shape (see ``training/evaluation-staff-course/evaluation-demo.md``):

* ``# Title`` then intro paragraphs (a ``Last Updated`` line becomes the
  page's revision line);
* ``## Before you start`` and any other ``##`` section without steps are
  shown as text;
* ``## N. Section`` holds steps, each ``### N.M Step title``;
* in a step: ``- **Where:**``, ``- **Action:**``, ``- **You should see:**``,
  ``- **If not:**``, ``- **What it does:**`` lines, and fenced blocks, each a
  copy box, labelled by the paragraph just above it;
* ``**Checkpoint:** …`` ends a section with what to report back;
* ``## Change log`` is left off the page.

Tokens (decision 5): ``{{training_url}}`` is the training system's address
and ``{{signin:<role>}}`` that role's training sign-in. A ``sub`` callable
receives HTML that is already escaped and returns it with the tokens
replaced; without one, the text is left as written.

Every text is escaped; only **bold**, *italic* and `code` are kept.
"""
from __future__ import annotations

import html
import json
import re
from typing import Callable, Optional

FIELDS = (("Where", "where"), ("Action", "act"), ("You should see", "exp"),
          ("If not", "fail"), ("What it does", "why"))

#: Replaces tokens in already-escaped HTML.
Sub = Callable[[str], str]

TRAINING_URL_TOKEN = "{{training_url}}"
SIGNIN_RE = re.compile(r"\{\{signin:([^{}]+)\}\}")
REVISION_RE = re.compile(r"Revision\s+(\d+)\.(\d+)")


def _same(text: str) -> str:
    return text


def inline(text: str, sub: Optional[Sub] = None) -> str:
    """Escape, then keep **bold**, *italic* and `code`, then fill the tokens."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<em>\1</em>", out)
    return (sub or _same)(out)


def plain(text: str) -> str:
    """The words of an inline text, with its marks taken off (for a label)."""
    return re.sub(r"\*\*|`|(?<![*\w])\*|\*(?![*\w])", "", text).strip()


def blocks(lines: list[str]) -> list[tuple[str, str]]:
    """Paragraphs, list items and fenced code, as (kind, text)."""
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            code = []
            while j < len(lines) and not lines[j].startswith("```"):
                code.append(lines[j])
                j += 1
            out.append(("code", "\n".join(code)))
            i = j + 1
            continue
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"^(\s*)[-*] (.*)$", line)
        if m:
            out.append(("sub" if m.group(1) else "li", m.group(2)))
        elif re.match(r"^\s*\d+\. ", line):
            out.append(("oli", re.sub(r"^\s*\d+\. ", "", line)))
        elif stripped.startswith("|"):
            out.append(("table", stripped))
        else:
            out.append(("p", stripped))
        i += 1
    return out


def parse(md: str) -> dict:
    lines = md.split("\n")
    title, revision, intro = "", "", []
    sections: list[dict] = []
    cur_sec: dict | None = None
    cur_step: dict | None = None
    body: list[str] = []

    def close_step():
        nonlocal cur_step, body
        if cur_step is not None:
            cur_step["blocks"] = blocks(body)
            cur_sec["steps"].append(cur_step)
        elif cur_sec is not None:
            cur_sec["text"] = blocks(body)
        elif body:
            intro.extend(body)
        cur_step, body = None, []

    for line in lines:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("Last Updated:") and not revision:
            revision = line.strip()
            continue
        if line.startswith("## "):
            close_step()
            name = line[3:].strip()
            cur_sec = {"title": name, "steps": [], "text": [], "skip": name == "Change log"}
            sections.append(cur_sec)
            continue
        if line.startswith("### ") and cur_sec is not None:
            close_step()
            m = re.match(r"^(\d+\.\d+)\s+(.*)$", line[4:].strip())
            num, name = (m.group(1), m.group(2)) if m else ("", line[4:].strip())
            cur_step = {"num": num, "title": name}
            continue
        body.append(line)
    close_step()
    return {"title": title, "revision": revision, "intro": blocks(intro), "sections": sections}


def revision_number(doc: dict) -> str:
    """``N.M`` from the ``Last Updated`` line, or "" when it carries none."""
    m = REVISION_RE.search(doc.get("revision") or "")
    return f"{m.group(1)}.{m.group(2)}" if m else ""


def step_key(step: dict) -> str:
    """The key a step's tick is saved under: its number (``3.2``)."""
    return step["num"] or step["title"]


def checkpoint_key(index: int, section: dict) -> str:
    """The key a section's checkpoint answer is saved under: ``cp-`` and the
    section's number (``cp-3``), or its place when it has none."""
    m = re.match(r"^(\d+)\.\s", section["title"])
    return f"cp-{m.group(1) if m else index + 1}"


def checkpoint_text(step: dict) -> str:
    """The raw checkpoint line a step ends its section with, or ""."""
    for kind, text in step["blocks"]:
        if kind == "p" and text.startswith("**Checkpoint:**"):
            return text[len("**Checkpoint:**"):].strip()
    return ""


def items(doc: dict) -> list[dict]:
    """Every step and checkpoint in course order: ``{"key", "kind", "label"}``,
    kind ``step`` or ``checkpoint``. What completing the course needs (TR1)."""
    out: list[dict] = []
    for index, sec in enumerate(doc["sections"]):
        if sec["skip"]:
            continue
        for step in sec["steps"]:
            out.append({"key": step_key(step), "kind": "step",
                        "label": f"{step['num']} {plain(step['title'])}".strip()})
            cp = checkpoint_text(step)
            if cp:
                out.append({"key": checkpoint_key(index, sec), "kind": "checkpoint",
                            "label": plain(cp), "section": plain(sec["title"])})
    return out


def _copy(code_html: str) -> str:
    return (f'<div class="copy"><code>{code_html}</code>'
            f'<button type="button" class="copybtn">Copy</button></div>')


def step_html(step: dict, sub: Optional[Sub] = None) -> tuple[str, str]:
    """The step's body, and its checkpoint line if the step ends a section."""
    sub = sub or _same
    fields: dict[str, str] = {}
    extra: list[str] = []
    checkpoint = ""
    label = ""
    for kind, text in step["blocks"]:
        if kind == "code":
            lab = f'<div class="lab">{inline(label, sub)}</div>' if label else ""
            extra.append(f'<div class="entry">{lab}{_copy(sub(html.escape(text)))}</div>')
            label = ""
            continue
        if label:
            extra.append(f'<p class="note">{inline(label, sub)}</p>')
            label = ""
        m = re.match(r"^\*\*([^*]+?):\*\*\s*(.*)$", text)
        if kind == "li" and m and m.group(1) in dict(FIELDS):
            key = dict(FIELDS)[m.group(1)]
            fields[key] = inline(m.group(2), sub)
            if key == "act":
                extra.append("__ACTION__")
            continue
        if kind == "p" and text.startswith("**Checkpoint:**"):
            checkpoint = inline(text[len("**Checkpoint:**"):].strip(), sub)
            continue
        if kind == "p":
            label = text
            continue
        extra.append(f'<p class="note">{inline(text, sub)}</p>')
    if label:
        extra.append(f'<p class="note">{inline(label, sub)}</p>')

    def row(lab: str, key: str) -> str:
        return (f'<div class="row"><div class="lab">{lab}</div><p>{fields[key]}</p></div>'
                if key in fields else "")

    parts = [row("Where", "where")]
    action = row("Action", "act")
    for piece in extra:
        parts.append(action if piece == "__ACTION__" else piece)
    if "__ACTION__" not in extra:
        parts.append(action)
    parts += [row("You should see", "exp"), row("If not", "fail"), row("What it does", "why")]
    return "".join(p for p in parts if p), checkpoint


def text_html(items_: list[tuple[str, str]], sub: Optional[Sub] = None) -> str:
    sub = sub or _same
    out: list[str] = []
    open_list = ""
    for kind, text in items_:
        want = {"li": "ul", "sub": "ul", "oli": "ol"}.get(kind, "")
        if open_list and want != open_list:
            out.append(f"</{open_list}>")
            open_list = ""
        if want and not open_list:
            out.append(f"<{want}>")
            open_list = want
        if kind in ("li", "sub", "oli"):
            out.append(f"<li>{inline(text, sub)}</li>")
        elif kind == "code":
            out.append(_copy(sub(html.escape(text))))
        elif kind == "table":
            continue
        else:
            out.append(f"<p>{inline(text, sub)}</p>")
    if open_list:
        out.append(f"</{open_list}>")
    return "".join(out)


# --- the tokens ----------------------------------------------------------------------

def _norm_role(role: str) -> str:
    return re.sub(r"[\s_-]+", " ", role).strip().lower()


def parse_signins(raw: str) -> dict[str, tuple[str, str, str]]:
    """``TRAINING_SIGNINS`` read into ``{normalised role: (role, username,
    password)}``. One entry per line, or entries separated by ``;``; in each,
    ``role | username | password``. The password is everything after the
    second bar, so it may hold a bar but not a semicolon. A malformed entry
    is skipped."""
    out: dict[str, tuple[str, str, str]] = {}
    for entry in re.split(r"[;\n]", raw or ""):
        parts = [p.strip() for p in entry.split("|", 2)]
        if len(parts) == 3 and all(parts):
            out[_norm_role(parts[0])] = (parts[0], parts[1], parts[2])
    return out


def app_sub(training_url: str, signins: dict[str, tuple[str, str, str]]) -> Sub:
    """The course page's tokens: the training address, and each sign-in drawn
    as a username and a password, each with its own copy button (TR7)."""
    url = html.escape((training_url or "").strip().rstrip("/"), quote=True)

    def signin(m: re.Match) -> str:
        role = html.unescape(m.group(1)).strip()
        got = signins.get(_norm_role(role))
        if not got:
            return (f'<em class="signin-missing">the {html.escape(role)} sign-in, not yet set '
                    f'in System Settings: ask the trainer</em>')
        _, user, password = got
        return ('<span class="signin">username '
                f'<span class="copy copy--inline"><code>{html.escape(user)}</code>'
                '<button type="button" class="copybtn">Copy</button></span> password '
                f'<span class="copy copy--inline"><code>{html.escape(password)}</code>'
                '<button type="button" class="copybtn">Copy</button></span></span>')

    def sub(text: str) -> str:
        text = text.replace(TRAINING_URL_TOKEN, url or "(the training system's address, "
                            "not yet set in System Settings)")
        return SIGNIN_RE.sub(signin, text)

    return sub


def page_sub(training_url: str) -> Sub:
    """The Claude page's tokens: the address as given, and each sign-in as the
    role's name only, so nothing secret can reach a public page (decision 5)."""
    url = html.escape((training_url or "").strip().rstrip("/"), quote=True)

    def sub(text: str) -> str:
        text = text.replace(TRAINING_URL_TOKEN, url)
        return SIGNIN_RE.sub(lambda m: f"the {m.group(1).strip()} sign-in (from the trainer)", text)

    return sub


# --- the course page in the application -------------------------------------------------

def body_html(doc: dict, sub: Optional[Sub] = None) -> str:
    """The course's sections for the application's course page (plan § 5.2).
    Each step is a ``section.step`` with ``data-key`` and ``id="step-<key>"``,
    so a later help button can point at it (phase 5); each checkpoint is a
    ``div.checkpoint`` with ``data-key`` and a text box."""
    sub = sub or _same
    out: list[str] = []
    if doc["intro"]:
        out.append(f'<div class="text">{text_html(doc["intro"], sub)}</div>')
    for index, sec in enumerate(doc["sections"]):
        if sec["skip"]:
            continue
        out.append(f'<h2>{html.escape(sec["title"])}</h2>')
        if sec["text"]:
            out.append(f'<div class="text">{text_html(sec["text"], sub)}</div>')
        for step in sec["steps"]:
            body, checkpoint = step_html(step, sub)
            key = html.escape(step_key(step), quote=True)
            out.append(f'<section class="step" data-key="{key}" id="step-{key}">'
                       f'<label class="step-head"><input type="checkbox" class="step-tick">'
                       f'<span class="step-num">{html.escape(step["num"])}</span>'
                       f'<span class="step-title">{inline(step["title"], sub)}</span></label>'
                       f'<div class="step-body">{body}</div></section>')
            if checkpoint:
                ck = html.escape(checkpoint_key(index, sec), quote=True)
                out.append(f'<div class="checkpoint" data-key="{ck}" id="{ck}">'
                           f'<label class="checkpoint-q" for="answer-{ck}"><strong>Checkpoint:</strong> '
                           f'{checkpoint}</label>'
                           f'<textarea class="checkpoint-a" id="answer-{ck}" rows="2" maxlength="2000" '
                           f'placeholder="Type your answer here"></textarea>'
                           f'<span class="checkpoint-saved" aria-live="polite"></span></div>')
    return "\n".join(out)


# --- the Claude page made by scripts/build_runbook.py -----------------------------------

CSS = """
:root {
  --bg: #F6F7F9; --panel: #FFFFFF; --fg: #1B2430; --muted: #5A6675; --line: #DCE1E8;
  --accent: #1F4E79; --accent-soft: #E6EEF6; --ok: #1E6B3A; --code-bg: #EEF1F5;
  --sans: "IBM Plex Sans", system-ui, sans-serif; --mono: "IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12161C; --panel: #1A2029; --fg: #E6EAF0; --muted: #9AA6B4; --line: #2C3542;
  --accent: #8DB8E2; --accent-soft: #1E2C3B; --ok: #7FD39B; --code-bg: #232B36; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #12161C; --panel: #1A2029; --fg: #E6EAF0; --muted: #9AA6B4; --line: #2C3542;
  --accent: #8DB8E2; --accent-soft: #1E2C3B; --ok: #7FD39B; --code-bg: #232B36; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font: 15px/1.55 var(--sans); }
.wrap { max-width: 60rem; margin: 0 auto; padding-block: 1.5rem 4rem;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; text-wrap: balance; }
h2 { font-size: 1.15rem; margin: 2rem 0 .75rem; color: var(--accent); text-wrap: balance; }
.sub { color: var(--muted); margin: 0 0 1rem; }
.bar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: var(--bg);
  display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; padding: .5rem 0; border-bottom: 1px solid var(--line); }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--bg); }
.count { font-weight: 700; font-variant-numeric: tabular-nums; }
button { font: inherit; cursor: pointer; }
.reset { background: none; border: 1px solid var(--line); color: var(--fg); border-radius: 6px; padding: .3rem .8rem; }
.text { background: var(--accent-soft); border-radius: 8px; padding: .9rem 1.1rem; }
.text ul, .text ol { margin: .25rem 0 .5rem; padding-left: 1.2rem; }
.text p { margin: .4rem 0; }
.step { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; margin: 0 0 .75rem; scroll-margin-top: 4rem; }
.step-head { display: flex; gap: .75rem; align-items: flex-start; padding: .8rem 1rem; cursor: pointer; }
.step-head input { width: 1.3rem; height: 1.3rem; margin-top: .15rem; flex: none; accent-color: var(--accent); }
.step-num { font-family: var(--mono); color: var(--muted); flex: none; min-width: 2.6rem; }
.step-title { font-weight: 600; min-width: 0; }
.step-body { padding: 0 1rem 1rem 4.9rem; display: grid; gap: .55rem; min-width: 0; }
.step.done .step-body { display: none; }
.step.done .step-title { color: var(--muted); text-decoration: line-through; }
.lab { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; }
.row p, .note { margin: .1rem 0 0; }
.entry { display: grid; gap: .2rem; }
.entry .lab { text-transform: none; letter-spacing: 0; font-size: .85rem; }
.copy { display: flex; gap: .5rem; align-items: stretch; min-width: 0; }
.copy code { flex: 1; min-width: 0; background: var(--code-bg); border-radius: 6px; padding: .45rem .6rem;
  font: .9rem/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
.copybtn { flex: none; border: 1px solid var(--accent); color: var(--accent); background: var(--panel); border-radius: 6px; padding: 0 .8rem; }
p code, li code { background: var(--code-bg); border-radius: 4px; padding: 0 .25rem; font-family: var(--mono); font-size: .9em; }
.report { border-left: 3px solid var(--ok); padding: .4rem .8rem; margin: .5rem 0 0; }
@media (max-width: 560px) { .step-body { padding-left: 1rem; } }
"""

JS = r"""
var KEY = __KEY__;
function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } }
function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
var state = load();
var cards = Array.prototype.slice.call(document.querySelectorAll(".step"));
function paint() {
  var done = cards.filter(function (c) { return c.querySelector("input").checked; }).length;
  document.getElementById("count").textContent = done + " of " + cards.length + " done";
}
cards.forEach(function (card) {
  var id = card.dataset.id, box = card.querySelector("input");
  box.checked = !!state[id];
  card.classList.toggle("done", box.checked);
  box.addEventListener("change", function () {
    state[id] = box.checked; save(state);
    card.classList.toggle("done", box.checked);
    paint();
    if (box.checked) {
      var next = cards.filter(function (c) { return !c.querySelector("input").checked; })[0];
      if (next) next.scrollIntoView({ block: "start",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  });
});
document.querySelectorAll(".copybtn").forEach(function (b) {
  b.addEventListener("click", function () {
    var code = b.previousElementSibling, text = code.textContent;
    var ok = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500); };
    var pick = function () { var r = document.createRange(); r.selectNodeContents(code);
      var s = getSelection(); s.removeAllRanges(); s.addRange(r); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, pick);
    else pick();
  });
});
document.getElementById("reset").addEventListener("click", function () {
  state = {}; save(state);
  cards.forEach(function (c) { c.querySelector("input").checked = false; c.classList.remove("done"); });
  paint(); window.scrollTo(0, 0);
});
paint();
"""


def render(doc: dict, key: str, page_title: str = "", sub: Optional[Sub] = None) -> str:
    """The whole Claude page, as ``scripts/build_runbook.py`` writes it."""
    sub = sub or _same
    out = [f"<title>{html.escape(page_title or doc['title'])}</title>",
           '<meta name="claude:viewport-fit-sides" content="cover">',
           '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700'
           '&family=IBM+Plex+Mono:wght@400;500&display=swap">',
           f"<style>{CSS}</style>", '<div class="wrap">',
           f"<h1>{html.escape(doc['title'])}</h1>"]
    if doc["revision"]:
        out.append(f'<p class="sub">{inline(doc["revision"], sub)}</p>')
    out.append('<div class="bar"><span class="count" id="count"></span>'
               '<button class="reset" id="reset" type="button">Reset</button></div>')
    if doc["intro"]:
        out.append(f'<div class="text" style="margin-top:1rem">{text_html(doc["intro"], sub)}</div>')
    for sec in doc["sections"]:
        if sec["skip"]:
            continue
        out.append(f"<h2>{html.escape(sec['title'])}</h2>")
        if sec["text"]:
            out.append(f'<div class="text">{text_html(sec["text"], sub)}</div>')
        for step in sec["steps"]:
            body, checkpoint = step_html(step, sub)
            sid = html.escape(step["num"] or step["title"])
            out.append(f'<section class="step" data-id="{sid}"><label class="step-head">'
                       f'<input type="checkbox"><span class="step-num">{html.escape(step["num"])}</span>'
                       f'<span class="step-title">{inline(step["title"], sub)}</span></label>'
                       f'<div class="step-body">{body}</div></section>')
            if checkpoint:
                out.append(f'<p class="report"><strong>Checkpoint:</strong> {checkpoint}</p>')
    out.append("</div>")
    out.append("<script>" + JS.replace("__KEY__", json.dumps(key)) + "</script>")
    return "\n".join(out)
