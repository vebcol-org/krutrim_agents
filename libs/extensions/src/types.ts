/**
 * Frontend mirror of the backend's `krutrim_agent_extensions.contracts` (Python).
 * Community ships all-no-op implementations, matching the backend's own
 * no-op defaults exactly — a consuming app supplies real ones via
 * `<Agent extensions={{ authProvider, visibilityFilter }}>`, nowhere else.
 */

export interface Principal {
  id: string;
  displayName?: string;
}

export const ANONYMOUS_PRINCIPAL: Principal = { id: 'anonymous', displayName: 'Anonymous' };

export interface AuthProvider {
  getPrincipal(): Principal | Promise<Principal>;
  /** Optional: headers to attach to outgoing backend requests (e.g. `Authorization`). */
  getAuthHeaders?(): Record<string, string> | Promise<Record<string, string>>;
}

export interface AgentVisibilityFilter {
  /** `null` means no restriction — every agent key is visible. Mirrors the
   * backend's `AgentVisibilityPolicy.visible_agent_keys`. */
  visibleAgentKeys(principal: Principal): Set<string> | null | Promise<Set<string> | null>;
}

export interface ExtensionHooks {
  authProvider?: AuthProvider;
  visibilityFilter?: AgentVisibilityFilter;
}

export const NOOP_AUTH_PROVIDER: AuthProvider = {
  getPrincipal: () => ANONYMOUS_PRINCIPAL,
};

export const NOOP_VISIBILITY_FILTER: AgentVisibilityFilter = {
  visibleAgentKeys: () => null,
};
