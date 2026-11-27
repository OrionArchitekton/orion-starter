---
name: "Orion Astro MPA Islands Starter"
framework: "astro@7.4.13"
polarity: "dark"
tokens: "src/styles/tokens.css"
---

# Orion Astro MPA Islands Starter Design System

Zero-JS-by-default Multi-Page Application starter for editorial hubs, marketing pages, and `/works/` microsites. Retains Midnight Navy (`#020B29`) ground continuity with Tailwind v4 OKLCH tokens, self-hosted `@fontsource-variable/*` typography, native CSS `@view-transition` MPA navigation, and selective interactive islands.

## Palette and Contrast Rules

- Ground: `#020B29` (`oklch(16.37% 0.0639 263.50)`)
- Surface: `#07143A` (`oklch(19.65% 0.0882 264.67)`)
- Primary ink: `#F8FAFC` (`>17:1` on ground)
- Muted metadata: `#94A3B8` (`7.57:1` on ground)
- Primary CTA: Copper Mid `#E68249` with Midnight Navy `#020B29` label (`7.07:1`), never white on copper.

## Typography

- Display / Headings: `Newsreader Variable`
- Body / UI: `IBM Plex Sans Variable`
- Code / Telemetry: `JetBrains Mono Variable`

## Performance and Accessibility Invariants

- Static routes (`/`, `/architecture`) emit `0 KB` client JavaScript.
- Interactive island route (`/playground`) hydrates only the isolated control island.
- Mandatory `prefers-reduced-motion: reduce` disables view transitions and animations.
- Zero Unicode long dashes (`U+2013`, `U+2014`, `U+2015`).
