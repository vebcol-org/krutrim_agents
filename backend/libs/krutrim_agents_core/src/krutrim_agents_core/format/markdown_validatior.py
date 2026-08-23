"""
Validator for markdown_export_standard.md.

Checks a markdown document against every rule in the spec's Pre-Export
Checklist (Section 8) plus the structural rules that back each checklist item.
Returns structured issues (errors vs. warnings), not just pass/fail, so a
caller can decide whether to block export or just surface a lint warning.

Usage:
    from markdown_validator import validate_document, ValidationReport

    report = validate_document(md_text, target_format="pdf")
    if not report.is_valid:
        for issue in report.errors:
            print(issue)

Run standalone: python markdown_validator.py path/to/file.md [--format pdf|docx]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    ERROR = "error"  # will break or visibly corrupt PDF/DOCX output
    WARNING = "warning"  # will render but degrades quality/fidelity
    INFO = "info"  # stylistic / spec-recommendation, non-blocking


@dataclass
class Issue:
    severity: Severity
    rule: str  # which spec section/rule this maps to
    message: str
    line: int | None = None  # 1-indexed line number, if applicable

    def __str__(self) -> str:
        loc = f"line {self.line}" if self.line else "document"
        return f"[{self.severity.value.upper()}] ({self.rule}) {loc}: {self.message}"


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.INFO]

    @property
    def is_valid(self) -> bool:
        """No errors. Warnings/infos don't block export."""
        return len(self.errors) == 0

    def add(
        self, severity: Severity, rule: str, message: str, line: int | None = None
    ) -> None:
        self.issues.append(Issue(severity, rule, message, line))

    def summary(self) -> str:
        return (
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s), "
            f"{len(self.infos)} info(s)"
        )


# ---------------------------------------------------------------------------
# Shared regex helpers
# ---------------------------------------------------------------------------

OPEN_MARKER_RE = re.compile(
    r"<!--\s*sec:id=(?P<id>[\w.\-]+)\s+level=(?P<level>\d+)"
    r"(?:\s+parent=(?P<parent>[\w.\-]+))?"
    r'\s+title="(?P<title>[^"]*)"\s*-->'
)
CLOSE_MARKER_RE = re.compile(r"<!--\s*/sec:id=(?P<id>[\w.\-]+)\s*-->")
LAYOUT_HINT_RE = re.compile(r"<!--\s*(repeat-header|width:\s*\d+%)\s*-->")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\|?[\s:|-]+\|?$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)")
BLOCK_MATH_RE = re.compile(r"\$\$([\s\S]+?)\$\$")
RAW_NEWLINE_ESCAPE_RE = re.compile(r"\\n")
HAND_DRAWN_RULE_RE = re.compile(r"^\s*[-_]{3,}\s*$")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# ---------------------------------------------------------------------------
# Check 0: Section identifier integrity (spec Section 0)
# ---------------------------------------------------------------------------


