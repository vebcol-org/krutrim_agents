"""The parser contract every format implementation satisfies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel


class ParsedDocument(BaseModel):
    success: bool
    text: str = ""
    parser_used: str = ""
    error: str | None = None


class BaseDocumentParser(ABC):
    name: ClassVar[str]
    supported_extensions: ClassVar[frozenset[str]] = frozenset()
    supported_mime_types: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def can_handle(cls, *, mime_type: str | None, file_name: str) -> bool:
        if mime_type and mime_type in cls.supported_mime_types:
            return True
        suffix = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        return suffix in cls.supported_extensions

    @abstractmethod
    def parse(self, data: bytes, *, file_name: str = "") -> ParsedDocument: ...
