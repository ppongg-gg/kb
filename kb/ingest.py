from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader
from rich.table import Table

from .models import BuildState, SourceDoc
from .utils import console

_SKIP_DIRS = {".git", ".obsidian", "__pycache__", "wiki", "outputs"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_TEXT_EXTS = {".md", ".txt", ".markdown"}
_PDF_EXTS = {".pdf"}


def compute_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext in _TEXT_EXTS:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "md" if ext in {".md", ".markdown"} else "txt"
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not read {path.name}: {e}")
            return "", "txt"
    if ext in _PDF_EXTS:
        try:
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text, "pdf"
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not parse PDF {path.name}: {e}")
            return "", "pdf"
    if ext in _IMAGE_EXTS:
        return "", "image"
    console.print(f"[yellow]Warning:[/yellow] Unsupported file type, skipping: {path.name}")
    return None, None


def load_state(wiki_path: Path) -> BuildState:
    state_file = wiki_path / "_state.json"
    if state_file.exists():
        try:
            return BuildState.model_validate_json(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return BuildState()


def save_state(wiki_path: Path, state: BuildState) -> None:
    state_file = wiki_path / "_state.json"
    state_file.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def ingest(vault: Path) -> list[SourceDoc]:
    raw_path = vault / "raw"
    wiki_path = vault / "wiki"
    wiki_path.mkdir(parents=True, exist_ok=True)

    state = load_state(wiki_path)
    old_hashes = dict(state.file_hashes)

    docs: list[SourceDoc] = []
    table = Table(title="Ingested Documents", show_lines=False)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Size", justify="right")
    table.add_column("Changed", justify="center")

    for path in sorted(raw_path.rglob("*")):
        if path.is_dir():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.name.startswith("."):
            continue

        content, file_type = extract_text(path)
        if file_type is None:
            continue

        md5 = compute_md5(path)
        rel_path = str(path.relative_to(vault)).replace("\\", "/")
        changed = old_hashes.get(rel_path) != md5
        state.file_hashes[rel_path] = md5

        size = path.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"

        docs.append(SourceDoc(
            path=path,
            rel_path=rel_path,
            md5=md5,
            content=content,
            file_type=file_type,
            size_bytes=size,
        ))

        table.add_row(
            path.name,
            file_type,
            size_str,
            "[green]yes[/green]" if changed else "no",
        )

    save_state(wiki_path, state)
    console.print(table)
    return docs
