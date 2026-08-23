import { createContext, type ReactNode } from 'react';

import {
  type AgentVisibilityFilter,
  type AuthProvider,
  type ExtensionHooks,
  NOOP_AUTH_PROVIDER,
  NOOP_VISIBILITY_FILTER,
} from './types';

export interface ExtensionContextValue {
  authProvider: AuthProvider;
  visibilityFilter: AgentVisibilityFilter;
}

export const ExtensionContext = createContext<ExtensionContextValue>({
  authProvider: NOOP_AUTH_PROVIDER,
  visibilityFilter: NOOP_VISIBILITY_FILTER,
});

export interface ExtensionProviderProps {
  hooks?: ExtensionHooks;
  children: ReactNode;
}

/**
 * Wraps `children` with whatever security hooks this app supplies. Omit
 * `hooks` (or any field on it) for the community no-op default.
 */
export function ExtensionProvider({ hooks, children }: ExtensionProviderProps) {
  const value: ExtensionContextValue = {
    authProvider: hooks?.authProvider ?? NOOP_AUTH_PROVIDER,
    visibilityFilter: hooks?.visibilityFilter ?? NOOP_VISIBILITY_FILTER,
  };
  return <ExtensionContext.Provider value={value}>{children}</ExtensionContext.Provider>;
}
