"""Collect legacy source files into a single context block for the agent."""
from pathlib import Path

SOURCE_EXTS = {".java", ".jsp", ".sql", ".xml", ".properties"}
MAX_BYTES = 400_000  # keep context sane


def collect_sources(root: str) -> str:
    parts, total = [], 0
    for p in sorted(Path(root).rglob("*")):
        if p.suffix in SOURCE_EXTS and p.is_file():
            text = p.read_text(errors="replace")
            total += len(text)
            if total > MAX_BYTES:
                parts.append(f"// TRUNCATED: corpus exceeded {MAX_BYTES} bytes")
                break
            parts.append(f"// ===== {p.relative_to(root)} =====\n{text}")
    if not parts:
        raise SystemExit(f"No legacy source files found under {root}")
    return "\n\n".join(parts)
