import type { SessionInfo } from '@krutrim_agent/shared-types';
import { Button, Sheet, SheetContent, SheetHeader, SheetTitle } from '@krutrim_agent/ui';
import { CalendarClock, FileText, Info, X } from 'lucide-react';

import type { UseSessionFilesResult } from '../../hooks/use-session-files';
import { RagFileRow } from './rag-file-row';

/** Header info button that opens `FilesDrawer` — sits between the session
 * list's "+" and the settings gear. Shows a count badge while the session
 * has attached files. */
export function FilesButton({
  count,
  disabled,
  onClick,
}: {
  count: number;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={count > 0 ? `Session files (${count})` : 'Session files'}
      disabled={disabled}
      onClick={onClick}
      className="relative"
    >
      <Info className="size-4" />
      {count > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.6rem] font-medium leading-none text-primary-foreground">
          {count > 9 ? '9+' : count}
        </span>
      )}
    </Button>
  );
}

export interface FilesDrawerProps {
  backendUrl: string;
  files: UseSessionFilesResult;
  /** The active session — its `created_at` is shown as the session's start time. */
  session?: SessionInfo | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Right-side drawer listing every document attached to the current
 * chat/agent session — persisted RAG documents (survive a reload) plus the
 * uploads still being processed. Opened from the header info button next to
 * the session list; also pops open automatically right after a file is
 * picked in the composer.
 */
export function FilesDrawer({ backendUrl, files, session, open, onOpenChange }: FilesDrawerProps) {
  const { documents, pending, count, handleRowIngest, removePending, removeDocument } = files;
  const startedAt = session ? new Date(session.created_at) : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent aria-describedby={undefined} className="gap-3">
        <SheetHeader>
          <SheetTitle>Session files{count > 0 ? ` (${count})` : ''}</SheetTitle>
          {startedAt && !Number.isNaN(startedAt.getTime()) && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CalendarClock className="size-3.5" />
              Session started {startedAt.toLocaleString()}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Documents indexed for retrieval in this session. The agent can search them while it answers.
          </p>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-2 overflow-y-auto pr-1">
          {count === 0 && (
            <p className="mt-6 text-center text-sm text-muted-foreground">
              No files yet. Use the <span className="font-medium text-foreground">+</span> button in the composer to
              attach a PDF, DOCX, Markdown or text file.
            </p>
          )}

          {pending.map((row) => (
            <RagFileRow
              key={row.rowId}
              backendUrl={backendUrl}
              rowId={row.rowId}
              fileName={row.file.name}
              jobId={row.jobId}
              status={row.status}
              errorText={row.error}
              onIngest={handleRowIngest}
              onRemove={() => removePending(row.rowId)}
            />
          ))}

          {documents.map((doc) => (
            <div
              key={doc.document_id}
              className="flex items-center gap-2.5 rounded-lg border border-border bg-muted/30 p-2.5"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-success/10 text-success">
                <FileText className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{doc.filename ?? doc.title}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {doc.kind === 'text' ? 'Pasted text' : 'Indexed'} ·{' '}
                  {new Date(doc.created_at).toLocaleString()}
                </p>
              </div>
              <button
                type="button"
                onClick={() => removeDocument(doc.document_id)}
                aria-label={`Remove ${doc.title}`}
                className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
