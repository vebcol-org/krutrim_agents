"""Shared docling wrapper — `docling` (OCR/layout models) is imported lazily
inside `parse()`, not at module import time, so importing `krutrim_agent_doc`
itself doesn't force docling's model-loading weight for a deployment that
only ever ingests `.txt`/`.md` (see `plain_text.py`)."""

from __future__ import annotations

import io

from krutrim_agent_doc.base import BaseDocumentParser, ParsedDocument


class DoclingAdapter(BaseDocumentParser):
    def parse(self, data: bytes, *, file_name: str = "") -> ParsedDocument:
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter

        try:
            stream = DocumentStream(name=file_name or self.name, stream=io.BytesIO(data))
            result = DocumentConverter().convert(stream)
            text = result.document.export_to_text()
        except Exception as exc:  # noqa: BLE001 - any docling failure is a parse failure, not a crash
            return ParsedDocument(success=False, parser_used=self.name, error=str(exc))
        return ParsedDocument(success=True, text=text, parser_used=self.name)
