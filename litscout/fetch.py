"""Step 2: download open-access PDFs for the selected papers.

Only open-access copies are fetched (OpenAlex OA links and arXiv).
Paywalled papers are listed so you can add them yourself with
`litscout add <file.pdf> --id <paper id>`.
"""
from __future__ import annotations

import re
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; litscout/0.1; literature search tool)"}


def safe_name(pid: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", pid)


def _try(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=UA, timeout=60, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code == 200 and r.content[:5] == b"%PDF-":
        return r.content
    return None


def candidate_urls(p: dict) -> list[str]:
    urls = []
    if p.get("arxiv_id"):
        urls.append(f"https://arxiv.org/pdf/{p['arxiv_id']}")
    urls += p.get("pdf_urls") or []
    if p.get("pdf_url") and p["pdf_url"] not in urls:
        urls.append(p["pdf_url"])
    if p.get("oa_url") and p["oa_url"] not in urls:
        urls.append(p["oa_url"])
    return urls


def fetch_all(ws, papers: list[dict]) -> tuple[int, list[dict]]:
    got, missing = 0, []
    for p in papers:
        dest = ws.pdfs / (safe_name(p["id"]) + ".pdf")
        if dest.exists():
            got += 1
            continue
        data = None
        for u in candidate_urls(p):
            data = _try(u)
            if "arxiv.org" in u:
                time.sleep(3)
            if data:
                break
        if data:
            dest.write_bytes(data)
            got += 1
            print(f"  got  {p['id']}  {p['title'][:70]}")
        else:
            missing.append(p)
            print(f"  --   {p['id']}  {p['title'][:70]}  (no open-access PDF)")
    return got, missing
