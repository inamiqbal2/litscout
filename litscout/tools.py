"""Model-free commands. Claude (in the Claude app) does the thinking; these do the
mechanical work: search, download, PDF text, passage search. No API key needed."""
from __future__ import annotations

import json
from pathlib import Path

import requests

from . import fetch as fetch_mod
from . import read as read_mod
from . import search
from .workspace import Workspace


def _data(ws):
    return ws.load("candidates.json") or {"queries": [], "candidates": []}


def cmd_search(a):
    ws = Workspace(a.workspace)
    data = _data(ws)
    have = {search._norm(p["title"]) for p in data["candidates"]}
    new = []
    for q in a.query or []:
        try:
            new += search.openalex_search(q, per_page=a.per_query, since=a.since)
        except requests.RequestException as e:
            print(f"OpenAlex failed for '{q}': {e}")
        if not a.no_arxiv:
            try:
                new += search.arxiv_search(q, n=15)
            except requests.RequestException as e:
                print(f"arXiv failed for '{q}': {e}")
        data["queries"].append(q)
    if a.snowball:
        ids = a.snowball if a.snowball != ["top"] else [
            p["id"] for p in sorted(data["candidates"], key=lambda p: -(p.get("score") or 0))
            if p["source"] == "openalex"][:5]
        byid = {p["id"]: p for p in data["candidates"]}
        for i in ids:
            p = byid.get(i)
            try:
                if p and p.get("referenced_works"):
                    new += search.openalex_by_ids(p["referenced_works"][:30])
                new += search.openalex_citing(i, n=15)
            except requests.RequestException as e:
                print(f"snowball failed for {i}: {e}")
    new = [p for p in search.merge(new) if search._norm(p["title"]) not in have
           and (not a.since or (p.get("year") or 0) >= a.since)]
    for p in new:
        p["score"] = None
    data["candidates"] += new
    ws.save("candidates.json", data)
    unscored = sum(1 for p in data["candidates"] if p.get("score") is None)
    print(f"{len(new)} new papers; {len(data['candidates'])} in total; {unscored} not yet scored.")


def cmd_list(a):
    ws = Workspace(a.workspace)
    ps = _data(ws)["candidates"]
    if a.unscored:
        ps = [p for p in ps if p.get("score") is None]
    if a.selected:
        ps = [p for p in ps if p.get("selected")]
    ps = ps[a.offset:a.offset + a.limit]
    for p in ps:
        print(f"[{p['id']}] {p['title']} ({p.get('year')}; cited {p.get('cited_by')})")
        if not a.short:
            print((p.get("abstract") or "(no abstract)")[:a.chars])
            print()
    print(f"-- {len(ps)} shown")


def cmd_score(a):
    ws = Workspace(a.workspace)
    data = _data(ws)
    raw = json.loads(Path(a.file).read_text())
    if isinstance(raw, list):
        raw = {r["id"]: [r["score"], r.get("why", "")] for r in raw}
    n = 0
    for p in data["candidates"]:
        if p["id"] in raw:
            s, why = raw[p["id"]] if isinstance(raw[p["id"]], list) else (raw[p["id"]], "")
            p["score"], p["why"] = float(s), why
            n += 1
    ws.save("candidates.json", data)
    left = sum(1 for p in data["candidates"] if p.get("score") is None)
    print(f"Scored {n}. {left} still unscored.")


def write_reading_list(ws, data):
    from .cli import write_reading_list as w
    w(ws, data)


def cmd_pick(a):
    ws = Workspace(a.workspace)
    data = _data(ws)
    for p in data["candidates"]:
        if p.get("source") != "local":
            p["selected"] = False
    ranked = sorted([p for p in data["candidates"] if p.get("score") is not None],
                    key=lambda p: (-p["score"], -(p.get("cited_by") or 0)))
    for p in ranked[:a.n]:
        p["selected"] = True
    for i in a.add or []:
        for p in data["candidates"]:
            if p["id"] == i:
                p["selected"] = True
    for i in a.drop or []:
        for p in data["candidates"]:
            if p["id"] == i:
                p["selected"] = False
    data["candidates"].sort(key=lambda p: (not p.get("selected"), -(p.get("score") or 0)))
    ws.save("candidates.json", data)
    write_reading_list(ws, data)
    print(f"{sum(1 for p in data['candidates'] if p.get('selected'))} selected -> {ws.path('reading_list.md')}")


