import * as React from 'react';

import { cn } from './utils';

export interface TimelineItemData {
  id: string;
  label: React.ReactNode;
  detail?: React.ReactNode;
  status: 'pending' | 'active' | 'done';
}

export interface TimelineProps extends React.HTMLAttributes<HTMLOListElement> {
  items: TimelineItemData[];
}

const STATUS_DOT: Record<TimelineItemData['status'], string> = {
  pending: 'bg-muted-foreground/40',
  active: 'animate-pulse bg-primary',
  done: 'bg-success',
};

/** Generic ordered-step visual primitive — a status dot per item, optional
 * expandable detail. Used for agent tool-call/step traces and multi-stage
 * ingestion progress; kept detail-agnostic (no specific renderer/domain
 * knowledge) so it's reusable beyond the research profile. */
export function Timeline({ items, className, ...props }: TimelineProps) {
  return (
    <ol className={cn('space-y-1', className)} {...props}>
      {items.map((item) => (
        <TimelineRow key={item.id} item={item} />
      ))}
    </ol>
  );
}

function TimelineRow({ item }: { item: TimelineItemData }) {
  const [expanded, setExpanded] = React.useState(false);
  const hasDetail = item.detail != null && item.detail !== '';

  return (
    <li className="flex gap-2">
      <span className={cn('mt-1.5 size-2 shrink-0 rounded-full', STATUS_DOT[item.status])} aria-hidden />
      <div className="min-w-0 flex-1">
        <button
          type="button"
          disabled={!hasDetail}
          onClick={() => setExpanded((v) => !v)}
          className={cn(
            'w-full truncate text-left font-mono text-xs text-foreground',
            hasDetail && 'cursor-pointer hover:text-primary',
          )}
        >
          {item.label}
        </button>
        {hasDetail && expanded && (
          <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted p-2 text-[0.68rem] whitespace-pre-wrap text-muted-foreground">
            {item.detail}
          </pre>
        )}
      </div>
    </li>
  );
}
