import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { randomUUID } from '@ag-ui/client';
import { Button, cn, Textarea } from '@krutrim_agent/ui';
import { ArrowUp, Loader2, Plus } from 'lucide-react';

import { PastedTextChip } from './pasted-text-chip';
import { RagFileRow, type RagFileStatus } from './rag-file-row';

/** Kept in sync with `krutrim_agent_doc`'s registered parsers
 * (`plain_text.py`, `docling/pdf.py`, `docling/docx.py`). */
const ACCEPTED_FILE_EXTENSIONS = '.txt,.md,.pdf,.docx';

/** A paste past this length collapses into a `PastedTextChip` instead of
 * filling the textarea with raw content — matches Claude/ChatGPT's UX for
 * large pastes. */
const LARGE_PASTE_THRESHOLD_CHARS = 1500;

/** Auto-grow ceiling for the textarea, in px — past this it scrolls
 * internally rather than pushing the message list further up. */
const MAX_TEXTAREA_HEIGHT = 200;

interface FileAttachment {
  id: string;
  file: File;
}

interface TextAttachment {
  id: string;
  text: string;
}

export interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
  /** Backend base URL + active session id — required to enable file
   * attachments (they upload through the RAG ingestion pipeline). Omit or
   * pass a null sessionId to hide the attach button, e.g. before a session
   * exists yet. */
  backendUrl?: string;
  sessionId?: string | null;
  /** Lazily creates (and returns) a session id when there isn't one yet —
   * lets a file be attached on a brand-new chat before its first message.
   * Omit for flows whose session always exists by the time the composer
   * renders (e.g. `AgentThread`). */
  ensureSession?: () => Promise<string | null>;
  /** Fires whenever "is at least one attached file still processing"
   * changes — lets a parent gate other UI (e.g. the tab title) while
   * embedding is in flight. */
  onUploadingChange?: (active: boolean) => void;
}

