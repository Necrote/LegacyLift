"""Collect legacy source files into a single context block for the agent."""
from pathlib import Path

from .config import MAX_BYTES, SOURCE_EXTS, SOURCE_NAMES


def collect_sources(root: str, exclude_dirs: frozenset = frozenset()) -> str:
    # rglob on a missing path yields nothing rather than raising, so without this check a
    # wrong working directory looks identical to a directory full of unsupported files.
    # These paths are typically relative to the repo root; say so instead of blaming the tree.
    base = Path(root)
    if not base.is_dir():
        raise SystemExit(
            f"{root} is not a directory (resolved to {base.resolve()}).\n"
            f"Paths are relative to the current directory - run this from the repo root."
        )
    parts, total = [], 0
    for p in sorted(base.rglob("*")):
        # Callers re-reading a *generated* tree (verify) must skip build output and our own
        # backups; analyze/generate pass nothing and keep the original walk-everything behavior.
        if exclude_dirs and exclude_dirs.intersection(p.relative_to(base).parts[:-1]):
            continue
        # Name match as well as suffix: Dockerfile and .dockerignore have no suffix at all,
        # and the fix loop cannot repair a container setup it was never shown.
        if (p.suffix in SOURCE_EXTS or p.name in SOURCE_NAMES) and p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            total += len(text)
            if total > MAX_BYTES:
                parts.append(f"// TRUNCATED: corpus exceeded {MAX_BYTES} bytes")
                break
            parts.append(f"// ===== {p.relative_to(root)} =====\n{text}")
    if not parts:
        skipped = f" (ignoring {'/'.join(sorted(exclude_dirs))})" if exclude_dirs else ""
        raise SystemExit(
            f"No legacy source files found under {root}{skipped} - the directory exists but "
            f"holds nothing with a supported extension ({' '.join(sorted(SOURCE_EXTS))}) "
            f"or name ({' '.join(sorted(SOURCE_NAMES))})."
        )
    return "\n\n".join(parts)
