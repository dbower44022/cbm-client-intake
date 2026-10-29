"""The shared grid on the Workspace Directories and My Email
(prds/shared-grid-plan.md § 12): each page loads grid.js after busy.js and
before its own script, links grid.css, has dropped its own sort code, and
names its grids; the directory's server-paged grid sorts on several columns
through the CRM's SortedList endpoint, else on the first column."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core.espo import EspoError
from directory import service
from directory.config import COMPANIES
from tests.test_directory import _accounts_client

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "frontend" / "shared"
DIR_FE = ROOT / "directory" / "frontend"
ME_FE = ROOT / "myemail" / "frontend"

# (page, its own script, the grid keys its scripts name)
PAGES = [
    (DIR_FE / "index.html", "app.js", [DIR_FE / "app.js"], ['"directory." + KIND', '"directory.companyContacts"']),
    (DIR_FE / "record.html", "record.js", [DIR_FE / "record.js"],
     ['"directory.record." + key', '"crEvtTable", "events"', '"crContactsTable", "contacts"',
      '"crInboxTable", "conversations"']),
    (ME_FE / "index.html", "app.js", [ME_FE / "app.js"], ['"myemail.inbox"']),
]


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node runtime available")
    prog = f"require({json.dumps(str(SHARED / 'grid.js'))});\nconst G = globalThis.CBMGrid;\n{script}"
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _fn(path: Path, name: str) -> str:
    """One top-level function's source out of a page script."""
    src = path.read_text(encoding="utf-8")
    m = re.search(r"\n  function " + name + r"\(.*?\n  }\n", src, re.S)
    assert m, f"{name} not found in {path.name}"
    return m.group(0)


@pytest.mark.parametrize("html,own,scripts,keys", PAGES, ids=lambda p: getattr(p, "name", None))
def test_page_loads_the_shared_grid(html, own, scripts, keys):
    text = html.read_text(encoding="utf-8")
    busy = text.index('<script src="/shared/busy.js"></script>')
    grid = text.index('<script src="/shared/grid.js"></script>')
    mine = text.index(f'<script src="{own}"></script>')
    assert busy < grid < mine, "grid.js comes after busy.js and before the page's own script"
    assert '<link rel="stylesheet" href="/shared/grid.css" />' in text
    assert 'data-sort="' not in text
    js = "".join(p.read_text(encoding="utf-8") for p in scripts)
    for key in keys:
        assert key in js, f"{key} missing"
    for old in ("makeColumnsResizable", "dir__grip", "dir__sortarrow", "convSort.", "convSort =", "cr__th-sort",
                "state.orderBy", "setSort(c.key)"):
        assert old not in js, f"leftover sort code: {old}"


def test_old_sort_css_is_gone():
    css = (DIR_FE / "styles.css").read_text() + (DIR_FE / "record.css").read_text()
    for old in ("dir__grip", "dir__sortarrow", "dir__table--resized", "cr__th-sort"):
        assert old not in css


def test_directory_pager_buttons_are_never_disabled():
    js = (DIR_FE / "app.js").read_text()
    assert 'prevBtn").disabled' not in js and 'nextBtn").disabled' not in js
    assert "This is the first page." in js and "This is the last page." in js


def test_directory_heading_marks_columns_the_crm_cannot_sort():
    js = (DIR_FE / "app.js").read_text()
    assert 'th.setAttribute("data-sortable", "false")' in js


def test_myemail_and_conversation_sort_values():
    out = _node(
        _fn(ME_FE / "app.js", "inboxSortVal")
        + _fn(DIR_FE / "record.js", "convSortVal")
        + """
      const rows = [
        {id:1, records:[{name:"Zeta"}], participants:"Zoe", subject:"Pricing", lastMessageAt:"2026-10-20 10:00:00", status:"Open"},
        {id:2, records:[{name:"Alpha"}], participants:"Adam", subject:"", lastMessageAt:"2026-01-03 10:00:00", status:""},
        {id:3, records:[], participants:"", subject:"Banking", lastMessageAt:null, status:"Closed"},
      ];
      const ids = (keys, f) => G.sortBy(rows, keys, f).map(r => r.id);
      console.log(JSON.stringify({
        rec: ids([{col:"record", dir:"asc"}], inboxSortVal),
        recDesc: ids([{col:"record", dir:"desc"}], inboxSortVal),
        date: ids([{col:"lastMessageAt", dir:"asc"}], inboxSortVal),
        dateDesc: ids([{col:"lastMessageAt", dir:"desc"}], inboxSortVal),
        subj: ids([{col:"subject", dir:"asc"}], convSortVal),
        status: ids([{col:"status", dir:"desc"}], convSortVal),
      }));
    """)
    assert out["rec"] == [2, 1, 3] and out["recDesc"] == [1, 2, 3], "no record sorts last both ways"
    assert out["date"] == [2, 1, 3] and out["dateDesc"] == [1, 2, 3], "by the stamp, blank last"
    assert out["subj"] == [3, 1, 2]
    assert out["status"] == [1, 3, 2]


