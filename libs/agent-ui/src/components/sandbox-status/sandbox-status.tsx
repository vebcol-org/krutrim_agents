import type { ContainerStatusEvent } from '@krutrim_agent/shared-types';
import { Badge, type BadgeProps } from '@krutrim_agent/ui';

import { useSseStatus } from '../../hooks';

const STATUS_VARIANT: Record<string, NonNullable<BadgeProps['variant']>> = {
  starting: 'accent',
  running: 'success',
  idle: 'default',
  tearing_down: 'destructive',
  stopped: 'default',
};

export interface SandboxStatusProps {
  /** URL of the Python backend. */
  backendUrl: string;
  /** The container's owner id (usually a session id) to watch, or `null` to show nothing. */
  ownerId: string | null;
}

/**
 * A live status pill for one sandbox container, fed by
 * `GET /api/status/containers/{ownerId}` (SSE). Renders nothing until the
 * first event arrives or when there's no `ownerId` to watch — this is the
 * minimum illustrative slice of a live-status UI (see the pending migration
 * plan), not a polished status dashboard.
 */
export function SandboxStatus({ backendUrl, ownerId }: SandboxStatusProps) {
  const url = ownerId ? `${backendUrl}/api/status/containers/${ownerId}` : null;
  const status = useSseStatus<ContainerStatusEvent>(url);

  if (!ownerId || !status) return null;

  return (
    <Badge variant={STATUS_VARIANT[status.status] ?? 'default'} className="gap-1.5">
      <span className="size-1.5 rounded-full bg-current" />
      {status.status.replace(/_/g, ' ')}
      {typeof status.ref_count === 'number' && status.ref_count > 1 ? ` (${status.ref_count})` : ''}
    </Badge>
  );
}
