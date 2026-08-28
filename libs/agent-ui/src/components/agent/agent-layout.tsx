import { useState } from 'react';
import type { Agent } from '@krutrim_agent/shared-types';

import { useAgentChat, useChat, useChatStream, useUrlSync, useWorkspace } from '../../hooks';
import { clamp, deriveRenderPayload } from '../../utils';
import { AgentThread } from '../agent-thread';
import { SandboxSettingsPanel, type SandboxSettingsTarget } from '../sandbox-settings-panel';
import type { AgentProps } from './agent';
import { ChatThread } from './chat-thread';
import { HistoryRail } from './history-rail';
import { OutputPanel } from './output-panel';
import { ResizeHandle } from './resize-handle';

const OUTPUT_MIN_WIDTH = 320;
const OUTPUT_MAX_WIDTH = 720;
const OUTPUT_DEFAULT_WIDTH = 420;

/**
 * 3-column shell (history rail / conversation / output). The history rail
 * is a `Project -> (Agent | Chat) -> Session` tree (`useWorkspace`,
 * `../../store/workspace-slice.ts`); the center pane renders either
 * `ChatThread` (the REST `chat` flow — `useChat`, `../../store/chat-slice.ts`)
 * or `AgentThread` (the live AG-UI streaming flow — `useAgentChat`)
 * depending on what's selected in the tree.
 */
export function AgentLayout({ backendUrl }: AgentProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [outputCollapsed, setOutputCollapsed] = useState(true);
  const [outputWidth, setOutputWidth] = useState(OUTPUT_DEFAULT_WIDTH);
  const [sandboxSettingsOpen, setSandboxSettingsOpen] = useState(false);

  const workspace = useWorkspace({ backendUrl });
  const chat = useChat({ backendUrl });
  const chatStream = useChatStream({ backendUrl });

  // Keeps the address bar in step with the open chat/agent + session.
  useUrlSync({ workspace, chat });

  const allChats = [...workspace.standaloneChats, ...Object.values(workspace.chatsByProject).flat()];
  const activeChat = chat.activeChatId ? (allChats.find((c) => c.chat_id === chat.activeChatId) ?? null) : null;

  const selection = workspace.selection;
  let activeAgent: Agent | null = null;
  let activeAgentProjectId: string | null = null;
  if (selection?.kind === 'agent') {
    for (const project of workspace.projects) {
      const found = workspace.agentsByProject[project.project_id]?.find((a) => a.agent_id === selection.agentId);
      if (found) {
        activeAgent = found;
        activeAgentProjectId = project.project_id;
        break;
      }
    }
  }

  const activeSession = chat.sessions.find((s) => s.session_id === chat.activeSessionId) ?? null;

  const activeAgentSessionId = selection?.kind === 'agent' ? selection.sessionId : null;
  // Lifted here (rather than inside `AgentThread`) so `OutputPanel`, a
  // sibling, can derive its canvas payload from the same live message list.
  const agentChat = useAgentChat({
    backendUrl,
    agentId: activeAgent?.agent_id ?? '',
    sessionId: activeAgent ? activeAgentSessionId : null,
  });
  const outputPayload = activeAgent ? deriveRenderPayload(agentChat.messages, activeAgent.display_name) : null;

  // Agent-owned session details aren't tracked here yet (the AG-UI client that will actually
  // need them is a later pass) — so an Agent's sandbox settings only cover its own
  // owner-level policy for now, not a specific session's, even though `selection.sessionId`
  // exists. `SessionPolicySection` is skipped in that case (see `SandboxSettingsPanel`).
  let sandboxTarget: SandboxSettingsTarget | null = null;
  if (activeAgent && activeAgentProjectId) {
    sandboxTarget = { kind: 'agent', agent: activeAgent, projectId: activeAgentProjectId };
  } else if (activeChat) {
    sandboxTarget = { kind: 'chat', chat: activeChat };
  }
  const sessionForPanel = sandboxTarget?.kind === 'chat' ? activeSession : null;
  const siblingSessionsForPanel = sandboxTarget?.kind === 'chat' ? chat.sessions : [];

  return (
    <div className="flex h-screen bg-background text-foreground">
      <HistoryRail
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        workspace={workspace}
        onOpenChatSession={chat.selectChat}
      />

      {activeAgent ? (
        <AgentThread
          backendUrl={backendUrl}
          agent={activeAgent}
          sessionId={activeAgentSessionId}
          onOpenSandboxSettings={() => setSandboxSettingsOpen(true)}
          messages={agentChat.messages}
          reasoningByMessageId={agentChat.reasoningByMessageId}
          isRunning={agentChat.isRunning}
          error={agentChat.error}
          sendMessage={agentChat.sendMessage}
        />
      ) : (
        <ChatThread
          backendUrl={backendUrl}
          activeChat={activeChat}
          sessions={chat.sessions}
          activeSessionId={chat.activeSessionId}
          historySessionId={chat.historySessionId}
          messages={chatStream.messages}
          reasoningByMessageId={chatStream.reasoningByMessageId}
          isLoading={chat.isLoading}
          isSending={chatStream.isRunning}
          error={chat.error ?? chatStream.error}
          onSelectSession={chat.selectSession}
          onNewSession={chat.startNewSession}
          onSend={chatStream.sendMessage}
          onOpenSandboxSettings={() => setSandboxSettingsOpen(true)}
          onEnsureSession={chat.ensureSession}
        />
      )}

      {!outputCollapsed && (
        <ResizeHandle
          onResize={(deltaX) => setOutputWidth((w) => clamp(w - deltaX, OUTPUT_MIN_WIDTH, OUTPUT_MAX_WIDTH))}
          onReset={() => setOutputWidth(OUTPUT_DEFAULT_WIDTH)}
        />
      )}
      <OutputPanel
        collapsed={outputCollapsed}
        onToggle={() => setOutputCollapsed((v) => !v)}
        width={outputWidth}
        agentKey={activeAgent?.agent_key ?? null}
        payload={outputPayload}
        trace={agentChat.trace}
      />

      {sandboxSettingsOpen && sandboxTarget && (
        <SandboxSettingsPanel
          backendUrl={backendUrl}
          target={sandboxTarget}
          session={sessionForPanel}
          siblingSessions={siblingSessionsForPanel}
          onClose={() => setSandboxSettingsOpen(false)}
        />
      )}
    </div>
  );
}
