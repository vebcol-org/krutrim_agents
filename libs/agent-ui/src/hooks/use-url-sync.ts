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
 * - `/agent/:agentId`                     — agent, its most recent session
 * - `/agent/:agentId/session/:sessionId`  — agent, that session (resumed on a
 *   cold link / reload when it still exists; otherwise falls back to the most
 *   recent one and the URL is rewritten to match)
 *
 * The two effects guard against echoing each other with `settledPathRef`: each
 * records the path it just drove to / applied from, and bails if the other
 * effect is merely observing that same value.
 *
 * Cold-load ordering: the URL→state effect waits for `workspace.hasLoaded`
 * before it can resolve an agent/chat id, and the state→URL effect refuses to
 * navigate while `selection` hasn't caught up to the id in the address bar —
 * without that guard a deep link is bounced to `/` in the gap before the
 * workspace fetch resolves.
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
  // Who last drove `settledPathRef`. `'url'` — the URL→state effect is resolving
  // that path and `selection` may not have caught up yet, so the state→URL
  // effect must NOT navigate (its `desiredPath` would be `/` or stale and would
  // bounce a valid deep link). `'state'` — the path came from `selection`, which
  // is the source of truth, so state→URL may drive freely.
  const settledFromRef = useRef<'url' | 'state' | null>(null);

  const { selection, hasLoaded, selectChat, openAgent } = workspace;
  const { historySessionId, openChatAt, selectSession } = chat;

  /** Does `selection` already point at whatever the URL names? (also true for `/`) */
  const selectionMatches = (route: ParsedRoute): boolean =>
    route.kind === 'none' ||
    (route.kind === 'agent' && selection?.kind === 'agent' && selection.agentId === route.agentId) ||
    (route.kind === 'chat' && selection?.kind === 'chat' && selection.chatId === route.chatId);

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
    // Can't resolve an agent/chat id until the workspace tree is in memory —
    // this re-runs once `hasLoaded` flips (it's in the dep list) to adopt then.
    if (!hasLoaded) return;

    const path = location.pathname;
    const route = parseRoute(path);
    // Adopt a genuinely new path, or retry one recorded earlier that never
    // applied (workspace was still loading). Skip only when it's applied *and*
    // `selection` already agrees.
    if (path === settledPathRef.current && selectionMatches(route)) return;
    settledPathRef.current = path;
    settledFromRef.current = 'url';

    if (route.kind === 'chat') {
      const sameChat = selection?.kind === 'chat' && selection.chatId === route.chatId;
      if (!sameChat) {
        selectChat(route.chatId);
        openChatAt(route.chatId, route.sessionId);
      } else if (route.sessionId && route.sessionId !== historySessionId) {
        selectSession(route.sessionId);
      }
    } else if (route.kind === 'agent') {
      const currentSessionId = selection?.kind === 'agent' ? selection.sessionId : null;
      const sameAgent = selection?.kind === 'agent' && selection.agentId === route.agentId;
      if (!sameAgent || (route.sessionId && route.sessionId !== currentSessionId)) {
        openAgent(route.agentId, route.sessionId);
      }
    }
    // route.kind === 'none' → leave whatever's open as-is.
    // Deps are deliberately narrow: URL changes + the one-shot `hasLoaded` flip;
    // the reverse direction is the effect below.
  }, [location.pathname, hasLoaded]);

  // Hand ownership back to state->URL once the URL->state adoption has produced
  // a `selection` (matching the URL, or the user has since moved elsewhere) —
  // from here on, `selection` changes are user-initiated and drive the URL.
  useEffect(() => {
    if (settledFromRef.current === 'url' && (selectionMatches(parseRoute(location.pathname)) || selection)) {
      settledFromRef.current = 'state';
    }
  }, [selection, location.pathname]);

  // state -> URL: selecting a chat/agent, switching or creating a session.
  useEffect(() => {
    if (desiredPath === location.pathname || desiredPath === settledPathRef.current) return;
    // Only drive the URL once `selection` is the acknowledged source of truth.
    // While the URL→state effect is still adopting a deep link (`'url'`), or
    // before anything has settled at all (`null`), `desiredPath` is `/` or stale
    // and navigating here would clobber the incoming link (usually to `/`).
    if (settledFromRef.current !== 'state') return;
    settledPathRef.current = desiredPath;
    settledFromRef.current = 'state';
    navigate(desiredPath);
  }, [desiredPath, location.pathname, navigate]);
}
