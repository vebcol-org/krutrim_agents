import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import type { UseChatResult } from './use-chat';
import type { UseWorkspaceResult } from './use-workspace';

/**
 * Two-way binding between the browser URL and what's open in the workspace, so
 * the current chat/agent + session is always visible in the address bar and
 * survives a reload / back-forward.
 *
 * Grammar:
 * - `/`                                   — nothing open
 * - `/chat/:chatId`                       — chat, newest session
 * - `/chat/:chatId/session/:sessionId`    — chat, that session
 * - `/agent/:agentId`                     — agent, its resumed session
 * - `/agent/:agentId/session/:sessionId`  — agent (session segment is
 *   informational for now; opening a specific agent session from a cold link
 *   isn't plumbed yet, so the URL is rewritten to whatever session actually
 *   resumed)
 *
 * The two effects guard against echoing each other with `settledPathRef`: each
 * records the path it just drove to / applied from, and bails if the other
 * effect is merely observing that same value.
 */

type ParsedRoute =
  | { kind: 'none' }
  | { kind: 'chat'; chatId: string; sessionId: string | null }
  | { kind: 'agent'; agentId: string; sessionId: string | null };

function parseRoute(pathname: string): ParsedRoute {
  const seg = pathname.split('/').filter(Boolean);
  if ((seg[0] === 'chat' || seg[0] === 'agent') && seg[1]) {
    const sessionId = seg[2] === 'session' && seg[3] ? seg[3] : null;
    return seg[0] === 'chat'
      ? { kind: 'chat', chatId: seg[1], sessionId }
      : { kind: 'agent', agentId: seg[1], sessionId };
  }
  return { kind: 'none' };
}

export function useUrlSync({ workspace, chat }: { workspace: UseWorkspaceResult; chat: UseChatResult }) {
  const location = useLocation();
  const navigate = useNavigate();
  const settledPathRef = useRef<string | null>(null);

  const { selection, selectChat, openAgent } = workspace;
  const { historySessionId, openChatAt, selectSession } = chat;

  const desiredPath = (() => {
    if (selection?.kind === 'chat') {
      return historySessionId ? `/chat/${selection.chatId}/session/${historySessionId}` : `/chat/${selection.chatId}`;
    }
    if (selection?.kind === 'agent') {
      return selection.sessionId
        ? `/agent/${selection.agentId}/session/${selection.sessionId}`
        : `/agent/${selection.agentId}`;
    }
    return '/';
  })();

  // URL -> state: cold load, back/forward, hand-edited address bar.
  useEffect(() => {
    const path = location.pathname;
    if (path === settledPathRef.current) return;
    settledPathRef.current = path;

    const route = parseRoute(path);
    if (route.kind === 'chat') {
      const sameChat = selection?.kind === 'chat' && selection.chatId === route.chatId;
      if (!sameChat) {
        selectChat(route.chatId);
        openChatAt(route.chatId, route.sessionId);
      } else if (route.sessionId && route.sessionId !== historySessionId) {
        selectSession(route.sessionId);
      }
    } else if (route.kind === 'agent') {
      const sameAgent = selection?.kind === 'agent' && selection.agentId === route.agentId;
      if (!sameAgent) openAgent(route.agentId);
    }
    // route.kind === 'none' → leave whatever's open as-is.
    // Deps are deliberately just `location.pathname`: this effect reacts to URL
    // changes only; the reverse direction is the effect below.
  }, [location.pathname]);

  // state -> URL: selecting a chat/agent, switching or creating a session.
  useEffect(() => {
    if (desiredPath === location.pathname || desiredPath === settledPathRef.current) return;
    settledPathRef.current = desiredPath;
    navigate(desiredPath);
  }, [desiredPath, location.pathname, navigate]);
}
