from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from .utils import GLOBAL_CONFIG, console, ensure_vault_structure, get_vault_path

app = typer.Typer(
    name="kb",
    help=(
        "LLM-powered personal knowledge base.\n\n"
        "Typical workflow:\n\n"
        "  kb add <files>          # copy source files into the vault\n"
        "  kb add-youtube <url>    # or fetch a YouTube transcript\n"
        "  kb add-url <url>        # or fetch a web article\n"
        "  kb compile              # build the wiki with Claude\n"
        "  kb ask \"your question\"  # query the compiled wiki\n"
        "  kb search <keywords>    # fast keyword search (no LLM)\n\n"
        "Run kb config to set your API key and default vault path."
    ),
    add_completion=False,
)

VaultArg = Annotated[Optional[str], typer.Option("--vault", "-v", help="Path to vault directory")]


# ── Input sources ──────────────────────────────────────────────────────────────

@app.command()
def add(
    files: Annotated[list[str], typer.Argument(help="File(s) to add to the vault")],
    vault: VaultArg = None,
) -> None:
    """Copy file(s) into the vault, routed by type.

    .md/.txt → raw/articles/   .pdf → raw/pdfs/   images → raw/images/
    """
    import shutil
    from .ingest import _IMAGE_EXTS, _PDF_EXTS, _TEXT_EXTS

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)

    _dest = {
        **{ext: vault_path / "raw" / "articles" for ext in _TEXT_EXTS},
        **{ext: vault_path / "raw" / "pdfs" for ext in _PDF_EXTS},
        **{ext: vault_path / "raw" / "images" for ext in _IMAGE_EXTS},
    }

    for raw in files:
        src = Path(raw).resolve()
        if not src.exists():
            console.print(f"[red]Not found:[/red] {raw}")
            continue
        if not src.is_file():
            console.print(f"[yellow]Skipped:[/yellow] {raw} (not a file)")
            continue
        dest_dir = _dest.get(src.suffix.lower())
        if dest_dir is None:
            console.print(f"[yellow]Skipped:[/yellow] {src.name} (unsupported type {src.suffix})")
            continue
        dest = dest_dir / src.name
        if dest.exists():
            console.print(f"[yellow]Already exists:[/yellow] {dest.relative_to(vault_path)}")
            continue
        shutil.copy2(src, dest)
        console.print(f"[green]Added:[/green] {src.name} → {dest.relative_to(vault_path)}")


@app.command("add-youtube")
def add_youtube(
    url: Annotated[str, typer.Argument(help="YouTube video URL")],
    vault: VaultArg = None,
) -> None:
    """Fetch a YouTube transcript and save it to raw/articles/.

    Metadata (title, channel) is fetched via YouTube's oEmbed endpoint — no API key needed.
    Falls back to any available language if English subtitles are unavailable.
    """
    from .youtube import add_youtube as _add_youtube

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)
    _add_youtube(vault_path, url)


@app.command("add-url")
def add_url(
    url: Annotated[str, typer.Argument(help="Web article URL")],
    vault: VaultArg = None,
) -> None:
    """Fetch a web article and save it to raw/articles/.

    Uses trafilatura to extract clean article text. Works on most static pages;
    JavaScript-heavy or paywalled sites will produce an error.
    """
    from .web import add_url as _add_url

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)
    _add_url(vault_path, url)


# ── Build pipeline ─────────────────────────────────────────────────────────────

@app.command()
def ingest(vault: VaultArg = None) -> None:
    """Scan raw/, extract text, and update file hashes in wiki/_state.json.

    No LLM calls — useful to preview which files have changed before compiling.
    """
    from . import ingest as ingest_module

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)
    docs = ingest_module.ingest(vault_path)
    console.print(f"[green]Ingested {len(docs)} document(s).[/green]")


@app.command()
def compile(
    vault: VaultArg = None,
    full: Annotated[bool, typer.Option("--full", help="Recompile all docs, ignoring cache")] = False,
) -> None:
    """Build or update the wiki with Claude (incremental by default).

    Phase 1 — Haiku summarises each changed document into wiki/summaries/.
    Phase 2 — Sonnet synthesises all summaries into concept articles in wiki/concepts/.
    Phase 2 re-runs whenever any summary changed or wiki/concepts/ is empty.
    """
    from .compile import compile_wiki

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)
    compile_wiki(vault_path, full=full)


# ── Query ──────────────────────────────────────────────────────────────────────

@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask the knowledge base")],
    vault: VaultArg = None,
) -> None:
    """Ask a question against the compiled wiki using a Claude agent.

    The agent reads the index and relevant articles via tool use, then writes
    a cited answer to the terminal and saves it to outputs/.
    Run kb compile first if you haven't already.
    """
    from .agent import ask as ask_fn

    vault_path = get_vault_path(vault)
    ask_fn(vault_path, question)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    vault: VaultArg = None,
    top: Annotated[int, typer.Option("--top", "-n", help="Max results to show")] = 10,
) -> None:
    """Keyword search across wiki articles and summaries (no LLM, instant).

    Uses BM25 ranking. Searches concept articles and per-source summaries.
    Run kb compile first to populate the wiki.
    """
    from .search import search as search_fn
    from rich.table import Table

    vault_path = get_vault_path(vault)
    results = search_fn(vault_path, query, top_k=top)

    if not results:
        console.print(
            "[yellow]No results.[/yellow] The wiki may not be compiled yet — run [bold]kb compile[/bold] first."
        )
        return

    t = Table(show_header=True, header_style="bold", show_lines=True, expand=True)
    t.add_column("#", width=3, justify="right", style="dim")
    t.add_column("Type", width=9)
    t.add_column("Title", min_width=20, max_width=35)
    t.add_column("Snippet")
    t.add_column("Path", style="dim", min_width=20, max_width=40)

    for i, r in enumerate(results, 1):
        kind_style = "cyan" if r["kind"] == "concept" else "green"
        t.add_row(
            str(i),
            f"[{kind_style}]{r['kind']}[/{kind_style}]",
            r["title"],
            r["snippet"],
            r["path"],
        )

    console.print(t)
    console.print(f"[dim]{len(results)} result(s) for '{query}'[/dim]")


