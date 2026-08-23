from krutrim_agents_core.format.markdown_parser import (
    MarkdownParseError,
    build_tree_from_headings,
    flatten_tree,
    get_heading_content,
    get_section_or_document,
    parse_block_elements,
    parse_document_tree,
    parse_headings,
    print_tree,
)

# A plain markdown document with NO sec:id markers at all — the real-world
# case of user-pasted or third-party content that was never authored against
# the marker spec.
UNMARKED_DOC = """\
# Quarterly Report

## Revenue

Revenue grew to **$4.2M** this quarter.

| Region | Revenue | Growth |
|---|---|---|
| APAC | $1.8M | 22% |
| NA | $2.4M | 9% |

### APAC Breakdown

APAC alone contributed most of the growth.

![Revenue chart](charts/revenue.png)

## Risks

The main risk formula: $Risk = P \\times I$

```python
def compute_risk(p, i):
    return p * i
```

## Appendix

$$
CAGR = \\left(\\frac{End}{Start}\\right)^{1/n} - 1
$$
"""

# A marked document with a genuine structural error: child references a
# parent id that doesn't exist. Used to test strict mode.
MALFORMED_MARKED_DOC = """\
<!-- sec:id=S1 level=2 title="Top" -->
## 1. Top
Content.
<!-- /sec:id=S1 -->

<!-- sec:id=S1.orphan level=3 parent=S1.nonexistent title="Orphan" -->
### 1.1 Orphan
Orphaned content.
<!-- /sec:id=S1.orphan -->
"""


def test_unmarked_heading_parse():
    print("=" * 70)
    print("TEST 1: parse_headings on a document with NO sec:id markers")
    print("=" * 70)
    headings = parse_headings(UNMARKED_DOC)
    for h in headings:
        print(f"  h{h.level}  '{h.title}'  (slug={h.slug})")
    assert len(headings) == 5, f"expected 5 headings, got {len(headings)}"
    assert headings[0].title == "Quarterly Report"
    assert headings[2].level == 3  # APAC Breakdown
    print("[OK] Headings parsed correctly from a document with zero markers.\n")


def test_heading_tree_and_content():
    print("=" * 70)
    print("TEST 2: build_tree_from_headings + get_heading_content")
    print("=" * 70)
    tree = build_tree_from_headings(UNMARKED_DOC)
    for node in tree:
        print(f"[{node.slug}] (h{node.level}) {node.title}")
        for child in node.children:
            print(f"  [{child.slug}] (h{child.level}) {child.title}")

    # Revenue (h2) should have APAC Breakdown (h3) nested under it
    revenue_node = tree[0].children[0]
    assert revenue_node.title == "Revenue"
    assert revenue_node.children[0].title == "APAC Breakdown"

    content = get_heading_content(UNMARKED_DOC, revenue_node)
    print("\nContent of 'Revenue' section (includes nested APAC Breakdown):")
    print(content)
    assert "$4.2M" in content
    assert "APAC alone contributed" in content  # nested subsection included
    print("[OK] Tree structure and content extraction correct.\n")


def test_block_elements_unmarked():
    print("=" * 70)
    print("TEST 3: parse_block_elements on the unmarked document")
    print("=" * 70)
    elements = parse_block_elements(UNMARKED_DOC)
    kinds = [e.kind for e in elements]
    print("Found element kinds in order:", kinds)

    assert "table" in kinds
    assert "image" in kinds
    assert "code" in kinds
    assert "block_math" in kinds
    assert "inline_math" in kinds

    table = next(e for e in elements if e.kind == "table")
    print(f"\nTable found at line {table.line}, {table.meta['row_count']} body rows")
    assert table.meta["row_count"] == 2

    image = next(e for e in elements if e.kind == "image")
    print(f"Image alt='{image.meta['alt']}' path='{image.meta['path']}'")
    assert image.meta["alt"] == "Revenue chart"

    code = next(e for e in elements if e.kind == "code")
    print(f"Code block lang='{code.meta['lang']}'")
    assert code.meta["lang"] == "python"

    # section_id should be None everywhere since this doc has no markers
    assert all(e.section_id is None for e in elements)
    print("[OK] All elements found; section_id correctly None (no markers present).\n")


