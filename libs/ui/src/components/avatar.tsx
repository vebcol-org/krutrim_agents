import * as React from 'react';
import * as AvatarPrimitive from '@radix-ui/react-avatar';

import { cn } from '../lib/utils';

export interface AvatarProps extends React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Root> {
  label: string;
  /** Optional image; falls back to initials from `label` if unset or unable to load. */
  src?: string;
}

/** Circular avatar — shows `src` when it loads, otherwise the initials of `label`. */
export const Avatar = React.forwardRef<React.ElementRef<typeof AvatarPrimitive.Root>, AvatarProps>(
  ({ label, src, className, ...props }, ref) => {
    const initials = label
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');

    return (
      <AvatarPrimitive.Root
        ref={ref}
        className={cn(
          'flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary font-mono text-xs font-medium text-primary-foreground',
          className,
        )}
        {...props}
      >
        {src && <AvatarPrimitive.Image src={src} alt={label} className="size-full object-cover" />}
        <AvatarPrimitive.Fallback delayMs={src ? 300 : undefined}>{initials || '?'}</AvatarPrimitive.Fallback>
      </AvatarPrimitive.Root>
    );
  },
);
Avatar.displayName = 'Avatar';
