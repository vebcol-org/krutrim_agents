import type { AgentScreenContext } from '../types';

/** Shown when nothing is open (the `/` route). Static — no context needed. */
export function HomeScreen(_ctx: AgentScreenContext) {
  return (
    <main className="flex min-w-0 flex-1 flex-col items-center justify-center gap-3 bg-background p-8 text-center">
      <h1 className="font-mono text-lg font-semibold text-foreground">Krutrim Agents</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        Pick a chat or an agent from the sidebar, or start a new one with the{' '}
        <span className="font-mono text-foreground">+</span> button.
      </p>
    </main>
  );
}
