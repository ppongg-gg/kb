from __future__ import annotations

import base64
import json
from pathlib import Path

import frontmatter
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .ingest import ingest, load_state, save_state
from .models import ConceptArticle, SummaryResult
from .utils import console, get_client
from . import index as index_module

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

SUMMARY_SYSTEM = (
    "You are a knowledge base compiler. Given a document, respond with only a JSON "
    "object (no markdown fences) with exactly these keys:\n"
    '- "summary": 2-3 sentence summary of the main argument or content\n'
    '- "concepts": list of 3-10 key concept strings (short noun phrases)'
)

CONCEPT_SYSTEM = (
    "You are a knowledge base architect. Given document summaries, identify concept "
    "clusters and write one article per concept that synthesizes knowledge across sources. "
    "Output one JSON object per line (JSONL — no surrounding array, no markdown fences). "
    "Each line must be a complete, self-contained JSON object with these keys:\n"
    '- "slug": kebab-case filename (lowercase, hyphens only, no special chars)\n'
    '- "title": human-readable title\n'
    '- "summary_one_line": one sentence summary\n'
    '- "body": full markdown article body using [[concept-slug]] for internal links '
    "and a ## Sources section with [[wiki/summaries/filename]] backlinks\n"
    '- "tags": list of tag strings\n'
    '- "source_slugs": list of raw file rel_paths that contributed\n'
    "Output every concept on its own line. Do not wrap in an array."
)

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _parse_json_response(text: str) -> dict | list:
    """Parse a single JSON object or array (used for Phase 1 summaries)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def _parse_jsonl_response(text: str) -> list[dict]:
    """Parse JSONL output from Phase 2 concept synthesis.

    One JSON object per line. Incomplete lines (truncated output) are skipped,
    so a token-limit cutoff only loses the last article rather than everything.
    """
    articles = []
    for line in text.splitlines():
        line = line.strip().rstrip(",")  # tolerate accidental array syntax
        if not line or line in ("[", "]"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                articles.append(obj)
        except json.JSONDecodeError:
            pass  # truncated or malformed line — skip silently
    return articles


def summarize_document(client, doc) -> SummaryResult:
    try:
        if doc.file_type == "image":
            ext = Path(doc.path).suffix.lower()
            media_type = _MEDIA_TYPES.get(ext, "image/jpeg")
            image_data = base64.standard_b64encode(Path(doc.path).read_bytes()).decode()
            messages = [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": "Summarize this image for a knowledge base. Respond with only the JSON object."},
            ]}]
        else:
            content = doc.content[:180_000] if len(doc.content) > 180_000 else doc.content
            messages = [{"role": "user", "content": content}]

        response = client.messages.create(
            model=HAIKU,
            max_tokens=512,
            system=[{"type": "text", "text": SUMMARY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        data = _parse_json_response(response.content[0].text)
        return SummaryResult(
            source_rel_path=doc.rel_path,
            summary=str(data.get("summary", "")),
            concepts=[str(c) for c in data.get("concepts", [])],
            wiki_path="",
        )
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Summary failed for {doc.rel_path}: {e}")
        return SummaryResult(
            source_rel_path=doc.rel_path,
            summary="[extraction failed]",
            concepts=[],
            wiki_path="",
        )


def run_phase1(client, vault: Path, docs, state, force: bool = False) -> list[SummaryResult]:
    summaries_dir = vault / "wiki" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    to_process = [
        d for d in docs
        if force or state.summary_hashes.get(d.rel_path) != d.md5
    ]

    if not to_process:
        console.print("[dim]All summaries up to date, skipping phase 1.[/dim]")
        # Return existing summaries from disk
        return _load_existing_summaries(vault, docs)

    results: list[SummaryResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Summarizing documents...", total=len(to_process))

        for doc in to_process:
            progress.update(task, description=f"Summarizing {doc.path.name[:40]}...")
            result = summarize_document(client, doc)

            stem = Path(doc.rel_path).stem
            wiki_path = f"wiki/summaries/{stem}.md"
            result.wiki_path = wiki_path

            post = frontmatter.Post(
                result.summary,
                source=doc.rel_path,
                concepts=result.concepts,
            )
            out_path = vault / wiki_path
            out_path.write_text(frontmatter.dumps(post), encoding="utf-8")

            state.summary_hashes[doc.rel_path] = doc.md5
            results.append(result)
            progress.advance(task)

    # Merge with unchanged docs' existing summaries
    processed_paths = {r.source_rel_path for r in results}
    for doc in docs:
        if doc.rel_path not in processed_paths:
            stem = Path(doc.rel_path).stem
            wiki_path = vault / "wiki" / "summaries" / f"{stem}.md"
            if wiki_path.exists():
                try:
                    post = frontmatter.load(str(wiki_path))
                    results.append(SummaryResult(
                        source_rel_path=doc.rel_path,
                        summary=post.content,
                        concepts=post.get("concepts", []),
                        wiki_path=f"wiki/summaries/{stem}.md",
                    ))
                except Exception:
                    pass

    return results


def _load_existing_summaries(vault: Path, docs) -> list[SummaryResult]:
    results = []
    for doc in docs:
        stem = Path(doc.rel_path).stem
        wiki_path = vault / "wiki" / "summaries" / f"{stem}.md"
        if wiki_path.exists():
            try:
                post = frontmatter.load(str(wiki_path))
                results.append(SummaryResult(
                    source_rel_path=doc.rel_path,
                    summary=post.content,
                    concepts=post.get("concepts", []),
                    wiki_path=f"wiki/summaries/{stem}.md",
                ))
            except Exception:
                pass
    return results


def run_phase2(client, vault: Path, summaries: list[SummaryResult]) -> list[ConceptArticle]:
    concepts_dir = vault / "wiki" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    parts = []
    for s in summaries:
        concepts_str = ", ".join(s.concepts) if s.concepts else "none"
        parts.append(f"## {s.source_rel_path}\n{s.summary}\nConcepts: {concepts_str}")
    combined = "\n\n".join(parts)

    # Sonnet has 200K context; leave room for output
    if len(combined) > 180_000:
        combined = combined[:180_000]
        console.print("[yellow]Warning:[/yellow] Summary text truncated to 180K chars for concept synthesis.")

    console.print("[dim]Running concept synthesis (Sonnet)...[/dim]")
    try:
        response = client.messages.create(
            model=SONNET,
            max_tokens=16000,
            system=[{"type": "text", "text": CONCEPT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": combined}],
        )
        raw_text = response.content[0].text
        data = _parse_jsonl_response(raw_text)
        if not data:
            raise ValueError("No concept articles parsed from response")
        if response.stop_reason == "max_tokens":
            console.print(
                f"[yellow]Warning:[/yellow] Concept synthesis hit token limit — "
                f"{len(data)} article(s) recovered from partial output."
            )
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Concept synthesis failed: {e}")
        return []

    articles: list[ConceptArticle] = []
    for item in data:
        try:
            slug = str(item.get("slug", "untitled")).strip()
            article = ConceptArticle(
                slug=slug,
                title=str(item.get("title", slug)),
                summary_one_line=str(item.get("summary_one_line", "")),
                body=str(item.get("body", "")),
                tags=[str(t) for t in item.get("tags", [])],
                source_slugs=[str(s) for s in item.get("source_slugs", [])],
                wiki_path=f"wiki/concepts/{slug}.md",
            )

            post = frontmatter.Post(
                article.body,
                title=article.title,
                summary_one_line=article.summary_one_line,
                tags=article.tags,
                sources=article.source_slugs,
            )
            out_path = vault / "wiki" / "concepts" / f"{slug}.md"
            out_path.write_text(frontmatter.dumps(post), encoding="utf-8")
            articles.append(article)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Skipped concept article: {e}")

    return articles


def compile_wiki(vault: Path, full: bool = False) -> None:
    client = get_client()
    wiki_path = vault / "wiki"
    wiki_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold]Compiling wiki[/bold] in [cyan]{vault}[/cyan]")

    docs = ingest(vault)
    if not docs:
        console.print("[yellow]No documents found in raw/. Add files and try again.[/yellow]")
        return

    state = _load_state_from_wiki(wiki_path)
    changed_count = sum(
        1 for d in docs if state.summary_hashes.get(d.rel_path) != d.md5
    )
    concepts_missing = not any((wiki_path / "concepts").glob("*.md"))
    any_changed = full or changed_count > 0 or concepts_missing

    summaries = run_phase1(client, vault, docs, state, force=full)
    save_state(wiki_path, state)

    articles: list[ConceptArticle] = []
    if any_changed and summaries:
        articles = run_phase2(client, vault, summaries)
    else:
        console.print("[dim]No changes detected, skipping concept synthesis.[/dim]")

    import datetime
    state.last_compile = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_state(wiki_path, state)

    index_module.build_index(vault)

    console.print(
        f"\n[green]Done.[/green] "
        f"{len(docs)} docs · {len(summaries)} summaries · {len(articles)} concept articles"
    )


def _load_state_from_wiki(wiki_path: Path):
    from .ingest import load_state
    return load_state(wiki_path)
