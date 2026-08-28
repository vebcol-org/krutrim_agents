import { useEffect } from 'react';
import type { RagIngestJobProgressEvent } from '@krutrim_agent/shared-types';
import { cn, Progress } from '@krutrim_agent/ui';
import { FileText, X } from 'lucide-react';

import { useSseStatus } from '../../hooks/use-sse-status';

const STAGE_LABEL: Record<'extracting' | 'chunking' | 'embedding' | 'indexing', string> = {
  extracting: 'Extracting text…',
  chunking: 'Chunking…',
  embedding: 'Embedding…',
  indexing: 'Indexing…',
};
const STAGE_ORDER: Array<'extracting' | 'chunking' | 'embedding' | 'indexing'> = [
  'extracting',
  'chunking',
  'embedding',
  'indexing',
];

export type RagFileStatus = 'uploading' | 'processing' | 'done' | 'error';

export interface RagFileRowProps {
  backendUrl: string;
  rowId: string;
  fileName: string;
  /** `null` until the upload POST has returned a job id. */
  jobId: string | null;
  /** Upload/ingest status owned by `useSessionFiles` — this row never uploads itself. */
  status: RagFileStatus;
  errorText?: string;
  /** Fires once the ingestion job reaches a terminal state, so the owner can
   * refetch the manifest / drop this pending row. */
  onIngest: (rowId: string, status: 'done' | 'error') => void;
  onRemove: () => void;
}

/**
 * Presentational row for one in-flight RAG upload: filename + a stage progress
 * bar driven by the ingestion job's SSE stream. The actual `POST /rag/file` is
 * done once, up in `useSessionFiles` — doing it here made React StrictMode (and
 * any remount, e.g. the files drawer closing/reopening) fire a duplicate upload.
 */
export function RagFileRow({ backendUrl, rowId, fileName, jobId, status, errorText, onIngest, onRemove }: RagFileRowProps) {
  const progress = useSseStatus<RagIngestJobProgressEvent>(jobId ? `${backendUrl}/api/status/jobs/${jobId}` : null);

  const isError = status === 'error' || progress?.stage === 'error';
  const stageIndex = progress && progress.stage !== 'error' ? STAGE_ORDER.indexOf(progress.stage) : -1;
  const stageFraction = progress && progress.total ? (progress.processed ?? 0) / progress.total : 0;
  const isDone = !isError && stageIndex === STAGE_ORDER.length - 1 && stageFraction >= 1;

  useEffect(() => {
    if (isDone) onIngest(rowId, 'done');
    else if (progress?.stage === 'error') onIngest(rowId, 'error');
    // `onIngest` deliberately excluded from deps: it's a new closure each parent
    // render, and including it would re-fire this every render rather than only
    // on a real terminal state.
  }, [rowId, isDone, progress?.stage]);

  const label = isError
    ? (errorText ?? progress?.error ?? 'Failed to process.')
    : status === 'uploading'
      ? 'Uploading…'
      : progress && progress.stage !== 'error'
        ? STAGE_LABEL[progress.stage]
        : 'Queued…';

  return (
    <div className="flex w-full flex-col gap-1 rounded-lg border border-border bg-muted/30 p-2">
      <div className="flex items-center gap-2">
        <div
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-md',
            isError ? 'bg-destructive/10 text-destructive' : isDone ? 'bg-success/10 text-success' : 'bg-primary/10 text-primary',
          )}
        >
          <FileText className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-mono">{fileName}</p>
          <p className={cn('truncate text-[10px]', isError ? 'text-destructive' : 'text-muted-foreground')}>{label}</p>
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${fileName}`}
          className="shrink-0 text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>
      {!isError && !isDone && (
        <Progress value={stageIndex < 0 ? 0 : stageIndex + stageFraction} max={STAGE_ORDER.length} />
      )}
    </div>
  );
}
