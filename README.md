# litscout

Research question → reading list → outlook report → ask questions of the papers.

1. **Find papers.** You give a research question and a few sentences about your own work.
   Claude writes search queries, litscout searches **OpenAlex** (250M+ scholarly works) and
   **arXiv**, follows references and citations of the best hits, and Claude scores every
   abstract for relevance. Result: `reading_list.md`.
2. **Outlook.** litscout downloads the open-access PDFs, Claude reads each paper and writes
   a structured note (findings with page numbers, methods, numbers, limits, relevance to you),
   then writes `outlook.md`: bottom line, knowledge map, agreements, conflicts, gaps,
   opportunities for your work, and a reading order.
3. **Ask.** `litscout ask` answers questions from the papers, citing `[Key, p. N]`.

## Install

Needs Python 3.10+ and an Anthropic API key (https://console.anthropic.com).

```bash
git clone https://github.com/inamiqbal2/litscout.git
cd litscout
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## Use

One command for steps 1 and 2:

```bash
litscout run my_topic \
  -q "How do dislocation loops change the mobility of migrating grain boundaries?" \
  -c "I run MD simulations of Al bicrystals and want to know which loop types and boundary types are unexplored."
```

(`-c` can be replaced by `--context-file my_abstract.txt`.)

Then read, in the `my_topic/` folder:

| File | What it is |
|---|---|
| `reading_list.md` | Selected papers with score and reason, plus the next 40 candidates |
| `missing_pdfs.md` | Selected papers that could not be downloaded, with links |
| `cards/*.md` | One note per paper |
| `outlook.md` | The outlook report and knowledge map |

Ask questions:

```bash
litscout ask my_topic "Which papers report boundary mobility values, and under what conditions?"
litscout ask my_topic          # interactive; answers are also saved to qa_log.md
```

### Step by step (to review the list before reading)

```bash
litscout init my_topic -q "..." -c "..."
litscout find my_topic --n 25 --since 2010   # edit the selection, then:
litscout select my_topic --add W123456 --drop W987654
litscout fetch my_topic
litscout add my_topic ~/Downloads/paper.pdf --id W987654   # papers you got yourself
litscout add my_topic ~/Downloads/my_own_notes.pdf --title "Group report 2025"
litscout read my_topic
litscout outlook my_topic
```

Options for `find` / `run`: `--n` papers to select (default 25), `--since YEAR`,
`--query "..."` to add your own search query (repeatable), `--no-snowball`, `--no-arxiv`.

## Missing PDFs

Many publishers block scripted downloads, and litscout does not try to get around that.
It downloads from arXiv and open repositories; for the rest it writes `missing_pdfs.md`
with a link and the file name to save as. Download them in your browser (through your
library if needed), save them into `my_topic/pdfs/` under that name, and run
`litscout read my_topic` and `litscout outlook my_topic` again. Until then those papers
are used from their abstracts only, and the outlook says so.

## Model and cost

Default model: `claude-opus-5-5`. Change with `export LITSCOUT_MODEL=claude-sonnet-5-5`
(cheaper). A 25-paper run sends every selected paper's full text to the model once, plus
the abstracts of a few hundred candidates; expect a few dollars per run. Each question
costs a few cents. Notes and text are cached, so re-running only processes new papers.

Optional: `export OPENALEX_MAILTO=you@example.org` puts OpenAlex requests in its faster
"polite pool".

## Limits

- It only finds what OpenAlex and arXiv index; check the reading list against what you know.
- Relevance scores come from abstracts. Always skim the list before trusting the outlook.
- Scanned PDFs without a text layer are used from their abstract only.
- Figures, plots and images are not read.
- Answers are only as good as the papers in the workspace; check cited pages before quoting.
- Paper text is sent to the Anthropic API. Do not use it on documents you may not share.

## Test without an API key

```bash
python tests/smoke_test.py /tmp/litscout_test
```

Runs the whole pipeline with real searches and downloads but a stand-in model.

License: MIT.