def check_section_markers(md: str, report: ValidationReport) -> None:
    opens = list(OPEN_MARKER_RE.finditer(md))
    closes = list(CLOSE_MARKER_RE.finditer(md))

    open_ids = [m.group("id") for m in opens]
    close_ids = [m.group("id") for m in closes]

    # Duplicate IDs (0.6: never nest two blocks with the same id)
    seen = set()
    for m in opens:
        sid = m.group("id")
        if sid in seen:
            report.add(
                Severity.ERROR,
                "0.6",
                f"Duplicate section id '{sid}' — ids must be unique within a document.",
                _line_of(md, m.start()),
            )
        seen.add(sid)

    # Every opening marker must have exactly one matching closing marker
    for oid in open_ids:
        count = close_ids.count(oid)
        if count == 0:
            report.add(
                Severity.ERROR,
                "0.1",
                f"Section id '{oid}' has an opening marker but no matching closing marker.",
            )
        elif count > 1:
            report.add(
                Severity.ERROR,
                "0.1",
                f"Section id '{oid}' has {count} closing markers — expected exactly 1.",
            )

    # Every closing marker must have a matching opening marker
    for cid in close_ids:
        if cid not in open_ids:
            report.add(
                Severity.ERROR,
                "0.1",
                f"Closing marker for '{cid}' has no matching opening marker.",
            )

    # parent references must point to an id that actually exists
    for m in opens:
        parent = m.group("parent")
        if parent and parent not in open_ids:
            report.add(
                Severity.ERROR,
                "0.1",
                f"Section '{m.group('id')}' declares parent='{parent}', "
                f"but no section with that id exists.",
                _line_of(md, m.start()),
            )

    # Marker must sit directly above its heading, no blank line between (0.1)
    for m in opens:
        rest = md[m.end() :]
        # allow exactly one newline then the heading; anything else is a violation
        next_content = rest.lstrip("\n")
        skipped = len(rest) - len(next_content)
        if skipped > 1:
            report.add(
                Severity.WARNING,
                "0.1",
                f"Blank line(s) found between opening marker '{m.group('id')}' "
                f"and its heading — marker should sit directly above the heading.",
                _line_of(md, m.start()),
            )
        if not next_content.lstrip().startswith("#"):
            report.add(
                Severity.WARNING,
                "0.1",
                f"Opening marker '{m.group('id')}' is not immediately followed "
                f"by a heading.",
                _line_of(md, m.start()),
            )

    # level attribute should match the actual heading depth that follows
    for m in opens:
        rest = md[m.end() :].lstrip("\n")
        heading_match = re.match(r"(#{1,6})\s", rest)
        if heading_match:
            actual_level = len(heading_match.group(1))
            declared_level = int(m.group("level"))
            if actual_level != declared_level:
                report.add(
                    Severity.ERROR,
                    "0.1",
                    f"Section '{m.group('id')}' declares level={declared_level} "
                    f"but the heading uses {actual_level} '#' characters.",
                    _line_of(md, m.start()),
                )


# ---------------------------------------------------------------------------
# Check 1: General structural rules (spec Section 1)
# ---------------------------------------------------------------------------


def check_general_structure(md: str, report: ValidationReport) -> None:
    # Raw \n used as literal escape instead of a real line break (rare but
    # happens when content is generated as a Python string and not rendered)
    for m in RAW_NEWLINE_ESCAPE_RE.finditer(md):
        report.add(
            Severity.ERROR,
            "1",
            r"Literal '\n' escape sequence found instead of a real newline — "
            "use actual line breaks or <br> inside table cells only.",
            _line_of(md, m.start()),
        )

    # Hand-drawn horizontal rules used as content (heuristic: a line of only
    # dashes/underscores that is NOT a table separator and NOT a real --- HR
    # placed between blank lines)
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if HAND_DRAWN_RULE_RE.match(line) and line.strip() not in ("---", "___", "***"):
            report.add(
                Severity.WARNING,
                "1",
                "Line resembles a hand-drawn separator — use a real markdown "
                "'---' horizontal rule or a section break, not repeated dashes.",
                i + 1,
            )

    # Heading level skips (no # straight to ###)
    prev_level = 0
    for m in HEADING_RE.finditer(md):
        level = len(m.group(1))
        if prev_level and level > prev_level + 1:
            report.add(
                Severity.ERROR,
                "1",
                f"Heading level skips from h{prev_level} to h{level} "
                f"('{m.group(2).strip()}') — heading levels must not skip.",
                _line_of(md, m.start()),
            )
        prev_level = level

    # Blank line between block elements — check heading immediately followed
    # by non-blank content (a common source of broken conversion)
    for m in HEADING_RE.finditer(md):
        end = m.end()
        remainder = md[end : end + 2]
        if remainder and not remainder.startswith("\n"):
            report.add(
                Severity.WARNING,
                "1",
                f"No newline after heading '{m.group(2).strip()}'.",
                _line_of(md, m.start()),
            )


# ---------------------------------------------------------------------------
# Check 2: Tables (spec Section 2)
# ---------------------------------------------------------------------------


