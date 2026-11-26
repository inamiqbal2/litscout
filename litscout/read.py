"""Step 3: extract text from each PDF and write a structured note ("card") per paper."""
from __future__ import annotations

import json
import re
import unicodedata

import logging

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

from . import llm
from .fetch import safe_name

MAX_CHARS = 900_000  # about 225k tokens; longer documents (books) are cut, with a warning


def pdf_pages(path) -> list[str]:
    try:
        reader = PdfReader(str(path))
    except Exception as e:  # noqa: BLE001 - pypdf raises many types
        print(f"  could not open {path.name}: {e}")
        return []
    pages = []
    for pg in reader.pages:
        try:
            pages.append(pg.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    return pages


def citekey(p: dict, used: set) -> str:
    first = (p.get("authors") or ["Anon"])[0].split()[-1] if p.get("authors") else "Anon"
    first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode()
    first = re.sub(r"[^A-Za-z]", "", first) or "Anon"
    base = f"{first}{p.get('year') or ''}"
    key, n = base, 0
    while key in used:
        n += 1
        key = base + "abcdefghijklmnopqrstuvwxyz"[n - 1]
    used.add(key)
    return key


def extract_text(ws, p: dict) -> dict:
    """Returns {'pages': [...], 'kind': 'fulltext'|'abstract'}; caches to text/."""
    out = ws.text / (safe_name(p["id"]) + ".json")
    pdf = ws.pdfs / (safe_name(p["id"]) + ".pdf")
    if out.exists():
        doc = json.loads(out.read_text())
        if not (doc["kind"] == "abstract" and pdf.exists() and doc.get("pdf_checked") != pdf.stat().st_size):
            return doc
    pages = pdf_pages(pdf) if pdf.exists() else []
    if sum(len(t) for t in pages) > 500:
        doc = {"pages": pages, "kind": "fulltext"}
    else:
        if pdf.exists():
            print(f"  {p['id']}: PDF has no text layer (scanned?); using the abstract")
        doc = {"pages": [p.get("abstract") or ""], "kind": "abstract",
               "pdf_checked": pdf.stat().st_size if pdf.exists() else None}
    out.write_text(json.dumps(doc, ensure_ascii=False))
    return doc


def page_marked(pages: list[str]) -> tuple[str, bool]:
    parts, total, cut = [], 0, False
    for i, t in enumerate(pages, 1):
        block = f"\n[[page {i}]]\n{t}"
        if total + len(block) > MAX_CHARS:
            cut = True
            break
        parts.append(block)
        total += len(block)
    return "".join(parts), cut


CARD_PROMPT = """You are reading a paper for a researcher and writing a structured note.

Research question: {question}
Their own work / direction: {context}

Paper metadata: {meta}
Text available: {kind}{cutnote}

Text (page numbers are marked [[page N]]):
<paper>
{text}
</paper>

Write a JSON object with these keys. Every claim must come from the text; give the
page number where it appears (use null when only the abstract is available).
Do not invent values. Keep notation (Miller indices, units, symbols) exactly as written.

{{
  "title": "...",
  "one_line": "what the paper does and finds, one sentence",
  "key_findings": [{{"claim": "...", "page": 3}}],
  "methods": "methods / techniques / models used",
  "systems": "materials, systems, datasets or conditions studied",
  "numbers": [{{"quantity": "...", "value": "...", "conditions": "...", "page": 5}}],
  "limitations": "limitations the authors state or that are evident",
  "open_questions": "questions the paper leaves open",
  "relevance": "how this paper bears on the research question and the researcher's own work",
  "tags": ["short", "topic", "labels"]
}}"""


def make_card(ws, p: dict, project: dict) -> dict:
    out = ws.cards / (safe_name(p["id"]) + ".json")
    doc = extract_text(ws, p)
    if out.exists():
        card = json.loads(out.read_text())
        if card.get("source_text") == doc["kind"]:
            return card  # re-read only when a PDF has arrived since the last card
    text, cut = page_marked(doc["pages"])
    meta = {k: p.get(k) for k in ("title", "authors", "year", "venue", "doi")}
    prompt = CARD_PROMPT.format(
        question=project["question"], context=project.get("context") or "(not given)",
        meta=json.dumps(meta, ensure_ascii=False), kind=doc["kind"],
        cutnote=" (document was long; only the first part is included)" if cut else "",
        text=text)
    if cut:
        print(f"  note: {p['id']} is long; the card covers the first ~{MAX_CHARS // 4000}k tokens")
    try:
        card = llm.ask_json(prompt, effort="medium")
    except ValueError as e:
        print(f"  card failed for {p['id']}: {e}")
        return {}
    card.update({"id": p["id"], "key": p["key"], "authors": p.get("authors"),
                 "year": p.get("year"), "doi": p.get("doi"), "source_text": doc["kind"]})
    out.write_text(json.dumps(card, indent=2, ensure_ascii=False))
    (ws.cards / (safe_name(p["id"]) + ".md")).write_text(card_markdown(card))
    return card


def card_markdown(c: dict) -> str:
    def pg(x):
        return f" (p. {x['page']})" if x.get("page") else ""
    lines = [f"# {c.get('title')}", "",
             f"**{c['key']}** — {', '.join(c.get('authors') or [])} ({c.get('year')})"
             + (f" — {c['doi']}" if c.get("doi") else ""),
             f"Source text: {c.get('source_text')}", "", c.get("one_line", ""), "",
             "## Key findings"]
    lines += [f"- {f.get('claim')}{pg(f)}" for f in c.get("key_findings", [])]
    lines += ["", "## Methods", str(c.get("methods", "")), "", "## Systems", str(c.get("systems", "")),
              "", "## Numbers"]
    lines += [f"- {n.get('quantity')}: {n.get('value')} [{n.get('conditions')}]{pg(n)}"
              for n in c.get("numbers", [])]
    lines += ["", "## Limitations", str(c.get("limitations", "")), "", "## Open questions",
              str(c.get("open_questions", "")), "", "## Relevance", str(c.get("relevance", "")), "",
              "Tags: " + ", ".join(c.get("tags", []))]
    return "\n".join(lines) + "\n"


def chunks_for(ws, p: dict, size: int = 1500, overlap: int = 200) -> list[dict]:
    doc = extract_text(ws, p)
    out = []
    for i, t in enumerate(doc["pages"], 1):
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            continue
        start = 0
        while start < len(t):
            out.append({"key": p["key"], "id": p["id"],
                        "page": i if doc["kind"] == "fulltext" else None,
                        "text": t[start:start + size]})
            start += size - overlap
    return out
