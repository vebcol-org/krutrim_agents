import { ChatThread } from '../../components/thread/chat-thread';
import type { AgentScreenContext } from '../types';

/** The built-in plain-chat screen — a thin adapter onto `ChatThread`. */
export function ChatScreen(ctx: AgentScreenContext) {
  const c = ctx.chat;
  if (!c) return null;
  return (
    <ChatThread
      backendUrl={ctx.backendUrl}
      activeChat={c.activeChat}
      sessions={c.sessions}
      activeSessionId={c.activeSessionId}
      historySessionId={c.historySessionId}
      messages={c.messages}
      reasoningByMessageId={c.reasoningByMessageId}
      isLoading={c.isLoading}
      isSending={c.isSending}
      error={c.error}
      onSelectSession={c.onSelectSession}
      onNewSession={c.onNewSession}
      onSend={c.onSend}
      onOpenSandboxSettings={ctx.onOpenSandboxSettings}
      onEnsureSession={c.onEnsureSession}
    />
  );
}
