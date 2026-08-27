# `krutrim_agent_doc` (backend/libs/krutrim_agent_doc)

Package name: **`krutrim-agent-doc`** (`backend/libs/krutrim_agent_doc/pyproject.toml`). Document parsing for RAG ingestion: plain text/markdown plus PDF/DOCX via [docling](https://github.com/docling-project/docling). Dependency of `krutrim_agent_celery` **only** — not `krutrim_agent_rag`, which stays dependency-light, and not the FastAPI backend, which never imports Celery task code (it dispatches by task name string via `celery_client.py`).

```
krutrim_agent_doc/
├── base.py              ParsedDocument, BaseDocumentParser(ABC)
├── registry.py           DocumentParserRegistry, default_registry()
├── plain_text.py           PlainTextParser — .txt/.md
└── docling/
    ├── base.py               DoclingAdapter — shared docling wrapper
    ├── pdf.py                  PdfParser — .pdf
    └── docx.py                 DocxParser — .docx
```

## `base.py`

- `ParsedDocument` (pydantic `BaseModel`) — `success: bool`, `text: str`, `parser_used: str`, `error: str | None`.
- `BaseDocumentParser(ABC)` — `name`, `supported_extensions`, `supported_mime_types` class vars; `can_handle(*, mime_type, file_name) -> bool` (extension or mime match); abstract `parse(data: bytes, *, file_name="") -> ParsedDocument`.

## `registry.py`

`DocumentParserRegistry` — **predicate-based** dispatch (first registered parser whose `can_handle()` matches wins), deliberately not built on `krutrim_agent_utils.PluginRegistry` (that's a keyed lookup; parser selection is a scan over a predicate, a genuinely different shape). `default_registry()` builds one with `PlainTextParser`, `PdfParser`, `DocxParser` registered, in that order. `registry.parse(data, *, mime_type=None, file_name="") -> ParsedDocument` never raises — an unmatched extension returns `ParsedDocument(success=False, error=...)`, same as any other parse failure; `registry.resolve(...)` is the raising variant (`UnsupportedDocumentError`) for callers that want to fail fast instead.

## `plain_text.py`

`PlainTextParser` — `.txt`/`.md`. Plain UTF-8 decode; a `UnicodeDecodeError` becomes `ParsedDocument(success=False, error="Document is not valid UTF-8 text.")`. This is what keeps the pre-existing text-paste ingestion path (`POST /rag/text`) behaving identically once routed through the parser registry instead of a bare `content.decode("utf-8")`.

## `docling/`

`DoclingAdapter` (`docling/base.py`) wraps `docling.document_converter.DocumentConverter`, exporting to markdown (`result.document.export_to_markdown()`). The `docling` import is **deferred inside `parse()`**, not at module top level — importing `krutrim_agent_doc` itself (or `PdfParser`/`DocxParser` as classes) never forces docling's OCR/layout model loading; only an actual `.parse()` call on a PDF/DOCX does. `PdfParser`/`DocxParser` just declare the format-specific `supported_extensions`/`supported_mime_types` on top of the shared adapter.

**Dependency weight**: docling pulls in `torch`, `transformers`, and several CV/OCR libraries — a real, heavy footprint, confirmed via `uv sync` (hundreds of MB, GPU-capable ML stack) compared to the rest of this workspace. It's a hard dependency of this package for v1, not an optional extra — revisit if a deployment that only ever ingests `.txt`/`.md` needs to avoid paying for it.

**`torch`/`faiss` OpenMP conflict**: `krutrim_agent_celery` now loads both this package (torch, via docling) and `krutrim_agent_rag` (faiss, via faisslite) in one worker process. Each links its own bundled OpenMP runtime, which aborts the process on macOS ("OMP: Error #15") unless `KMP_DUPLICATE_LIB_OK=TRUE` is set before either is first imported — and even with that set, two OpenMP thread pools genuinely running concurrently can still segfault, not just abort. `krutrim_agent_celery/app.py` sets `KMP_DUPLICATE_LIB_OK=TRUE` and pins `faiss.omp_set_num_threads(1)` (mirrored in `backend/tests/conftest.py` for the test process) as the first things it does, ahead of any import that could pull in either library. If this proves insufficient under real production load, the more robust fix is running docling extraction in a separate process/queue from anything touching the vector index, so torch and faiss never coexist in one process at all.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_doc/pyproject.toml) — package `krutrim-agent-doc`: `pydantic`, `docling`.

## Relevant tests

- `backend/tests/test_document_parsers.py` — `PlainTextParser` decode/error behavior, `can_handle()` matching for all three parsers, registry dispatch (including the unsupported-extension path). Deliberately doesn't exercise the docling-backed parsers' actual `parse()` — that loads real OCR/layout models, too slow/heavy for a unit test; covered instead via `test_process_rag_document.py`'s fake-registry test of the *calling* code's wiring.
