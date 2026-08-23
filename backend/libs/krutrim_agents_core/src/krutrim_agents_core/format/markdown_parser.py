"""
Reference implementation of markdown_export_standard.md, Section 0
(Section Identifiers) — extended to cover markdown parsing generally, not
just the id-marker mechanics.

Implements:
  Marker-based (documents authored with sec:id comments):
    1. parse_document_tree(md)      -> nested SectionNode tree (id/level/parent/title)
    2. flatten_tree(nodes)          -> flat list of SectionNode, document order
    3. extract_section(md, id)      -> full raw content of one section (incl. nested)
    4. replace_section(md, id, new) -> document with that section swapped in
    5. strip_section_markers(md)    -> clean markdown, safe for PDF/DOCX export

  Content-aware parsing (works with or without sec:id markers):
    6. parse_headings(md)           -> flat list of HeadingNode from '#' syntax alone
    7. build_tree_from_headings(md) -> nested tree inferred purely from heading depth
    8. parse_block_elements(md)     -> tables / images / code fences / math found
                                        anywhere in the document, each with its
                                        enclosing section id (if any) attached
    9. get_section_or_document(md, id=None) -> unified accessor: returns one
                                        section's content by id, or the whole
                                        document if id is None / markers absent

No third-party dependencies — stdlib `re` only, matching the spec's intent that
this pattern be trivially portable to any backend language/runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

OPEN_MARKER_RE = re.compile(
    r"<!--\s*sec:id=(?P<id>[\w.\-]+)\s+level=(?P<level>\d+)"
    r"(?:\s+parent=(?P<parent>[\w.\-]+))?"
    r'\s+title="(?P<title>[^"]*)"\s*-->'
)
CLOSE_MARKER_RE = re.compile(r"<!--\s*/sec:id=(?P<id>[\w.\-]+)\s*-->")
ANY_SEC_MARKER_RE = re.compile(
    r"^[ \t]*<!--\s*/?sec:id=[\w.\-]+[^>]*-->[ \t]*\n?", re.MULTILINE
)

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
TABLE_BLOCK_RE = re.compile(
    r"(?P<header>^\|.*\|[ \t]*\n)"
    r"(?P<sep>^\|?[\s:|-]+\|?[ \t]*\n)"
    r"(?P<body>(?:^\|.*\|[ \t]*\n?)*)",
    re.MULTILINE,
)
IMAGE_RE = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)(?:\s+"[^"]*")?\)')
CODE_FENCE_RE = re.compile(
    r"^```(?P<lang>\w*)\n(?P<body>[\s\S]*?)^```[ \t]*$", re.MULTILINE
)
BLOCK_MATH_RE = re.compile(r"\$\$(?P<body>[\s\S]+?)\$\$")
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(?P<body>[^$\n]+?)(?<!\$)\$(?!\$)")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _compile_section_pattern(section_id: str, *, capture_body: bool) -> re.Pattern:
    """
    Build the single canonical open/close matched-pair pattern for a given
    section id. Both extract_section and replace_section previously built
    near-duplicate patterns inline — centralized here so there is exactly one
    definition of what "a section span" means.
    """
    escaped_id = re.escape(section_id)
    open_part = (
        r"<!--\s*sec:id=" + escaped_id + r"\s+level=\d+"
        r'(?:\s+parent=[\w.\-]+)?\s+title="[^"]*"\s*-->'
    )
    close_part = r"<!--\s*/sec:id=" + escaped_id + r"\s*-->"
    body_part = r"([\s\S]*?)" if capture_body else r"[\s\S]*?"
    return re.compile(open_part + body_part + close_part)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SectionNode:
    """A section defined by an explicit sec:id marker pair."""

    id: str
    level: int
    parent: str | None
    title: str
    children: list[SectionNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "level": self.level,
            "parent": self.parent,
            "title": self.title,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class HeadingNode:
    """A section inferred purely from '#' heading syntax, no marker required."""

    title: str
    level: int
    start: int  # character offset where the heading line begins
    content_start: (
        int  # character offset where body content begins (after heading line)
    )
    content_end: int | None = None  # filled in once the next heading/EOF is known
    slug: str = ""
    children: list[HeadingNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level,
            "slug": self.slug,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class BlockElement:
    """A structural element (table/image/code/math) found in the document,
    tagged with the id of its enclosing sec:id section, if any."""

    kind: str  # "table" | "image" | "code" | "block_math" | "inline_math"
    content: str  # raw matched text
    line: int
    section_id: str | None = None
    meta: dict = field(default_factory=dict)


class MarkdownParseError(ValueError):
    """Raised for structurally invalid marker usage that callers must not
    silently ignore (e.g. a section referencing a parent id that doesn't
    exist). Distinct from ValueError used for simple 'not found' lookups so
    callers can catch structural corruption specifically."""


# ===========================================================================
# PART A — marker-based section parsing (original functionality, kept
# backward compatible, plus flatten_tree added)
# ===========================================================================


def parse_document_tree(md: str, *, strict: bool = False) -> list[SectionNode]:
    """
    Scan every opening marker in document order and reconstruct the section
    tree (spec Section 0.3).

    strict=False (default, backward-compatible): a section whose declared
    parent id doesn't exist in the document is treated as a root node —
    matches original behavior.

    strict=True: the same situation raises MarkdownParseError instead of
    silently promoting the node to root. Use this whenever the caller wants
    to guarantee the document is well-formed rather than degrade gracefully
    (e.g. before running replace_section on it).
    """
    nodes: dict[str, SectionNode] = {}
    roots: list[SectionNode] = []
    declared_parents: dict[str, str] = {}

    for m in OPEN_MARKER_RE.finditer(md):
        node = SectionNode(
            id=m.group("id"),
            level=int(m.group("level")),
            parent=m.group("parent"),
            title=m.group("title"),
        )
        if node.id in nodes and strict:
            raise MarkdownParseError(f"Duplicate section id '{node.id}'.")
        nodes[node.id] = node
        if node.parent:
            declared_parents[node.id] = node.parent

    for child_id, parent_id in declared_parents.items():
        if parent_id not in nodes and strict:
            raise MarkdownParseError(
                f"Section '{child_id}' declares parent='{parent_id}', "
                f"which does not exist in the document."
            )

    for node in nodes.values():
        if node.parent and node.parent in nodes:
            nodes[node.parent].children.append(node)
        else:
            roots.append(node)

    return roots


def flatten_tree(nodes: list[SectionNode]) -> list[SectionNode]:
    """
    Flatten a SectionNode tree into document-order list. Useful when a caller
    wants "every section" without walking the nested structure themselves —
    e.g. to build a flat dropdown, or to iterate and validate every id.
    """
    flat: list[SectionNode] = []
    for node in nodes:
        flat.append(node)
        flat.extend(flatten_tree(node.children))
    return flat


def extract_section(
    md: str, section_id: str, *, include_markers: bool = False
) -> str | None:
    """
    Extract the full span between <!-- sec:id=X ... --> and <!-- /sec:id=X -->,
    matched pair, per spec Section 0.3. Returns None if the id isn't found.
    """
    pattern = _compile_section_pattern(section_id, capture_body=True)
    match = pattern.search(md)
    if not match:
        return None
    if include_markers:
        return match.group(0)
    return match.group(1).strip("\n")


def replace_section(md: str, section_id: str, new_block: str) -> str:
    """
    Swap out one section's full marked span for newly generated content.
    Raises ValueError if the section id isn't found.
    """
    pattern = _compile_section_pattern(section_id, capture_body=False)
    if not pattern.search(md):
        raise ValueError(f"Section id '{section_id}' not found in document.")
    return pattern.sub(lambda _: new_block, md, count=1)


def strip_section_markers(md: str) -> str:
    """
    Remove every sec:id opening/closing marker line. Must run before handing
    markdown to the PDF/DOCX generation pipeline (spec Section 0.5).
    """
    return ANY_SEC_MARKER_RE.sub("", md)


def print_tree(nodes: list[SectionNode], indent: int = 0) -> None:
    for node in nodes:
        print("  " * indent + f"[{node.id}] (h{node.level}) {node.title}")
        print_tree(node.children, indent + 1)


# ===========================================================================
# PART B — content-aware parsing, works whether or not sec:id markers exist
# ===========================================================================


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    return re.sub(r"[\s]+", "-", slug)


def parse_headings(md: str) -> list[HeadingNode]:
    """
    Flat list of every heading found via plain '#' syntax, independent of
    any sec:id markers. This is the fallback path for documents that were
    never authored with the marker system — e.g. a user-pasted markdown file,
    or third-party source content that needs to be sectioned after the fact.

    content_end for each node extends to the next heading at the SAME OR
    SHALLOWER depth (not simply "the next heading of any depth") — so a h2
    section's content_end correctly spans past any nested h3/h4 children,
    matching the "section including its subsections" semantics used by
    get_heading_content and build_tree_from_headings.
    """
    matches = list(HEADING_RE.finditer(md))
    nodes: list[HeadingNode] = []
    for m in matches:
        title = m.group(2).strip()
        node = HeadingNode(
            title=title,
            level=len(m.group(1)),
            start=m.start(),
            content_start=m.end() + 1 if m.end() < len(md) else m.end(),
            slug=_slugify(title),
        )
        nodes.append(node)

    for i, node in enumerate(nodes):
        end = len(md)
        for later in nodes[i + 1 :]:
            if later.level <= node.level:
                end = later.start
                break
        node.content_end = end

    return nodes


def build_tree_from_headings(md: str) -> list[HeadingNode]:
    """
    Infer a nested section tree purely from heading depth (h1 > h2 > h3...),
    with no dependency on sec:id markers at all. Use this for markdown that
    was never authored with the marker system, or as a cross-check that a
    marker-declared tree (parse_document_tree) actually matches the real
    heading structure of the document.
    """
    flat = parse_headings(md)
    roots: list[HeadingNode] = []
    stack: list[HeadingNode] = []

    for node in flat:
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    return roots


def get_heading_content(
    md: str, node: HeadingNode, *, include_heading_line: bool = False
) -> str:
    """
    Extract the raw text belonging to a HeadingNode (everything up to the
    next heading, at any depth — node.content_end already reflects this).
    """
    start = node.start if include_heading_line else node.content_start
    return md[start : node.content_end].strip("\n")


def parse_block_elements(
    md: str, section_tree: list[SectionNode] | None = None
) -> list[BlockElement]:
    """
    Find every table, image, fenced code block, and math expression in the
    document, in document order, each tagged with `line` and — if a marker-
    based section_tree is supplied — the id of the sec:id section it falls
    inside (None if the document has no markers or the element sits outside
    any marked section).

    This is the piece the original module was missing entirely: it could
    locate a *section* by id, but had no structured view of what's actually
    inside a section (tables/images/etc.) short of returning it as one raw
    string blob.
    """
    elements: list[BlockElement] = []

    spans: list[tuple[int, int, str]] = []
    if section_tree is not None:
        flat = flatten_tree(section_tree)
        for node in flat:
            m = _compile_section_pattern(node.id, capture_body=True).search(md)
            if m:
                spans.append((m.start(1), m.end(1), node.id))

    def _enclosing_section(pos: int) -> str | None:
        best: tuple[int, int, str] | None = None
        for start, end, sid in spans:
            if start <= pos <= end:
                if best is None or (end - start) < (best[1] - best[0]):
                    best = (start, end, sid)
        return best[2] if best else None

    for m in TABLE_BLOCK_RE.finditer(md):
        rows = m.group("body").count("\n")
        elements.append(
            BlockElement(
                kind="table",
                content=m.group(0),
                line=_line_of(md, m.start()),
                section_id=_enclosing_section(m.start()),
                meta={"row_count": rows},
            )
        )

    for m in IMAGE_RE.finditer(md):
        elements.append(
            BlockElement(
                kind="image",
                content=m.group(0),
                line=_line_of(md, m.start()),
                section_id=_enclosing_section(m.start()),
                meta={"alt": m.group("alt"), "path": m.group("path")},
            )
        )

    for m in CODE_FENCE_RE.finditer(md):
        elements.append(
            BlockElement(
                kind="code",
                content=m.group(0),
                line=_line_of(md, m.start()),
                section_id=_enclosing_section(m.start()),
                meta={"lang": m.group("lang")},
            )
        )

    for m in BLOCK_MATH_RE.finditer(md):
        elements.append(
            BlockElement(
                kind="block_math",
                content=m.group(0),
                line=_line_of(md, m.start()),
                section_id=_enclosing_section(m.start()),
            )
        )

    block_spans = [(m.start(), m.end()) for m in BLOCK_MATH_RE.finditer(md)]
    for m in INLINE_MATH_RE.finditer(md):
        if any(bs <= m.start() < be for bs, be in block_spans):
            continue
        elements.append(
            BlockElement(
                kind="inline_math",
                content=m.group(0),
                line=_line_of(md, m.start()),
                section_id=_enclosing_section(m.start()),
            )
        )

    elements.sort(key=lambda e: e.line)
    return elements


def get_section_or_document(md: str, section_id: str | None = None) -> str:
    """
    Unified accessor covering both cases in one call:
      - section_id given and found  -> that section's content
      - section_id given, not found -> raises ValueError
      - section_id is None          -> the whole document, with any sec:id
                                        markers stripped (safe default for a
                                        caller that doesn't know/care whether
                                        markers exist)

    This exists because callers integrating against arbitrary markdown (some
    marked, some not) previously had to branch on "does this doc even have
    markers" themselves before calling extract_section.
    """
    if section_id is None:
        return strip_section_markers(md).strip("\n")

    result = extract_section(md, section_id)
    if result is None:
        raise ValueError(
            f"Section id '{section_id}' not found. Document may not use "
            f"sec:id markers — use build_tree_from_headings() for "
            f"heading-based sectioning instead."
        )
    return result
