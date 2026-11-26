"""Command-line entry point: `litscout <command> <workspace> ...`."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import fetch as fetch_mod
from . import outlook as outlook_mod
from . import read as read_mod
from . import search
from .workspace import Workspace


def selected(ws) -> list[dict]:
    data = ws.load("candidates.json")
    if not data:
        raise SystemExit("No candidates yet. Run `litscout find` first (or `litscout add`).")
    return [p for p in data["candidates"] if p.get("selected")]


def write_reading_list(ws, data):
    sel = [p for p in data["candidates"] if p.get("selected")]
    rest = [p for p in data["candidates"] if not p.get("selected")][:40]
    def row(p):
        link = p.get("doi") or p.get("oa_url") or ""
        return (f"| {'' if p.get('score') is None else p.get('score')} | {p['title'][:110]} | {p.get('year')} | "
                f"{p.get('cited_by', '')} | {p['id']} | {p.get('why', '')} | {link} |")
    head = "| Score | Title | Year | Cited by | ID | Why | Link |\n|---|---|---|---|---|---|---|"
    q = (ws.load("project.json") or {}).get("question", "")
    text = [f"# Reading list\n\nQuestion: {q}\n", "Search queries used:"]
    text += [f"- {x}" for x in data.get("queries", [])]
    text += ["", f"## Selected ({len(sel)})", "", head] + [row(p) for p in sel]
    text += ["", "## Next best candidates (not selected)", "", head] + [row(p) for p in rest]
    text += ["", "To change the selection, tell Claude which papers to add or drop."]
    ws.write("reading_list.md", "\n".join(text) + "\n")


# ---------------- commands ----------------

def cmd_init(a):
    ws = Workspace(a.workspace)
    context = a.context or ""
    if a.context_file:
        context = Path(a.context_file).read_text()
    if not a.question:
        raise SystemExit("--question is required")
    ws.save("project.json", {"question": a.question, "context": context})
    ws.pdfs
    print(f"Workspace ready: {ws.root}")


def cmd_find(a):
    ws = Workspace(a.workspace)
    pr = ws.project
    data = search.find(pr["question"], pr.get("context", ""), n_select=a.n, since=a.since,
                       snowball=not a.no_snowball, use_arxiv=not a.no_arxiv,
                       extra_queries=a.query)
    old = ws.load("candidates.json")
    if old:  # keep papers the user added by hand
        data["candidates"] += [p for p in old["candidates"] if p.get("source") == "local"]
    ws.save("candidates.json", data)
    write_reading_list(ws, data)
    print(f"\n{len(data['candidates'])} candidates; {a.n} selected. See {ws.path('reading_list.md')}")


def cmd_select(a):
    ws = Workspace(a.workspace)
    data = ws.load("candidates.json")
    ids = {p["id"]: p for p in data["candidates"]}
    for i in a.add or []:
        if i in ids:
            ids[i]["selected"] = True
        else:
            print(f"unknown id {i}")
    for i in a.drop or []:
        if i in ids:
            ids[i]["selected"] = False
    ws.save("candidates.json", data)
    write_reading_list(ws, data)
    print(f"{sum(1 for p in data['candidates'] if p.get('selected'))} selected.")


def cmd_fetch(a):
    ws = Workspace(a.workspace)
    got, missing = fetch_mod.fetch_all(ws, selected(ws))
    lines = ["# Papers without a downloaded PDF", "",
             "Many publishers block scripted downloads. Open each link in your browser",
             "(through your library if needed), save the PDF into the workspace's `pdfs/`",
             "folder under the file name shown, then run `litscout read` again.", "",
             "Or: `litscout add <workspace> <file.pdf> --id <ID>`", "",
             "| Save as | Title | Year | Open |", "|---|---|---|---|"]
    for p in missing:
        link = (p.get("pdf_urls") or [None])[0] or p.get("oa_url") or p.get("doi") or ""
        lines.append(f"| pdfs/{fetch_mod.safe_name(p['id'])}.pdf | {p['title'][:100]} | "
                     f"{p.get('year')} | {link} |")
    ws.write("missing_pdfs.md", "\n".join(lines) + "\n")
    print(f"\n{got} PDFs in {ws.pdfs}; {len(missing)} missing (listed in missing_pdfs.md).")
    print("Missing papers are still used, from their abstracts.")


def cmd_add(a):
    ws = Workspace(a.workspace)
    data = ws.load("candidates.json") or {"queries": [], "candidates": []}
    src = Path(a.pdf).expanduser()
    if not src.exists():
        raise SystemExit(f"{src} not found")
    ids = {p["id"]: p for p in data["candidates"]}
    pid = a.id or "local_" + fetch_mod.safe_name(src.stem)
    if pid not in ids:
        p = {"id": pid, "title": a.title or src.stem.replace("_", " "), "year": a.year,
             "authors": [a.author] if a.author else [], "venue": None, "doi": None,
             "cited_by": 0, "abstract": "", "pdf_url": None, "oa_url": None, "arxiv_id": None,
             "referenced_works": [], "source": "local", "score": 10.0,
             "why": "added by the user"}
        data["candidates"].append(p)
        ids[pid] = p
    ids[pid]["selected"] = True
    shutil.copy(src, ws.pdfs / (fetch_mod.safe_name(pid) + ".pdf"))
    for stale in (ws.text / (fetch_mod.safe_name(pid) + ".json"),
                  ws.cards / (fetch_mod.safe_name(pid) + ".json")):
        stale.unlink(missing_ok=True)  # re-read with the new PDF
    ws.save("candidates.json", data)
    print(f"Added {src.name} as {pid}.")


def cmd_read(a):
    ws = Workspace(a.workspace)
    pr = ws.project
    data = ws.load("candidates.json")
    papers = [p for p in data["candidates"] if p.get("selected")]
    used = set()
    for p in data["candidates"]:  # stable keys across runs
        if p.get("key"):
            used.add(p["key"])
    for p in papers:
        if not p.get("key"):
            p["key"] = read_mod.citekey(p, used)
    ws.save("candidates.json", data)

    chunks = []
    for i, p in enumerate(papers, 1):
        print(f"[{i}/{len(papers)}] {p['key']}: {p['title'][:70]}")
        read_mod.make_card(ws, p, pr)
        chunks += read_mod.chunks_for(ws, p)
    ws.save("index.json", chunks)
    print(f"\nNotes in {ws.cards}; {len(chunks)} passages indexed for `litscout ask`.")


def cmd_outlook(a):
    ws = Workspace(a.workspace)
    import json
    cards = [json.loads(f.read_text()) for f in sorted(ws.cards.glob("*.json"))]
    if not cards:
        raise SystemExit("No paper notes yet. Run `litscout read` first.")
    outlook_mod.build(ws, ws.project, cards)
    print(f"Outlook written to {ws.path('outlook.md')}")


def cmd_ask(a):
    from .qa import Collection
    col = Collection(Workspace(a.workspace))
    if a.question:
        print(col.answer(" ".join(a.question)))
        return
    print("Ask questions about your papers. Empty line or Ctrl-D to quit.")
    while True:
        try:
            q = input("\n? ").strip()
        except EOFError:
            break
        if not q:
            break
        print("\n" + col.answer(q))


def cmd_setup(a):
    from . import llm
    import getpass
    if llm.saved_key() and not a.force:
        print(f"An API key is already saved in {llm.KEY_FILE}. Use --force to replace it.")
        return
    print("Paste your Anthropic API key (starts with sk-ant-). Get one at https://console.anthropic.com")
    key = getpass.getpass("API key (hidden): ").strip()
    if not key.startswith("sk-ant-"):
        raise SystemExit("That does not look like an Anthropic API key; nothing saved.")
    llm.save_key(key)
    print(f"Saved to {llm.KEY_FILE} (readable only by you).")


def _open(path):
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("win"):
            import os
            os.startfile(str(path))  # noqa: S606
    except Exception:  # noqa: BLE001
        pass


def cmd_start(a):
    """Guided mode for people who do not want to type commands."""
    from . import llm
    if not (llm.saved_key() or __import__("os").environ.get("ANTHROPIC_API_KEY")):
        cmd_setup(argparse.Namespace(force=False))
    base = Path(a.home).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    existing = sorted(p.name for p in base.iterdir() if (p / "project.json").exists())
    print("\nlitscout: research question -> papers -> outlook -> questions\n")
    if existing:
        print("Your projects: " + ", ".join(existing))
    name = input("Project name (new or existing, e.g. gb_loops): ").strip() or "my_research"
    name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    ws_path = base / name
    a2 = argparse.Namespace(workspace=str(ws_path), question=None, context=None, context_file=None,
                            n=25, since=None, query=None, no_snowball=False, no_arxiv=False)
    if (ws_path / "outlook.md").exists():
        print(f"\n{name} is already done. Opening its outlook; ask your questions below.")
        _open(ws_path / "outlook.md")
    else:
        if not (ws_path / "project.json").exists():
            a2.question = input("\nYour research question:\n> ").strip()
            a2.context = input("\nA few sentences on your own work and direction (Enter to skip):\n> ").strip()
            n = input("\nHow many papers to read? [25]: ").strip()
            a2.n = int(n) if n.isdigit() else 25
            since = input("Only papers from year (Enter for any): ").strip()
            a2.since = int(since) if since.isdigit() else None
            cmd_init(a2)
        cmd_find(a2)
        _open(ws_path / "reading_list.md")
        input("\nThe reading list is open. Press Enter to download and read the papers "
              "(or Ctrl-C to stop and edit the selection first) ")
        cmd_fetch(a2)
        cmd_read(a2)
        cmd_outlook(a2)
        _open(ws_path / "outlook.md")
        print(f"\nAll files are in {ws_path}")
    cmd_ask(argparse.Namespace(workspace=str(ws_path), question=[]))


def cmd_run(a):
    if a.question:
        cmd_init(a)
    cmd_find(a)
    cmd_fetch(a)
    cmd_read(a)
    cmd_outlook(a)
    print("\nDone. Next: `litscout ask " + a.workspace + "`")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="litscout", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def ws_arg(p):
        p.add_argument("workspace", help="folder for this research question")

    def init_args(p):
        p.add_argument("--question", "-q", help="your research question")
        p.add_argument("--context", "-c", help="a few sentences on your own work and direction")
        p.add_argument("--context-file", help="file describing your work (abstract, proposal ...)")

    def find_args(p):
        p.add_argument("--n", type=int, default=25, help="papers to select (default 25)")
        p.add_argument("--since", type=int, help="only papers from this year on")
        p.add_argument("--query", action="append", help="add your own search query (repeatable)")
        p.add_argument("--no-snowball", action="store_true", help="skip reference/citation following")
        p.add_argument("--no-arxiv", action="store_true", help="search OpenAlex only")

    p = sub.add_parser("init", help="create a workspace for a research question"); ws_arg(p); init_args(p)
    p.set_defaults(f=cmd_init)
    p = sub.add_parser("find", help="search and rank papers -> reading_list.md"); ws_arg(p); find_args(p)
    p.set_defaults(f=cmd_find)
    p = sub.add_parser("select", help="add or drop papers from the selection"); ws_arg(p)
    p.add_argument("--add", nargs="*"); p.add_argument("--drop", nargs="*"); p.set_defaults(f=cmd_select)
    p = sub.add_parser("fetch", help="download open-access PDFs"); ws_arg(p); p.set_defaults(f=cmd_fetch)
    p = sub.add_parser("add", help="add a PDF you already have"); ws_arg(p)
    p.add_argument("pdf"); p.add_argument("--id", help="ID from reading_list.md, if it is listed there")
    p.add_argument("--title"); p.add_argument("--year", type=int); p.add_argument("--author")
    p.set_defaults(f=cmd_add)
    p = sub.add_parser("read", help="read each paper and write notes + search index"); ws_arg(p)
    p.set_defaults(f=cmd_read)
    p = sub.add_parser("outlook", help="write outlook.md from the notes"); ws_arg(p)
    p.set_defaults(f=cmd_outlook)
    p = sub.add_parser("ask", help="ask questions of the papers"); ws_arg(p)
    p.add_argument("question", nargs="*"); p.set_defaults(f=cmd_ask)
    from . import tools
    tools.register(sub, ws_arg)
    p = sub.add_parser("setup", help="save your Anthropic API key")
    p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_setup)
    p = sub.add_parser("start", help="guided mode: asks you everything, step by step")
    p.add_argument("--home", default="~/litscout_projects", help="where projects are kept")
    p.set_defaults(f=cmd_start)
    p = sub.add_parser("run", help="init + find + fetch + read + outlook in one go"); ws_arg(p)
    init_args(p); find_args(p); p.set_defaults(f=cmd_run)

    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    sys.exit(main())
