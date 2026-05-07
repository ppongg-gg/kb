from __future__ import annotations

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
