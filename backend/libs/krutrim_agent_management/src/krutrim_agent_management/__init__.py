"""Pluggable persistence layer: projects, agent memory, sessions, and a result cache.

`Storage` is the backend-agnostic contract; `LocalStorage` (SQLite + filesystem) is the
only implementation today.
"""

from krutrim_agent_management.base import Storage
from krutrim_agent_management.blobstore import BlobStore, LocalBlobStore
from krutrim_agent_management.local import LocalStorage
from krutrim_agent_management.models import (
    Agent,
    Chat,
    OwnerType,
    Project,
    SessionInfo,
    SharingScope,
)
from krutrim_agent_management.paths import default_storage_root

__all__ = [
    "Agent",
    "BlobStore",
    "Chat",
    "LocalBlobStore",
    "LocalStorage",
    "OwnerType",
    "Project",
    "SessionInfo",
    "SharingScope",
    "Storage",
    "default_storage_root",
]
