import { useEffect, useRef } from 'react';

/**
 * Surfaces a background job's status in the browser tab title while the tab
 * is hidden — so a user who switched away while a RAG upload was embedding
 * still notices when it finishes, without this codebase's first use of the
 * Notification API (a bigger UX commitment — a permission prompt, uneven
 * browser support — than the ask; a title-bar change covers "show status on
 * blur" directly).
 *
 * `active` gates whether the title is touched at all — pass `false` once
 * there's nothing left to report so an idle session's tab title is never
 * silently held hostage. `label` is the short status string to prefix the
 * title with (e.g. "● Embedding…" or "✓ Embedding complete").
 */
export function useBlurStatusTitle(active: boolean, label: string | null): void {
  const originalTitle = useRef<string | null>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    if (!active || !label) {
      if (originalTitle.current !== null) {
        document.title = originalTitle.current;
        originalTitle.current = null;
      }
      return;
    }

    if (originalTitle.current === null) {
      originalTitle.current = document.title;
    }

    function applyTitle() {
      if (document.visibilityState === 'hidden' && originalTitle.current !== null) {
        document.title = `${label} — ${originalTitle.current}`;
      }
    }

    applyTitle();
    document.addEventListener('visibilitychange', applyTitle);
    return () => document.removeEventListener('visibilitychange', applyTitle);
  }, [active, label]);

  // Revert on unmount regardless of `active`, so navigating away mid-upload
  // never leaves a stale status in the tab title.
  useEffect(() => {
    return () => {
      if (originalTitle.current !== null && typeof document !== 'undefined') {
        document.title = originalTitle.current;
      }
    };
  }, []);
}
