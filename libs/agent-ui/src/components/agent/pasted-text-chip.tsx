import { FileText, X } from 'lucide-react';

export interface PastedTextChipProps {
  text: string;
  onRemove: () => void;
}

/** Formats a byte count as the nearest of B/KB/MB, matching how Claude/ChatGPT
 * label their pasted-text attachment cards. */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Claude/ChatGPT-style attachment chip for a large block of pasted text —
 * collapses it out of the textarea so the composer doesn't fill with raw
 * content. Purely a client-side display affordance: the full text is still
 * sent inline as part of the message on send (see `Composer.submit`), it's
 * never RAG-ingested like a real file upload.
 */
export function PastedTextChip({ text, onRemove }: PastedTextChipProps) {
  const lineCount = text.split('\n').length;
  const size = formatSize(new Blob([text]).size);

  return (
    <div className="flex w-56 shrink-0 items-center gap-2 rounded-lg border border-border bg-muted/30 p-2">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
        <FileText className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-mono">Pasted text</p>
        <p className="truncate text-[10px] text-muted-foreground">
          {lineCount} lines · {size}
        </p>
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove pasted text"
        className="shrink-0 text-muted-foreground hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