# ── Utility ────────────────────────────────────────────────────────────────────

@app.command()
def status(vault: VaultArg = None) -> None:
    """Show vault status: document counts, wiki outputs, and pending changes."""
    import datetime
    from rich.table import Table
    from .ingest import load_state, _TEXT_EXTS, _PDF_EXTS, _IMAGE_EXTS

    vault_path = get_vault_path(vault)
    raw = vault_path / "raw"
    wiki = vault_path / "wiki"

    type_counts: dict[str, int] = {"articles": 0, "pdfs": 0, "images": 0}
    raw_rel_paths: set[str] = set()
    for subdir, exts in [("articles", _TEXT_EXTS), ("pdfs", _PDF_EXTS), ("images", _IMAGE_EXTS)]:
        d = raw / subdir
        if d.exists():
            files = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in exts]
            type_counts[subdir] = len(files)
            for f in files:
                raw_rel_paths.add(str(f.relative_to(vault_path)).replace("\\", "/"))

    state = load_state(wiki) if wiki.exists() else None
    last_compile = "[yellow]never[/yellow]"
    if state and state.last_compile:
        try:
            dt = datetime.datetime.fromisoformat(state.last_compile)
            last_compile = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            last_compile = state.last_compile

    summarized = set(state.summary_hashes.keys()) if state else set()
    pending = len(raw_rel_paths - summarized)

    concept_count = len(list((wiki / "concepts").glob("*.md"))) if (wiki / "concepts").exists() else 0
    summary_count = len(list((wiki / "summaries").glob("*.md"))) if (wiki / "summaries").exists() else 0

    overview = Table(show_header=False, box=None, padding=(0, 2))
    overview.add_column(style="dim")
    overview.add_column()
    overview.add_row("Vault", str(vault_path))
    overview.add_row("Last compile", last_compile)
    console.print(overview)
    console.print()

    raw_table = Table(title="Raw documents", show_header=True, header_style="bold")
    raw_table.add_column("Location")
    raw_table.add_column("Files", justify="right")
    raw_table.add_row("raw/articles/", str(type_counts["articles"]))
    raw_table.add_row("raw/pdfs/", str(type_counts["pdfs"]))
    raw_table.add_row("raw/images/", str(type_counts["images"]))
    raw_table.add_row("[bold]Total[/bold]", f"[bold]{sum(type_counts.values())}[/bold]")
    console.print(raw_table)
    console.print()

    wiki_table = Table(title="Wiki", show_header=True, header_style="bold")
    wiki_table.add_column("Type")
    wiki_table.add_column("Count", justify="right")
    wiki_table.add_row("Summaries", str(summary_count))
    wiki_table.add_row("Concept articles", str(concept_count))
    if pending > 0:
        wiki_table.add_row(
            "[yellow]Pending compile[/yellow]",
            f"[yellow]{pending} doc(s) — run kb compile[/yellow]",
        )
    console.print(wiki_table)


@app.command()
def config(
    vault: Annotated[Optional[str], typer.Option("--vault", help="Set default vault path")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="Set Anthropic API key")] = None,
) -> None:
    """Show or update the global config (~/.kb).

    With no flags: print current resolved values.
    With flags: write new values into ~/.kb (created if missing).

    Settings in ~/.kb are the baseline; a local .env in the working directory
    overrides them. Vault path is also overridable per-command with --vault.
    """
    import os
    from .utils import _load_env

    if vault or api_key:
        lines: list[str] = []
        if GLOBAL_CONFIG.exists():
            lines = GLOBAL_CONFIG.read_text(encoding="utf-8").splitlines()

        def _set(key: str, value: str) -> None:
            prefix = f"{key}="
            for i, line in enumerate(lines):
                if line.startswith(prefix):
                    lines[i] = f"{key}={value}"
                    return
            lines.append(f"{key}={value}")

        if vault:
            _set("KB_VAULT", str(Path(vault).resolve()))
        if api_key:
            _set("ANTHROPIC_API_KEY", api_key)

        GLOBAL_CONFIG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        console.print(f"[green]Saved[/green] → {GLOBAL_CONFIG}")

    _load_env()
    resolved_vault = os.environ.get("KB_VAULT", "[not set]")
    raw_key = os.environ.get("ANTHROPIC_API_KEY", "")
    masked_key = (raw_key[:12] + "..." + raw_key[-4:]) if len(raw_key) > 16 else ("[not set]" if not raw_key else raw_key)

    from rich.table import Table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("Config file", str(GLOBAL_CONFIG))
    t.add_row("KB_VAULT", resolved_vault)
    t.add_row("ANTHROPIC_API_KEY", masked_key)
    console.print(t)


if __name__ == "__main__":
    app()
