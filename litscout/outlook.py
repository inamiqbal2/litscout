"""Step 4: synthesise the paper cards into an outlook report and knowledge map."""
from __future__ import annotations

import json

from . import llm

OUTLOOK_PROMPT = """You are helping a researcher plan their work from the papers they have collected.

Research question: {question}
Their own work / direction: {context}

Below are structured notes on {n} papers. Each has a citation key (e.g. Smith2021).
Cite papers as [Key, p. N] (or [Key] when no page is given). Use only these notes;
say plainly where the papers are silent. Do not invent papers, numbers or pages.

<notes>
{cards}
</notes>

Write a Markdown report with these sections:

# Outlook: <short title>

## 1. Bottom line
Five to eight bullet points: what the collected literature says about the research
question, and what it means for the researcher's direction.

## 2. Knowledge map
A table with columns: Theme | What is established | Key papers | Strength of evidence.
Then a short list of how the themes connect.

## 3. Where papers agree
## 4. Where papers disagree or conflict
For each conflict, state the differing conditions (material, method, scale, assumptions)
that may explain it. Present these as candidates to check, not verdicts.

## 5. Gaps and open questions
What has not been done, measured or explained.

## 6. Opportunities for the researcher's work
Concrete directions, each tied to a gap and to the papers that motivate it, with
why it is feasible and what would count as a result.

## 7. Methods and tools in use
Which methods, models, datasets or experimental techniques recur, with papers.

## 8. Suggested reading order
The 8-12 papers to read first, in order, with one line each on why.

## 9. Limits of this report
Which papers were read from the abstract only, and what the collection may be missing."""


def build(ws, project: dict, cards: list[dict]) -> str:
    compact = []
    for c in cards:
        if not c:
            continue
        compact.append({k: c.get(k) for k in (
            "key", "title", "year", "source_text", "one_line", "key_findings", "methods",
            "systems", "numbers", "limitations", "open_questions", "relevance", "tags")})
    prompt = OUTLOOK_PROMPT.format(
        question=project["question"], context=project.get("context") or "(not given)",
        n=len(compact), cards=json.dumps(compact, indent=1, ensure_ascii=False))
    print(f"Writing the outlook from {len(compact)} paper notes ...")
    report = llm.ask(prompt, effort="high", max_tokens=64000)
    ws.write("outlook.md", report)
    return report
