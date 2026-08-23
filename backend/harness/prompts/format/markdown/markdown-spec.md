# Markdown Authoring Spec: PDF & DOCX Export Standard

Purpose: a single, reusable set of markdown authoring rules that guarantees clean
conversion to PDF and DOCX. This file is **domain-agnostic and document-agnostic**
— it applies to any markdown output (research reports, briefs, memos, proposals,
anything) that may later be exported to PDF or Word. Reference this file instead
of repeating these rules inside individual document schemas.

This is an **authoring discipline**, not a post-processing cleanup step: follow
these rules while writing the markdown, not after. PDF/DOCX generation here goes
through native document-generation pipelines (LaTeX-based for PDF, docx-js/XML-based
for Word) — these rules are written for that pipeline, not a naive markdown-to-PDF
pass.

---

## 0. Section Identifiers (frontend extraction & partial regeneration)

Purpose: every section and subsection carries a stable, machine-extractable ID so
a frontend can parse the document into addressable blocks, render it section-by-
section, and later replace **just one section** with newly generated content —
without re-parsing or re-rendering the whole document. This is the same pattern
used for canvas-style partial edits: a stable anchor per block that survives
regeneration.

These identifiers are **markdown comments**, invisible in normal markdown
rendering and stripped automatically before PDF/DOCX export (see 0.5) — they
never appear in the delivered document, only in the raw source the frontend
consumes.

### 0.1 Identifier syntax

Every heading-level block (section or subsection) is immediately preceded by an
HTML-comment marker on its own line, directly above the heading, with no blank
line between the marker and the heading:

```markdown
<!-- sec:id=S6.market-size level=2 parent=S6 title="Market Size & Growth" -->
## 6.2 Market Size & Growth
```

**Fields:**
| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable, unique identifier for this block — see 0.2 for the naming scheme |
| `level` | yes | Heading depth (2 = `##`, 3 = `###`, etc.) — lets the frontend build a tree without re-parsing `#` characters |
| `parent` | only for subsections | The `id` of the section this one nests under — builds the hierarchy |
| `title` | yes | Human-readable title, duplicated from the heading text — lets the frontend build a nav/TOC from markers alone, without scanning heading text separately |

A closing marker is placed immediately after the last line of that section's
content, before the next section's opening marker:

```markdown
<!-- /sec:id=S6.market-size -->
```

Everything between an opening and its matching closing marker — including any
nested subsections — belongs to that block. This makes extraction a matched-pair
regex problem, not a "guess where the section ends" problem.

### 0.2 ID naming scheme

`S{section_number}[.{slug}]`

- Top-level sections use the schema's fixed section number: `S1`, `S2`, `S6`, `S20`
  — matching the numbering in the Full Report / Executive Brief schema, so the
  same ID scheme lines up with the document schema files directly.
- Subsections append a short, lowercase, hyphenated slug of the subsection title:
  `S6.market-size`, `S6.competitive-landscape`, `S10.stakeholder-regulators`.
- IDs must be **stable across regeneration** — if a section is regenerated with
  new content, its `id` does not change, so the frontend can match old block to
  new block by ID alone. Only create a new ID if the content becomes a genuinely
  new/different topic, not when existing content is merely updated or expanded.
- IDs are unique within a single document. They are not required to be globally
  unique across documents.

### 0.3 Regex extraction pattern

Because markers are matched open/close pairs on their own lines, a section's full
content (including nested subsections) can be extracted with a pattern such as:

```regex
<!-- sec:id=S6\.market-size[^>]*-->([\s\S]*?)<!-- /sec:id=S6\.market-size -->
```

General form for extracting any block by ID:

```regex
<!-- sec:id={ID}[^>]*-->([\s\S]*?)<!-- /sec:id={ID} -->
```

To extract just the top-level table of contents (all opening markers, ignoring
body content), match every opening marker line independently:

```regex
<!-- sec:id=([\w.\-]+) level=(\d+)(?: parent=([\w.\-]+))? title="([^"]*)" -->
```

This single pattern yields `id`, `level`, `parent`, and `title` for every block
in one pass — enough to reconstruct the full document tree and render a
clickable nav without touching section bodies at all.

### 0.4 Partial regeneration / replace-in-place workflow

1. Frontend requests deeper/updated content for a specific section by its `id`
   (e.g., user clicks "go deeper" on `S6.market-size`).
2. Backend regenerates only that section's content, keeping the same `id`,
   `level`, `parent`, and `title` (title may update if genuinely renamed, but the
   `id` stays fixed so the frontend can still match it).
3. Backend returns the new block, still wrapped in its opening/closing markers.
4. Frontend performs a straightforward string replace: find the existing
   `<!-- sec:id=X -->...<!-- /sec:id=X -->` span in the stored document, replace
   it with the new span. No full-document re-render or re-parse needed.
