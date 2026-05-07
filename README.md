# kb

An LLM-powered personal knowledge base. Drop raw documents into a vault, compile them into a structured wiki with Claude, then query that wiki with a Claude agent.

The wiki is entirely owned by the LLM — you never edit it manually.

## How it works

```
raw/articles/*.md  ──┐
raw/pdfs/*.pdf     ──┤  kb compile  ──>  wiki/concepts/*.md   ──┐
raw/images/*.png   ──┘                   wiki/summaries/*.md  ──┤  kb ask "..."
                                         wiki/_index.json     ──┘
```

1. **Ingest**: walks `raw/`, extracts text, tracks file hashes for incremental builds
2. **Compile phase 1**: Haiku summarises each document into `wiki/summaries/`
3. **Compile phase 2**: Sonnet reads all summaries and synthesises concept articles into `wiki/concepts/` with `[[backlinks]]`
4. **Ask**: a Haiku agent navigates the wiki via tool use and answers your question; output is saved to `outputs/`

The vault is an Obsidian-compatible folder — open it directly in Obsidian to browse the wiki, backlink graph, and Q&A outputs.

## Setup

**Requirements**: Python 3.12+, [uv](https://docs.astral.sh/uv/)

### Option A — global install (recommended)

Install `kb` as a global tool so it works from any directory:

```bash
git clone ...
cd kb
uv tool install .
```

Then configure it once:

```bash
kb config --vault /absolute/path/to/your/vault
kb config --api-key sk-ant-...
```

Settings are saved to `~/.kb` and applied on every `kb` invocation.

### Option B — project-local

```bash
git clone ...
cd kb
uv sync
```

Add your API key and vault path to `.env` at the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
KB_VAULT=./vault
```

Use `uv run kb <command>` instead of `kb` throughout.

## Usage

### 1. Add source documents

**Copy files in** — routes by file type automatically:

```bash
kb add paper.pdf note.md screenshot.png
```

- `.md`, `.txt` → `raw/articles/`
- `.pdf` → `raw/pdfs/`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` → `raw/images/`

**Fetch a YouTube transcript**:

```bash
kb add-youtube "https://www.youtube.com/watch?v=VIDEO_ID"
```

Downloads the transcript, groups it into timestamped paragraphs, and saves it as `raw/articles/<title>.md`. No YouTube API key needed.

**Or drop files manually** into the appropriate subfolder:
- `vault/raw/articles/` — markdown files (works great with [Obsidian Web Clipper](https://obsidian.md/clipper))
- `vault/raw/pdfs/` — PDF papers
- `vault/raw/images/` — figures, screenshots, diagrams

### 2. Compile the wiki

```bash
kb compile
```

Subsequent runs are incremental — only changed files are re-summarised. Force a full rebuild:

```bash
kb compile --full
```

### 3. Ask questions

```bash
kb ask "What are the key concepts in my research?"
kb ask "How does multi-head attention relate to scaling laws?"
kb ask "Summarise the main findings across all papers"
```

Answers are printed to the terminal and saved as markdown files in `vault/outputs/`, ready to view in Obsidian.

### Optional: ingest only (no LLM calls)

```bash
kb ingest
```

Useful to preview what files will be processed and check which have changed.

## Configuration

`kb config` shows or updates the global config stored in `~/.kb`:

```bash
kb config                               # show current settings
kb config --vault /path/to/vault        # set default vault
kb config --api-key sk-ant-...          # set API key
```

You can also set `KB_VAULT` and `ANTHROPIC_API_KEY` in a `.env` file in your working directory — local `.env` values override the global `~/.kb` config.

## Vault as an Obsidian vault

Open the `vault/` directory as your Obsidian vault. The wiki compiles to standard Obsidian-compatible markdown:
- `[[backlinks]]` are resolved automatically by Obsidian
- YAML frontmatter tags are indexed
- `wiki/index.md` is the entry point
- Q&A outputs in `outputs/` appear as regular notes

## Cost estimate

Using default models (Haiku + Sonnet):

| Operation | Cost |
|---|---|
| Full compile, 100 docs | ~$0.68 |
| Incremental compile, 5 new docs | ~$0.03 |
| Single Q&A session | ~$0.017 |
| 10 sessions/day, 30 days | ~$7/month |

## Models

| Task | Model |
|---|---|
| Summaries (per doc) | claude-haiku-4-5-20251001 |
| Concept synthesis | claude-sonnet-4-6 |
| Q&A agent | claude-haiku-4-5-20251001 |

Override vault path per-command with `--vault`:
```bash
kb compile --vault /path/to/my/vault
```

## Project layout

```
kb/
├── kb/
│   ├── cli.py       # entry point: ingest, compile, add, add-youtube, ask, config
│   ├── models.py    # pydantic data models
│   ├── utils.py     # shared client, vault helpers, global config
│   ├── ingest.py    # document ingestion + hashing
│   ├── compile.py   # LLM compilation pipeline
│   ├── index.py     # index generation
│   ├── agent.py     # Q&A agent
│   └── youtube.py   # YouTube transcript fetching
└── vault/           # your Obsidian vault
    ├── raw/
    ├── wiki/
    └── outputs/
```
