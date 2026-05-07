from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
from rich.markdown import Markdown

from .models import MasterIndex
from .utils import console, get_client

HAIKU = "claude-haiku-4-5-20251001"

AGENT_SYSTEM = (
    "You are a personal knowledge base assistant. Answer questions using only the "
    "articles in the wiki. Always call get_index first to understand what's available, "
    "then read relevant articles before answering. Be specific and cite sources using "
    "[[wiki/path]] notation. If information is not in the wiki, say so."
)

TOOLS = [
    {
        "name": "get_index",
        "description": (
            "Returns the full master index as a JSON object showing all topics and articles. "
            "Always call this first to understand what is available in the wiki."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_article",
        "description": (
            "Reads the full markdown content of a wiki article. "
            "path must be a wiki-relative path like 'wiki/concepts/machine-learning.md'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Wiki-relative path to the article"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_articles",
        "description": "Lists all article paths under a given topic name from the index.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "Topic name from the index"}},
            "required": ["topic"],
        },
    },
]


def _tool_get_index(vault: Path) -> str:
    index_file = vault / "wiki" / "_index.json"
    if not index_file.exists():
        return json.dumps({"error": "Index not found. Run kb compile first."})
    return index_file.read_text(encoding="utf-8")


def _tool_read_article(vault: Path, path: str) -> str:
    clean = path.strip().replace("\\", "/")
    if not clean.startswith("wiki/"):
        return "[Access denied: path must start with 'wiki/']"
    full_path = vault / clean
    if not full_path.exists():
        return f"[Article not found: {clean}]"
    try:
        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"[Error reading article: {e}]"


def _tool_list_articles(vault: Path, index: MasterIndex, topic: str) -> str:
    entries = index.topics.get(topic, [])
    if not entries:
        available = list(index.topics.keys())
        return json.dumps({"error": f"Topic '{topic}' not found.", "available_topics": available})
    return json.dumps([e.path for e in entries])


def _dispatch(vault: Path, index: MasterIndex, name: str, tool_input: dict) -> str:
    if name == "get_index":
        return _tool_get_index(vault)
    if name == "read_article":
        return _tool_read_article(vault, tool_input.get("path", ""))
    if name == "list_articles":
        return _tool_list_articles(vault, index, tool_input.get("topic", ""))
    return f"[Unknown tool: {name}]"


def _slugify(text: str, max_words: int = 5) -> str:
    words = re.sub(r"[^a-z0-9\s]", "", text.lower()).split()[:max_words]
    return "-".join(words) or "answer"


def ask(vault: Path, question: str) -> str:
    index_file = vault / "wiki" / "_index.json"
    if not index_file.exists():
        console.print("[red]Error:[/red] Wiki index not found. Run [bold]kb compile[/bold] first.")
        import typer
        raise typer.Exit(1)

    index = MasterIndex.model_validate_json(index_file.read_text(encoding="utf-8"))
    client = get_client()

    messages = [{"role": "user", "content": question}]
    final_text = ""

    console.print(f"\n[bold]Q:[/bold] {question}\n")

    while True:
        response = client.messages.create(
            model=HAIKU,
            max_tokens=2048,
            system=[{"type": "text", "text": AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _dispatch(vault, index, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason — extract any text and break
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text
            break

    if final_text:
        console.print(Markdown(final_text))
        _save_output(vault, question, final_text)

    return final_text


def _save_output(vault: Path, question: str, answer: str) -> None:
    outputs_dir = vault / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    slug = _slugify(question)
    filename = f"{timestamp}-{slug}.md"

    post = frontmatter.Post(answer, question=question, date=now.isoformat())
    (outputs_dir / filename).write_text(frontmatter.dumps(post), encoding="utf-8")
    console.print(f"\n[dim]Saved to outputs/{filename}[/dim]")
