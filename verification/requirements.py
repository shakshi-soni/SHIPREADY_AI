"""
verification/requirements.py — Documentation & code-quality checks

Every function here reads the actual filesystem and returns
(bool, evidence_str). Nothing here trusts an LLM's claim that a file
"was generated" — it re-opens the file and checks its real contents.
"""

from __future__ import annotations

import re
from pathlib import Path

REQUIRED_README_SECTIONS = ("Setup", "Usage", "Architecture")

# Markers that indicate generated content is a placeholder, not real
# content. Checked case-insensitively. This is the deterministic backstop
# for the planning prompt's "never write TODO" instruction — a prompt is
# a request, not a guarantee, so real enforcement lives here, not there.
PLACEHOLDER_MARKERS = (
    "todo",
    "tbd",
    "to be determined",
    "coming soon",
    "fill this in",
    "fill in",
    "lorem ipsum",
    "placeholder",
    "xxx",
    "not yet implemented",
)

MIN_SECTION_CONTENT_CHARS = 20  # a section heading alone isn't enough


def contains_placeholder_text(content: str) -> tuple[bool, str]:
    """Returns (found, marker) — True if any known placeholder marker
    appears in the content, case-insensitively."""
    lower = content.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lower:
            return True, marker
    return False, ""


def check_readme_exists(target_dir: Path) -> tuple[bool, str]:
    readme = Path(target_dir) / "README.md"
    if readme.exists() and readme.stat().st_size > 0:
        return True, f"README.md present ({readme.stat().st_size} bytes)"
    return False, "README.md missing or empty"


def _extract_section_content(content: str, section_name: str) -> str:
    """Finds a markdown heading matching section_name and returns the text
    until the next heading of the same or higher level (or end of doc)."""
    lines = content.split("\n")
    heading_pattern = re.compile(r"^(#{1,6})\s*" + re.escape(section_name), re.IGNORECASE)
    start_idx = None
    heading_level = None

    for i, line in enumerate(lines):
        match = heading_pattern.match(line.strip())
        if match:
            start_idx = i
            heading_level = len(match.group(1))
            break

    if start_idx is None:
        return ""

    section_lines = []
    for line in lines[start_idx + 1:]:
        stripped = line.strip()
        next_heading = re.match(r"^(#{1,6})\s", stripped)
        if next_heading and len(next_heading.group(1)) <= heading_level:
            break
        section_lines.append(line)

    return "\n".join(section_lines).strip()


def check_readme_min_sections(
    target_dir: Path, required_sections: tuple[str, ...] = REQUIRED_README_SECTIONS
) -> tuple[bool, str]:
    readme = Path(target_dir) / "README.md"
    if not readme.exists():
        return False, "README.md does not exist"

    content = readme.read_text(encoding="utf-8", errors="replace")
    problems = []

    for section in required_sections:
        section_content = _extract_section_content(content, section)

        if not section_content:
            problems.append(f"{section}: heading missing entirely")
            continue

        has_placeholder, marker = contains_placeholder_text(section_content)
        if has_placeholder:
            problems.append(f"{section}: contains placeholder text ({marker!r})")
            continue

        if len(section_content) < MIN_SECTION_CONTENT_CHARS:
            problems.append(
                f"{section}: only {len(section_content)} chars of content "
                f"(minimum {MIN_SECTION_CONTENT_CHARS}) — heading with no real content"
            )

    if not problems:
        return True, f"All required sections present with real content: {list(required_sections)}"
    return False, "; ".join(problems)


def check_architecture_doc_exists(target_dir: Path) -> tuple[bool, str]:
    """Passes if there's a standalone ARCHITECTURE.md, OR the README itself
    has a real Architecture section with actual, non-placeholder content
    under it (not just the heading)."""
    target_dir = Path(target_dir)
    arch_doc = target_dir / "ARCHITECTURE.md"
    if arch_doc.exists() and arch_doc.stat().st_size > 0:
        content = arch_doc.read_text(encoding="utf-8", errors="replace")
        has_placeholder, marker = contains_placeholder_text(content)
        if has_placeholder:
            return False, f"ARCHITECTURE.md exists but contains placeholder text ({marker!r})"
        if len(content.strip()) < MIN_SECTION_CONTENT_CHARS:
            return False, f"ARCHITECTURE.md exists but has almost no content ({len(content)} chars)"
        return True, f"ARCHITECTURE.md present with real content ({arch_doc.stat().st_size} bytes)"

    readme = target_dir / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8", errors="replace")
        section_content = _extract_section_content(content, "Architecture")
        if section_content:
            has_placeholder, marker = contains_placeholder_text(section_content)
            if has_placeholder:
                return False, f"README's Architecture section contains placeholder text ({marker!r})"
            if len(section_content) >= MIN_SECTION_CONTENT_CHARS:
                return True, "README contains a substantive Architecture section"

    return False, "No ARCHITECTURE.md and no substantive Architecture section in README"


def check_source_files_present(target_dir: Path, entrypoint: str = "app.py") -> tuple[bool, str]:
    entry_path = Path(target_dir) / entrypoint
    if entry_path.exists() and entry_path.stat().st_size > 0:
        return True, f"Entrypoint {entrypoint!r} present"
    return False, f"Entrypoint {entrypoint!r} missing or empty"