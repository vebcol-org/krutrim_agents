import { useState } from 'react';
import type { RagIngestJobProgressEvent } from '@krutrim_agent/shared-types';
import { Button, Input, Label, Progress, Sheet, SheetContent, SheetHeader, SheetTitle, Textarea } from '@krutrim_agent/ui';

import { submitRagText } from '../../api/sessions';
import { useSseStatus } from '../../hooks/use-sse-status';

export interface RagUploadSheetProps {
  backendUrl: string;
  sessionId: string;
  onClose: () => void;
}

const STAGE_LABEL: Record<RagIngestJobProgressEvent['stage'], string> = {
  extracting: 'Extracting text…',
  chunking: 'Chunking…',
  embedding: 'Embedding…',
  indexing: 'Indexing…',
};
const STAGE_ORDER: RagIngestJobProgressEvent['stage'][] = ['extracting', 'chunking', 'embedding', 'indexing'];

/**
 * "Add research information" — pasted text or a `.txt` file's contents
 * (read client-side via the File API; v1 RAG ingestion is text-only, so
 * there's no separate binary upload endpoint — both inputs feed the same
 * `POST /api/sessions/{id}/rag/text`), with live stage progress via SSE.
 *
 * Lives in `agent-ui`, not `agent-renderers/src/research/` (where the rest
 * of the research-specific UI lives), because it needs `submitRagText`/
 * `useSseStatus` — pulling those in from `agent-renderers` would create a
 * circular workspace dependency (`agent-ui` already depends on
 * `agent-renderers` for `getAgentRenderer`, not the other way around). The
 * backend route itself is a plain session-level API, not research-specific,
 * so this placement isn't actually a layering violation — see
 * `AgentThread`'s header, where this is triggered only when the active
 * profile is `research` today.
 */
export function RagUploadSheet({ backendUrl, sessionId, onClose }: RagUploadSheetProps) {
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const progress = useSseStatus<RagIngestJobProgressEvent>(jobId ? `${backendUrl}/api/status/jobs/${jobId}` : null);

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith('.txt')) {
      setError('Only .txt files are supported.');
      return;
    }
    const content = await file.text();
    setText(content);
    setError(null);
    if (!title.trim()) setTitle(file.name);
  }

  async function submit() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await submitRagText(backendUrl, sessionId, { text: trimmed, title: title.trim() || null });
      setJobId(response.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit.');
    } finally {
      setSubmitting(false);
    }
  }

  const stageIndex = progress ? STAGE_ORDER.indexOf(progress.stage) : -1;
  const stageFraction = progress && progress.total > 0 ? progress.processed / progress.total : 0;
  const isDone = stageIndex === STAGE_ORDER.length - 1 && stageFraction >= 1;

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>Add research information</SheetTitle>
        </SheetHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rag-title">Title (optional)</Label>
          <Input
            id="rag-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Q3 planning notes"
            disabled={jobId != null}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rag-text">Paste text, or upload a .txt file</Label>
          <Textarea
            id="rag-text"
            rows={10}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste research notes, a document, or anything you want the agent to be able to recall…"
            disabled={jobId != null}
          />
          <input
            type="file"
            accept=".txt,text/plain"
            disabled={jobId != null}
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            className="text-xs text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs file:text-foreground"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        {jobId && (
          <Progress
            value={stageIndex < 0 ? 0 : stageIndex + stageFraction}
            max={STAGE_ORDER.length}
            label={progress ? STAGE_LABEL[progress.stage] : 'Queued…'}
          />
        )}

        {isDone ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <Button onClick={submit} disabled={submitting || !text.trim() || jobId != null}>
            {submitting ? 'Submitting…' : 'Add to research context'}
          </Button>
        )}
      </SheetContent>
    </Sheet>
  );
}