# --- the directory's server sort ----------------------------------------------

class _Sorting:
    """The accounts fake plus a SortedList endpoint that sorts on several keys."""

    def __init__(self, *, has_endpoint=True, refuse=False):
        self.inner = _accounts_client()
        self.has_endpoint = has_endpoint
        self.refuse = refuse
        self.calls = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def list(self, entity, **kw):
        self.calls.append(("list", kw.get("order_by"), kw.get("order")))
        data = await self.inner.list(entity, **kw)
        ob = kw.get("order_by")
        if ob and kw.get("select") != "id":
            rows = sorted(data["list"], key=lambda r: str(r.get(ob) or ""), reverse=kw.get("order") == "desc")
            data = {**data, "list": rows}
        return data

    async def sorted_list(self, entity, order, *, where=None, select=None, max_size=50, offset=0):
        self.calls.append(("sorted", list(order)))
        if not self.has_endpoint:
            return None
        if self.refuse:
            raise EspoError("sorted list Account failed: Cannot sort by 'x'.")
        rows = list((await self.inner.list(entity, where=where, max_size=200))["list"])
        for col, d in reversed(order):
            rows.sort(key=lambda r: str(r.get(col) or ""), reverse=d == "desc")
        return {"list": rows[offset:offset + max_size]}


def test_parse_sort_keeps_only_sortable_columns():
    cols = [{"key": "name", "sortable": True}, {"key": "website", "sortable": False},
            {"key": "cCompanyType", "sortable": True}]
    assert service.parse_sort("name:desc,website:asc,bogus:asc,cCompanyType", cols) == [
        ("name", "desc"), ("cCompanyType", "asc")]
    assert service.parse_sort("", cols) == []


@pytest.mark.asyncio
async def test_several_columns_sort_through_the_sorted_list_endpoint():
    client = _Sorting()
    page = await service.list_records(client, COMPANIES, sort="cCompanyType:desc,name:asc")
    assert client.calls[0] == ("sorted", [("cCompanyType", "desc"), ("name", "asc")])
    assert [r["name"] for r in page["rows"]] == ["Gamma", "Beta", "Acme"]
    assert page["total"] == 3 and page["multiSort"] is True
    assert page["sort"] == "cCompanyType:desc,name:asc"


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", [{"has_endpoint": False}, {"refuse": True}])
async def test_without_the_endpoint_the_first_column_sorts(kw):
    client = _Sorting(**kw)
    page = await service.list_records(client, COMPANIES, sort="name:desc,cCompanyType:asc")
    assert ("list", "name", "desc") in client.calls
    assert [r["name"] for r in page["rows"]] == ["Gamma", "Beta", "Acme"]
    assert page["multiSort"] is False and page["sort"] == "name:desc"


@pytest.mark.asyncio
async def test_no_sort_keeps_the_default_order_and_one_column_needs_no_endpoint():
    client = _Sorting()
    page = await service.list_records(client, COMPANIES)
    assert client.calls == [("list", "name", "asc")] and page["sort"] == ""
    client = _Sorting()
    page = await service.list_records(client, COMPANIES, sort="name:desc")
    assert client.calls == [("list", "name", "desc")] and page["multiSort"] is True
    # The old one-column form still works.
    client = _Sorting()
    await service.list_records(client, COMPANIES, order_by="cCompanyType", order="desc")
    assert client.calls == [("list", "cCompanyType", "desc")]


def test_the_edit_window_save_is_never_disabled():
    js = (Path(__file__).resolve().parent.parent / "directory" / "frontend" / "app.js").read_text()
    # Only the in-flight disable while a save runs remains.
    assert '$("modalSaveBtn").disabled = !changed' not in js
    assert '$("modalSaveBtn").disabled = true; $("saveInfo").textContent = "Saving' in js
    assert "Nothing has changed yet" in js
