# Design System — AutoCoach

## Product Context
- **What this is:** AI-powered powerlifting form coach — upload a video, get a grade, annotated keyframes, and LLM coaching cues
- **Who it's for:** Amateur lifters who found fitness later in life, people training solo who want honest feedback. The vibe is inclusive, strong, and fun — not intimidating gym-bro culture
- **Space/industry:** Fitness tech, form analysis. Competitors: CueForm.ai, JuggernautAI, QuickPose.ai
- **Project type:** Web app (dashboard + landing page)

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian — function-first, data-dense, monospace-forward
- **Decoration level:** Intentional — accent glows, bar dividers between sections, color-coded data values. Not minimal, not maximalist
- **Mood:** Warm power. Like a well-equipped garage gym with good lighting. Technical and precise but inviting. You glance at your results and think "wow, what great information" — not "wow, what a beautiful app." The data IS the design
- **Reference sites:** CueForm.ai (direct competitor, clean but generic), JuggernautAI (polished but cold), QuickPose.ai (technical but clinical)

## Typography
- **Display/Hero:** Instrument Serif — used ONLY for the main hero headline ("Your form, *analyzed*"). Rare and impactful. Never for subheadings or body
- **Body:** Instrument Sans — clean, warm geometric sans. All body copy, descriptions, coaching text
- **UI/Labels:** Geist Mono — THE star of the system. Section labels (`// BIOMECHANICS`), metric headers, badge text, input labels, timestamps, grade letters, angle values, all data. This is the industrial personality
- **Data/Tables:** Geist Mono (tabular-nums) — all numeric data, table cells, scores
- **Code:** Geist Mono
- **Loading:** Google Fonts for Instrument Serif + Instrument Sans; CDN for Geist Mono (or self-hosted)
- **Scale:**
  - `--text-xs`: 0.75rem (12px) — timestamps, fine print
  - `--text-sm`: 0.875rem (14px) — labels, captions, table data
  - `--text-base`: 1rem (16px) — body text
  - `--text-lg`: 1.125rem (18px) — section headers
  - `--text-xl`: 1.25rem (20px) — card titles
  - `--text-2xl`: 1.5rem (24px) — page headings
  - `--text-3xl`: 2rem (32px) — hero subheadings
  - `--text-hero`: 3.5rem (56px) — hero headline only (Instrument Serif)

## Color
- **Approach:** Balanced — warm accent + strong semantics, color is functional (communicates grade quality, form issues, trends)
- **Primary/Accent:** `#E85D3A` (warm rust/coral) — buttons, active states, accent bars, glow effects. Energetic without being aggressive
- **Accent hover:** `#D14E2E` — darker rust for hover states
- **Accent glow:** `rgba(232, 93, 58, 0.3)` — used as box-shadow on primary buttons and grade cards
- **Neutrals (dark mode — default):**
  - Background: `#111110` (near-black with warmth)
  - Surface: `#1A1A19` (cards, panels)
  - Surface raised: `#242423` (elevated cards, modals)
  - Border: `#333332` (subtle dividers)
  - Text muted: `#888886` (secondary text, timestamps)
  - Text secondary: `#BBBBBA` (descriptions, less important text)
  - Text primary: `#FFFFFF` (headings, important content)
- **Neutrals (light mode):**
  - Background: `#FAF8F5` (warm cream)
  - Surface: `#FFFFFF` (cards)
  - Surface raised: `#F5F3F0` (elevated areas)
  - Border: `#E5E2DD` (dividers)
  - Text muted: `#8A8785` (secondary text)
  - Text secondary: `#555553` (descriptions)
  - Text primary: `#111110` (headings, important content)
- **Semantic:**
  - Success: `#34D399` — good form, passing metrics, upward trends
  - Warning: `#FBBF24` — borderline metrics, areas to watch
  - Error: `#F87171` — form issues, safety warnings, downward trends
  - Info: `#60A5FA` — neutral callouts, tips, system status
- **Grade colors (used in metric values and grade cards):**
  - A range: Success green (`#34D399`)
  - B range: Between success and warning
  - C range: Warning yellow (`#FBBF24`)
  - D-F range: Error red (`#F87171`)
- **Dark mode:** Default. This is the primary experience. Light mode is the alternate
- **Dark mode strategy:** True dark (#111110 base), not gray. Warm neutral undertones. Reduce accent glow intensity slightly in light mode

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — data-dense where it matters (metrics tables, biomechanics) but breathing room around sections
- **Scale:**
  - `--space-2xs`: 2px
  - `--space-xs`: 4px
  - `--space-sm`: 8px
  - `--space-md`: 16px
  - `--space-lg`: 24px
  - `--space-xl`: 32px
  - `--space-2xl`: 48px
  - `--space-3xl`: 64px

## Layout
- **Approach:** Grid-disciplined for the app dashboard; creative touches on the landing page hero
- **Grid:** 12-column on desktop (1200px+), 8-column on tablet (768px+), 4-column on mobile
- **Max content width:** 1200px
- **Border radius:**
  - `--radius-sm`: 4px — inputs, small badges
  - `--radius-md`: 8px — cards, buttons
  - `--radius-lg`: 12px — modals, large containers
  - `--radius-full`: 9999px — pills, avatar circles
- **Section dividers:** 2px accent bar (`#E85D3A`) between major content sections. This is a signature element

## Motion
- **Approach:** Minimal-functional — motion serves comprehension, not decoration
- **Easing:**
  - Enter: `ease-out` (elements arriving)
  - Exit: `ease-in` (elements leaving)
  - Move: `ease-in-out` (repositioning)
- **Duration:**
  - Micro: 50-100ms (button hover, toggle)
  - Short: 150-250ms (card transitions, tab switches)
  - Medium: 250-400ms (panel open/close, page transitions)
  - Long: 400-700ms (hero entrance on landing page only)
- **Accent glow animation:** Subtle pulse on grade card after score loads (one-time, 600ms)
- **No scroll-driven animations.** No parallax. No bouncing. Keep it grounded

## Component Patterns

### Section Labels
Monospace, uppercase, prefixed with `//`. Example: `// BIOMECHANICS`. Color: text-muted. This is the signature UI pattern — use it for every section header in the app.

### Metric Display
Value in Geist Mono, color-coded by quality (green/yellow/red). Label in Geist Mono text-muted above the value. Unit suffix in text-muted smaller size.

### Grade Card
Large grade letter in Geist Mono (48-72px), accent glow border, brief description below. The hero element of any analysis result.

### Coaching Cues
Left-colored border (severity: red=safety, yellow=form, blue=optimization). Body text in Instrument Sans. Source attribution in Geist Mono text-muted.

### History Items
Lift type pill badge, date in Geist Mono, grade, trend indicator (`▲ from C+` in green or `▼ from B+` in red).

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-17 | Initial design system created | Created by /design-consultation based on product context + competitive research (CueForm, JuggernautAI, QuickPose) |
| 2026-03-17 | Dark mode as default | Competitors all default light. Dark feels more technical/powerful and differentiates. Matches "garage gym" mood |
| 2026-03-17 | Geist Mono as primary UI font | User loved the industrial/technical feel on grade cards — extended it to be the system's personality. Competitors use generic sans-serifs everywhere |
| 2026-03-17 | Instrument Serif hero-only | Rare usage makes it impactful. Overuse would fight the industrial vibe |
| 2026-03-17 | Accent glow effects | Adds energy without being flashy. Makes grade cards and CTAs feel alive |
| 2026-03-17 | `//` section label pattern | Industrial code-comment aesthetic. Unique to AutoCoach, reinforces the "data IS the design" philosophy |
