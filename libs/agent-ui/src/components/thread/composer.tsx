import { useLayoutEffect, useRef, useState } from 'react';
import { randomUUID } from '@ag-ui/client';
import { Button, cn, Textarea } from '@krutrim_agent/ui';
import { ArrowUp, Loader2, Plus, Square } from 'lucide-react';

import { PastedTextChip } from './pasted-text-chip';

/** Kept in sync with `krutrim_agent_doc`'s registered parsers
 * (`plain_text.py`, `docling/pdf.py`, `docling/docx.py`). */
const ACCEPTED_FILE_EXTENSIONS = '.txt,.md,.pdf,.docx';

/** A paste past this length collapses into a `PastedTextChip` instead of
 * filling the textarea with raw content — matches Claude/ChatGPT's UX. */
const LARGE_PASTE_THRESHOLD_CHARS = 1500;

/** Auto-grow ceiling for the textarea, in px. */
const MAX_TEXTAREA_HEIGHT = 200;

interface TextAttachment {
  id: string;
  text: string;
}

export interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
  /** Rendered in the bottom-left controls row (e.g. a session model picker). */
  leftSlot?: React.ReactNode;
  /** When true (and `onStop` is set) the send button becomes a stop button that
   * stays enabled while `disabled` is true. */
  isRunning?: boolean;
  onStop?: () => void;
  /** Backend base URL + active session id — required to enable file attachments
   * (they upload through the RAG ingestion pipeline). Omit / pass a null
   * `sessionId` to hide the attach button. */
  backendUrl?: string;
  sessionId?: string | null;
  /** Lazily creates (and returns) a session id when there isn't one yet — lets a
   * file be attached on a brand-new chat before its first message. */
  ensureSession?: () => Promise<string | null>;
  /** Hands picked files up to the owner (`useSessionFiles`); the composer no
   * longer tracks attachment state itself. */
  onAddFiles?: (files: File[]) => void;
  /** Fired right after files are handed up, so the owner can expand the bar. */
  onFilesAdded?: () => void;
}

export function Composer({
  disabled,
  onSend,
  leftSlot,
  isRunning,
  onStop,
  backendUrl,
  sessionId,
  ensureSession,
  onAddFiles,
  onFilesAdded,
}: ComposerProps) {
  const [value, setValue] = useState('');
  const [textAttachments, setTextAttachments] = useState<TextAttachment[]>([]);
  // A session id resolved on demand via `ensureSession`, kept so later uploads
  // reuse it before the parent's own `sessionId` prop catches up.
  const [lazySessionId, setLazySessionId] = useState<string | null>(null);
  const [resolvingSession, setResolvingSession] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const effectiveSessionId = sessionId ?? lazySessionId;
  const canAttach = Boolean(backendUrl && onAddFiles && (effectiveSessionId || ensureSession));

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  /** Resolves a session first (a new chat has none until its first message) so
   * every upload can go to a real `POST /api/sessions/{id}/rag/file`. */
  async function handleFilesPicked(files: File[]) {
    if (files.length === 0 || !onAddFiles) return;
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
    onAddFiles(files);
    onFilesAdded?.();
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
    if (disabled) return;
    const combined = [value.trim(), ...textAttachments.map((a) => a.text)].filter(Boolean).join('\n\n');
    if (!combined) return;
    onSend(combined);
    setValue('');
    setTextAttachments([]);
  }

  const hasText = value.trim().length > 0 || textAttachments.length > 0;
  const sendDisabled = disabled || !hasText;
  const showStop = Boolean(isRunning && onStop);

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
          {textAttachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-1.5 pt-1.5">
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
              ) : attachError ? (
                <span className="text-xs text-destructive">{attachError}</span>
              ) : (
                leftSlot && (
                  <div onClick={(e) => e.stopPropagation()} className="flex items-center">
                    {leftSlot}
                  </div>
                )
              )}
            </div>

            {showStop ? (
              <Button
                type="button"
                size="icon"
                aria-label="Stop generating"
                className="size-8 rounded-full"
                onClick={(e) => {
                  e.stopPropagation();
                  onStop?.();
                }}
              >
                <Square className="size-[0.9rem] fill-current" />
              </Button>
            ) : (
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
                <ArrowUp className="size-[1.15rem]" />
              </Button>
            )}
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
