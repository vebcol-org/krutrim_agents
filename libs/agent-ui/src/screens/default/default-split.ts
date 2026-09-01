import type { AgentTurnSplitter } from '../types';

/**
 * The built-in turn splitter, used for any agent that hasn't registered its
 * own (see `registry.ts`). No concept of a work log — the whole assistant turn
 * is the output. Only a light scaffolding strip (lone pseudo-tag lines, blank
 * run collapsing); anything richer is an agent's own business.
 */
const LONE_TAG_LINE_RE = /^[ \t]*<\/?[a-z_][\w-]*(?:\s[^>\n]*)?>[ \t]*$/gim;

function stripScaffolding(md: string): string {
  return md.replace(LONE_TAG_LINE_RE, '').replace(/\n{3,}/g, '\n\n').trim();
}

export const defaultSplitTurn: AgentTurnSplitter = (text, { title }) => {
  const content = stripScaffolding(text);
  return {
    narration: '',
    output: content ? { kind: 'markdown', title, content } : null,
  };
};
