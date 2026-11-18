"""Tiny keyword-based retrieval over the project documentation (RAG).

No external services or dependencies: documents in ``docs/`` are split into
sections, and the sections most relevant to a question are returned with a
BM25-style score. The AI assistant gives these sections to the language
model as context - or shows them directly when no model is configured.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_STOP = frozenset("""
a an and are as at be but by can do does for from has have how i if in into is it
its me my of on or our so that the their them then there these they this to us
was we what when where which who why will with you your should would could about
""".split())

_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    words = _TOKEN.findall(text.lower())
    out = []
    for w in words:
        if w in _STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return out


@dataclass
class Chunk:
    source: str
    title: str
    text: str
    tokens: Counter
    length: int


def split_markdown(source: str, markdown: str, max_chars: int = 1400) -> list[Chunk]:
    """Split a markdown document into chunks at headings."""
    chunks: list[Chunk] = []
    title = source
    buf: list[str] = []

    def flush():
        text = "\n".join(buf).strip()
        buf.clear()
        if len(text) < 40:
            return
        for i in range(0, len(text), max_chars):
            piece = text[i:i + max_chars]
            tokens = tokenize(title + " " + piece)
            chunks.append(Chunk(source, title, piece, Counter(tokens), len(tokens)))

    for line in markdown.splitlines():
        if re.match(r"^#{1,3}\s+\S", line):
            flush()
            title = line.lstrip("#").strip()
        buf.append(line)
    flush()
    return chunks


def load_docs(directory: str | Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    base = Path(directory)
    if not base.is_dir():
        return chunks
    for path in sorted(base.glob("*.md")):
        try:
            chunks.extend(split_markdown(path.name, path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return chunks


def search(chunks: list[Chunk], query: str, k: int = 3) -> list[tuple[float, Chunk]]:
    """Return up to ``k`` (score, chunk) pairs, best first."""
    terms = tokenize(query)
    if not terms or not chunks:
        return []
    n = len(chunks)
    avg_len = sum(c.length for c in chunks) / n or 1.0
    df = Counter()
    for chunk in chunks:
        for term in set(terms):
            if term in chunk.tokens:
                df[term] += 1
    scored = []
    for chunk in chunks:
        score = 0.0
        for term in set(terms):
            tf = chunk.tokens.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * chunk.length / avg_len))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:k]
