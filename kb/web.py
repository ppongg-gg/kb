from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from .utils import console

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:80]


def fetch_article(url: str) -> tuple[str, str]:
    """Return (title, markdown_content). Raises ValueError on failure."""
    try:
        import trafilatura
    except ImportError:
        raise ImportError("trafilatura is required: uv add trafilatura")

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not download page — check the URL or your network connection")

    metadata = trafilatura.extract_metadata(downloaded)
    title = (metadata.title if metadata else None) or url

    content = trafilatura.extract(
        downloaded,
        include_formatting=True,
        include_links=False,
        output_format="markdown",
    )
    if not content:
        raise ValueError(
            "Could not extract article content — the page may be JavaScript-rendered or paywalled"
        )

    return title, content


def build_markdown(url: str, title: str, content: str) -> tuple[str, str]:
    """Return (filename_stem, markdown_content)."""
    post = frontmatter.Post(
        "\n".join([
            f"# {title}",
            "",
            f"> **Source:** [{title}]({url})",
            "",
            content,
        ]),
        title=title,
        source=url,
        type="web-article",
    )
    return _slugify(title), frontmatter.dumps(post)


def add_url(vault: Path, url: str) -> None:
    console.print(f"[dim]Fetching {url}...[/dim]")
    try:
        title, content = fetch_article(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    console.print(f"[dim]Title:[/dim] {title}")

    slug, markdown = build_markdown(url, title, content)
    filename = f"{slug}.md"
    dest = vault / "raw" / "articles" / filename

    if dest.exists():
        console.print(f"[yellow]Already exists:[/yellow] raw/articles/{filename}")
        return

    dest.write_text(markdown, encoding="utf-8")
    word_count = len(content.split())
    console.print(
        f"[green]Added:[/green] {title} → raw/articles/{filename} "
        f"([dim]{word_count:,} words[/dim])"
    )
