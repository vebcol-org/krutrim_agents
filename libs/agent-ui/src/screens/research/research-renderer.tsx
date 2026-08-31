import { useMemo, useState, type ComponentPropsWithoutRef, type JSX } from 'react';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import remarkMath from 'remark-math';

import 'katex/dist/katex.min.css';

import { ProseMarkdown } from '../default/prose';
import type { AgentRendererProps } from '../types';
import { flattenTree, prepareResearchMarkdown, type SectionNode } from './section-markers';
import { SectionToc } from './toc';

type HeadingTag = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
const HEADING_TAGS: HeadingTag[] = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'];

/** Assigns `id={section.id}` to headings in document order, matching them
 * 1:1 against the flattened `sec:id` tree — a spec-compliant document has
 * exactly one heading per section marker, in the same order, so this lines
 * up without needing a separate slugger. A document with no markers (or a
 * heading/marker count mismatch) just renders those headings without an id
 * — no crash, no lost content, just no scroll-anchor for that heading. */
function makeHeadingComponents(flatSections: SectionNode[]): Partial<Record<HeadingTag, (props: ComponentPropsWithoutRef<HeadingTag>) => JSX.Element>> {
  let index = 0;
  const components: Partial<Record<HeadingTag, (props: ComponentPropsWithoutRef<HeadingTag>) => JSX.Element>> = {};
  for (const tag of HEADING_TAGS) {
    const Tag = tag;
    components[tag] = (props: ComponentPropsWithoutRef<HeadingTag>) => {
      const section = flatSections[index];
      index += 1;
      return <Tag id={section?.id} {...props} />;
    };
  }
  return components;
}

/**
 * Renders a research report per `backend/harness/prompts/format/markdown/markdown-spec.md`:
 * parses/strips the `sec:id` section markers into a TOC (Section 0), renders
 * GFM tables (Section 1-2), math via `remark-math`/`rehype-katex` (Section 3),
 * and `<!-- width:NN% -->` image hints via a pre-processing rewrite +
 * `rehype-raw` (Section 4). `<!-- repeat-header -->` (also Section 2) is a
 * print-only hint with no browser equivalent — stripped silently.
 */
export function ResearchRenderer({ payload }: AgentRendererProps) {
  const { tree, content } = useMemo(() => prepareResearchMarkdown(payload.content), [payload.content]);
  const flatSections = useMemo(() => flattenTree(tree), [tree]);
  const headingComponents = useMemo(() => makeHeadingComponents(flatSections), [flatSections]);
  const [activeId, setActiveId] = useState<string | null>(null);

  function scrollToSection(id: string) {
    setActiveId(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-border px-6 py-4">
        <span className="mb-1 block font-mono text-xs uppercase tracking-widest text-primary">Research Report</span>
        <h2 className="font-mono text-xl font-semibold text-foreground">{payload.title}</h2>
      </header>

      <div className="flex min-h-0 flex-1">
        <SectionToc tree={tree} activeId={activeId} onSelect={scrollToSection} />
        <div className="min-w-0 flex-1 overflow-y-auto px-6 py-6 lg:px-8">
          <ProseMarkdown
            content={content}
            remarkPlugins={[remarkMath]}
            rehypePlugins={[rehypeRaw, rehypeKatex]}
            components={headingComponents}
          />
        </div>
      </div>
    </div>
  );
}