def check_tables(md: str, report: ValidationReport) -> None:
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if TABLE_ROW_RE.match(line):
            # find the full table block
            start = i
            table_lines = [line]
            i += 1
            while i < len(lines) and TABLE_ROW_RE.match(lines[i]):
                table_lines.append(lines[i])
                i += 1

            if len(table_lines) < 2:
                report.add(
                    Severity.WARNING,
                    "2",
                    "Table-like line found with no separator row — may not "
                    "be a real table.",
                    start + 1,
                )
                continue

            header_cols = [c.strip() for c in table_lines[0].strip("|").split("|")]
            sep_line = table_lines[1]
            if not TABLE_SEP_RE.match(sep_line.strip()):
                report.add(
                    Severity.ERROR,
                    "2",
                    "Table header is not followed by a valid separator row "
                    "(e.g. |---|---|).",
                    start + 2,
                )

            expected_cols = len(header_cols)
            for j, row in enumerate(table_lines[2:], start=3):
                cols = [c.strip() for c in row.strip("|").split("|")]
                if len(cols) != expected_cols:
                    report.add(
                        Severity.ERROR,
                        "2",
                        f"Table row has {len(cols)} columns, expected "
                        f"{expected_cols} (ragged row — must match header).",
                        start + j,
                    )

            if expected_cols > 6:
                report.add(
                    Severity.WARNING,
                    "2",
                    f"Table has {expected_cols} columns (>6) — consider "
                    f"splitting into stacked tables per spec Section 2.",
                    start + 1,
                )

            if len(table_lines) - 2 >= 15:
                preceding = "\n".join(lines[max(0, start - 2) : start])
                if "repeat-header" not in preceding:
                    report.add(
                        Severity.INFO,
                        "2",
                        f"Table has {len(table_lines) - 2} rows (15+) and may "
                        f"cross a page break — consider adding "
                        f"'<!-- repeat-header -->' above it.",
                        start + 1,
                    )
        else:
            i += 1


# ---------------------------------------------------------------------------
# Check 3: Math (spec Section 3)
# ---------------------------------------------------------------------------


def check_math(md: str, report: ValidationReport, target_format: str) -> None:
    inline_matches = list(INLINE_MATH_RE.finditer(md))
    block_matches = list(BLOCK_MATH_RE.finditer(md))

    if target_format == "docx" and (inline_matches or block_matches):
        report.add(
            Severity.WARNING,
            "3",
            f"Document contains {len(inline_matches)} inline and "
            f"{len(block_matches)} block LaTeX math expression(s), but target "
            f"format is DOCX — equation fidelity is materially lower in DOCX. "
            f"Consider pre-rendering complex equations as images, or "
            f"recommending PDF instead.",
        )

    # Check for likely-unterminated inline math. This deliberately excludes
    # currency usage ($4.2B, $1,234.00) per spec Section 2, which is NOT math
    # and must not be flagged. Heuristic: a '$' is treated as a currency
    # marker (not a math delimiter) when immediately followed by digits that
    # resolve to a plain number/amount pattern rather than an equation body.
    CURRENCY_RE = re.compile(r"\$\d[\d,]*\.?\d*[BMKbmk%]?\b")
    # Remove currency-looking spans first so they never interfere with
    # delimiter-balance checks below.
    md_no_currency = CURRENCY_RE.sub("", md)
    # Also remove valid, properly-closed $$...$$  and $...$ pairs, leaving
    # only genuinely stray single '$' characters behind.
    md_no_math = BLOCK_MATH_RE.sub("", md_no_currency)
    md_no_math = INLINE_MATH_RE.sub("", md_no_math)

    stray_dollars = re.findall(r"\$", md_no_math)
    if stray_dollars:
        # find the first stray one for a useful line number
        m = re.search(r"\$", md_no_math)
        approx_line = _line_of(md, md.find(m.group(0))) if m else None
        report.add(
            Severity.ERROR,
            "3",
            f"Found {len(stray_dollars)} unmatched '$' character(s) that are "
            f"neither valid math delimiters nor currency amounts — inline "
            f"math may be unterminated (e.g. '$E = mc^2' with no closing '$').",
            approx_line,
        )


# ---------------------------------------------------------------------------
# Check 4: Images & diagrams (spec Section 4)
# ---------------------------------------------------------------------------


