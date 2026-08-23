import ReactMarkdown, { type Options as ReactMarkdownOptions } from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface ProseMarkdownProps {
  content: string;
  remarkPlugins?: ReactMarkdownOptions['remarkPlugins'];
  rehypePlugins?: ReactMarkdownOptions['rehypePlugins'];
  components?: ReactMarkdownOptions['components'];
}

/** Shared prose-wrapper markup — previously duplicated verbatim between
 * `default-renderer.tsx` and `trading/renderer.tsx`. Always includes
 * `remark-gfm`; a caller (e.g. `research/renderer.tsx`) can extend both
 * plugin lists for spec-specific syntax (math, raw HTML for image-width
 * hints) without touching this shared prose styling. */
export function ProseMarkdown({ content, remarkPlugins, rehypePlugins, components }: ProseMarkdownProps) {
  return (
    <div className="prose-invert max-w-none text-sm leading-relaxed text-foreground [&_a]:text-primary [&_blockquote]:border-l-2 [&_blockquote]:border-primary [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_h1]:font-mono [&_h2]:font-mono [&_h3]:font-mono [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, ...(remarkPlugins ?? [])]}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
