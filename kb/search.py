from __future__ import annotations

import re
from pathlib import Path

import frontmatter
from rank_bm25 import BM25Okapi

from .utils import console


def _tokenize(text: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9]+", " ", text.lower()).split() if t]


def _extract_snippet(body: str, query_tokens: list[str], max_len: int = 160) -> str:
    body_lower = body.lower()
    best_pos = -1
    for token in query_tokens:
        pos = body_lower.find(token)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        text = body[:max_len].strip()
        suffix = "…" if len(body) > max_len else ""
    else:
        start = max(0, best_pos - 40)
        end = min(len(body), start + max_len)
        text = body[start:end].strip()
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(body) else ""
        text = prefix + text + suffix

    return re.sub(r"\s+", " ", text)


def search(vault: Path, query: str, top_k: int = 10) -> list[dict]:
    """BM25 keyword search over wiki/concepts and wiki/summaries.

    Returns a list of result dicts (path, title, kind, score, snippet),
    sorted by relevance descending. Returns [] if the wiki hasn't been compiled yet.
    """
    wiki = vault / "wiki"
    if not wiki.exists():
        return []

    docs: list[dict] = []
    for kind, directory in [("concept", wiki / "concepts"), ("summary", wiki / "summaries")]:
        if not directory.exists():
            continue
        for md_file in sorted(directory.glob("*.md")):
            try:
                post = frontmatter.load(str(md_file))
                rel_path = str(md_file.relative_to(vault)).replace("\\", "/")
                title = str(post.get("title") or md_file.stem.replace("-", " ").title())
                docs.append({"path": rel_path, "title": title, "body": post.content, "kind": kind})
            except Exception:
                pass

    if not docs:
        return []

    corpus = [_tokenize(f"{d['title']} {d['body']}") for d in docs]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query))

    results = []
    for idx, score in sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]:
        if score <= 0:
            break
        doc = docs[idx]
        results.append({
            "path": doc["path"],
            "title": doc["title"],
            "kind": doc["kind"],
            "score": round(float(score), 3),
            "snippet": _extract_snippet(doc["body"], _tokenize(query)),
        })

    return results
