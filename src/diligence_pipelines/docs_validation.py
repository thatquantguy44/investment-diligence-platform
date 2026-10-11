from __future__ import annotations

import re
from pathlib import Path


MARKDOWN_LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")


def _local_target(source: Path, target: str) -> Path | None:
    target = target.strip().split("#", 1)[0].split("?", 1)[0]
    if not target or "://" in target or target.startswith("mailto:"):
        return None
    return (source.parent / target).resolve()


def validate_docs(root: Path) -> int:
    """Validate required roadmap/handoff files and local Markdown links."""
    errors: list[str] = []
    required = [root / "README.md", root / "docs" / "MASTER_HANDOFF.md", root / "docs" / "MASTER_ROADMAP.md"]
    spec_root = root / "docs" / "specs"
    spec_dirs = sorted(path for path in spec_root.iterdir() if path.is_dir() and path.name.isdigit())
    if not spec_dirs:
        errors.append(f"{spec_root}: no numbered spec directories found")
    for path in required:
        if not path.is_file():
            errors.append(f"missing required document: {path.relative_to(root)}")
    for spec_dir in spec_dirs:
        roadmap = spec_dir / "ROADMAP.md"
        if not roadmap.is_file():
            errors.append(f"missing spec roadmap: {roadmap.relative_to(root)}")
        handoff = spec_dir / "HANDOFF.md"
        if not handoff.is_file():
            errors.append(f"missing spec handoff: {handoff.relative_to(root)}")
        spec_documents = sorted(path for path in spec_dir.glob("*.md") if path.name not in {"ROADMAP.md", "HANDOFF.md"})
        if len(spec_documents) != 1:
            names = ", ".join(path.name for path in spec_documents) or "none"
            errors.append(f"spec must contain exactly one spec document: {spec_dir.relative_to(root)} ({names})")

    ignored_parts = {".git", ".data", "node_modules", "dist", "build"}
    markdown_files = sorted(path for path in root.rglob("*.md") if not ignored_parts.intersection(path.parts))
    for source in markdown_files:
        for raw_target in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>")
            resolved = _local_target(source, target)
            if resolved is not None and not resolved.exists():
                errors.append(f"broken Markdown link: {source.relative_to(root)} -> {target}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"validated documentation: {len(markdown_files)} Markdown file(s), {len(spec_dirs)} spec roadmap(s)")
    return 0
