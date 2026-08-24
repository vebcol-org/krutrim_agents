from __future__ import annotations

from typing import ClassVar

from krutrim_agent_doc.docling.base import DoclingAdapter


class DocxParser(DoclingAdapter):
    name: ClassVar[str] = "docx"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".docx"})
    supported_mime_types: ClassVar[frozenset[str]] = frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    )
