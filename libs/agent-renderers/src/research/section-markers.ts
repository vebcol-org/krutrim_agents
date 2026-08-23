/**
 * TypeScript port of `backend/libs/krutrim_agents_core/src/krutrim_agents_core/format/markdown_parser.py`
 * — that module's own docstring notes it has "no third-party dependencies...
 * matching the spec's intent that this pattern be trivially portable to any
 * backend language/runtime." Content already sits in the browser as the
 * final assistant message text, so this parses/strips client-side rather
 * than round-tripping to the backend.
 *
 * Covers the pieces a frontend renderer needs from
 * `backend/harness/prompts/format/markdown/markdown-spec.md` Section 0: the
 * `<!-- sec:id=... -->` / `<!-- /sec:id=... -->` marker pair (for a TOC/nav),
 * plus the two other comment conventions defined elsewhere in that spec —
 * `<!-- width:NN% -->` (Section 4, image sizing) and `<!-- repeat-header -->`
 * (Section 2, print-only table hint) — which are unrelated to `sec:id` but
 * need the same "strip before rendering" treatment.
 */

export interface SectionNode {
  id: string;
  level: number;
  parent: string | null;
  title: string;
  children: SectionNode[];
}

const OPEN_MARKER_RE =
  /<!--\s*sec:id=(?<id>[\w.-]+)\s+level=(?<level>\d+)(?:\s+parent=(?<parent>[\w.-]+))?\s+title="(?<title>[^"]*)"\s*-->/g;

const ANY_SEC_MARKER_RE = /^[ \t]*<!--\s*\/?sec:id=[\w.-]+[^>]*-->[ \t]*\n?/gm;

const REPEAT_HEADER_RE = /^[ \t]*<!--\s*repeat-header\s*-->[ \t]*\n?/gm;

const WIDTH_HINT_IMAGE_RE = /<!--\s*width:\s*(\d+)%\s*-->\s*\n!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

/** Mirrors `parse_document_tree` — scans every opening marker in document
 * order and reconstructs the section tree. A section whose declared parent
 * id doesn't exist is promoted to root (matches the Python default's
 * non-strict behavior — a frontend renderer should degrade gracefully on a
 * malformed document, not throw). */
export function parseDocumentTree(md: string): SectionNode[] {
  const nodes = new Map<string, SectionNode>();
  const order: string[] = [];

  for (const match of md.matchAll(OPEN_MARKER_RE)) {
    const groups = match.groups as { id: string; level: string; parent?: string; title: string };
    if (nodes.has(groups.id)) continue; // duplicate id — keep the first, matches non-strict tolerance
    nodes.set(groups.id, {
      id: groups.id,
      level: Number(groups.level),
      parent: groups.parent ?? null,
      title: groups.title,
      children: [],
    });
    order.push(groups.id);
  }

  const roots: SectionNode[] = [];
  for (const id of order) {
    const node = nodes.get(id)!;
    const parent = node.parent ? nodes.get(node.parent) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

/** Mirrors `flatten_tree` — document-order flat list, e.g. for a flat nav. */
export function flattenTree(nodes: SectionNode[]): SectionNode[] {
  const flat: SectionNode[] = [];
  for (const node of nodes) {
    flat.push(node);
    flat.push(...flattenTree(node.children));
  }
  return flat;
}

/** Mirrors `strip_section_markers` — removes every `sec:id` open/close
 * marker line. These are a frontend/backend contract only and must never
 * reach the rendered output (spec Section 0.5). */
export function stripSectionMarkers(md: string): string {
  return md.replace(ANY_SEC_MARKER_RE, '');
}

/** `<!-- repeat-header -->` (spec Section 2) is a print/export-only hint —
 * browsers don't paginate, so there's no rendering equivalent. Stripped
 * silently rather than left as a stray HTML comment in the output. */
function stripRepeatHeaderHints(md: string): string {
  return md.replace(REPEAT_HEADER_RE, '');
}

/** `<!-- width:NN% -->` directly above an image (spec Section 4) has no
 * native markdown sizing syntax — rewritten here into an inline
 * `<img width="NN%">` tag, which `ReactMarkdown` renders as real HTML given
 * `rehype-raw` (see `research/renderer.tsx`). */
function applyImageWidthHints(md: string): string {
  return md.replace(WIDTH_HINT_IMAGE_RE, (_match, width: string, alt: string, src: string) => {
    const safeAlt = alt.replace(/"/g, '&quot;');
    return `<img src="${src}" alt="${safeAlt}" width="${width}%" />`;
  });
}

/** Full pre-render pass: parse the section tree (before anything is
 * stripped, since the tree needs the markers), then strip every marker
 * comment convention and apply the width-hint rewrite, returning clean
 * markdown ready for `ReactMarkdown`. */
export function prepareResearchMarkdown(md: string): { tree: SectionNode[]; content: string } {
  const tree = parseDocumentTree(md);
  let content = stripSectionMarkers(md);
  content = stripRepeatHeaderHints(content);
  content = applyImageWidthHints(content);
  return { tree, content };
}
