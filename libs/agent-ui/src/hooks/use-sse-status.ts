import { useEffect, useState } from 'react';

/**
 * Subscribes to a backend SSE endpoint (`GET /api/status/...` — see
 * `krutrim_agent_backend/api/status_routes.py`) and returns the most recently
 * received JSON payload, or `null` before the first event / whenever `url`
 * is `null` (pass `null` to disable the subscription entirely, e.g. when
 * there's no active session to watch yet).
 *
 * `EventSource` auto-reconnects on transient errors on its own — there's
 * nothing for this hook to do beyond letting the browser retry; a
 * persistently-down backend just means the last-known status keeps showing.
 */
export function useSseStatus<T>(url: string | null): T | null {
  const [status, setStatus] = useState<T | null>(null);

  useEffect(() => {
    setStatus(null);
    if (!url) return;

    const source = new EventSource(url);
    source.onmessage = (event) => {
      try {
        setStatus(JSON.parse(event.data) as T);
      } catch {
        // Malformed payload — ignore, keep the last-known-good status. A
        // live stream should degrade gracefully on one bad frame rather
        // than tear down the subscription (see `schemas.ts`'s note on why
        // SSE payloads aren't validated as strictly as REST responses).
      }
    };

    return () => source.close();
  }, [url]);

  return status;
}
