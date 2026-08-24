"""Tests for `krutrim_agent_doc` — plain-text parsing and registry dispatch.
Deliberately does not exercise the docling-backed PDF/DOCX parsers (they
load real OCR/layout models — slow, and not worth the cost for a dispatch-
logic unit test); `can_handle()` matching for those is covered directly."""

from __future__ import annotations

from krutrim_agent_doc.docling.docx import DocxParser
from krutrim_agent_doc.docling.pdf import PdfParser
from krutrim_agent_doc.plain_text import PlainTextParser
from krutrim_agent_doc.registry import DocumentParserRegistry, UnsupportedDocumentError


def test_plain_text_parser_decodes_utf8():
    result = PlainTextParser().parse("hello world".encode(), file_name="notes.txt")
    assert result.success is True
    assert result.text == "hello world"


def test_plain_text_parser_rejects_invalid_utf8():
    result = PlainTextParser().parse(b"\xff\xfe\x00\x01", file_name="notes.txt")
    assert result.success is False
    assert "UTF-8" in result.error


def test_plain_text_parser_can_handle_by_extension():
    parser = PlainTextParser()
    assert parser.can_handle(mime_type=None, file_name="notes.txt") is True
    assert parser.can_handle(mime_type=None, file_name="README.md") is True
    assert parser.can_handle(mime_type=None, file_name="report.pdf") is False


def test_pdf_parser_can_handle_by_extension_and_mime():
    parser = PdfParser()
    assert parser.can_handle(mime_type=None, file_name="report.pdf") is True
    assert parser.can_handle(mime_type="application/pdf", file_name="unnamed") is True
    assert parser.can_handle(mime_type=None, file_name="notes.txt") is False


def test_docx_parser_can_handle_by_extension():
    assert DocxParser().can_handle(mime_type=None, file_name="report.docx") is True


def test_registry_dispatches_by_extension_first_match_wins():
    registry = DocumentParserRegistry()
    registry.register(PlainTextParser())
    registry.register(PdfParser())

    result = registry.parse(b"hello", file_name="notes.txt")
    assert result.success is True
    assert result.parser_used == "plain_text"


def test_registry_raises_for_unsupported_extension():
    registry = DocumentParserRegistry()
    registry.register(PlainTextParser())

    try:
        registry.resolve(mime_type=None, file_name="archive.zip")
        raised = False
    except UnsupportedDocumentError:
        raised = True
    assert raised


def test_registry_parse_returns_failure_for_unsupported_extension_instead_of_raising():
    registry = DocumentParserRegistry()
    registry.register(PlainTextParser())

    result = registry.parse(b"data", file_name="archive.zip")
    assert result.success is False
    assert "archive.zip" in result.error
