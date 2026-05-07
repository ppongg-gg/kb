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

# Global config file — set KB_VAULT and ANTHROPIC_API_KEY here once so every
# command works from any directory without a local .env.
GLOBAL_CONFIG = Path.home() / ".kb"

_VAULT_SUBDIRS = [
    "raw/articles",
    "raw/pdfs",
    "raw/images",
    "wiki/concepts",
    "wiki/summaries",
    "outputs",
]


def _load_env() -> None:
    """Load config: global ~/.kb first, then .env in cwd if present (cwd wins).

    Deliberately uses an explicit cwd path rather than load_dotenv()'s default
    find_dotenv() behaviour, which walks up the calling file's directory tree and
    would always find the project .env regardless of where kb is invoked from.
    """
    load_dotenv(GLOBAL_CONFIG, override=False)
    load_dotenv(Path.cwd() / ".env", override=True)


def get_vault_path(vault: str | None) -> Path:
    _load_env()
    raw = vault or os.environ.get("KB_VAULT")
    if not raw:
        console.print(
            "[red]Error:[/red] No vault configured.\n"
            f"Run [bold]kb config[/bold] to set one, or pass [bold]--vault PATH[/bold]."
        )
        raise typer.Exit(1)
    p = Path(raw).resolve()
    if not p.exists():
        console.print(f"[red]Error:[/red] Vault directory not found: {p}")
        raise typer.Exit(1)
    return p


def ensure_vault_structure(vault: Path) -> None:
    for sub in _VAULT_SUBDIRS:
        (vault / sub).mkdir(parents=True, exist_ok=True)


def get_client() -> anthropic.Anthropic:
    _load_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY not set.\n"
            f"Run [bold]kb config[/bold] to configure it, or set it in your environment."
        )
        raise typer.Exit(1)
    return anthropic.Anthropic(api_key=key)
