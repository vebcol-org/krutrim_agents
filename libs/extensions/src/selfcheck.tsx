import { useEffect, useState } from 'react';

import { NOOP_AUTH_PROVIDER } from './types';
import { useAuthProvider } from './use-extensions';

interface ExtensionStatusResponse {
  edition: string;
  hooks: Record<string, string>;
  storage_backend: string;
  sandbox_runtime: string;
}

export interface ExtensionSelfCheckProps {
  /** Same backend URL passed to `<Agent backendUrl={...}>`. */
  backendUrl: string;
}

/**
 * Drift detector: cross-checks what this app was configured with (via
 * `<ExtensionProvider hooks={...}>` / `<Agent extensions={...}>`) against
 * what the backend reports at `GET /api/system/extensions`. Renders a
 * persistent, unmissable banner on mismatch — e.g. this app passed a real
 * `AuthProvider` but the backend still reports `edition: "community"`/no-op
 * hooks (or vice versa) — rather than silently operating against a
 * misconfigured backend. Renders nothing when they agree, which includes
 * the common community case (both no-op).
 *
 * Deliberately styled with inline styles, not Tailwind classes — this is a
 * fail-loud alarm banner, so it must render correctly even if the
 * consuming app's Tailwind content-scanning somehow hasn't picked up this
 * package yet (see each package's README for the `@source` requirement).
 */
export function ExtensionSelfCheck({ backendUrl }: ExtensionSelfCheckProps) {
  const authProvider = useAuthProvider();
  const [mismatch, setMismatch] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${backendUrl}/api/system/extensions`)
      .then((res) => (res.ok ? (res.json() as Promise<ExtensionStatusResponse>) : null))
      .then((status) => {
        if (cancelled || !status) return;
        const frontendHasRealAuth = authProvider !== NOOP_AUTH_PROVIDER;
        const backendHasRealAuth = status.hooks['RequestAuthenticator'] !== 'NoOpRequestAuthenticator';
        if (frontendHasRealAuth !== backendHasRealAuth) {
          setMismatch(
            frontendHasRealAuth
              ? 'This app is configured with a real auth provider, but the backend reports no authentication is active.'
              : `The backend reports edition "${status.edition}" with real authentication active, but this app has no auth provider configured.`,
          );
        } else {
          setMismatch(null);
        }
      })
      .catch(() => {
        // Backend unreachable — not this component's job to report connectivity issues.
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, authProvider]);

  if (!mismatch) return null;

  return (
    <div
      role="alert"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        padding: '8px 16px',
        background: '#b3392f',
        color: '#fff6f5',
        fontFamily: 'monospace',
        fontSize: 13,
        textAlign: 'center',
      }}
    >
      Extension configuration drift detected: {mismatch}
    </div>
  );
}
