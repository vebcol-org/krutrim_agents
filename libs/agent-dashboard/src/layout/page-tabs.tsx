import type { Page } from '../types';

export interface PageTabsProps {
  pages: Page[];
  activePageId: string;
  onSelect: (pageId: string) => void;
}

/** Tab nav across workbook.pages. Renders nothing for a single-page workbook. */
export function PageTabs({ pages, activePageId, onSelect }: PageTabsProps) {
  if (pages.length <= 1) return null;

  return (
    <div className="kdash-page-tabs" role="tablist">
      {pages.map((page) => (
        <button
          key={page.id}
          type="button"
          role="tab"
          aria-selected={page.id === activePageId}
          className="kdash-page-tab"
          onClick={() => onSelect(page.id)}
        >
          {page.name}
        </button>
      ))}
    </div>
  );
}
