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

```bash
git clone ...
cd kb
uv sync
```

Add your API key to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
KB_VAULT=./vault
```

## Usage

### 1. Add source documents

Drop files into `vault/raw/`:
- `vault/raw/articles/` -- markdown files (works great with Obsidian Web Clipper)
- `vault/raw/pdfs/` -- PDF papers
- `vault/raw/images/` -- figures, screenshots, diagrams

### 2. Compile the wiki

```bash
uv run kb compile
```

Subsequent runs are incremental -- only changed files are re-summarised. Force a full rebuild:

```bash
uv run kb compile --full
```

### 3. Ask questions

```bash
uv run kb ask "What are the key concepts in my research?"
uv run kb ask "How does multi-head attention relate to scaling laws?"
uv run kb ask "Summarise the main findings across all papers"
```

Answers are printed to the terminal and saved as markdown files in `vault/outputs/`, ready to view in Obsidian.

### Optional: ingest only (no LLM calls)

```bash
uv run kb ingest
```

Useful to preview what files will be processed and check which have changed.

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

Override vault path with `--vault`:
```bash
uv run kb compile --vault /path/to/my/vault
```

## Project layout

```
kb/
├── kb/
│   ├── cli.py       # entry point
│   ├── models.py    # pydantic data models
│   ├── utils.py     # shared client, vault helpers
│   ├── ingest.py    # document ingestion + hashing
│   ├── compile.py   # LLM compilation pipeline
│   ├── index.py     # index generation
│   └── agent.py     # Q&A agent
└── vault/           # your Obsidian vault
    ├── raw/
    ├── wiki/
    └── outputs/
```
