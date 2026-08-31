import { Provider } from 'react-redux';
import { ThemeProvider } from '@krutrim_agent/ui';
import { ExtensionProvider, type ExtensionHooks } from '@krutrim_agent/extensions';

import { store } from '../../store/store';
import { AgentLayout } from './agent-layout';

export interface AgentProps {
  /** URL of the Python backend. */
  backendUrl: string;
  /**
   * Security-hook overrides (auth provider, agent-visibility filter) — a
   * consuming app supplies its own here. Omit for the community default
   * (no-op hooks, matching the backend's own no-op defaults exactly). This
   * is the only prop a consuming app needs to fork nothing else in this
   * package for — see `@krutrim_agent/extensions`.
   */
  extensions?: ExtensionHooks;
}

/**
 * Sole top-level product — owns its own Redux `Provider`, `ThemeProvider`,
 * and `ExtensionProvider`. The actual 3-column shell (history rail /
 * conversation / output) lives in `AgentLayout`; this component exists
 * purely to wire up the providers it needs, so `AgentLayout` itself stays a
 * plain consumer of Redux/theme/extension context rather than owning its
 * own instance of any of them.
 */
export function Agent({ backendUrl, extensions }: AgentProps) {
  return (
    <Provider store={store}>
      <ThemeProvider>
        <ExtensionProvider hooks={extensions}>
          <AgentLayout backendUrl={backendUrl} />
        </ExtensionProvider>
      </ThemeProvider>
    </Provider>
  );
}
