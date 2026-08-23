---
name: outreach-drafting
description: How to research a prospect and draft a personalized outreach note. Use whenever asked to prepare or write outreach to a specific company or contact.
license: MIT
---

# Outreach Drafting

## When to Use

Use whenever the user names a company or contact they want to reach out to — not for generic "how do I sell X" advice.

## How to Use

1. Research the prospect first (see the `web-research` skill): what the company does, anything recent and relevant (funding, launches, news), and — if named — the specific contact's role.
2. Draft a short, specific outreach note (email or message):
   - Open with something that shows you actually looked at their company, not a generic template line.
   - State the value proposition in one or two sentences, specific to what you learned about them.
   - One clear, low-friction ask (a short call, a reply, not "let's hop on a 30 min sync").
   - No filler, no hype words, no more than a handful of short paragraphs.
3. Note explicitly what in the draft is inferred vs. confirmed from a source, so the user can sanity-check before sending.

## Rules

- Never fabricate a fact about the company or contact — if something couldn't be verified, say so instead of guessing.
- Keep it short. A long "personalized" email reads as fake personalization.
- Once the draft is ready, call `render_content` with `kind="markdown"` so the user can review it in the canvas before sending anywhere themselves — this agent never sends messages on the user's behalf.
