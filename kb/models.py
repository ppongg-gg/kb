from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class SourceDoc(BaseModel):
    path: Path
    rel_path: str
    md5: str
    content: str
    file_type: Literal["md", "pdf", "image", "txt"]
    size_bytes: int


class SummaryResult(BaseModel):
    source_rel_path: str
    summary: str
    concepts: list[str]
    wiki_path: str


class ConceptArticle(BaseModel):
    slug: str
    title: str
    summary_one_line: str
    body: str
    tags: list[str]
    source_slugs: list[str]
    wiki_path: str = ""


class IndexEntry(BaseModel):
    path: str
    title: str
    one_line: str
    keywords: list[str]
    entry_type: Literal["concept", "summary"]


class MasterIndex(BaseModel):
    generated_at: str
    topics: dict[str, list[IndexEntry]]
    all_entries: list[IndexEntry]


class BuildState(BaseModel):
    file_hashes: dict[str, str] = {}
    summary_hashes: dict[str, str] = {}
    last_compile: str | None = None
