from __future__ import annotations

import os
import re
from typing import BinaryIO, ClassVar

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

from krutrim_agent_doc.docling.base import DoclingAdapter, ParsedDocument


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean flag from the environment (accepts 1/true/yes/on, case-insensitive)."""
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}




class PdfParser(DoclingAdapter):
    name: ClassVar[str] = "pdf"
    supported_extensions: ClassVar[frozenset[str]] = frozenset({".pdf"})
    supported_mime_types: ClassVar[frozenset[str]] = frozenset({"application/pdf"})

    MIN_SCORE_RAW: ClassVar[float] = 0.65
    MIN_SCORE_OCR: ClassVar[float] = 0.65
    MIN_CHARS_PER_PAGE: ClassVar[int] = 40

    # Env var names controlling escalation. Each stage only runs if the
    # corresponding flag is enabled AND the previous stage's score was too low.
    ENV_ENABLE_OCR_STAGE: ClassVar[str] = "PDF_PARSER_ENABLE_OCR_STAGE"
    ENV_ENABLE_ML_STAGE: ClassVar[str] = "PDF_PARSER_ENABLE_ML_STAGE"

    def parse(self, data: BinaryIO, file_name: str) -> ParsedDocument:
        """
        Escalate stage-by-stage, but only if the corresponding env flag allows it:
          1. Raw text-layer extraction (pypdfium2, zero ML / zero OCR) - always runs
          2. Docling + OCR only               - gated by ENV_ENABLE_OCR_STAGE
          3. Docling + OCR + full ML          - gated by ENV_ENABLE_ML_STAGE

        If a stage is disabled via env var, or the score is already good enough,
        the current best result is returned as-is (no further escalation).
        """
        result = self._extract_raw(data)
        if result.score >= self.MIN_SCORE_RAW:
            return result
        if not _env_flag(self.ENV_ENABLE_OCR_STAGE):
            return result

        result = self._extract_with_docling(data, use_full_ml=False)
        if result.score >= self.MIN_SCORE_OCR:
            return result
        if not _env_flag(self.ENV_ENABLE_ML_STAGE):
            return result

        result = self._extract_with_docling(data, use_full_ml=True)
        return result

    # ---------- Stage 1: no ML, no OCR ----------
    def _extract_raw(self, bytes: BinaryIO) -> ParsedDocument:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(bytes)
        page_texts = []
        for page in pdf:
            textpage = page.get_textpage()
            page_texts.append(textpage.get_text_range())
            textpage.close()
            page.close()
        num_pages = len(pdf)
        pdf.close()

        text = "\n".join(page_texts)
        score = self._score_text(text, num_pages)
        
        return ParsedDocument(success=True, text=text, score=score, parser_used="raw")

    # ---------- Stage 2 / 3: Docling pipeline, OCR (+ optional table/layout ML) ----------
    def _extract_with_docling(self, bytes: BinaryIO, *, use_full_ml: bool) -> ParsedDocument:
        pipeline_options = PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=use_full_ml,
            ocr_options=EasyOcrOptions(force_full_page_ocr=True),  # stage 1 already
        )                                                           # showed the text layer is bad
        if use_full_ml:
            pipeline_options.table_structure_options = TableStructureOptions(
                mode=TableFormerMode.ACCURATE,
                do_cell_matching=True,
            )

        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        document = converter.convert(str(bytes)).document
        text = document.export_to_text()
        num_pages = len(document.pages) if document.pages else 1
        score = self._score_text(text, num_pages)
        stage = "ocr_full_ml" if use_full_ml else "ocr_only"
        return ParsedDocument(success=True, text=text, score=score, parser_used=stage)

    # ---------- Scoring heuristic ----------
    def _score_text(self, text: str, num_pages: int) -> float:
        """
        Dependency-free quality heuristic in [0, 1], combining:
          - text density per page (catches blank/scanned pages with no layer)
          - alnum ratio (catches garbled font-encoding extraction)
          - junk-character ratio (replacement/control chars)
        """
        num_pages = max(num_pages, 1)
        stripped = text.strip()
        if not stripped:
            return 0.0

        chars_per_page = len(stripped) / num_pages
        density_score = min(chars_per_page / (self.MIN_CHARS_PER_PAGE * 5), 1.0)

        alnum_ratio = sum(c.isalnum() for c in stripped) / len(stripped)

        junk = len(re.findall(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]", stripped))
        junk_ratio = junk / len(stripped)

        score = 0.5 * density_score + 0.4 * alnum_ratio + 0.1 * (1 - junk_ratio)
        return max(0.0, min(score, 1.0))