def check_images(md: str, report: ValidationReport) -> None:
    for m in IMAGE_RE.finditer(md):
        alt_text, path = m.group(1), m.group(2)
        if not alt_text.strip():
            report.add(
                Severity.WARNING,
                "4",
                f"Image '{path}' has empty alt text — always write descriptive "
                f"alt text per spec Section 4.",
                _line_of(md, m.start()),
            )
        if path.strip().lower().endswith((".mmd", ".mermaid")):
            report.add(
                Severity.ERROR,
                "4",
                f"Image reference '{path}' points to raw Mermaid source, not "
                f"a pre-rendered image file — diagrams must be pre-rendered "
                f"to PNG/SVG before embedding.",
                _line_of(md, m.start()),
            )

    # Raw Mermaid/SVG code fences dropped directly into the document
    if re.search(r"```mermaid", md):
        report.add(
            Severity.ERROR,
            "4",
            "Raw ```mermaid code block found — diagrams must be pre-rendered "
            "to a static image and embedded via markdown image syntax, not "
            "left as live diagram source.",
        )


# ---------------------------------------------------------------------------
# Check 5: TOC / front matter (spec Section 6)
# ---------------------------------------------------------------------------


def check_toc(md: str, report: ValidationReport) -> None:
    # Heuristic: a "Table of Contents" heading followed closely by what looks
    # like a hand-typed list of "Section Title .... 12" page-number entries
    toc_match = re.search(r"^#+\s*Table of Contents\s*$", md, re.MULTILINE)
    if toc_match:
        window = md[toc_match.end() : toc_match.end() + 800]
        if re.search(r"\.{3,}\s*\d+\s*$", window, re.MULTILINE):
            report.add(
                Severity.WARNING,
                "6",
                "Table of Contents section appears to contain hand-typed "
                "page numbers (dot leaders + digits) — TOC should be "
                "generated from real heading structure, not typed manually.",
            )


# ---------------------------------------------------------------------------
# Check 6: Pre-export marker cleanliness (spec Section 0.5 / 8)
# ---------------------------------------------------------------------------


def check_export_readiness(
    md: str, report: ValidationReport, target_format: str | None
) -> None:
    if target_format in ("pdf", "docx"):
        if OPEN_MARKER_RE.search(md) or CLOSE_MARKER_RE.search(md):
            report.add(
                Severity.ERROR,
                "0.5",
                f"Document is being validated for {target_format.upper()} "
                f"export but still contains sec:id markers — strip them "
                f"with strip_section_markers() before export.",
            )
        if LAYOUT_HINT_RE.search(md):
            report.add(
                Severity.INFO,
                "0.6",
                "Layout hint comments (repeat-header / width) present — "
                "confirm the export pipeline consumes and strips these "
                "before final output.",
            )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def validate_document(
    md: str,
    target_format: str | None = None,  # "pdf" | "docx" | None (pre-export lint)
) -> ValidationReport:
    """
    Run every check against a markdown document.

    target_format:
        None    -> validate general spec compliance only (authoring-time lint)
        "pdf"   -> also check math/table guidance for PDF and require markers stripped
        "docx"  -> also flag math fidelity concerns for DOCX and require markers stripped
    """
    report = ValidationReport()

    check_section_markers(md, report)
    check_general_structure(md, report)
    check_tables(md, report)
    check_math(md, report, target_format or "")
    check_images(md, report)
    check_toc(md, report)
    check_export_readiness(md, report, target_format)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate markdown against the export standard."
    )
    parser.add_argument("path", help="Path to the markdown file to validate.")
    parser.add_argument(
        "--format",
        choices=["pdf", "docx"],
        default=None,
        help="Validate as pre-export for this target format (also requires markers stripped).",
    )
    args = parser.parse_args()

    with open(args.path, "r", encoding="utf-8") as f:
        md = f.read()

    report = validate_document(md, target_format=args.format)

    for issue in report.issues:
        print(issue)

    print()
    print(report.summary())
    sys.exit(0 if report.is_valid else 1)


if __name__ == "__main__":
    main()
