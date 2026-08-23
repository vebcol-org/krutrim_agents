import { isTauri } from '@tauri-apps/api/core';

/**
 * True when running inside the Tauri desktop shell, false in the plain
 * browser (web app). Lets shared code (e.g. `agent-ui`) branch on desktop
 * vs. web without every consumer importing `@tauri-apps/api` directly.
 */
export function isTauriRuntime(): boolean {
  return isTauri();
}
