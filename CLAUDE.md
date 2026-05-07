# kb — Claude Code Guide

## Project Overview

`kb` is a Python CLI tool that compiles raw source documents into an LLM-maintained wiki and lets a Claude agent answer questions against it. All wiki content is owned by the LLM — never edited manually.

## Commands

```bash
kb ingest [--vault PATH]                 # walk raw/, hash files, update _state.json
kb compile [--vault PATH] [--full]       # build/update wiki
kb ask "question" [--vault PATH]         # Q&A agent session
kb add <file> [file ...] [--vault PATH]  # copy files into the appropriate raw/ subdirectory
kb add-youtube <url> [--vault PATH]      # fetch YouTube transcript, save as raw/articles/<title>.md
kb config [--vault PATH] [--api-key KEY] # show or update global config (~/.kb)
```

When installed via `uv tool install`, all commands run as bare `kb` (no `uv run`). When running from the project directory with `uv run kb`, both forms work.

## Project Structure

```
kb/
├── kb/
│   ├── cli.py       # typer commands: ingest, compile, add, add-youtube, ask, config
│   ├── models.py    # pydantic v2 models (SourceDoc, SummaryResult, ConceptArticle, MasterIndex, BuildState)
│   ├── utils.py     # get_client(), get_vault_path(), ensure_vault_structure(), shared console
│   ├── ingest.py    # walk raw/, extract text (md/pdf/image), MD5 hashing, _state.json
│   ├── compile.py   # phase 1 (Haiku summaries) + phase 2 (Sonnet concept synthesis)
│   ├── index.py     # build _index.json + index.md from wiki files
│   ├── agent.py     # Haiku Q&A agent with tool-use loop
│   └── youtube.py   # YouTube transcript fetching (oEmbed metadata + transcript API)
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
├── raw/articles/     ← .md files (Obsidian Web Clipper, YouTube transcripts)
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
- **Phase 2 (concept synthesis)**: re-runs in full whenever any summary changed **or** `wiki/concepts/` is empty. Partial synthesis would produce inconsistent backlinks across articles, so it always rebuilds from scratch.
- Use `--full` to force a complete rebuild regardless of hashes.

## Global Config

`~/.kb` is a dotenv file loaded on every `kb` invocation regardless of working directory:

```
ANTHROPIC_API_KEY=sk-ant-...
KB_VAULT=/absolute/path/to/vault
```

`kb config` reads and writes this file:

```bash
kb config                          # show current values
kb config --vault /path/to/vault   # set default vault
kb config --api-key sk-ant-...     # set API key
```

Load order in `utils._load_env()`: `~/.kb` (baseline) → `<cwd>/.env` (override). A local `.env` always wins over the global config.

Vault path resolution order: `--vault` CLI arg → `KB_VAULT` env var → `./vault/`

## `kb add` — Adding Files

Routes files to the correct `raw/` subdirectory based on extension:

```bash
kb add paper.pdf note.md screenshot.png
```

- `.md`, `.txt` → `raw/articles/`
- `.pdf` → `raw/pdfs/`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` → `raw/images/`

Skips files that already exist at the destination. Unsupported extensions are skipped with a warning.

## `kb add-youtube` — YouTube Transcripts

Fetches a transcript and saves it as a markdown file in `raw/articles/`:

```bash
kb add-youtube "https://www.youtube.com/watch?v=VIDEO_ID"
```

- Metadata (title, channel) is fetched from YouTube's oEmbed endpoint — no API key required.
- Transcript is fetched via `youtube-transcript-api`; falls back to any available language if English is unavailable.
- Raw segments are grouped into ~45-second paragraphs with `[MM:SS]` timestamps.
- Output frontmatter includes `type: youtube-transcript` so the compiler can identify the source.
- Saved as `raw/articles/<slugified-title>.md`; skips if file already exists.

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

- **Phase 2 JSONL output**: concept synthesis uses JSONL (one JSON object per line) rather than a JSON array. This means a token-limit truncation only loses the last article; all earlier articles are recoverable. A warning is printed when `stop_reason == "max_tokens"`.
- **Concepts missing trigger**: if `wiki/concepts/` is empty (e.g. after a failed Phase 2 run), the next `kb compile` automatically re-runs Phase 2 even if no documents changed.
- **Index one-liners**: `_index.json` one-line summaries come from `summary_one_line` frontmatter saved during compile. If a concept article lacks this field (legacy), the index falls back to the first non-heading sentence of the body.
- **Windows UTF-8**: `utils.py` reconfigures `sys.stdout` to UTF-8 and creates the Rich console with `legacy_windows=False` to prevent cp1252 encoding errors on LLM-generated Unicode characters (subscripts, special punctuation, etc.).