export function Composer({ disabled, onSend, backendUrl, sessionId, ensureSession, onUploadingChange }: ComposerProps) {
  const [value, setValue] = useState('');
  const [fileAttachments, setFileAttachments] = useState<FileAttachment[]>([]);
  const [textAttachments, setTextAttachments] = useState<TextAttachment[]>([]);
  const [fileStatuses, setFileStatuses] = useState<Record<string, RagFileStatus>>({});
  // A session id resolved on demand via `ensureSession` — kept so that once
  // the first attachment forces a session into being, later ones reuse it
  // even before the parent's own `sessionId` prop catches up.
  const [lazySessionId, setLazySessionId] = useState<string | null>(null);
  const [resolvingSession, setResolvingSession] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const effectiveSessionId = sessionId ?? lazySessionId;
  const canAttach = Boolean(backendUrl && (effectiveSessionId || ensureSession));
  const anyFileProcessing = fileAttachments.some((a) => (fileStatuses[a.id] ?? 'processing') === 'processing');

  useEffect(() => {
    onUploadingChange?.(anyFileProcessing);
  }, [anyFileProcessing, onUploadingChange]);

  // Reset the "uploading" flag on unmount so an abandoned attachment never
  // leaves a parent's UI (e.g. a disabled send button) stuck.
  useEffect(() => () => onUploadingChange?.(false), [onUploadingChange]);

  // Auto-grow the textarea to fit its content (up to a ceiling), then let it
  // scroll — the Claude/ChatGPT single-field-that-expands behaviour.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  function handleFileRowStatusChange(rowId: string, status: RagFileStatus) {
    setFileStatuses((prev) => ({ ...prev, [rowId]: status }));
  }

  function addFiles(selected: File[]) {
    const newRows = selected.map((file) => ({ id: randomUUID(), file }));
    setFileAttachments((prev) => [...prev, ...newRows]);
  }

  /** Runs after the native file dialog closes. Resolves a session first (a
   * new chat has none until its first message) so every `RagFileRow` can
   * upload against a real `POST /api/sessions/{id}/rag/file`. */
  async function handleFilesPicked(files: File[]) {
    if (files.length === 0) return;
    setAttachError(null);

    let sid = effectiveSessionId;
    if (!sid && ensureSession) {
      setResolvingSession(true);
      try {
        sid = await ensureSession();
      } finally {
        setResolvingSession(false);
      }
      if (!sid) {
        setAttachError('Could not start a session for the upload. Try again.');
        return;
      }
      setLazySessionId(sid);
    }
    if (!sid) return;
    addFiles(files);
  }

  function removeFileAttachment(id: string) {
    setFileAttachments((prev) => prev.filter((a) => a.id !== id));
    setFileStatuses((prev) => {
      const rest = { ...prev };
      delete rest[id];
      return rest;
    });
  }

  function removeTextAttachment(id: string) {
    setTextAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = e.clipboardData.getData('text/plain');
    if (pasted.length <= LARGE_PASTE_THRESHOLD_CHARS) return;
    e.preventDefault();
    setTextAttachments((prev) => [...prev, { id: randomUUID(), text: pasted }]);
  }

  function submit() {
    if (disabled || anyFileProcessing) return;
    const combined = [value.trim(), ...textAttachments.map((a) => a.text)].filter(Boolean).join('\n\n');
    if (!combined) return;
    onSend(combined);
    setValue('');
    setTextAttachments([]);
    setFileAttachments([]);
    setFileStatuses({});
  }

  const hasAttachments = fileAttachments.length > 0 || textAttachments.length > 0;
  const hasText = value.trim().length > 0 || textAttachments.length > 0;
  const sendDisabled = disabled || anyFileProcessing || !hasText;

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="mx-auto w-full max-w-2xl">
        <div
          onClick={() => textareaRef.current?.focus()}
          className={cn(
            'flex cursor-text flex-col gap-2 rounded-[1.75rem] border border-input bg-muted/40 p-2 shadow-sm transition-colors',
            'focus-within:border-primary/60 focus-within:bg-background focus-within:shadow-md',
            disabled && 'opacity-60',
          )}
        >
          {hasAttachments && (
            <div className="flex flex-wrap gap-2 px-1.5 pt-1.5">
              {fileAttachments.map((a) => (
                <RagFileRow
                  key={a.id}
                  backendUrl={backendUrl!}
                  sessionId={effectiveSessionId!}
                  file={a.file}
                  rowId={a.id}
                  onStatusChange={handleFileRowStatusChange}
                  onRemove={() => removeFileAttachment(a.id)}
                />
              ))}
              {textAttachments.map((a) => (
                <PastedTextChip key={a.id} text={a.text} onRemove={() => removeTextAttachment(a.id)} />
              ))}
            </div>
          )}

          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onPaste={handlePaste}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask a question to get started…"
            rows={1}
            className="min-h-0 resize-none border-0 bg-transparent px-3 py-1.5 text-[0.95rem] leading-6 shadow-none focus-visible:border-0 focus-visible:ring-0"
            disabled={disabled}
          />

          <div className="flex items-center justify-between gap-2 px-1">
            <div className="flex items-center gap-1">
              {canAttach && (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={ACCEPTED_FILE_EXTENSIONS}
                    className="hidden"
                    onChange={(e) => {
                      // Snapshot into a plain array BEFORE clearing the input:
                      // `e.target.files` is a live FileList and `e.target.value = ''`
                      // empties it synchronously, so a reference captured first
                      // would already be empty by the time it's read.
                      const picked = e.target.files ? Array.from(e.target.files) : [];
                      e.target.value = '';
                      if (picked.length > 0) void handleFilesPicked(picked);
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Attach file"
                    disabled={disabled || resolvingSession}
                    className="size-8 rounded-full"
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                  >
                    {resolvingSession ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-[1.15rem]" />}
                  </Button>
                </>
              )}
              {resolvingSession ? (
                <span className="text-xs text-muted-foreground">Starting session…</span>
              ) : anyFileProcessing ? (
                <span className="text-xs text-muted-foreground">Processing attachments…</span>
              ) : attachError ? (
                <span className="text-xs text-destructive">{attachError}</span>
              ) : null}
            </div>

            <Button
              type="button"
              size="icon"
              aria-label="Send message"
              className="size-8 rounded-full"
              onClick={(e) => {
                e.stopPropagation();
                submit();
              }}
              disabled={sendDisabled}
            >
              {anyFileProcessing ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-[1.15rem]" />}
            </Button>
          </div>
        </div>

        <p className="mt-1.5 text-center text-[0.7rem] text-muted-foreground">
          Press <kbd className="font-sans font-medium">Enter</kbd> to send,{' '}
          <kbd className="font-sans font-medium">Shift</kbd>+<kbd className="font-sans font-medium">Enter</kbd> for a new
          line
        </p>
      </div>
    </div>
  );
}
