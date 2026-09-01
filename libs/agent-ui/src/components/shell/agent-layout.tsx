import { useEffect, useRef, useState } from 'react';
import type { Agent } from '@krutrim_agent/shared-types';

import { useAgentChat, useAgentHistory, useChat, useChatStream, useUrlSync, useWorkspace } from '../../hooks';
import { getScreen } from '../../screens/registry';
import type { AgentScreenContext } from '../../screens/types';
import { clamp, deriveAssistantTurn } from '../../utils';
import { SandboxSettingsPanel, type SandboxSettingsTarget } from '../panels/sandbox-settings-panel';
import { SettingsPanel } from '../panels/settings-panel';
import type { AgentProps } from './agent';
import { HistoryRail } from './history-rail';
import { OutputPanel } from './output-panel';
import { ResizeHandle } from './resize-handle';

const OUTPUT_MIN_WIDTH = 520;
const OUTPUT_MAX_WIDTH = 920;
const OUTPUT_DEFAULT_WIDTH = 420;

/**
 * The 3-column shell (history rail / centre / output). The rail is a
 * `Project -> (Agent | Chat) -> Session` tree; the centre and the output panel
 * are supplied by the **screen** resolved from what's selected —
 * `getScreen('home' | 'chat' | <agent_key>)` (see `../../screens/`). This
 * component owns every hook and hands each screen the slice of state it needs
 * via `AgentScreenContext`.
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
  const agentChat = useAgentChat({
    backendUrl,
    agentId: activeAgent?.agent_id ?? '',
    sessionId: historyReady ? activeAgentSessionId : null,
    initialMessages: agentHistory.messages,
  });

  // Which screen fills the centre + output columns.
  const screenKey =
    selection?.kind === 'agent'
      ? (activeAgent?.agent_key ?? 'default')
      : selection?.kind === 'chat'
        ? 'chat'
        : 'home';
  const screen = getScreen(screenKey);
  const isAgentScreen = selection?.kind === 'agent';

  // The latest assistant turn is divided by the screen's own splitter (see
  // `screens/<key>/` — `research` splits on `===FINAL_REPORT===`) into
  // `narration` (middle work-log column) and `output` (the output panel).
  // `turnFinished` gates the fallback where a marker-less turn that *ended
  // normally* is taken as the finished output — while streaming, or after a Stop
  // / a reload of a stopped turn, its text stays entirely in the work log
  // instead of masquerading as a finished answer. (`lastAssistantInterrupted`
  // can read stale after a later successful turn, but that turn carries the
  // marker, so the split is correct regardless.)
  const turnFinished =
    !agentChat.isRunning && !agentChat.interrupted && !agentHistory.lastAssistantInterrupted;
  const assistantTurn = deriveAssistantTurn(agentChat.messages, screenKey, activeAgent?.display_name ?? '', {
    finished: turnFinished,
  });
  const outputPayload = isAgentScreen ? assistantTurn.output : null;
  const narration = isAgentScreen ? assistantTurn.narration : '';
  // Live trace while a run is in flight (or once it has produced steps);
  // otherwise the trace rebuilt from the checkpoint so a reload still shows the
  // work log (`useAgentHistory` — tool calls only; steps aren't persisted).
  const trace =
    agentChat.isRunning || agentChat.trace.length > 0 ? agentChat.trace : agentHistory.trace;

  const screenCtx: AgentScreenContext = {
    backendUrl,
    onOpenSandboxSettings: () => setSandboxSettingsOpen(true),
    onOpenModelSettings: () => setModelSettingsOpen(true),
    agent: activeAgent
      ? {
          agent: activeAgent,
          sessionId: activeAgentSessionId,
          messages: agentChat.messages,
          trace,
          narration,
          isRunning: agentChat.isRunning,
          error: agentChat.error,
          interrupted: agentChat.interrupted,
          sendMessage: agentChat.sendMessage,
          onStop: agentChat.stop,
        }
      : undefined,
    chat:
      screenKey === 'chat'
        ? {
            activeChat,
            sessions: chat.sessions,
            activeSessionId: chat.activeSessionId,
            historySessionId: chat.historySessionId,
            messages: chatStream.messages,
            reasoningByMessageId: chatStream.reasoningByMessageId,
            isLoading: chat.isLoading,
            isSending: chatStream.isRunning,
            error: chat.error ?? chatStream.error,
            onSelectSession: chat.selectSession,
            onNewSession: chat.startNewSession,
            onSend: chatStream.sendMessage,
            onEnsureSession: chat.ensureSession,
          }
        : undefined,
  };
  const ScreenCenter = screen.Center;

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

      <ScreenCenter {...screenCtx} />

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
        screen={screen}
        canvasCapable={isAgentScreen}
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
