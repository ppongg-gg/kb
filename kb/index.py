from __future__ import annotations

import datetime
from pathlib import Path

import frontmatter

from .models import IndexEntry, MasterIndex
from .utils import console


def _first_sentence(content: str) -> str:
    for line in content.strip().splitlines():
        line = line.strip().lstrip("# ")
        if line and not line.startswith("!") and not line.startswith("|"):
            sentence = line.split(".")[0]
            return sentence[:120]
    return ""


def build_index(vault: Path) -> MasterIndex:
    wiki_path = vault / "wiki"
    all_entries: list[IndexEntry] = []
    topics: dict[str, list[IndexEntry]] = {}

    # Concept articles
    for path in sorted((wiki_path / "concepts").glob("*.md")):
        try:
            post = frontmatter.load(str(path))
            title = post.get("title") or path.stem.replace("-", " ").title()
            tags: list[str] = post.get("tags") or []
            one_line = post.get("summary_one_line") or _first_sentence(post.content) or title
            keywords = tags[:5]

            entry = IndexEntry(
                path=f"wiki/concepts/{path.name}",
                title=title,
                one_line=one_line,
                keywords=keywords,
                entry_type="concept",
            )
            all_entries.append(entry)

            primary = tags[0] if tags else "general"
            topics.setdefault(primary, []).append(entry)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not index {path.name}: {e}")

    # Summaries
    sources: list[IndexEntry] = []
    for path in sorted((wiki_path / "summaries").glob("*.md")):
        try:
            post = frontmatter.load(str(path))
            title = post.get("title") or path.stem
            first_sentence = post.content.strip().split(".")[0][:120] if post.content.strip() else title
            concepts: list[str] = post.get("concepts") or []

            entry = IndexEntry(
                path=f"wiki/summaries/{path.name}",
                title=title,
                one_line=first_sentence,
                keywords=concepts[:5],
                entry_type="summary",
            )
            all_entries.append(entry)
            sources.append(entry)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not index {path.name}: {e}")

    if sources:
        topics["sources"] = sources

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    master = MasterIndex(generated_at=now, topics=topics, all_entries=all_entries)

    # Write _index.json
    (wiki_path / "_index.json").write_text(master.model_dump_json(indent=2), encoding="utf-8")

    # Write index.md
    lines = [
        "---",
        "title: Knowledge Base Index",
        "---",
        "# Knowledge Base Index",
        f"*Generated: {now[:19].replace('T', ' ')} UTC*",
        "",
    ]

    concept_topics = {k: v for k, v in topics.items() if k != "sources"}
    if concept_topics:
        lines.append("## Concepts")
        lines.append("")
        for topic, entries in sorted(concept_topics.items()):
            lines.append(f"### {topic.replace('-', ' ').title()}")
            for e in entries:
                slug = Path(e.path).stem
                lines.append(f"- [[wiki/concepts/{slug}|{e.title}]] — {e.one_line}")
            lines.append("")

    if sources:
        lines.append("## Sources")
        lines.append("")
        for e in sources:
            stem = Path(e.path).stem
            lines.append(f"- [[wiki/summaries/{stem}|{stem}]] — {e.one_line}")
        lines.append("")

    (wiki_path / "index.md").write_text("\n".join(lines), encoding="utf-8")

    n_concepts = len(all_entries) - len(sources)
    console.print(f"[dim]Index: {n_concepts} concept articles, {len(sources)} summaries[/dim]")
    return master
