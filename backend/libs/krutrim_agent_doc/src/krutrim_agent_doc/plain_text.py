"""`.txt`/`.md` — decode as UTF-8, no extraction needed. Keeps the pre-existing
text-paste ingestion path (`/rag/text`) behaving identically once routed
through the parser registry."""

from __future__ import annotations

from typing import ClassVar

from krutrim_agent_doc.base import BaseDocumentParser, ParsedDocument


class PlainTextParser(BaseDocumentParser):
    name: ClassVar[str] = "plain_text"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".txt", ".md"})
    supported_mime_types: ClassVar[frozenset[str]] = frozenset(
        {"text/plain", "text/markdown"}
    )

    def parse(self, data: bytes, *, file_name: str = "") -> ParsedDocument:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ParsedDocument(
                success=False,
                parser_used=self.name,
                error="Document is not valid UTF-8 text.",
            )
        return ParsedDocument(success=True, text=text, parser_used=self.name)
