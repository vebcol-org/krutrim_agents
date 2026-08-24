from __future__ import annotations

from typing import ClassVar

from krutrim_agent_doc.docling.base import DoclingAdapter


class PdfParser(DoclingAdapter):
    name: ClassVar[str] = "pdf"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".pdf"})
    supported_mime_types: ClassVar[frozenset[str]] = frozenset({"application/pdf"})