def cmd_extract(a):
    """Page-marked text for every selected paper + the passage index."""
    ws = Workspace(a.workspace)
    data = _data(ws)
    sel = [p for p in data["candidates"] if p.get("selected")]
    used = {p["key"] for p in data["candidates"] if p.get("key")}
    for p in sel:
        if not p.get("key"):
            p["key"] = read_mod.citekey(p, used)
    ws.save("candidates.json", data)
    chunks = []
    print("key | id | text | pages | file")
    for p in sel:
        doc = read_mod.extract_text(ws, p)
        txt = ws.text / f"{p['key']}.txt"
        header = (f"{p['title']}\n{', '.join(p.get('authors') or [])} ({p.get('year')}) "
                  f"{p.get('doi') or ''}\nText: {doc['kind']}\n")
        body = "".join(f"\n[[page {i}]]\n{t}" for i, t in enumerate(doc["pages"], 1)) \
            if doc["kind"] == "fulltext" else "\n[[abstract]]\n" + doc["pages"][0]
        txt.write_text(header + body)
        chunks += read_mod.chunks_for(ws, p)
        card = "done" if (ws.cards / f"{p['key']}.md").exists() else "no card yet"
        print(f"{p['key']} | {p['id']} | {doc['kind']} | {len(doc['pages'])} | text/{txt.name} | {card}")
    ws.save("index.json", chunks)
    print(f"{len(chunks)} passages indexed.")


def cmd_grep(a):
    from .qa import BM25
    ws = Workspace(a.workspace)
    chunks = ws.load("index.json", [])
    if not chunks:
        raise SystemExit("No index yet: run extract first.")
    bm = BM25([c["text"] for c in chunks])
    for i in bm.top(" ".join(a.query), a.k):
        c = chunks[i]
        print(f"[{c['key']}{', p. ' + str(c['page']) if c['page'] else ''}] {c['text']}\n")


def cmd_status(a):
    ws = Workspace(a.workspace)
    pr = ws.load("project.json") or {}
    data = _data(ws)
    sel = [p for p in data["candidates"] if p.get("selected")]
    pdfs = {f.stem for f in ws.pdfs.glob("*.pdf")}
    cards = {f.stem for f in ws.cards.glob("*.md")}
    print("Question:", pr.get("question"))
    print(f"Candidates: {len(data['candidates'])} "
          f"(unscored {sum(1 for p in data['candidates'] if p.get('score') is None)}); selected {len(sel)}")
    print(f"PDFs: {sum(1 for p in sel if fetch_mod.safe_name(p['id']) in pdfs)} of {len(sel)}; "
          f"digests: {sum(1 for p in sel if (ws.root / 'digests' / (str(p.get('key')) + '.md')).exists())} of {len(sel)}; "
          f"cards: {sum(1 for p in sel if p.get('key') in cards)} of {len(sel)}; "
          f"outlook: {'yes' if ws.path('outlook.md').exists() else 'no'}")


def register(sub, ws_arg):
    p = sub.add_parser("search", help="[no model] search OpenAlex/arXiv and add candidates"); ws_arg(p)
    p.add_argument("--query", action="append"); p.add_argument("--since", type=int)
    p.add_argument("--per-query", type=int, default=40); p.add_argument("--no-arxiv", action="store_true")
    p.add_argument("--snowball", nargs="*", help="IDs to follow references/citations of, or 'top'")
    p.set_defaults(f=cmd_search)
    p = sub.add_parser("list", help="[no model] print candidates"); ws_arg(p)
    p.add_argument("--unscored", action="store_true"); p.add_argument("--selected", action="store_true")
    p.add_argument("--limit", type=int, default=30); p.add_argument("--offset", type=int, default=0)
    p.add_argument("--chars", type=int, default=1200); p.add_argument("--short", action="store_true")
    p.set_defaults(f=cmd_list)
    p = sub.add_parser("score", help="[no model] load relevance scores from a JSON file"); ws_arg(p)
    p.add_argument("file"); p.set_defaults(f=cmd_score)
    p = sub.add_parser("pick", help="[no model] select the top N scored papers"); ws_arg(p)
    p.add_argument("--n", type=int, default=25); p.add_argument("--add", nargs="*"); p.add_argument("--drop", nargs="*")
    p.set_defaults(f=cmd_pick)
    p = sub.add_parser("extract", help="[no model] page-marked text + passage index"); ws_arg(p)
    p.set_defaults(f=cmd_extract)
    p = sub.add_parser("grep", help="[no model] best-matching passages for a query"); ws_arg(p)
    p.add_argument("query", nargs="+"); p.add_argument("--k", type=int, default=15); p.set_defaults(f=cmd_grep)
    p = sub.add_parser("status", help="[no model] where a project stands"); ws_arg(p)
    p.set_defaults(f=cmd_status)


# ---------------- low-usage helpers ----------------