def test_block_elements_with_section_attribution():
    print("=" * 70)
    print("TEST 4: parse_block_elements WITH section_tree (id attribution)")
    print("=" * 70)
    marked_doc = """\
<!-- sec:id=S1 level=2 title="Findings" -->
## 1. Findings

| A | B |
|---|---|
| 1 | 2 |

<!-- sec:id=S1.sub level=3 parent=S1 title="Sub Findings" -->
### 1.1 Sub Findings

![chart](img.png)

<!-- /sec:id=S1.sub -->
<!-- /sec:id=S1 -->
"""
    tree = parse_document_tree(marked_doc)
    elements = parse_block_elements(marked_doc, section_tree=tree)
    for e in elements:
        print(f"  {e.kind:12s} section_id={e.section_id}")

    table = next(e for e in elements if e.kind == "table")
    image = next(e for e in elements if e.kind == "image")
    assert table.section_id == "S1", f"expected S1, got {table.section_id}"
    assert image.section_id == "S1.sub", f"expected S1.sub, got {image.section_id}"
    print("[OK] Elements correctly attributed to their innermost enclosing section.\n")


def test_strict_mode_catches_orphan_parent():
    print("=" * 70)
    print("TEST 5: strict=True catches orphaned parent reference")
    print("=" * 70)
    # non-strict: silently promotes to root (backward-compatible behavior)
    tree = parse_document_tree(MALFORMED_MARKED_DOC, strict=False)
    print("Non-strict mode result:")
    print_tree(tree)
    assert len(tree) == 2  # both S1 and S1.orphan end up as roots

    # strict: raises
    try:
        parse_document_tree(MALFORMED_MARKED_DOC, strict=True)
        raise AssertionError("Expected MarkdownParseError to be raised")
    except MarkdownParseError as e:
        print(f"\nStrict mode raised as expected: {e}")
    print("[OK] Strict mode correctly rejects malformed parent references.\n")


def test_unified_accessor():
    print("=" * 70)
    print("TEST 6: get_section_or_document unified accessor")
    print("=" * 70)
    marked_doc = """\
<!-- sec:id=S1 level=2 title="Only Section" -->
## 1. Only Section
Body text.
<!-- /sec:id=S1 -->
"""
    # with an id, marked doc -> returns that section
    result = get_section_or_document(marked_doc, "S1")
    print("By id:", repr(result))
    assert "Body text." in result

    # with no id -> whole doc, markers stripped
    result_full = get_section_or_document(marked_doc, None)
    print("Whole doc (markers stripped):", repr(result_full))
    assert "sec:id" not in result_full

    # id given but wrong -> raises with a helpful hint
    try:
        get_section_or_document(marked_doc, "S99")
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        print(f"\nRaised as expected: {e}")
    print("[OK] Unified accessor covers all three cases correctly.\n")


def test_flatten_tree():
    print("=" * 70)
    print("TEST 7: flatten_tree")
    print("=" * 70)
    doc = """\
<!-- sec:id=A level=2 title="A" -->
## A
<!-- sec:id=A.1 level=3 parent=A title="A.1" -->
### A.1
<!-- /sec:id=A.1 -->
<!-- sec:id=A.2 level=3 parent=A title="A.2" -->
### A.2
<!-- /sec:id=A.2 -->
<!-- /sec:id=A -->
"""
    tree = parse_document_tree(doc)
    flat = flatten_tree(tree)
    ids = [n.id for n in flat]
    print("Flattened order:", ids)
    assert ids == ["A", "A.1", "A.2"]
    print("[OK] flatten_tree produces correct document-order flat list.\n")


if __name__ == "__main__":
    test_unmarked_heading_parse()
    test_heading_tree_and_content()
    test_block_elements_unmarked()
    test_block_elements_with_section_attribution()
    test_strict_mode_catches_orphan_parent()
    test_unified_accessor()
    test_flatten_tree()
    print("=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)
