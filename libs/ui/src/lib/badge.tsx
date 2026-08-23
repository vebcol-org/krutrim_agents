import * as React from 'react';
import { type VariantProps, cva } from 'class-variance-authority';

import { cn } from './utils';

export const badgeVariants = cva(
  'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-mono uppercase tracking-wide whitespace-nowrap',
  {
    variants: {
      variant: {
        default: 'border-border bg-secondary text-muted-foreground',
        accent: 'border-primary/40 bg-primary/10 text-primary',
        success: 'border-success/40 bg-success/10 text-success',
        destructive: 'border-destructive/40 bg-destructive/10 text-destructive',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
