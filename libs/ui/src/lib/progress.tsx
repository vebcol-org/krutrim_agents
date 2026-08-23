import * as React from 'react';

import { cn } from './utils';

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number;
  max?: number;
  label?: React.ReactNode;
}

/** Simple determinate progress bar — used for RAG-ingestion stage progress
 * (`research/rag-upload-panel.tsx`) and reusable anywhere else a "step N of
 * M" indicator is needed. */
export function Progress({ value, max = 100, label, className, ...props }: ProgressProps) {
  const pct = max <= 0 ? 0 : Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={cn('w-full', className)} {...props}>
      {label != null && <div className="mb-1 font-mono text-xs text-muted-foreground">{label}</div>}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