def _rank_local(ws, papers):
    """Rank papers on this computer (no model): keyword match of title+abstract
    against the question, context and queries, with a small citation bonus."""
    import math
    from .qa import BM25
    pr = ws.load("project.json") or {}
    data = _data(ws)
    query = " ".join([pr.get("question", ""), pr.get("context", "")] + data.get("queries", []))
    docs = [f"{p['title']} {p['title']} {p.get('abstract') or ''}" for p in papers]
    if not docs:
        return []
    bm = BM25(docs)
    from .qa import tokens
    q = tokens(query)
    out = []
    for i, tf in enumerate(bm.tf):
        L = len(bm.toks[i]) or 1
        s = sum(bm.idf[w] * tf[w] * 2.5 / (tf[w] + 1.5 * (0.25 + 0.75 * L / bm.avg)) for w in set(q) if w in tf)
        s *= 1 + 0.1 * math.log1p(papers[i].get("cited_by") or 0)
        if not papers[i].get("abstract"):
            s *= 0.6
        out.append((s, papers[i]))
    out.sort(key=lambda x: -x[0])
    return [p for _, p in out]


def cmd_shortlist(a):
    """Print only the best N unscored candidates, compactly, for Claude to judge."""
    ws = Workspace(a.workspace)
    unscored = [p for p in _data(ws)["candidates"] if p.get("score") is None]
    top = _rank_local(ws, unscored)[:a.n]
    for p in top:
        ab = " ".join((p.get("abstract") or "(no abstract)").split())[:a.chars]
        print(f"[{p['id']}] {p['title']} ({p.get('year')}; cited {p.get('cited_by')}) :: {ab}")
    print(f"-- {len(top)} of {len(unscored)} unscored shown (best keyword matches first)")


def _conclusion(pages):
    import re as _re
    pat = _re.compile(r"\n\s*(\d+\.?\s*)?(conclusions?|concluding remarks|summary and conclusions?|summary)\s*\n", _re.I)
    for i in range(len(pages) - 1, -1, -1):
        m = pat.search("\n" + pages[i])
        if m:
            text = ("\n" + pages[i])[m.end():]
            if len(text) < 1500 and i + 1 < len(pages):
                text += " " + pages[i + 1]
            return i + 1, " ".join(text.split())
    return None, ""


def cmd_digest(a):
    """A short extract per selected paper (abstract, conclusions, the passages most
    relevant to the question, with page numbers). Claude reads these instead of whole papers."""
    from .qa import BM25
    ws = Workspace(a.workspace)
    pr = ws.load("project.json") or {}
    data = _data(ws)
    sel = [p for p in data["candidates"] if p.get("selected") and p.get("key")]
    if not sel:
        raise SystemExit("Run extract first.")
    ddir = ws._dir("digests")
    query = pr.get("question", "") + " " + pr.get("context", "")
    total = 0
    for p in sel:
        if a.only and p["key"] not in a.only:
            continue
        doc = read_mod.extract_text(ws, p)
        parts = [f"# {p['title']}", f"{p['key']} | {', '.join((p.get('authors') or [])[:4])} ({p.get('year')}) | "
                 f"{p.get('doi') or ''} | text: {doc['kind']}, {len(doc['pages'])} pages", "",
                 "ABSTRACT: " + " ".join((p.get("abstract") or "(none)").split())]
        if doc["kind"] == "fulltext":
            cp, ctext = _conclusion(doc["pages"])
            if ctext:
                parts += ["", f"CONCLUSIONS (p. {cp}): " + ctext[:a.chars]]
            chunks = [c for c in read_mod.chunks_for(ws, p)]
            if chunks:
                bm = BM25([c["text"] for c in chunks])
                parts.append("")
                parts.append("MOST RELEVANT PASSAGES:")
                for i in bm.top(query, a.passages):
                    c = chunks[i]
                    parts.append(f"(p. {c['page']}) {c['text'][:900]}")
        text = "\n".join(parts) + "\n"
        (ddir / f"{p['key']}.md").write_text(text)
        total += len(text)
    print(f"{len(sel)} digests in digests/, about {total // 4000}k tokens in total "
          f"(full texts would be about {sum(len(t) for p in sel for t in read_mod.extract_text(ws, p)['pages']) // 4000}k).")


def register_light(sub, ws_arg):
    p = sub.add_parser("shortlist", help="[no model] best N unscored candidates, compact"); ws_arg(p)
    p.add_argument("--n", type=int, default=40); p.add_argument("--chars", type=int, default=300)
    p.set_defaults(f=cmd_shortlist)
    p = sub.add_parser("digest", help="[no model] short extract per paper for low-usage reading"); ws_arg(p)
    p.add_argument("--chars", type=int, default=2500); p.add_argument("--passages", type=int, default=4)
    p.add_argument("--only", nargs="*", help="only these paper keys")
    p.set_defaults(f=cmd_digest)
