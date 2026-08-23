"""
Test suite for markdown_validator.py (validates markdown against
markdown_export_standard.md).

Run with:
    pytest test_markdown_validator.py -v

Assumes markdown_validator.py (with validate_document, ValidationReport,
Severity, and the individual check_* functions) is importable from the
same directory / on PYTHONPATH.
"""

import pytest
from krutrim_agents_core.format.markdown_validatior import (
    Severity,
    ValidationReport,
    check_export_readiness,
    check_general_structure,
    check_images,
    check_math,
    check_section_markers,
    check_tables,
    check_toc,
    validate_document,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def rules(report, rule=None, severity=None):
    """Filter issues by rule id and/or severity for easy assertions."""
    issues = report.issues
    if rule is not None:
        issues = [i for i in issues if i.rule == rule]
    if severity is not None:
        issues = [i for i in issues if i.severity == severity]
    return issues


def has_error(report, rule):
    return len(rules(report, rule=rule, severity=Severity.ERROR)) > 0


def has_warning(report, rule):
    return len(rules(report, rule=rule, severity=Severity.WARNING)) > 0


# A minimal, fully-clean document reused as a baseline in several tests.
CLEAN_DOC = """\
# Title

Some intro paragraph.

## Section One

Body text here.

| Col A | Col B |
|---|---|
| 1 | 2 |
"""


# ---------------------------------------------------------------------------
# Section 0 — section identifier markers
# ---------------------------------------------------------------------------


class TestSectionMarkers:
    def test_matched_open_close_no_errors(self):
        md = (
            '<!-- sec:id=S1 level=1 title="Intro" -->\n'
            "# Intro\n"
            "Body text.\n"
            "<!-- /sec:id=S1 -->\n"
        )
        report = ValidationReport()
        check_section_markers(md, report)
        assert not rules(report, rule="0.1", severity=Severity.ERROR)

    def test_open_without_close_is_error(self):
        md = '<!-- sec:id=S1 level=1 title="Intro" -->\n# Intro\nBody.\n'
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_error(report, "0.1")

    def test_close_without_open_is_error(self):
        md = "# Intro\nBody.\n<!-- /sec:id=S1 -->\n"
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_error(report, "0.1")

    def test_duplicate_ids_is_error(self):
        md = (
            '<!-- sec:id=S1 level=1 title="A" -->\n# A\n<!-- /sec:id=S1 -->\n'
            '<!-- sec:id=S1 level=1 title="B" -->\n# B\n<!-- /sec:id=S1 -->\n'
        )
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_error(report, "0.6")

    def test_multiple_closing_markers_for_same_id_is_error(self):
        md = (
            '<!-- sec:id=S1 level=1 title="A" -->\n# A\n'
            "<!-- /sec:id=S1 -->\n<!-- /sec:id=S1 -->\n"
        )
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_error(report, "0.1")

    def test_parent_must_exist(self):
        md = (
            '<!-- sec:id=S1.sub level=2 parent=S1 title="Sub" -->\n'
            "## Sub\n"
            "<!-- /sec:id=S1.sub -->\n"
        )
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_error(report, "0.1")

    def test_parent_exists_no_error(self):
        md = (
            '<!-- sec:id=S1 level=1 title="Top" -->\n# Top\n'
            '<!-- sec:id=S1.sub level=2 parent=S1 title="Sub" -->\n'
            "## Sub\n"
            "<!-- /sec:id=S1.sub -->\n"
            "<!-- /sec:id=S1 -->\n"
        )
        report = ValidationReport()
        check_section_markers(md, report)
        parent_errors = [
            i
            for i in rules(report, rule="0.1", severity=Severity.ERROR)
            if "parent=" in i.message
        ]
        assert not parent_errors

    def test_blank_line_between_marker_and_heading_is_warning(self):
        md = '<!-- sec:id=S1 level=1 title="A" -->\n\n# A\n<!-- /sec:id=S1 -->\n'
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_warning(report, "0.1")

    def test_marker_not_followed_by_heading_is_warning(self):
        md = '<!-- sec:id=S1 level=1 title="A" -->\nJust text, no heading.\n'
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_warning(report, "0.1")

    def test_level_mismatch_is_error(self):
        md = '<!-- sec:id=S1 level=1 title="A" -->\n## A (actually h2)\n<!-- /sec:id=S1 -->\n'
        report = ValidationReport()
        check_section_markers(md, report)
        assert has_error(report, "0.1")

    def test_level_match_no_error(self):
        md = '<!-- sec:id=S1 level=2 title="A" -->\n## A\n<!-- /sec:id=S1 -->\n'
        report = ValidationReport()
        check_section_markers(md, report)
        level_errors = [
            i
            for i in rules(report, rule="0.1", severity=Severity.ERROR)
            if "declares level=" in i.message
        ]
        assert not level_errors

    def test_nested_parent_child_spans_no_false_positive(self):
        """Reproduces the spec's worked example (Section 9) — should be clean."""
        md = (
            '<!-- sec:id=S6 level=2 title="Findings" -->\n'
            "## 6. Findings\n\n"
            '<!-- sec:id=S6.market-size level=3 parent=S6 title="Market Size" -->\n'
            "### 6.1 Market Size\n\nBody.\n"
            "<!-- /sec:id=S6.market-size -->\n\n"
            '<!-- sec:id=S6.competitive-landscape level=3 parent=S6 title="Competition" -->\n'
            "### 6.2 Competition\n\nBody.\n"
            "<!-- /sec:id=S6.competitive-landscape -->\n\n"
            "<!-- /sec:id=S6 -->\n"
        )
        report = ValidationReport()
        check_section_markers(md, report)
        assert not report.errors


# ---------------------------------------------------------------------------
# Section 1 — general structural rules
# ---------------------------------------------------------------------------


class TestGeneralStructure:
    def test_clean_doc_no_errors(self):
        report = ValidationReport()
        check_general_structure(CLEAN_DOC, report)
        assert not report.errors

    def test_literal_backslash_n_is_error(self):
        md = "Line one.\\nLine two forced onto a new line.\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert has_error(report, "1")

    def test_br_inside_table_cell_is_allowed_elsewhere(self):
        # <br> itself isn't flagged by this check; only literal \n is.
        md = "| A | B |\n|---|---|\n| line1<br>line2 | x |\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert not rules(report, rule="1", severity=Severity.ERROR)

    def test_hand_drawn_rule_is_warning(self):
        md = "Some text\n----------------\nMore text\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert has_warning(report, "1")

    def test_real_horizontal_rule_not_flagged(self):
        md = "Some text\n\n---\n\nMore text\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert not report.warnings

    def test_heading_level_skip_is_error(self):
        md = "# Title\n\n### Subsection (skipped h2)\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert has_error(report, "1")

    def test_sequential_headings_no_error(self):
        md = "# Title\n\n## Section\n\n### Subsection\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert not rules(report, rule="1", severity=Severity.ERROR)

    def test_heading_level_can_decrease_without_error(self):
        # Going from ### back to ## is a normal sibling transition, not a skip.
        md = "# Title\n\n## A\n\n### A.1\n\n## B\n"
        report = ValidationReport()
        check_general_structure(md, report)
        assert not rules(report, rule="1", severity=Severity.ERROR)


# ---------------------------------------------------------------------------
# Section 2 — tables
# ---------------------------------------------------------------------------


class TestTables:
    def test_valid_table_no_errors(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        report = ValidationReport()
        check_tables(md, report)
        assert not report.errors

    def test_missing_separator_row_is_error(self):
        md = "| A | B |\n| 1 | 2 |\n| 3 | 4 |\n"
        report = ValidationReport()
        check_tables(md, report)
        assert has_error(report, "2")

    def test_ragged_row_is_error(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 | 3 |\n"
        report = ValidationReport()
        check_tables(md, report)
        assert has_error(report, "2")

    def test_wide_table_is_warning(self):
        header = "| " + " | ".join(f"C{i}" for i in range(7)) + " |"
        sep = "|" + "|".join(["---"] * 7) + "|"
        row = "| " + " | ".join(str(i) for i in range(7)) + " |"
        md = f"{header}\n{sep}\n{row}\n"
        report = ValidationReport()
        check_tables(md, report)
        assert has_warning(report, "2")

    def test_six_column_table_not_flagged_as_wide(self):
        header = "| " + " | ".join(f"C{i}" for i in range(6)) + " |"
        sep = "|" + "|".join(["---"] * 6) + "|"
        row = "| " + " | ".join(str(i) for i in range(6)) + " |"
        md = f"{header}\n{sep}\n{row}\n"
        report = ValidationReport()
        check_tables(md, report)
        assert not rules(report, rule="2", severity=Severity.WARNING)

    def test_long_table_without_repeat_header_is_info(self):
        header = "| A | B |\n|---|---|\n"
        rows = "".join(f"| {i} | {i * 2} |\n" for i in range(16))
        md = header + rows
        report = ValidationReport()
        check_tables(md, report)
        assert rules(report, rule="2", severity=Severity.INFO)

    def test_long_table_with_repeat_header_not_flagged(self):
        header = "<!-- repeat-header -->\n| A | B |\n|---|---|\n"
        rows = "".join(f"| {i} | {i * 2} |\n" for i in range(16))
        md = header + rows
        report = ValidationReport()
        check_tables(md, report)
        assert not rules(report, rule="2", severity=Severity.INFO)

    def test_short_table_not_flagged_for_length(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        report = ValidationReport()
        check_tables(md, report)
        assert not rules(report, rule="2", severity=Severity.INFO)


# ---------------------------------------------------------------------------
# Section 3 — math
# ---------------------------------------------------------------------------


class TestMath:
    def test_pdf_target_no_math_warning(self):
        md = "Inline math: $x^2 + y^2 = z^2$ in a PDF doc."
        report = ValidationReport()
        check_math(md, report, "pdf")
        assert not rules(report, rule="3", severity=Severity.WARNING)

    def test_docx_target_with_math_is_warning(self):
        md = "Inline math: $x^2 + y^2 = z^2$ in a DOCX doc."
        report = ValidationReport()
        check_math(md, report, "docx")
        assert has_warning(report, "3")

    def test_docx_target_without_math_no_warning(self):
        md = "No equations here at all."
        report = ValidationReport()
        check_math(md, report, "docx")
        assert not rules(report, rule="3", severity=Severity.WARNING)

    def test_block_math_counted_for_docx_warning(self):
        md = "$$E = mc^2$$"
        report = ValidationReport()
        check_math(md, report, "docx")
        assert has_warning(report, "3")

    def test_unterminated_inline_math_is_error(self):
        md = "The formula $E = mc^2 has no closing delimiter."
        report = ValidationReport()
        check_math(md, report, "pdf")
        assert has_error(report, "3")

    def test_currency_amounts_not_flagged_as_math(self):
        md = "The market was valued at $4.2B, growing to $12,345.67 next year."
        report = ValidationReport()
        check_math(md, report, "pdf")
        assert not rules(report, rule="3", severity=Severity.ERROR)

    def test_currency_and_valid_math_together_not_flagged(self):
        md = "Revenue was $4.2B and the growth model is $r = \\frac{a}{b}$."
        report = ValidationReport()
        check_math(md, report, "pdf")
        assert not rules(report, rule="3", severity=Severity.ERROR)

    def test_percent_currency_style_not_flagged(self):
        md = "CAGR was $12.4%, higher than the prior period."
        report = ValidationReport()
        check_math(md, report, "pdf")
        assert not rules(report, rule="3", severity=Severity.ERROR)

    def test_valid_block_math_not_flagged_as_unterminated(self):
        md = "Consider the identity:\n\n$$a^2 + b^2 = c^2$$\n\nWhich holds generally."
        report = ValidationReport()
        check_math(md, report, "pdf")
        assert not rules(report, rule="3", severity=Severity.ERROR)


# ---------------------------------------------------------------------------
# Section 4 — images & diagrams
# ---------------------------------------------------------------------------


class TestImages:
    def test_image_with_alt_text_no_warning(self):
        md = "![Revenue growth chart](chart.png)"
        report = ValidationReport()
        check_images(md, report)
        assert not report.issues

    def test_empty_alt_text_is_warning(self):
        md = "![](chart.png)"
        report = ValidationReport()
        check_images(md, report)
        assert has_warning(report, "4")

    def test_raw_mermaid_file_reference_is_error(self):
        md = "![Flow diagram](diagram.mmd)"
        report = ValidationReport()
        check_images(md, report)
        assert has_error(report, "4")

    def test_raw_mermaid_code_fence_is_error(self):
        md = "```mermaid\ngraph TD; A-->B;\n```"
        report = ValidationReport()
        check_images(md, report)
        assert has_error(report, "4")

    def test_pre_rendered_png_not_flagged(self):
        md = "![Architecture diagram](diagram.png)"
        report = ValidationReport()
        check_images(md, report)
        assert not report.errors


# ---------------------------------------------------------------------------
# Section 6 — TOC / front matter
# ---------------------------------------------------------------------------


class TestToc:
    def test_hand_typed_toc_with_dot_leaders_is_warning(self):
        md = (
            "## Table of Contents\n\n"
            "Introduction ..................... 1\n"
            "Findings .......................... 5\n"
        )
        report = ValidationReport()
        check_toc(md, report)
        assert has_warning(report, "6")

    def test_no_toc_heading_no_warning(self):
        md = "# Title\n\nJust regular content, no ToC section.\n"
        report = ValidationReport()
        check_toc(md, report)
        assert not report.issues

    def test_toc_heading_without_dot_leaders_not_flagged(self):
        md = "## Table of Contents\n\n(Generated automatically from headings.)\n"
        report = ValidationReport()
        check_toc(md, report)
        assert not report.issues


# ---------------------------------------------------------------------------
# Section 0.5 / 8 — pre-export readiness
# ---------------------------------------------------------------------------


class TestExportReadiness:
    def test_markers_present_for_pdf_target_is_error(self):
        md = '<!-- sec:id=S1 level=1 title="A" -->\n# A\n<!-- /sec:id=S1 -->\n'
        report = ValidationReport()
        check_export_readiness(md, report, "pdf")
        assert has_error(report, "0.5")

    def test_markers_present_for_docx_target_is_error(self):
        md = '<!-- sec:id=S1 level=1 title="A" -->\n# A\n<!-- /sec:id=S1 -->\n'
        report = ValidationReport()
        check_export_readiness(md, report, "docx")
        assert has_error(report, "0.5")

    def test_markers_stripped_for_pdf_target_no_error(self):
        md = "# A\nBody text.\n"
        report = ValidationReport()
        check_export_readiness(md, report, "pdf")
        assert not rules(report, rule="0.5", severity=Severity.ERROR)

    def test_markers_allowed_when_no_target_format(self):
        # target_format=None means authoring-time lint; markers are expected.
        md = '<!-- sec:id=S1 level=1 title="A" -->\n# A\n<!-- /sec:id=S1 -->\n'
        report = ValidationReport()
        check_export_readiness(md, report, None)
        assert not rules(report, rule="0.5", severity=Severity.ERROR)

    def test_layout_hints_reported_as_info_for_export(self):
        md = "<!-- repeat-header -->\n| A |\n|---|\n| 1 |\n"
        report = ValidationReport()
        check_export_readiness(md, report, "pdf")
        assert rules(report, rule="0.6", severity=Severity.INFO)


# ---------------------------------------------------------------------------
# ValidationReport behavior
# ---------------------------------------------------------------------------


class TestValidationReport:
    def test_empty_report_is_valid(self):
        report = ValidationReport()
        assert report.is_valid
        assert report.errors == []
        assert report.warnings == []
        assert report.infos == []

    def test_warnings_and_infos_do_not_invalidate(self):
        report = ValidationReport()
        report.add(Severity.WARNING, "1", "just a warning")
        report.add(Severity.INFO, "2", "just an info")
        assert report.is_valid

    def test_single_error_invalidates(self):
        report = ValidationReport()
        report.add(Severity.ERROR, "1", "something broke")
        assert not report.is_valid

    def test_summary_counts_are_accurate(self):
        report = ValidationReport()
        report.add(Severity.ERROR, "1", "e1")
        report.add(Severity.ERROR, "1", "e2")
        report.add(Severity.WARNING, "2", "w1")
        report.add(Severity.INFO, "3", "i1")
        summary = report.summary()
        assert "2 error(s)" in summary
        assert "1 warning(s)" in summary
        assert "1 info(s)" in summary

    def test_issue_str_includes_severity_rule_and_location(self):
        report = ValidationReport()
        report.add(Severity.ERROR, "2", "ragged row", line=42)
        text = str(report.issues[0])
        assert "ERROR" in text
        assert "(2)" in text
        assert "line 42" in text


# ---------------------------------------------------------------------------
# validate_document — full integration
# ---------------------------------------------------------------------------


class TestValidateDocumentIntegration:
    def test_clean_document_is_valid(self):
        report = validate_document(CLEAN_DOC)
        assert report.is_valid

    def test_worked_example_clean_before_export(self):
        """The spec's own Section 9 worked example, validated with no
        target format (authoring-time), should have no errors."""
        md = (
            '<!-- sec:id=S6 level=2 title="Current State / Core Findings" -->\n'
            "## 6. Current State / Core Findings\n\n"
            '<!-- sec:id=S6.market-size level=3 parent=S6 title="Market Size & Growth" -->\n'
            "### 6.1 Market Size & Growth\n\n"
            "The global market was valued at **$4.2B** in 2025, growing at "
            "**12.4%** CAGR. [WEB]\n\n"
            "| Metric | Value | Confidence |\n"
            "|---|---|---|\n"
            "| TAM | $4.2B | High |\n"
            "| CAGR | 12.4% | Medium |\n\n"
            "<!-- /sec:id=S6.market-size -->\n\n"
            "<!-- sec:id=S6.competitive-landscape level=3 parent=S6 "
            'title="Competitive Landscape" -->\n'
            "### 6.2 Competitive Landscape\n\n"
            "Three players hold roughly 60% combined share... [WEB]\n\n"
            "<!-- /sec:id=S6.competitive-landscape -->\n\n"
            "<!-- /sec:id=S6 -->\n"
        )
        report = validate_document(md, target_format=None)
        assert report.is_valid

    def test_worked_example_fails_pdf_export_if_markers_not_stripped(self):
        md = (
            '<!-- sec:id=S6 level=2 title="Findings" -->\n'
            "## 6. Findings\n\nBody.\n"
            "<!-- /sec:id=S6 -->\n"
        )
        report = validate_document(md, target_format="pdf")
        assert not report.is_valid
        assert has_error(report, "0.5")

    def test_document_with_multiple_error_types(self):
        md = (
            "# Title\n\n"
            "### Skipped level\n\n"
            "| A | B |\n"
            "| 1 | 2 | 3 |\n"  # missing separator + ragged row
            "\n"
            "Unterminated math: $x + y\n"
        )
        report = validate_document(md)
        assert not report.is_valid
        assert has_error(report, "1")
        assert has_error(report, "2")
        assert has_error(report, "3")

    def test_docx_target_flags_math_fidelity_warning(self):
        md = "# Title\n\nEquation: $$\\int_0^1 x^2 dx$$\n"
        report = validate_document(md, target_format="docx")
        assert has_warning(report, "3")

    def test_report_issues_include_line_numbers_where_applicable(self):
        md = "# Title\n\n### Skipped to h3\n"
        report = validate_document(md)
        heading_skip_issues = rules(report, rule="1", severity=Severity.ERROR)
        assert heading_skip_issues
        assert heading_skip_issues[0].line is not None


# ---------------------------------------------------------------------------
# Parametrized sanity sweep across target_format values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target_format", [None, "pdf", "docx"])
def test_validate_document_never_raises_on_clean_input(target_format):
    validate_document(CLEAN_DOC, target_format=target_format)


@pytest.mark.parametrize("target_format", [None, "pdf", "docx"])
def test_validate_document_never_raises_on_empty_input(target_format):
    report = validate_document("", target_format=target_format)
    assert report.is_valid
