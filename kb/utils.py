from __future__ import annotations

import os
import sys
from pathlib import Path

import anthropic
import typer
from dotenv import load_dotenv
from rich.console import Console

# On Windows the default stdout encoding is cp1252, which can't represent many
# Unicode characters that LLMs routinely produce. Reconfigure to UTF-8 before
# creating the console so all output goes through a UTF-8 stream.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.platform == "win32" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(legacy_windows=False)

_VAULT_SUBDIRS = [
    "raw/articles",
    "raw/pdfs",
    "raw/images",
    "wiki/concepts",
    "wiki/summaries",
    "outputs",
]


def get_vault_path(vault: str | None) -> Path:
    load_dotenv()
    raw = vault or os.environ.get("KB_VAULT") or "vault"
    p = Path(raw).resolve()
    if not p.exists():
        raise typer.BadParameter(f"Vault directory not found: {p}")
    return p


def ensure_vault_structure(vault: Path) -> None:
    for sub in _VAULT_SUBDIRS:
        (vault / sub).mkdir(parents=True, exist_ok=True)


def get_client() -> anthropic.Anthropic:
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set. Add it to .env or your environment.")
        raise typer.Exit(1)
    return anthropic.Anthropic(api_key=key)
