from pathlib import Path


def ensure_cache_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


def paper_root(cache_root: Path, cache_key: str) -> Path:
    return cache_root / "arxiv" / cache_key
