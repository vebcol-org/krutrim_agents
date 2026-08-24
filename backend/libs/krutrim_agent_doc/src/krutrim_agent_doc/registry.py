"""Predicate-based parser dispatch — first registered parser whose
`can_handle()` matches wins. Deliberately not `krutrim_agent_utils.PluginRegistry`
(that's a keyed lookup; parser selection is a predicate scan over file
name/mime type, a genuinely different shape)."""

from __future__ import annotations

from krutrim_agent_doc.base import BaseDocumentParser, ParsedDocument


class UnsupportedDocumentError(ValueError):
    pass


class DocumentParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[BaseDocumentParser] = []

    def register(self, parser: BaseDocumentParser) -> None:
        self._parsers.append(parser)

    def resolve(self, *, mime_type: str | None, file_name: str) -> BaseDocumentParser:
        for parser in self._parsers:
            if parser.can_handle(mime_type=mime_type, file_name=file_name):
                return parser
        raise UnsupportedDocumentError(
            f"No parser registered for '{file_name}' (mime_type={mime_type!r})."
        )

    def parse(
        self, data: bytes, *, mime_type: str | None = None, file_name: str = ""
    ) -> ParsedDocument:
        try:
            parser = self.resolve(mime_type=mime_type, file_name=file_name)
        except UnsupportedDocumentError as exc:
            return ParsedDocument(success=False, error=str(exc))
        return parser.parse(data, file_name=file_name)


def default_registry() -> DocumentParserRegistry:
    from krutrim_agent_doc.docling.docx import DocxParser
    from krutrim_agent_doc.docling.pdf import PdfParser
    from krutrim_agent_doc.plain_text import PlainTextParser

    registry = DocumentParserRegistry()
    registry.register(PlainTextParser())
    registry.register(PdfParser())
    registry.register(DocxParser())
    return registry
