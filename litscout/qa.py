"""Step 5: ask questions of the collection.

Retrieval: keyword (BM25) search over page-tagged chunks of every paper, plus
the per-paper notes. The model answers only from that material and cites
[Key, p. N].
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime

from . import llm

STOP = set("""a an the of and or in on for to with by from at as is are was were be been
this that these those it its into than then there their which who whom what when where how
why do does did not no can could may might will would should we our you your they them""".split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text.lower()) if t not in STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.toks = [tokens(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.toks)) / max(len(self.toks), 1)
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        n = len(self.toks)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.tf = [Counter(t) for t in self.toks]

    def top(self, query: str, k: int = 20) -> list[int]:
        q = tokens(query)
        scores = []
        for i, tf in enumerate(self.tf):
            L = len(self.toks[i])
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
            scores.append(s)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [i for i in order[:k] if scores[i] > 0]


ANSWER_PROMPT = """Answer the researcher's question using only the material below from
their paper collection.

Rules:
- Cite every statement as [Key, p. N] (or [Key] if no page). Use the citation keys shown.
- For "which papers" or "list all" questions, go through the paper notes one by one so
  none is missed.
- If the material does not answer the question, say so and say what is missing.
  Do not fill gaps from general knowledge without labelling it "(general knowledge, not
  from the collection)".
- Keep notation and units exactly as in the source.

Research context: {question}

<paper_notes>
{cards}
</paper_notes>

<passages>
{passages}
</passages>

Question: {q}"""


class Collection:
    def __init__(self, ws):
        self.ws = ws
        self.chunks = ws.load("index.json", [])
        if not self.chunks:
            raise SystemExit("No index yet. Run `litscout read` first.")
        self.bm25 = BM25([c["text"] for c in self.chunks])
        self.cards = []
        for f in sorted(ws.cards.glob("*.json")):
            c = json.loads(f.read_text())
            self.cards.append({k: c.get(k) for k in (
                "key", "title", "year", "one_line", "key_findings", "systems", "numbers", "tags")})

    def answer(self, q: str, k: int = 25) -> str:
        hits = [self.chunks[i] for i in self.bm25.top(q, k)]
        passages = "\n\n".join(
            f"[{h['key']}{', p. ' + str(h['page']) if h['page'] else ''}] {h['text']}" for h in hits)
        prompt = ANSWER_PROMPT.format(
            question=self.ws.project["question"],
            cards=json.dumps(self.cards, indent=1, ensure_ascii=False),
            passages=passages or "(no keyword matches)", q=q)
        ans = llm.ask(prompt, effort="medium")
        with open(self.ws.path("qa_log.md"), "a") as f:
            f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M} — {q}\n\n{ans}\n")
        return ans
