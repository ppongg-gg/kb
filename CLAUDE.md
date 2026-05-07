# kb — Claude Code Guide

## Project Overview

`kb` is a Python CLI tool that compiles raw source documents into an LLM-maintained wiki and lets a Claude agent answer questions against it. All wiki content is owned by the LLM — never edited manually.

## Commands

```bash
uv run kb ingest [--vault PATH]         # walk raw/, hash files, update _state.json
uv run kb compile [--vault PATH] [--full]  # build/update wiki
uv run kb ask "question" [--vault PATH]    # Q&A agent session
```

## Project Structure

```
kb/
├── kb/
│   ├── cli.py       # typer commands: ingest, compile, ask
│   ├── models.py    # pydantic v2 models (SourceDoc, SummaryResult, ConceptArticle, MasterIndex, BuildState)
│   ├── utils.py     # get_client(), get_vault_path(), ensure_vault_structure(), shared console
│   ├── ingest.py    # walk raw/, extract text (md/pdf/image), MD5 hashing, _state.json
│   ├── compile.py   # phase 1 (Haiku summaries) + phase 2 (Sonnet concept synthesis)
│   ├── index.py     # build _index.json + index.md from wiki files
│   └── agent.py     # Haiku Q&A agent with tool-use loop
└── vault/           # the Obsidian vault (gitignored wiki/ and outputs/)
    ├── raw/         # user drops source files here
    ├── wiki/        # LLM-generated (never edit manually)
    └── outputs/     # Q&A results
```

## Models Used

| Task | Model | Why |
|---|---|---|
| Per-doc summaries | `claude-haiku-4-5-20251001` | Fast, cheap, reliable JSON on repetitive calls |
| Concept synthesis | `claude-sonnet-4-6` | One large call that shapes the entire wiki structure |
| Q&A agent | `claude-haiku-4-5-20251001` | Fast interactive responses; cached index keeps cost low |

Prompt caching (`cache_control: {"type": "ephemeral"}`) is applied to system prompts in all three phases.

## Vault Layout

```
vault/
├── raw/articles/     ← .md files (Obsidian Web Clipper output)
├── raw/pdfs/         ← PDF papers
├── raw/images/       ← figures, screenshots
├── wiki/_state.json  ← MD5 hashes for incremental builds
├── wiki/_index.json  ← machine-readable index read by the Q&A agent
├── wiki/index.md     ← human-readable TOC (Obsidian entry point)
├── wiki/summaries/   ← one .md per raw file
├── wiki/concepts/    ← synthesized concept articles with [[backlinks]]
└── outputs/          ← timestamped Q&A results
```

## Incremental Build Logic

- **Phase 1 (summaries)**: skipped per-file if `_state.json` hash matches — only changed/new files are re-summarized.
- **Phase 2 (concept synthesis)**: re-runs in full whenever any summary changed. Partial synthesis would produce inconsistent backlinks across articles.
- Use `--full` to force a complete rebuild regardless of hashes.

## Environment

`.env` at project root:
```
ANTHROPIC_API_KEY=sk-ant-...
KB_VAULT=./vault          # default vault path; override with --vault
```

Vault path resolution order: `--vault` CLI arg → `KB_VAULT` env var → `./vault/`

## Adding New Document Types

To support a new file extension, add it to the relevant set in `ingest.py`:
- `_TEXT_EXTS` for plain-text formats
- `_PDF_EXTS` for PDF-like formats  
- `_IMAGE_EXTS` for image formats (handled as vision messages in `compile.py`)

## Extending the Agent

The Q&A agent uses three tools: `get_index`, `read_article`, `list_articles`. Add new tools in `agent.py` by:
1. Adding a dict to the `TOOLS` list (Anthropic tool format)
2. Adding a dispatch branch in `_dispatch()`
3. Implementing the tool function

## Known Behaviour

- The `_index.json` one-line summaries come from `summary_one_line` frontmatter saved during compile. If a concept article was generated without this field (legacy), the index falls back to the first sentence of the body.
- On Windows, `utils.py` reconfigures `sys.stdout` to UTF-8 before creating the Rich console to prevent cp1252 encoding errors on LLM-generated Unicode characters.
