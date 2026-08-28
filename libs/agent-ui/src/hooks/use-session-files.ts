import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { randomUUID } from '@ag-ui/client';
import type { RagDocument } from '@krutrim_agent/shared-types';

import { deleteSessionRagDocument, fetchSessionRagDocuments, submitRagFile } from '../api/sessions';
import type { RagFileStatus } from '../components/agent/rag-file-row';

/**
 * The files attached to one chat/agent session — the persisted RAG documents
 * (`GET .../rag/documents`, survives reloads) merged with the uploads still in
 * flight this session. Drives `FilesDrawer`.
 *
 * The `POST /api/sessions/{id}/rag/file` call is owned **here**, fired exactly
 * once per picked file. It used to live in `RagFileRow`'s mount effect, which
 * React StrictMode (and any remount — e.g. the drawer closing) double-invoked,
 * producing a duplicate upload. `RagFileRow` is now purely presentational.
 */

export interface PendingUpload {
  rowId: string;
  file: File;
  /** `null` until the upload POST returns. */
  jobId: string | null;
  documentId: string | null;
  status: RagFileStatus;
  error?: string;
}

export interface UseSessionFilesResult {
  /** Persisted documents not currently represented by a live `pending` row. */
  documents: RagDocument[];
  pending: PendingUpload[];
  /** Total count for the header badge. */
  count: number;
  /** At least one upload is still uploading/processing. */
  isProcessing: boolean;
  addFiles: (files: File[]) => void;
  removePending: (rowId: string) => void;
  removeDocument: (documentId: string) => void;
  /** Called by a `RagFileRow` when its ingestion job reaches a terminal state. */
  handleRowIngest: (rowId: string, status: 'done' | 'error') => void;
  refetch: () => void;
}

export function useSessionFiles({
  backendUrl,
  sessionId,
}: {
  backendUrl: string;
  sessionId: string | null;
}): UseSessionFilesResult {
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const patchRow = useCallback((rowId: string, patch: Partial<PendingUpload>) => {
    setPending((prev) => prev.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r)));
  }, []);

  const refetch = useCallback(() => {
    const sid = sessionIdRef.current;
    if (!backendUrl || !sid) {
      setDocuments([]);
      return;
    }
    fetchSessionRagDocuments(backendUrl, sid)
      .then((docs) => {
        if (sessionIdRef.current === sid) setDocuments(docs);
      })
      .catch(() => {
        /* transient — keep the last-known list */
      });
  }, [backendUrl]);

  useEffect(() => {
    setPending([]);
    refetch();
  }, [sessionId, refetch]);

  const addFiles = useCallback(
    (files: File[]) => {
      const sid = sessionIdRef.current;
      if (files.length === 0 || !backendUrl || !sid) return;

      const rows: PendingUpload[] = files.map((file) => ({
        rowId: randomUUID(),
        file,
        jobId: null,
        documentId: null,
        status: 'uploading',
      }));
      setPending((prev) => [...prev, ...rows]);

      for (const row of rows) {
        submitRagFile(backendUrl, sid, row.file)
          .then((res) => {
            patchRow(row.rowId, { jobId: res.job_id, documentId: res.document_id, status: 'processing' });
            refetch();
          })
          .catch((err) => {
            patchRow(row.rowId, {
              status: 'error',
              error: err instanceof Error ? err.message : 'Upload failed.',
            });
          });
      }
    },
    [backendUrl, patchRow, refetch],
  );

  const removePending = useCallback(
    (rowId: string) => {
      setPending((prev) => {
        const row = prev.find((r) => r.rowId === rowId);
        if (row?.documentId && backendUrl && sessionIdRef.current) {
          void deleteSessionRagDocument(backendUrl, sessionIdRef.current, row.documentId).then(refetch);
        }
        return prev.filter((r) => r.rowId !== rowId);
      });
    },
    [backendUrl, refetch],
  );

  const removeDocument = useCallback(
    (documentId: string) => {
      const sid = sessionIdRef.current;
      if (!backendUrl || !sid) return;
      setDocuments((prev) => prev.filter((d) => d.document_id !== documentId));
      setPending((prev) => prev.filter((r) => r.documentId !== documentId));
      deleteSessionRagDocument(backendUrl, sid, documentId).catch(refetch);
    },
    [backendUrl, refetch],
  );

  const handleRowIngest = useCallback(
    (rowId: string, status: 'done' | 'error') => {
      patchRow(rowId, { status });
      if (status === 'done') {
        refetch();
        // Let the persisted chip take over once the manifest reflects it.
        window.setTimeout(() => setPending((prev) => prev.filter((r) => r.rowId !== rowId)), 400);
      }
    },
    [patchRow, refetch],
  );

  const pendingDocIds = useMemo(
    () => new Set(pending.map((r) => r.documentId).filter(Boolean) as string[]),
    [pending],
  );
  const visibleDocuments = useMemo(
    () => documents.filter((d) => !pendingDocIds.has(d.document_id)),
    [documents, pendingDocIds],
  );

  const isProcessing = pending.some((r) => r.status === 'uploading' || r.status === 'processing');
  const count = visibleDocuments.length + pending.length;

  return {
    documents: visibleDocuments,
    pending,
    count,
    isProcessing,
    addFiles,
    removePending,
    removeDocument,
    handleRowIngest,
    refetch,
  };
}