5. If regeneration produces genuinely new subsections that didn't exist before,
   they get new IDs following the naming scheme (0.2) and are nested under the
   correct `parent` — the frontend tree updates by inserting the new nodes rather
   than rebuilding from scratch.

### 0.5 Stripping markers before export

Section identifier comments must be **removed entirely** before PDF or DOCX
generation — they are a frontend/backend contract, not part of the delivered
document. Strip every line matching `<!-- sec:id=...-->` and `<!-- /sec:id=...-->`
before handing the markdown to the export pipeline described in the rest of this
spec. This is a simple line-removal pass and should happen before any of the
table/math/image rules below are applied.

### 0.6 Rules for maintaining marker integrity

- Never place a section identifier mid-paragraph or mid-table — only directly
  above a heading, and only a closing marker directly after a block's last line.
- Never nest two blocks with the same `id`.
- When a section is split into new subsections during regeneration, existing
  sibling sections' IDs must not be renumbered or shifted — only the changed
  section's subtree changes, so unrelated parts of the frontend state stay valid.
- The `<!-- repeat-header -->` and `<!-- width: 60% -->` markers used elsewhere
  in this spec (Sections 2 and 4 below) are a different, unrelated comment
  convention — do not confuse them with `sec:id` markers. Both are stripped
  before export the same way, but they serve different purposes (layout hint vs.
  section addressing) and must not be merged into one syntax.

---

## 1. General Structural Rules (apply to every document)

- Never use raw `\n` inside a cell or paragraph to force a line break — use
  separate paragraphs, or `<br>` only inside table cells where unavoidable.
- Never hand-draw a horizontal rule or separator using dashes/underscores as body
  content — use a real section break or paragraph border, not literal characters.
- Keep one blank line between every block element (heading, paragraph, table,
  list, image) — ambiguous adjacency is the most common cause of broken
  conversion in both pipelines.
- Every table must declare a full header row and a consistent column count on
  every row — no ragged rows. True merged cells are not reliably supported in
  either PDF or DOCX generation here; simulate a merge by repeating the value or
  leaving a cell intentionally blank instead.
- Use heading levels (`#`, `##`, `###`) consistently and never skip a level
  (e.g., no `#` straight to `###`). Heading levels drive the Table of Contents,
  and in DOCX must map to built-in Heading styles or the TOC will not populate.
- Do not simulate page breaks, page numbers, or headers/footers with text —
  these are generation-time settings applied by the document builder, not
  markdown content.

---

## 2. Tables

- For tables with more than 4 columns, or any table going into a fixed-width PDF
  page, specify intended column-width proportions (as a comment or note next to
  the table) — unmanaged columns can compress unreadably in PDF or overflow
  margins in DOCX.
- Numeric columns: right-align, and pre-format the number as final display text
  directly in the markdown (`$1,234.00`, `(456)` for negatives, `12.4%`, `1.5×`)
  — do not rely on the converter to apply numeric or financial formatting.
  Markdown's `:---:` alignment marker controls text justification only, not
  number formatting.
- Tables wider than ~6 columns: prefer splitting into two stacked tables over
  shrinking font or wrapping aggressively — both formats degrade badly on very
  wide single tables.
- Long tables (15+ rows) that will cross a page break: mark with
  `<!-- repeat-header -->` directly above the table so the generation step
  applies header-row-repeat rather than leaving a headerless continuation on the
  next page.

---

## 3. Math & Formulas (MathJax / LaTeX notation)

- Write inline math as `$...$` and block/display equations as `$$...$$` —
  standard LaTeX syntax is the agreed signal to render as an equation, not
  literal text, even inside an otherwise plain markdown document.
- **PDF target:** equations render natively through the LaTeX-based pipeline.
  Correct `$...$`/`$$...$$` syntax is sufficient — no extra handling needed.
- **DOCX target:** equations do not reliably convert to native Word equations
  (OMML) through this pipeline. For DOCX output:
  - Simple formulas (single fraction, exponent, basic ratio) — write as plain
    Unicode/text instead of LaTeX (e.g., `P/E = Price ÷ EPS`, `x²`, `±5%`) since
    this degrades far more gracefully than broken math markup.
  - Complex or multi-line equations — pre-render as a static image and embed
    (see Section 4), rather than attempting live DOCX math.
  - If a document requesting DOCX output contains non-trivial equations, flag it
    to the user before export: equation fidelity is materially lower in DOCX
    than PDF, and PDF should be offered as the primary format for math-heavy
    content.

---

## 4. Images & Diagrams

- Never embed raw diagram source (Mermaid, SVG source, chart-library code)
  directly expecting it to render — pre-render to a static image file (PNG/SVG)
  first, then reference it with standard markdown image syntax:
  `![Descriptive alt text](path/to/image.png)`.
- Always write real, descriptive alt text — it becomes the accessible/fallback
  text in both PDF and DOCX, and is what displays if the image fails to embed.
- If the default embed size would be wrong for the page, note an intended width
  as a percentage directly above the image: `<!-- width: 60% -->` — markdown has
  no native image-sizing syntax, so this convention signals intent to the
  generation step.
