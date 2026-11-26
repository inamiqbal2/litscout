"""End-to-end smoke test with a fake model: real OpenAlex/arXiv search and PDF
download, no Anthropic API calls. Run: python tests/smoke_test.py /tmp/ws"""
import json
import re
import sys

from litscout import llm, cli


def fake_ask(prompt, system="", effort="medium", max_tokens=32000, model=None):
    if "search queries" in prompt:
        return json.dumps(["grain boundary migration molecular dynamics",
                           "dislocation grain boundary interaction"])
    if "Score how useful" in prompt:
        n = len(re.findall(r"^\[\d+\] ", prompt, re.M))
        return json.dumps([{"i": i, "score": 10 - (i % 10), "why": "test"} for i in range(n)])
    if "structured note" in prompt:
        return json.dumps({"title": "t", "one_line": "x", "key_findings": [{"claim": "c", "page": 1}],
                           "methods": "m", "systems": "s", "numbers": [], "limitations": "",
                           "open_questions": "", "relevance": "r", "tags": ["a"]})
    if "Outlook" in prompt:
        return "# Outlook: test\n"
    return "answer [Key, p. 1]"


llm.ask = fake_ask
ws = sys.argv[1]
cli.main(["run", ws, "-q", "How do dislocations interact with migrating grain boundaries?",
          "-c", "MD of loops at Al GBs", "--n", "4", "--since", "2015"])
cli.main(["ask", ws, "which papers use MD?"])
