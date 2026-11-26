# litscout

**Not a programmer? Get litscout from the download page: [inamiqbal2.github.io/litscout](https://inamiqbal2.github.io/litscout/)**, one button, no GitHub needed.

**From a research question to the papers that answer it.** Tell Claude what you want to find out and what
you work on. litscout searches the scholarly literature, Claude reads the papers that matter, writes an
outlook for your work, and then answers your questions with the paper and page each answer came from.

It runs inside the Claude desktop app. You only chat; no programming, no terminal, no API key.

## What you need

- The **Claude desktop app** (https://claude.ai/download) on Mac or Windows, with access to its **Code** tab.
- A **paid Claude plan (Pro or higher) is strongly recommended.** litscout is built to use as little as possible
  (the computer does the searching and picks out the important parts of each paper; Claude reads only those), but a
  project still means reading 15 papers. On the free plan the limit usually runs out partway.
  Nothing is lost: every step is saved, so when your limit resets, open the folder again and type `continue`.
- That's it. Claude installs anything else it needs the first time (it may ask you to click "Install" once).

## Getting started (about 5 minutes)

1. **Download litscout** from the [download page](https://inamiqbal2.github.io/litscout/) and unzip it.
   Move the `litscout` folder to your Documents (not Downloads, which gets cleaned out).
2. **Open the folder in the Claude app.** Go to the **Code** tab and open the `litscout` folder.
3. **Type `start`.** Claude sets itself up, then asks you four short questions: your research question, a few
   sentences about your own work, any years or fields to focus on, and how many papers to read closely.
4. **Check the reading list** Claude shows you, add or drop papers if you like, and say go.
5. **Read your outlook.** Claude downloads the free papers, reads them, and writes `outlook.md`: the bottom
   line, a map of the themes, where papers agree and conflict, gaps, opportunities for your work, and a
   reading order.
6. **Ask anything.** "Which papers measured X?", "What explains the disagreement on Y?", "What has nobody
   tried yet?" Answers cite `[Paper, p. N]` and say so when your papers do not cover it.

## Things you can say

| Say | What happens |
|---|---|
| `start` (or just type your research question) | A new project, from the questions to the outlook |
| `continue` | Picks up where it stopped (for example after your Claude limit reset) |
| `find more papers on <topic>` | Searches again and adds the best new papers |
| `go deeper` | Follows the references and citations of the best papers |
| `read <paper> in full` | Reads one paper cover to cover instead of its key parts |
| `show my reading list` | The papers Claude picked, one line each |
| `add <paper>` / `drop <paper>` | Changes the list |
| `I added PDFs` | After you download papers yourself; Claude reads them too |
| `update the outlook` | Rewrites the outlook with everything read so far |
| `where am I?` | Where each project stands |
| `show me the folder` | Opens the project folder |

## Papers that will not download

Many publishers block automatic downloads, and litscout does not try to get around that. Free copies (arXiv,
open repositories, open-access journals) download by themselves. For the rest, Claude gives you a list of
links: download them through your library in your browser, then say `I added PDFs`. Until then those papers
are read from their abstracts, and the outlook says which ones.

## Where things are

Everything about your research is in `My Research/`, one folder per question:
`reading_list.md`, `outlook.md`, `cards/` (one note per paper), `pdfs/`, and `qa_log.md` (every question you
asked, with the answer).

## Cost and privacy

litscout is free (MIT license). You pay for your Claude plan. The text of the papers and your questions are
read by Claude, so do not use it on documents you are not allowed to share.

## Limits

- It finds what OpenAlex (250M+ works) and arXiv index; check the list against what you know.
- It reads text, not figures. Scanned PDFs without a text layer are used from their abstract.
- To save usage, Claude reads each paper's abstract, conclusions and the passages most relevant to your
  question, not every page. Say `read <paper> in full` for the ones that matter most.
- Treat the outlook as a well-organised first draft, and check cited pages before quoting.

---

## For programmers

The Python package (`pip install -e .`, Python 3.10+) has two sets of commands:

- **Model-free tools** that Claude drives (`litscout search | list | score | pick | fetch | extract | grep | status`);
  the procedure Claude follows is in `CLAUDE.md`.
- **A standalone mode** that calls the Anthropic API itself, for use without the Claude app:
  `litscout setup` (saves an API key), then `litscout start` (guided) or
  `litscout run <folder> -q "question" -c "your work"` and `litscout ask <folder>`.
  Default model `claude-opus-5-5`; set `LITSCOUT_MODEL` to change it.

`python tests/smoke_test.py /tmp/litscout_test` runs the standalone pipeline with real searches and a
stand-in model.

License: MIT.
