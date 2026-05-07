from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

import frontmatter
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from .utils import console

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})"
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_CHUNK_SECONDS = 45  # group transcript segments into ~45-second paragraphs


def extract_video_id(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def fetch_metadata(video_id: str) -> dict:
    """Fetch title and channel via YouTube's oEmbed endpoint (no API key needed)."""
    oembed_url = (
        f"https://www.youtube.com/oembed"
        f"?url=https://www.youtube.com/watch?v={video_id}&format=json"
    )
    try:
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "kb/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not fetch video metadata: {e}")
        return {}


def fetch_transcript(video_id: str, languages: list[str] | None = None) -> list[dict]:
    """Return transcript segments as dicts with 'text', 'start', 'duration'."""
    api = YouTubeTranscriptApi()
    langs = languages or ["en"]
    try:
        snippets = api.fetch(video_id, languages=langs)
    except NoTranscriptFound:
        # Fall back to the first available transcript in any language
        transcript_list = api.list(video_id)
        first = next(iter(transcript_list))
        snippets = first.fetch()
    return [{"text": s.text, "start": s.start, "duration": s.duration} for s in snippets]


def _format_timestamp(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"[{m:02d}:{s:02d}]"


def _chunk_segments(segments: list[dict]) -> list[tuple[float, str]]:
    """Group raw transcript segments into ~CHUNK_SECONDS paragraphs."""
    if not segments:
        return []
    chunks: list[tuple[float, str]] = []
    start = segments[0]["start"]
    texts: list[str] = []

    for seg in segments:
        if seg["start"] - start >= _CHUNK_SECONDS and texts:
            chunks.append((start, " ".join(texts)))
            start = seg["start"]
            texts = []
        texts.append(seg["text"].replace("\n", " ").strip())

    if texts:
        chunks.append((start, " ".join(texts)))
    return chunks


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:80]


def build_markdown(video_id: str, url: str, metadata: dict, segments: list[dict]) -> tuple[str, str]:
    """Return (filename_stem, markdown_content)."""
    title = metadata.get("title") or f"YouTube {video_id}"
    channel = metadata.get("author_name") or "Unknown"
    watch_url = f"https://www.youtube.com/watch?v={video_id}"

    chunks = _chunk_segments(segments)

    transcript_lines = [
        f"{_format_timestamp(start)} {text}" for start, text in chunks
    ]

    post = frontmatter.Post(
        "\n".join([
            f"# {title}",
            "",
            f"> **Channel:** {channel}  ",
            f"> **Source:** [{title}]({watch_url})",
            "",
            "## Transcript",
            "",
            *[f"{line}\n" for line in transcript_lines],
        ]),
        title=title,
        channel=channel,
        source=watch_url,
        type="youtube-transcript",
    )

    return _slugify(title), frontmatter.dumps(post)


def add_youtube(vault: Path, url: str) -> None:
    video_id = extract_video_id(url)
    if not video_id:
        console.print(f"[red]Error:[/red] Could not extract video ID from: {url}")
        return

    console.print(f"[dim]Fetching metadata for {video_id}...[/dim]")
    metadata = fetch_metadata(video_id)
    title = metadata.get("title") or video_id
    console.print(f"[dim]Title:[/dim] {title}")

    console.print("[dim]Fetching transcript...[/dim]")
    try:
        segments = fetch_transcript(video_id)
    except TranscriptsDisabled:
        console.print("[red]Error:[/red] Transcripts are disabled for this video.")
        return
    except Exception as e:
        console.print(f"[red]Error:[/red] Could not fetch transcript: {e}")
        return

    slug, content = build_markdown(video_id, url, metadata, segments)
    filename = f"{slug}.md"
    dest = vault / "raw" / "articles" / filename

    if dest.exists():
        console.print(f"[yellow]Already exists:[/yellow] raw/articles/{filename}")
        return

    dest.write_text(content, encoding="utf-8")
    console.print(
        f"[green]Added:[/green] {title} → raw/articles/{filename} "
        f"([dim]{len(segments)} segments → {len(_chunk_segments(segments))} paragraphs[/dim])"
    )
