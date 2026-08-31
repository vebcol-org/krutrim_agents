import { AgentThread } from '../components/thread/agent-thread';
import type { AgentScreenContext } from './types';

/**
 * The shared centre pane for every agent-type screen — the live AG-UI thread
 * (`AgentThread`). A screen module that needs a different middle column supplies
 * its own `Center` instead of this; `research` and `default` both use this one
 * and differentiate only via `OutputRenderer` / `turnSplitter`.
 */
export function AgentScreen(ctx: AgentScreenContext) {
  const a = ctx.agent;
  if (!a) return null;
  return (
    <AgentThread
      backendUrl={ctx.backendUrl}
      agent={a.agent}
      sessionId={a.sessionId}
      onOpenSandboxSettings={ctx.onOpenSandboxSettings}
      onOpenModelSettings={ctx.onOpenModelSettings}
      messages={a.messages}
      trace={a.trace}
      narration={a.narration}
      isRunning={a.isRunning}
      error={a.error}
      interrupted={a.interrupted}
      sendMessage={a.sendMessage}
      onStop={a.onStop}
    />
  );
}
