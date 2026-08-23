import type { SectionNode } from './section-markers';

export interface SectionTocProps {
  tree: SectionNode[];
  activeId?: string | null;
  onSelect: (id: string) => void;
}

function TocNode({ node, activeId, onSelect }: { node: SectionNode; activeId?: string | null; onSelect: (id: string) => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(node.id)}
        className={`block w-full truncate rounded px-2 py-1 text-left font-mono text-xs hover:bg-muted ${
          activeId === node.id ? 'bg-muted text-primary' : 'text-muted-foreground'
        }`}
        title={node.title}
      >
        {node.title}
      </button>
      {node.children.length > 0 && (
        <ul className="ml-3 border-l border-border pl-1">
          {node.children.map((child) => (
            <TocNode key={child.id} node={child} activeId={activeId} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** Nested section nav, built purely from the `sec:id` marker tree — see
 * `section-markers.ts`. Renders nothing if the document has no markers
 * (e.g. a short answer with no section structure). */
export function SectionToc({ tree, activeId, onSelect }: SectionTocProps) {
  if (tree.length === 0) return null;

  return (
    <nav aria-label="Sections" className="w-48 shrink-0 overflow-y-auto border-r border-border p-3">
      <ul className="space-y-0.5">
        {tree.map((node) => (
          <TocNode key={node.id} node={node} activeId={activeId} onSelect={onSelect} />
        ))}
      </ul>
    </nav>
  );
}
