from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from .utils import console, ensure_vault_structure, get_vault_path

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


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask the knowledge base")],
    vault: VaultArg = None,
) -> None:
    """Ask a question against the compiled wiki."""
    from .agent import ask as ask_fn

    vault_path = get_vault_path(vault)
    ask_fn(vault_path, question)


if __name__ == "__main__":
    app()
