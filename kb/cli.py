from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from .utils import GLOBAL_CONFIG, console, ensure_vault_structure, get_vault_path

app = typer.Typer(
    name="kb",
    help="LLM-powered personal knowledge base.",
    add_completion=False,
)

VaultArg = Annotated[Optional[str], typer.Option("--vault", "-v", help="Path to vault directory")]


@app.command()
def ingest(vault: VaultArg = None) -> None:
    """Walk raw/, extract text, compute hashes, and update the build state."""
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
    """Build or update the wiki (incremental by default)."""
    from .compile import compile_wiki

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)
    compile_wiki(vault_path, full=full)


@app.command()
def add(
    files: Annotated[list[str], typer.Argument(help="File(s) to add to the vault")],
    vault: VaultArg = None,
) -> None:
    """Copy file(s) into the appropriate raw/ subdirectory based on type."""
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
    """Fetch a YouTube transcript and save it as a markdown file in raw/articles/."""
    from .youtube import add_youtube as _add_youtube

    vault_path = get_vault_path(vault)
    ensure_vault_structure(vault_path)
    _add_youtube(vault_path, url)


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask the knowledge base")],
    vault: VaultArg = None,
) -> None:
    """Ask a question against the compiled wiki."""
    from .agent import ask as ask_fn

    vault_path = get_vault_path(vault)
    ask_fn(vault_path, question)


@app.command()
def config(
    vault: Annotated[Optional[str], typer.Option("--vault", help="Set default vault path")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="Set Anthropic API key")] = None,
) -> None:
    """Show or update the global config (~/.kb).

    With no flags: show current resolved values.
    With flags: write new values into ~/.kb.
    """
    import os
    from .utils import _load_env

    if vault or api_key:
        # Read existing lines, update or add keys
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

    # Always show current state after applying changes
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
