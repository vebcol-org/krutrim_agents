import { useEffect, useState } from 'react';
import type { RagIngestJobProgressEvent } from '@krutrim_agent/shared-types';
import { cn, Progress } from '@krutrim_agent/ui';
import { FileText, X } from 'lucide-react';

import { submitRagFile } from '../../api/sessions';
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

export type RagFileStatus = 'processing' | 'done' | 'error';

export interface RagFileRowProps {
  backendUrl: string;
  sessionId: string;
  file: File;
  /** A stable id the parent assigned when this row was created (before the
   * backend's `document_id` exists) — used as the tracking key so the
   * parent can compute "is anything still processing" from the very first
   * render, not only once upload has succeeded. */
  rowId: string;
  onStatusChange: (rowId: string, status: RagFileStatus) => void;
  onRemove: () => void;
}

/**
 * A Claude/ChatGPT-style attachment chip for one uploaded file — owns its
 * own `submitRagFile` call and `useSseStatus` subscription, matching React's
 * usual "one hook instance per list item via sub-component" idiom rather
 * than trying to fan a single hook out across N files manually.
 */
export function RagFileRow({ backendUrl, sessionId, file, rowId, onStatusChange, onRemove }: RagFileRowProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const progress = useSseStatus<RagIngestJobProgressEvent>(jobId ? `${backendUrl}/api/status/jobs/${jobId}` : null);

  useEffect(() => {
    let cancelled = false;
    submitRagFile(backendUrl, sessionId, file)
      .then((response) => {
        if (!cancelled) setJobId(response.job_id);
      })
      .catch((err) => {
        if (!cancelled) setSubmitError(err instanceof Error ? err.message : 'Failed to upload.');
      });
    return () => {
      cancelled = true;
    };
    // Submit exactly once per mounted row — one row per selected file, and
    // `file`/`sessionId`/`backendUrl` don't change across this row's lifetime.
  }, []);

  const isError = submitError != null || progress?.stage === 'error';
  const stageIndex = progress && progress.stage !== 'error' ? STAGE_ORDER.indexOf(progress.stage) : -1;
  const stageFraction = progress && progress.total ? (progress.processed ?? 0) / progress.total : 0;
  const isDone = !isError && stageIndex === STAGE_ORDER.length - 1 && stageFraction >= 1;
  const status: RagFileStatus = isError ? 'error' : isDone ? 'done' : 'processing';

  useEffect(() => {
    onStatusChange(rowId, status);
    // `onStatusChange` deliberately excluded: it's a new closure each parent
    // render, and including it here would re-fire this effect (and thus the
    // parent's state update) every render instead of only on real status change.
  }, [rowId, status]);

  const label = isError
    ? (submitError ?? progress?.error ?? 'Failed to process.')
    : progress && progress.stage !== 'error'
      ? STAGE_LABEL[progress.stage]
      : jobId
        ? 'Queued…'
        : 'Uploading…';

  return (
    <div className="flex w-56 shrink-0 flex-col gap-1 rounded-lg border border-border bg-muted/30 p-2">
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
          <p className="truncate text-xs font-mono">{file.name}</p>
          <p className={cn('truncate text-[10px]', isError ? 'text-destructive' : 'text-muted-foreground')}>{label}</p>
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${file.name}`}
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
