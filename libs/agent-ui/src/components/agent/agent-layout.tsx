import { useEffect, useRef, useState } from 'react';
import type { Agent } from '@krutrim_agent/shared-types';

import { useAgentChat, useAgentHistory, useChat, useChatStream, useUrlSync, useWorkspace } from '../../hooks';
import { clamp, deriveAssistantTurn } from '../../utils';
import { AgentThread } from '../agent-thread';
import { SandboxSettingsPanel, type SandboxSettingsTarget } from '../sandbox-settings-panel';
import { SettingsPanel } from '../settings-panel';
import type { AgentProps } from './agent';
import { ChatThread } from './chat-thread';
import { HistoryRail } from './history-rail';
import { OutputPanel } from './output-panel';
import { ResizeHandle } from './resize-handle';

const OUTPUT_MIN_WIDTH = 520;
const OUTPUT_MAX_WIDTH = 920;
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
  const [modelSettingsOpen, setModelSettingsOpen] = useState(false);

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
  // The Agent flow is a pure live stream with no store-backed history, so on a
  // page refresh the message list starts empty — load the persisted turns and
  // seed the stream with them (see `useAgentHistory`).
  const agentHistory = useAgentHistory({
    backendUrl,
    sessionId: activeAgent ? activeAgentSessionId : null,
  });
  // Only bind the streaming client once history for THIS session has loaded: the
  // internal `HttpAgent` is memoised on `sessionId` and seeded once, so binding
  // early would build it empty and ignore the late history.
  const historyReady =
    !!activeAgent && !!activeAgentSessionId && agentHistory.loadedSessionId === activeAgentSessionId;
  // Lifted here (rather than inside `AgentThread`) so `OutputPanel`, a
  // sibling, can derive its canvas payload from the same live message list.
  const agentChat = useAgentChat({
    backendUrl,
    agentId: activeAgent?.agent_id ?? '',
    sessionId: historyReady ? activeAgentSessionId : null,
    initialMessages: agentHistory.messages,
  });
  // The latest assistant turn is divided by the agent's own splitter (see
  // `@krutrim_agent/agent-renderers` — `research` splits on `===FINAL_REPORT===`)
  // into `narration` (middle work-log column) and `output` (the output panel).
  // `turnFinished` gates the fallback where a marker-less turn that *ended
  // normally* is taken as the finished output — while streaming, or after a Stop
  // / a reload of a stopped turn, its text stays entirely in the work log
  // instead of masquerading as a finished answer. (`lastAssistantInterrupted`
  // can read stale after a later successful turn, but that turn carries the
  // marker, so the split is correct regardless.)
  const turnFinished =
    !agentChat.isRunning && !agentChat.interrupted && !agentHistory.lastAssistantInterrupted;
  const assistantTurn = deriveAssistantTurn(
    agentChat.messages,
    activeAgent?.agent_key ?? null,
    activeAgent?.display_name ?? '',
    { finished: turnFinished },
  );
  const outputPayload = activeAgent ? assistantTurn.output : null;
  const narration = activeAgent ? assistantTurn.narration : '';
  // Live trace while a run is in flight (or once it has produced steps);
  // otherwise the trace rebuilt from the checkpoint so a reload still shows the
  // work log (`useAgentHistory` — tool calls only; steps aren't persisted).
  const trace =
    agentChat.isRunning || agentChat.trace.length > 0 ? agentChat.trace : agentHistory.trace;

  // Reveal the output explorer automatically once there's assistant output or a
  // run finishes. Never auto-closes; a manual toggle is respected.
  const wasRunningRef = useRef(false);
  useEffect(() => {
    const justFinished = wasRunningRef.current && !agentChat.isRunning;
    wasRunningRef.current = agentChat.isRunning;
    if (outputPayload && (justFinished || agentChat.isRunning)) setOutputCollapsed(false);
  }, [agentChat.isRunning, outputPayload]);

  // A fresh session starts with the explorer tucked away again.
  useEffect(() => {
    setOutputCollapsed(true);
  }, [activeAgentSessionId]);

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
        backendUrl={backendUrl}
        workspace={workspace}
        onOpenChatSession={chat.selectChat}
      />

      {activeAgent ? (
        <AgentThread
          backendUrl={backendUrl}
          agent={activeAgent}
          sessionId={activeAgentSessionId}
          onOpenSandboxSettings={() => setSandboxSettingsOpen(true)}
          onOpenModelSettings={() => setModelSettingsOpen(true)}
          messages={agentChat.messages}
          trace={trace}
          narration={narration}
          isRunning={agentChat.isRunning}
          error={agentChat.error}
          interrupted={agentChat.interrupted}
          sendMessage={agentChat.sendMessage}
          onStop={agentChat.stop}
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
        busy={agentChat.isRunning}
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

      {modelSettingsOpen && activeAgent && (
        <SettingsPanel
          backendUrl={backendUrl}
          agentId={activeAgent.agent_id}
          agentLabel={activeAgent.display_name}
          onClose={() => setModelSettingsOpen(false)}
        />
      )}
    </div>
  );
}