- Do not auto-generate diagrams as a side effect of writing a document — image
  creation is a separate, explicit step; this section only defines how to embed
  one once it exists.

---

## 5. Index vs. Glossary

- A **Glossary** (term → definition, alphabetized, presented as a simple table
  or list) is standard content and converts cleanly to both PDF and DOCX with no
  special handling.
- A true back-of-book **Index** (term → page number(s), auto-generated from
  occurrences throughout the document) is fundamentally different and is **not**
  produced from markdown directly — it requires native index-field marking in
  the DOCX XML, or a LaTeX `\index{}` pass for PDF, applied as a dedicated
  post-processing step after the base document exists. Treat any request for a
  true Index as a distinct, heavier deliverable — confirm with the user before
  committing to it rather than treating it as a default document feature.

---

## 6. Front Matter & Navigation

- Table of Contents: never hand-write a static list of section titles and page
  numbers as body text. Rely entirely on real Heading-styled sections so the
  DOCX/PDF generator builds a live, accurate TOC — a hand-typed TOC will desync
  from real page numbers the moment the document is generated or edited.
- Title pages, revision blocks, and metadata headers are fine as structured
  text (bold labels, key-value pairs) — these render identically and reliably
  in both formats.

---

## 7. Format-Selection Guidance

Use this table to decide, or to advise the user, which export format fits a
given document's content:

| Content in the document | Recommend | Why |
|---|---|---|
| Heavy math/statistical notation | PDF | DOCX math fidelity is materially worse |
| Financial tables needing conditional formatting (colored negatives, etc.) | Either | Both require pre-formatted text; true conditional formatting is a manual finishing step in either format |
| Multiple diagrams/images | Either | Both embed pre-rendered images equally well |
| A true page-linked Index | Flag as extra step | Neither format generates this automatically from markdown |
| Content the user will keep editing afterward | DOCX | Native editability |
| Content meant for final/external distribution | PDF | Fixed layout, consistent rendering everywhere |
| Standard prose/tables only, no math/diagrams | Either | No meaningful fidelity difference; default to user preference or PDF for sharing |

---

## 8. Pre-Export Checklist

Before generating PDF or DOCX from any markdown document, verify:

- [ ] All `<!-- sec:id=... -->` and `<!-- /sec:id=... -->` markers are stripped
      (see Section 0.5) — these must never appear in the delivered PDF/DOCX
- [ ] No raw `\n` used for line breaks anywhere in the document
- [ ] Every table has a complete header row and consistent column counts
- [ ] Numeric/financial values are pre-formatted as final display text
- [ ] Wide tables (6+ columns) are split or column-width-annotated
- [ ] All math uses proper `$...$`/`$$...$$` syntax, with DOCX fallback applied
      if the target format is DOCX and equations are non-trivial
- [ ] All images are pre-rendered files with descriptive alt text, not raw
      diagram source
- [ ] Heading levels are sequential with no skipped levels
- [ ] No hand-typed Table of Contents, page numbers, or headers/footers
- [ ] If an Index (not Glossary) was requested, it's been confirmed as a
      separate step rather than assumed automatic
- [ ] Target format has been sanity-checked against Section 7 given the
      document's actual content (math, financial tables, diagrams, etc.)

---

## 9. Worked Example

A minimal two-section excerpt showing identifiers, a subsection, and correct
structural formatting together:

```markdown
<!-- sec:id=S6 level=2 title="Current State / Core Findings" -->
## 6. Current State / Core Findings

<!-- sec:id=S6.market-size level=3 parent=S6 title="Market Size & Growth" -->
### 6.1 Market Size & Growth

The global market was valued at **$4.2B** in 2025, growing at **12.4%** CAGR. [WEB]

| Metric | Value | Confidence |
|---|---|---|
| TAM | $4.2B | High |
| CAGR | 12.4% | Medium |

<!-- /sec:id=S6.market-size -->

<!-- sec:id=S6.competitive-landscape level=3 parent=S6 title="Competitive Landscape" -->
### 6.2 Competitive Landscape

Three players hold roughly 60% combined share... [WEB]

<!-- /sec:id=S6.competitive-landscape -->

<!-- /sec:id=S6 -->
```

Notes on the example:
- The parent `S6` block's closing marker comes after both children's closing
  markers — parent spans always fully enclose their children.
- Numeric values (`$4.2B`, `12.4%`) are pre-formatted as final text per Section 2.
- Source tags (`[WEB]`) sit inline in prose per the document schema's tagging
  convention — unrelated to, and untouched by, the section-ID system.

---

## Usage Note

This spec is referenced by, not duplicated inside, individual document schemas
(e.g., the Executive Brief / Full Report research schema). Any future document
type — proposals, memos, comparison decks, whatever — should point back to this
file for export rules rather than restating them, so the conversion standard
stays in one place and stays consistent across every document the system
produces.