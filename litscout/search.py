"""Step 1: turn a research question into a ranked reading list.

Sources: OpenAlex (250M+ scholarly works, free, no key) and arXiv.
The model writes the search queries, then scores every candidate's
abstract for relevance to the question and the user's own work.
"""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET

import requests

from . import llm

OPENALEX = "https://api.openalex.org/works"
ARXIV = "https://export.arxiv.org/api/query"
UA = {"User-Agent": "litscout/0.1 (literature search tool)"}


def _get(url, params, tries=3):
    mailto = os.environ.get("OPENALEX_MAILTO")  # optional: OpenAlex "polite pool"
    if mailto and "openalex" in url:
        params = {**params, "mailto": mailto}
    for i in range(tries):
        r = requests.get(url, params=params, headers=UA, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", 2 ** (i + 1)))
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


# ---------- query generation ----------

def make_queries(question: str, context: str, n: int = 6) -> list[str]:
    prompt = f"""A researcher needs papers for this research question.

Research question: {question}
Their own work / direction: {context or "(not given)"}

Write {n} short keyword search queries (3-8 words each) for a scholarly search
engine. Cover different angles: the core phenomenon, methods, materials or
systems, competing explanations, and closely related fields. Use the terms
authors would put in titles and abstracts.

Return a JSON list of strings."""
    qs = llm.ask_json(prompt, effort="low")
    return [q for q in qs if isinstance(q, str)][:n]


# ---------- OpenAlex ----------

def _abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def _from_openalex(w: dict) -> dict:
    loc = w.get("best_oa_location") or {}
    oa = w.get("open_access") or {}
    authors = [a["author"]["display_name"] for a in w.get("authorships", [])[:6]
               if a.get("author")]
    arxiv_id = None
    repo_pdfs, pub_pdfs = [], []
    for l in w.get("locations") or []:
        u = (l.get("landing_page_url") or "")
        m = re.search(r"arxiv\.org/abs/([^\s?#]+)", u)
        if m:
            arxiv_id = m.group(1)
        if l.get("pdf_url"):
            kind = (l.get("source") or {}).get("type")
            (repo_pdfs if kind == "repository" else pub_pdfs).append(l["pdf_url"])
    return {
        "id": w["id"].rsplit("/", 1)[-1],
        "title": w.get("display_name") or "",
        "year": w.get("publication_year"),
        "authors": authors,
        "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "doi": w.get("doi"),
        "cited_by": w.get("cited_by_count", 0),
        "abstract": _abstract(w.get("abstract_inverted_index")),
        "pdf_url": loc.get("pdf_url"),
        # repositories (PMC, institutional, arXiv) first: publishers often block scripts
        "pdf_urls": list(dict.fromkeys(repo_pdfs + pub_pdfs)),
        "oa_url": oa.get("oa_url"),
        "arxiv_id": arxiv_id,
        "referenced_works": [r.rsplit("/", 1)[-1] for r in w.get("referenced_works", [])],
        "source": "openalex",
    }


def openalex_search(query: str, per_page: int = 40, since: int | None = None) -> list[dict]:
    params = {"search": query, "per-page": per_page}
    filters = ["type:article|review|preprint|book-chapter"]
    if since:
        filters.append(f"from_publication_date:{since}-01-01")
    params["filter"] = ",".join(filters)
    r = _get(OPENALEX, params)
    return [_from_openalex(w) for w in r.json().get("results", [])]


def openalex_by_ids(ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        r = _get(OPENALEX, {"filter": "openalex:" + "|".join(chunk), "per-page": 50})
        out += [_from_openalex(w) for w in r.json().get("results", [])]
    return out


def openalex_citing(work_id: str, n: int = 25) -> list[dict]:
    r = _get(OPENALEX, {"filter": f"cites:{work_id}", "sort": "cited_by_count:desc",
                        "per-page": n})
    return [_from_openalex(w) for w in r.json().get("results", [])]


# ---------- arXiv ----------

def arxiv_search(query: str, n: int = 20) -> list[dict]:
    r = _get(ARXIV, {"search_query": f"all:{query}", "max_results": n})
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(r.text).findall("a:entry", ns):
        aid = e.findtext("a:id", "", ns).rsplit("/abs/", 1)[-1]
        out.append({
            "id": "arXiv:" + re.sub(r"v\d+$", "", aid),
            "title": " ".join(e.findtext("a:title", "", ns).split()),
            "year": int(e.findtext("a:published", "0000", ns)[:4]),
            "authors": [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)][:6],
            "venue": "arXiv",
            "doi": None,
            "cited_by": 0,
            "abstract": " ".join(e.findtext("a:summary", "", ns).split()),
            "pdf_url": f"https://arxiv.org/pdf/{aid}",
            "oa_url": f"https://arxiv.org/abs/{aid}",
            "arxiv_id": aid,
            "referenced_works": [],
            "source": "arxiv",
        })
    time.sleep(3)  # arXiv asks for one request every 3 seconds
    return out


# ---------- merge + rank ----------

def _norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def merge(papers: list[dict]) -> list[dict]:
    seen = {}
    for p in papers:
        k = _norm(p["title"])
        if not k:
            continue
        if k not in seen:
            seen[k] = p
        else:  # prefer the OpenAlex record, keep any PDF link
            old = seen[k]
            if old["source"] == "arxiv" and p["source"] == "openalex":
                p["pdf_url"] = p["pdf_url"] or old["pdf_url"]
                p["arxiv_id"] = p["arxiv_id"] or old["arxiv_id"]
                seen[k] = p
            else:
                old["pdf_url"] = old["pdf_url"] or p["pdf_url"]
    return list(seen.values())


def score(papers: list[dict], question: str, context: str, batch: int = 30) -> list[dict]:
    """Model scores each abstract 0-10 for relevance; adds 'score' and 'why'."""
    for i in range(0, len(papers), batch):
        part = papers[i:i + batch]
        listing = "\n\n".join(
            f"[{j}] {p['title']} ({p['year']}; cited {p['cited_by']})\n"
            f"{(p['abstract'] or '(no abstract)')[:1800]}"
            for j, p in enumerate(part))
        prompt = f"""Score how useful each paper is for this researcher.

Research question: {question}
Their own work / direction: {context or "(not given)"}

10 = must read (directly addresses the question), 7 = strongly relevant,
4 = background or adjacent, 0 = unrelated. Judge only from title and abstract.

Papers:
{listing}

Return a JSON list with one object per paper:
[{{"i": <index>, "score": <0-10>, "why": "<one short sentence>"}}]"""
        try:
            res = llm.ask_json(prompt, effort="low")
        except ValueError:
            res = []
        by_i = {r.get("i"): r for r in res if isinstance(r, dict)}
        for j, p in enumerate(part):
            r = by_i.get(j, {})
            p["score"] = float(r.get("score", 0) or 0)
            p["why"] = r.get("why", "")
        print(f"  scored {min(i + batch, len(papers))}/{len(papers)}")
    return papers


def find(question: str, context: str, n_select: int = 25, per_query: int = 40,
         since: int | None = None, snowball: bool = True, use_arxiv: bool = True,
         extra_queries: list[str] | None = None) -> dict:
    print("Writing search queries ...")
    queries = make_queries(question, context) + (extra_queries or [])
    for q in queries:
        print("  -", q)

    pool = []
    for q in queries:
        try:
            pool += openalex_search(q, per_page=per_query, since=since)
        except requests.RequestException as e:
            print(f"  OpenAlex failed for '{q}': {e}")
        if use_arxiv:
            try:
                pool += arxiv_search(q, n=15)
            except requests.RequestException as e:
                print(f"  arXiv failed for '{q}': {e}")
    pool = merge(pool)
    print(f"Found {len(pool)} unique candidates. Scoring abstracts ...")
    pool = score(pool, question, context)

    if snowball:
        top = sorted([p for p in pool if p["source"] == "openalex"],
                     key=lambda p: -p["score"])[:5]
        have = {_norm(p["title"]) for p in pool}
        extra = []
        print("Following references and citations of the top 5 papers ...")
        for p in top:
            try:
                extra += openalex_by_ids(p["referenced_works"][:30])
                extra += openalex_citing(p["id"], n=15)
            except requests.RequestException as e:
                print(f"  snowball failed for {p['id']}: {e}")
        extra = [e for e in merge(extra) if _norm(e["title"]) not in have
                 and (not since or (e["year"] or 0) >= since)]
        if extra:
            print(f"  {len(extra)} new candidates from snowballing. Scoring ...")
            pool += score(extra, question, context)

    # rank: relevance first, citations break ties
    pool.sort(key=lambda p: (-p["score"], -(p["cited_by"] or 0)))
    for p in pool[:n_select]:
        p["selected"] = True
    return {"queries": queries, "candidates": pool}
