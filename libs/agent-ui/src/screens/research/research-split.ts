import type { AgentTurnSplitter } from '../types';

/**
 * The research agent is told (see `backend/.../profiles/research/prompts.py`,
 * `_FINAL_ANSWER_PROTOCOL`) to write its working narration, then a single
 * marker line, then the report:
 *
 *     …planning / progress notes…
 *     ===FINAL_REPORT===
 *     # The Report
 *     …markdown following the export spec…
 *
 * Everything before the marker is the middle-column work log; everything after
 * is the deliverable the `ResearchRenderer` sections and renders. Kept
 * byte-for-byte in sync with the backend prompt marker.
 */
export const FINAL_REPORT_MARKER = '===FINAL_REPORT===';

/** Tolerant: 2+ `=`, optional spaces, `FINAL REPORT` / `FINAL_REPORT`. */
const MARKER_RE = /^[ \t]*={2,}[ \t]*FINAL[ _]REPORT[ \t]*={2,}[ \t]*$/im;

/**
 * Strips control scaffolding a weaker model leaks into its answer: a stray
 * `===FINAL_REPORT===` line, pseudo-XML wrappers (`<user_message>`, `<answer>`,
 * `<final_report>`, `<spec …>`, `<function_call>`), a leading decision-contract
 * block (`decision:` / `reason:` / …), and any line that is only a lone
 * `<tag>` / `</tag>`. `<!-- sec:id=… -->` section comments are deliberately
 * left in place — `prepareResearchMarkdown` consumes them for the TOC.
 */
export function sanitizeResearchReport(md: string): string {
  let out = md;
  out = out.replace(MARKER_RE, '');
  out = out.replace(/^[ \t]*<\/?[a-z_][\w-]*(?:\s[^>\n]*)?>[ \t]*$/gim, '');
  out = out.replace(
    /<\/?(?:user_message|answer|spec|function_call|decision|research_context|thinking|final_report|report)\b[^>]*>/gi,
    '',
  );
  out = out.replace(
    /^\s*(?:\*\*)?(?:decision|reason|user_message|research_instruction)(?:\*\*)?\s*:[\s\S]*?\n\s*\n/i,
    '',
  );
  return out.replace(/\n{3,}/g, '\n\n').trim();
}

export const researchSplitTurn: AgentTurnSplitter = (text, { finished, title }) => {
  const match = MARKER_RE.exec(text);

  let narration: string;
  let reportSource: string | null;
  if (match) {
    narration = text.slice(0, match.index).trimEnd();
    reportSource = text.slice(match.index + match[0].length).replace(/^\s+/, '');
  } else if (finished) {
    // Ended normally but never emitted the marker (a model that ignored the
    // protocol): treat the whole turn as the report.
    narration = '';
    reportSource = text;
  } else {
    // Still streaming, or stopped before the report — keep it all in the log.
    narration = text;
    reportSource = null;
  }

  const narrationClean = sanitizeResearchReport(narration);
  const reportClean = reportSource == null ? '' : sanitizeResearchReport(reportSource);
  return {
    narration: narrationClean,
    output: reportClean ? { kind: 'markdown', title, content: reportClean } : null,
  };
};
