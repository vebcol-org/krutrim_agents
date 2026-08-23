import { DefaultRenderer } from '../default-renderer';
import type { AgentRendererProps } from '../types';

/** Outreach drafts are plain markdown — reuses the built-in renderer as-is. */
export function SalesRenderer(props: AgentRendererProps) {
  return <DefaultRenderer {...props} />;
}
