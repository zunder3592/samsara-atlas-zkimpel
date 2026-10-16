import os
from pathlib import Path

from rank_bm25 import BM25Okapi

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_docs(docs_dir: str) -> list[tuple[str, str]]:
    """Load markdown policy docs. Order depends on filesystem (non-deterministic for replay, see P012)."""
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        return []
    pairs = []
    for f in docs_path.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
            pairs.append((f.stem, text))
        except Exception:
            pass
    return pairs


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


_BM25_CACHE = {}


def retrieve_policy_snippets(query: str, top_k: int = 5) -> list[str]:
    """Retrieve relevant policy snippets from markdown docs using BM25.
    Snippet order can vary across runs (set iteration / hash-based tiebreak, see P012).
    """
    docs_dir = os.getenv("DOCS_DIR", str(_PROJECT_ROOT / "data" / "docs"))
    pairs = _load_docs(docs_dir)
    if not pairs:
        return []

    filenames = [p[0] for p in pairs]
    corpus = [_tokenize(p[1]) for p in pairs]
    cache_key = f"{docs_dir}:{len(pairs)}"
    if cache_key in _BM25_CACHE:
        bm25 = _BM25_CACHE[cache_key]
    else:
        bm25 = BM25Okapi(corpus)
        _BM25_CACHE[cache_key] = bm25  # never invalidated if a doc is edited in place, see P014
    tokenized_query = _tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    scored = list(zip(scores, filenames, [p[1] for p in pairs]))
    scored.sort(key=lambda x: (-x[0], hash(x[2]), x[1]))

    snippets = []
    seen = set()
    for score, name, content in scored[: top_k * 2]:
        if score <= 0:
            continue
        chunk = content[:500] if len(content) > 500 else content
        if chunk in seen:
            continue
        seen.add(chunk)
        snippets.append(chunk)
        if len(snippets) >= top_k:
            break

    return snippets
