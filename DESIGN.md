---
name: Pipo RV — Comissões
description: Internal platform for managing variable remuneration (RV) at Pipo Saúde — payroll-grade financial software with editorial typography.
colors:
  black: "#000000"
  night: "#060D41"
  cyan: "#3B9AFF"
  beige-lightest: "#F7F3EB"
  beige-light: "#E6D9C2"
  beige-regular: "#DDD6D0"
  neutral-darkest: "#3C404A"
  neutral-dark: "#6B6663"
  neutral-regular: "#BCBAB5"
  neutral-light: "#E2E1DF"
  neutral-lightest: "#F6F6F6"
  fg-1: "#000000"
  fg-2: "#3C404A"
  fg-3: "#6B6663"
  fg-muted: "#BCBAB5"
  bg-1: "#FFFFFF"
  bg-2: "#F6F6F6"
  bg-3: "#F7F3EB"
  border-subtle: "#E2E1DF"
  border-regular: "#BCBAB5"
  success-dark: "#17A66D"
  success-light: "#A8F2CE"
  success-lightest: "#D4F8E7"
  warning-dark: "#FFB033"
  warning-light: "#FFD17D"
  warning-lightest: "#FFEEC2"
  warning-text: "#9A6B0F"
  danger-dark: "#F04646"
  danger-light: "#FFACAC"
  danger-lightest: "#FFDEDE"
  blue-dark: "#1527A9"
  blue-regular: "#3370D1"
  blue-light: "#A2CEFF"
  purple-regular: "#8B3ADD"
  pink-regular: "#FE7B9D"
  peach-regular: "#FFA28D"
typography:
  display:
    fontFamily: "DM Serif Display, Georgia, serif"
    fontSize: "30px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.005em"
  display-numeric:
    fontFamily: "DM Serif Display, Georgia, serif"
    fontSize: "38px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Poppins, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.005em"
  title:
    fontFamily: "Poppins, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Work Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  ui:
    fontFamily: "Manrope, Work Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1
  label:
    fontFamily: "IBM Plex Mono, ui-monospace, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 500
    letterSpacing: "0.06em"
rounded:
  sm: "8px"
  md: "16px"
  lg: "24px"
  pill: "9999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "16px"
  "4": "24px"
  "5": "32px"
  "6": "48px"
  "7": "64px"
components:
  button-primary:
    backgroundColor: "{colors.black}"
    textColor: "{colors.bg-1}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.black}"
    textColor: "{colors.bg-1}"
  button-secondary:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.fg-1}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.fg-2}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  button-danger:
    backgroundColor: "{colors.danger-lightest}"
    textColor: "{colors.danger-dark}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  input-text:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.fg-1}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "11px 14px"
  card-default:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.fg-2}"
    rounded: "{rounded.md}"
    padding: "24px"
  kpi-card:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.fg-1}"
    rounded: "{rounded.md}"
    padding: "20px"
  score-card:
    backgroundColor: "{colors.night}"
    textColor: "{colors.bg-1}"
    rounded: "{rounded.md}"
    padding: "28px"
  badge-default:
    backgroundColor: "{colors.neutral-lightest}"
    textColor: "{colors.neutral-dark}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  badge-approved:
    backgroundColor: "{colors.success-lightest}"
    textColor: "{colors.success-dark}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
  badge-pending:
    backgroundColor: "{colors.warning-lightest}"
    textColor: "{colors.warning-text}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
  badge-contested:
    backgroundColor: "{colors.danger-lightest}"
    textColor: "{colors.danger-dark}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
  chip-default:
    backgroundColor: "{colors.bg-1}"
    textColor: "{colors.fg-2}"
    typography: "{typography.ui}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
  chip-active:
    backgroundColor: "{colors.black}"
    textColor: "{colors.bg-1}"
    typography: "{typography.ui}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
---

# Design System: Pipo RV — Comissões

## 1. Overview

**Creative North Star: "The Editorial Ledger"**

This is payroll-grade software dressed in editorial clothes. Five roles — ADMIN, FINANCE, GERENTE, EV, CN — log in to see commissions, validate apurações, dispute calculations, and watch numbers settle into place. The system handles money that sales people are about to receive. Trust is the only feature that matters; the design earns it twice. First through restraint: warm beige paper, a strict typographic hierarchy, no gradients on cells that hold real numbers. Second through editorial weight: the big numbers sit in DM Serif Display the way headlines sit in a printed broadsheet, signaling that this number was set with care and is not to be rounded.

The personality is **a private bank's monthly statement, redrawn for the screen**. Density is high but never crowded — every grid leaves air, every status badge speaks in mono, every page header floats above an `apuração / contestações / 2026.05` breadcrumb in lowercase mono. The system is bilingual by accident: English UI verbs ("Export", "Filter") share space with Portuguese domain language ("Apuração", "Contestações", "Apólices") because that is how the team talks. The rendered file does not paper over that.

What the system explicitly rejects: dark-mode-by-default dashboards with neon accents; SaaS hero layouts with a giant gradient orb; the "rainbow KPI strip" where each card is a different brand color; identical-card grids that all look like the marketing team's icon library; modals as the first thought for any action.

**Key Characteristics:**
- Restrained color: warm tinted neutrals + black-as-action + a single saturated identity moment (night blue + cyan).
- Editorial display + four functional sans + mono — five fonts working in fixed roles, never blurring.
- Tabular numerals on every number cell. Money does not jitter.
- Flat surfaces with one shadow vocabulary used sparingly for hover and float.
- Lowercase mono for breadcrumbs, labels, timestamps, and section codes — the data dialect.

## 2. Colors

A warm-paper neutral base with disciplined semantic accents. The palette is a working ledger in good light, not a marketing site.

### Primary
- **Pure Black** (`#000000`, `--black`, `--fg-1`): the only color that means "primary action". Lives on the primary button, active navigation indicator, current stepper dot, focus rings (`box-shadow: 0 0 0 2px #000 inset`), and the default `bar-fill`. Used as text on the lightest surfaces.

### Secondary (the identity moment)
- **Night** (`#060D41`, `--night`): reserved for two surfaces — the simulator's `score-card` and the login frame's brand panel. Saturated dark blue, used as a full background, not as an accent.
- **Cyan** (`#3B9AFF`, `--cyan`): the punctuation on Night. Appears as the radial glow behind a score card, as the `score-final` numeral, and as the dot grid on the login halftone. Outside of those contexts, it is **not** an action color.

### Tertiary (the warm-surface family)
- **Beige Lightest** (`#F7F3EB`, `--bg-3`, `--beige-lightest`): the "paper" surface. Backgrounds for callouts, dropzone hover, empty-state illustration disc, the `nav-item.active` background tint, login frame fallbacks. The signature of the brand.
- **Beige Light** (`#E6D9C2`, `--beige-light`): user avatar fill, callout border, distribution-bar alternate fill (`bar-fill.beige`), warm illustrations.
- **Beige Regular** (`#DDD6D0`): low-frequency separator and background tint.

### Neutral
- **fg-1** (`#000000`): primary text, headings, KPI values.
- **fg-2** (`#3C404A`, `--neutral-darkest`): secondary text — body copy, table cell content.
- **fg-3** (`#6B6663`, `--neutral-dark`): tertiary text — captions, breadcrumbs, table headers, section labels.
- **fg-muted** (`#BCBAB5`, `--neutral-regular`): placeholder text, sort glyph, disabled state.
- **bg-1** (`#FFFFFF`): card and surface fill.
- **bg-2** (`#F6F6F6`, `--neutral-lightest`): the page background — the canvas the cards float on.
- **border-subtle** (`#E2E1DF`, `--neutral-light`): the only divider you should reach for — table borders, card outlines, sidebar separator.
- **border-regular** (`#BCBAB5`, same hex as `--neutral-regular`): used as an inset glow on `:hover` (`box-shadow: var(--shadow-hover)`), not as a static border.

### Semantic — feedback
- **success-dark** (`#17A66D`): success badges and `bar-fill.success`. Money paid, approval granted, validation passed.
- **success-lightest** (`#D4F8E7`): success badge background — the dominant feedback surface.
- **warning-dark** (`#FFB033`): warning bar fill, warning indicators. The text variant on warning badges is **`#9A6B0F`** — never use `--warning-dark` as a text color, contrast is insufficient.
- **warning-lightest** (`#FFEEC2`): pending / review badges.
- **danger-dark** (`#F04646`): destructive action text color, contestation bar fill.
- **danger-lightest** (`#FFDEDE`): danger badge background and danger button fill.

### Chart palette (and only chart)
- **blue-dark** (`#1527A9`), **blue-regular** (`#3370D1`), **blue-light** (`#A2CEFF`), **purple-regular** (`#8B3ADD`), **pink-regular** (`#FE7B9D`), **peach-regular** (`#FFA28D`): the six colors `chart-colors` cycles through. **Chart-only.** Never use these as UI accents, button colors, or surface tints.

### Named Rules

**The Black-Reserve Rule.** `#000` is the only action color. Primary buttons, active nav, current stepper dot, primary `bar-fill`, focus rings — they all converge on black. If you reach for another saturated color to mean "click here", you are wrong. Saturated hues are reserved for state (success / warning / danger) and the Night identity moment.

**The Night Sky Rule.** The `night` + `cyan` combination is reserved for moments of high stake or punctuation: the score card (the result of a CN simulator run) and the login frame. Outside those two surfaces, do not use `night` as a background and do not use `cyan` as text. Diluting this combination across the app dissolves its meaning.

**The Beige Paper Rule.** Warm beige (`bg-3 / #F7F3EB`) is the system's voice for "here is something for you". Use it on callouts, dropzones, the active-nav background, empty-state illustrations, and login surfaces. Do not use it as the page background — that is `bg-2` (cool white).

## 3. Typography

**Display Font:** DM Serif Display (with Georgia, serif fallback)
**Heading Font:** Poppins (with system-ui, sans-serif fallback)
**Body Font:** Work Sans (with system-ui, sans-serif fallback)
**UI Font:** Manrope (with Work Sans, system-ui, sans-serif fallback)
**Mono / Label Font:** IBM Plex Mono (with ui-monospace, Menlo, monospace fallback)

**Character:** Five fonts in fixed roles. Display for ceremony, Poppins for hierarchy, Work Sans for prose, Manrope for chrome, IBM Plex Mono for data. The pairing reads like a financial newspaper redesigned for software — generous serif numerals on top of clean sans tables, with mono for the cells where precision matters.

### Hierarchy

- **Display Numeric** (DM Serif Display, 400, 38px, line-height 1, letter-spacing -0.01em): KPI values, score numerals, big H1s on page-titles. Used at 30px on `topbar h1`, 38px on `kpi-value`, 48px on `score-final strong`. Always 400 — never bold.
- **Display Section** (DM Serif Display, 400, 22px): section headers inside content (`section-h h2`). Lowercase mono `lab` micro-label sits above it.
- **Headline** (Poppins, 600, 22px / line-height 1.2): h2-level headings inside cards.
- **Title** (Poppins, 600, 16px / line-height 1.3): card titles (`card-head h3`), dropzone strong, empty-state h4.
- **Body** (Work Sans, 400, 14px / line-height 1.5): default text — paragraphs, descriptions, input value text. Cap reading-width at ~75ch.
- **UI** (Manrope, 600, 13px): buttons, nav items, tabs, table cell content, chip labels, deltas. The "chrome" voice.
- **Label** (IBM Plex Mono, 500, 11px, letter-spacing 0.06em, lowercase or uppercase per context): KPI labels, breadcrumbs, badge text, table column headers (uppercase), audit log timestamps, distribution amounts, dev-foot.
- **Caption** (Work Sans, 400, 12px, color `fg-3`): card-sub, table `.muted`, kpi-foot.

### Named Rules

**The Editorial Numerals Rule.** Every "important number" — KPI values, score finals, big H1s — is set in DM Serif Display at 400 weight, never bold. Bolding a serif numeral would be brutalism; this system reads as editorial. Numbers are first-class typographic objects, not data points.

**The Mono-Voice Rule.** Anything that smells like data or metadata speaks in IBM Plex Mono: timestamps, IDs, percentages in cells, KPI labels, breadcrumbs, sort affordances, audit log rows, dev footer. Mono is the data dialect. Body prose never uses mono.

**The Lowercase Mono Rule.** Mono labels at the page-header level — breadcrumbs (`apuração / contestações / 2026.05`), section codes (`section-h .lab`), KPI labels — are **lowercase**, not uppercase. Uppercase mono is reserved for table column headers and dev-foot, where it reads as a code label. Lowercase mono reads as quiet metadata.

**The Tabular Numerals Rule.** Any cell that holds a number — table `.num`, `.strong-num`, `.cell-progress .pct`, distribution amounts — uses `font-variant-numeric: tabular-nums; font-feature-settings: "tnum"`. Money that jitters as it sorts is broken.

## 4. Elevation

The system is **flat at rest with one ambient shadow vocabulary used sparingly for hover, float, and the dev footer**. Cards do not lift; they are outlined by `border-subtle`. Surfaces float on the page background through 1px borders, not shadows. Depth is communicated structurally, not through atmosphere.

### Shadow Vocabulary

- **shadow-01** (`box-shadow: 0 1px 2px rgba(0,0,0,.06)`): the dev-foot pill at the bottom-right corner, and any element that needs to read as "above the page" without ceremony. The only resting shadow.
- **shadow-02** (`box-shadow: 0 0 2px rgba(0,0,0,.2),0 2px 15px rgba(0,0,0,.08)`): mid-elevation float — modals, popovers (when introduced).
- **shadow-03** (`box-shadow: 0 0 4px rgba(0,0,0,.05),0 8px 40px rgba(0,0,0,.10)`): high-elevation overlay — the largest dialogs, full-bleed alerts.
- **shadow-hover** (`box-shadow: 0 1px 1px rgba(0,0,0,.05), 0 0 0 1px #BCBAB5 inset`): the hover signal. **Notice:** the hover shadow is an *inset border* — the ring around the element shifts darker on hover, not a glow underneath. This is the system's signature interaction shape. Used on `.search:hover`, `.icon-btn:hover`, `.btn-secondary:hover`, `.chip:hover`, `.field-input:hover`.

### Named Rules

**The Flat-By-Default Rule.** Cards, KPIs, table wraps, callouts, and inputs are flat at rest. Their boundary is a 1px `border-subtle` outline, not a drop shadow. Shadow is a response to interaction (`shadow-hover`), elevation (modals → `shadow-02/03`), or detachment (the dev-foot pill).

**The Inset-Hover Rule.** Hover does not make elements lift toward the user. Hover tightens the border via `shadow-hover` (inset 1px `#BCBAB5`). The element does not move. This is critical for tables and inputs where movement on hover would make selection feel imprecise.

**The Focus-Inset Rule.** Focused inputs use `box-shadow: 0 0 0 2px #000 inset` — a 2px inset black ring inside the existing 1px border. No outer outline, no glow. The focus indicator lives within the field's footprint.

## 5. Components

### Buttons
- **Shape:** rounded-sm radius (`var(--r-sm)` = 8px) on all variants. Same shape across `:sm` (28px min-height), `:md` (36px), `:lg` (44px).
- **Primary:** solid black background (`#000`), white text (`#FFF`), Manrope 600 13px, uppercase letter-spacing nominal, 9×16px padding (md). Hover: `box-shadow: 0 0 0 2px #000 inset, 0 1px 1px rgba(0,0,0,.05)` — the button does not lift; it grows a subtle inner ring.
- **Secondary:** white fill, fg-1 text, 1px `border-subtle` stroke. Hover: `shadow-hover`. The default for any non-primary action.
- **Ghost:** transparent fill, fg-2 text. Hover: `bg-2` background. The lightest-touch action.
- **Danger:** `danger-lightest` fill, `danger-dark` text, 1px `danger-light` border. Used for destructive confirmation buttons.
- **Loading state:** shows spinner (`animation: spin 0.6s linear infinite`) + label "Carregando..." inline; opacity drops to 0.5 during disabled or loading.

### Inputs
- **Style:** 1px `border-subtle` stroke, `rounded-sm` (8px) radius, 11×14px internal padding, Work Sans 14px text, white fill. Disabled fields fall to `bg-2` background and `fg-muted` text.
- **Hover:** `shadow-hover` (inset border darkens to `#BCBAB5`). The field stays in place.
- **Focus:** `box-shadow: 0 0 0 2px #000 inset`, no outline. Black inner ring inside the border.
- **Error:** border swaps to `danger-default` (`#F04646`); below the field, an 11px IBM Plex Mono error message in `danger-default`.
- **Label:** `field-label` — Manrope 600 12px, fg-2 — sits above the input with a 6px gap.
- **Help text:** `field-help` — IBM Plex Mono 11px, fg-3 — sits below.
- **Dropzone variant** (`.dropzone`): 2px dashed `neutral-light` border, `bg-3` (warm beige) background, 48×24px padding, 36px upload icon, Poppins 600 15px strong copy. Hover: border darkens to `fg-3`, background to `beige-lightest`.

### Cards / Containers
- **Default card** (`.card`): white fill, 1px `border-subtle`, `rounded-md` (16px), 24px internal padding, 16px gap between children. No shadow at rest.
- **KPI card** (`.kpi`): same shell as `.card` but 20px padding, 12px gap, with optional `kpi-grafismo` SVG decoration absolutely positioned bottom-right at 0.5 opacity. Internal hierarchy: lowercase mono label at top, DM Serif numeric value mid (38px), `kpi-foot` row at bottom with delta pill + caption.
- **Score card** (`.score-card`): `night` (`#060D41`) fill, white text, `rounded-md`, 28px padding. Decorated with a `radial-gradient` cyan glow at 0.18 opacity, top-right. Reserved for simulator output (CN role).
- **Border:** every card uses `border-subtle` (1px). Score card has no border.
- **Internal padding:** 20px (KPI) / 24px (default card) / 28px (score card).

### Chips & Filter pills
- **Shape:** `rounded-pill` (9999px radius), 5×12px padding, Manrope 500 12px, 1px `border-subtle` stroke, white fill.
- **State (active):** background swaps to black, text to white, border to black. Hover (inactive): `shadow-hover`.

### Status Badges
- **Shape:** `rounded-pill`, 3×10px padding, IBM Plex Mono 500 11px, line-height 1.4. Always preceded by a `::before` colored dot (6px diameter, `currentColor` fill).
- **Variants** (background / text):
  - draft: `neutral-lightest` / `neutral-dark`
  - calc: `#EAF1FB` / `blue-dark`
  - review: `warning-lightest` / `#9A6B0F` (warning text variant)
  - validating: `#F2E9FB` / `purple-regular`
  - approved / paid / resolved: `success-lightest` / `success-dark`
  - locked: `neutral-light` / `neutral-darkest`
  - contested: `danger-lightest` / `danger-dark`
  - pending: `warning-lightest` / `#9A6B0F`

### Tables
- **Header row:** `bg-2` background, IBM Plex Mono 500 10.5px **uppercase** with 0.06em letter-spacing, `fg-3` text, 11×16px padding, 1px `border-subtle` bottom.
- **Body row:** Manrope text, 13×16px padding, 1px `border-subtle` between rows, no border on the last row. Hover: row background swaps to `bg-2`.
- **Numeric cells** (`.num`, `.strong-num`): `font-variant-numeric: tabular-nums`. `.strong-num` uses IBM Plex Mono 600 fg-1.
- **Container:** wrapped in `.table-wrap` — 1px `border-subtle`, `rounded-md`, `overflow:hidden`, white fill. The table corners inherit from the wrap.
- **Cell progress** (`.cell-progress`): a 6px `bar` with a `bar-fill` (black by default; `success`/`warn`/`danger` variants), aligned with a right-aligned mono percentage at 12px.

### Navigation
- **Sidebar shell:** 240px fixed-width column, white fill, 1px `border-subtle` right edge, sticky-top, full-viewport height.
- **Brand block** (top): 22×20×18px padding, 12px gap. Brand mark is a 34px black square with `rounded-sm-ish` (10px) radius and a single white DM Serif glyph centered. Brand name uses Poppins 600 15px for the product, IBM Plex Mono 10px lowercase for the role tag.
- **Nav section labels:** IBM Plex Mono 10px **uppercase**, 0.08em letter-spacing, `fg-muted`.
- **Nav items:** Manrope 500 13.5px, 8×12px padding, 8px radius, 18×18px icon (fg-3 default), gap 10px. Default state has a transparent 2px left-border placeholder. **Active state** flips: background `beige-lightest`, font-weight 600, fg-1, icon fg-1, **2px left-border in pure black**. Hover (inactive): `bg-2` background, fg-1.
- **Topbar:** 18×32px padding, 72px min-height, white fill, 1px `border-subtle` bottom, sticky-top, z-index 10. Left side: lowercase mono breadcrumbs above a DM Serif Display 30px page title. Right side: 260px-wide pill search field, 36×36 round icon buttons.

### Stepper (apuração)
- **Track:** horizontal flex row, 18×0px padding. Each step is a 28px circle dot + label, joined by 1.5px lines.
- **States:** default — white fill, 1.5px `neutral-light` ring, IBM Plex Mono 600 11px fg-3 number. Done — `success-dark` fill + ring, white check. Current — black fill + ring, white number, label flips to fg-1 600 weight.

### List Items (contestations, audit feed)
- **Layout:** 3-column grid (`auto / 1fr / auto`), 18×20px padding, 16px column gap, 1px `border-subtle` between rows.
- **Quote block:** when an item embeds a user quote, the quote sits inside a 10×12px `bg-2` rounded-sm panel **with a 2px solid `neutral-regular` left edge** — this is an editorial blockquote treatment, not a severity stripe.

### Activity Timeline
- **Layout:** 2-column grid (24px / 1fr) per item. Each item draws a vertical 1.5px `neutral-light` line through its `::before` to connect to the next item.
- **Dot states:** default — white fill, 1.5px `neutral-light` ring, fg-3 icon. Done — `success-dark` fill + ring, white icon. Current — black fill + ring, white icon.

### Score Card (signature component, CN role)
The simulator's payoff: a `night`-fill card with a cyan radial glow top-right (200×200px at 0.18 opacity), uppercase mono labels at 11px in 60% white, intermediate values in DM Serif 28px, and the final number in DM Serif 48px **cyan**, with a small white "R$" prefix. The system has exactly one place where saturated color and large display type meet on a dark surface — this is it.

### Login Frame (signature component)
Two-column 50/50 split. Left side (`login-side`): full `night` background with a radial cyan glow bottom-left and an overlaid `dot-grid` pattern (cyan dots, 32px spacing, 0.15 opacity). Right side (`login-form-side`): white surface, fg-2 text, DM Serif Display 34px h2, slightly chunkier inputs (14×16px padding, 14px text). The system's only "drenched" surface.

### Diff Block (contestações)
2-column mono grid. The header row carries an uppercase Manrope label. Below, `.old` cells are line-through fg-3, `.new` cells are `success-lightest` fill with `success-dark` 600 text. A factual record, not a celebration.

### Audit Log Row
3-column grid (160px / 1fr / 180px), 10×16px padding, IBM Plex Mono 11.5px, 1px `border-subtle` bottom. Timestamps in fg-3, actor name in fg-1 600, action description in Manrope (overrides the row's mono inheritance for prose). Hover: `bg-2`.

### Matrix (commission rate table)
Mono-voice grid with separated borders (`border-collapse: separate`). Headers: `bg-2`, uppercase 10.5px IBM Plex Mono 600, fg-3. First-column cells inherit the same treatment but with fg-1. The currently-applicable rate cell is highlighted with a 2px `success-dark` border and `success-lightest` fill — a 700-weight `success-dark` value sits inside.

## 6. Do's and Don'ts

### Do:

- **Do** use `#000` as the only primary action color. Buttons, active nav, current step, primary bar fills.
- **Do** set every "important number" in DM Serif Display at weight 400 — KPI values, score finals, page-title H1s.
- **Do** put any data-shaped string (timestamps, IDs, percentages, KPI labels, breadcrumbs, audit timestamps) in IBM Plex Mono. Body prose stays in Work Sans.
- **Do** apply `font-variant-numeric: tabular-nums` to every numeric cell. Use `.num`, `.strong-num`, or set the rule directly.
- **Do** float surfaces with 1px `border-subtle`, not drop shadows. Cards are flat at rest.
- **Do** use `shadow-hover` (inset 1px `#BCBAB5`) for hover affordance on inputs, search, icon buttons, secondary buttons, and chips. Elements do not lift.
- **Do** focus inputs with `box-shadow: 0 0 0 2px #000 inset` — the focus ring lives inside the field's footprint.
- **Do** start each table column header in IBM Plex Mono 10.5px uppercase with 0.06em letter-spacing, `fg-3` text, on a `bg-2` row with a `border-subtle` bottom.
- **Do** prefix every status badge with a `::before` colored dot using `currentColor`. The dot is the badge's signature.
- **Do** treat warm beige (`bg-3 / #F7F3EB`) as the "warm-surface" voice — callouts, dropzones, active-nav background, empty-state illustrations. Reach for it when something needs a softer hand.
- **Do** keep the `night` + `cyan` combination on exactly two surfaces: the simulator's score card and the login frame.

### Don't:

- **Don't** use `border-left` or `border-right` greater than 1px as a colored severity accent on cards, KPIs, alerts, or callouts. The pattern exists only on (a) the active sidebar nav item (a known navigation idiom) and (b) the editorial blockquote inside list-items. Do not extend it elsewhere — no "red stripe = error" cards.
- **Don't** apply `background-clip: text` with a gradient. Decorative gradient text is forbidden across this system. Hierarchy comes from weight (400 vs 600) and family (DM Serif vs Poppins vs Manrope), never from color tricks.
- **Don't** use glassmorphism, frosted backdrops, or `backdrop-filter: blur` decoratively. The system has zero glass surfaces and that is intentional.
- **Don't** build a "hero metric" template (giant number + small label + supporting stats + gradient accent). The KPI card is deliberately quiet — restrained padding, mono label, serif numeral, optional outline-stroke `kpi-grafismo` decoration at 0.5 opacity bottom-right. Don't escalate it.
- **Don't** lay out the page as a grid of identical cards with icon + heading + paragraph. Vary the card sizes, vary their content density, mix in tables and lists. The 4-up KPI grid is the **only** identical-card grid in the system.
- **Don't** open a modal as the first answer to any new interaction. Inline editing, side panels (`detail-grid`'s 360px sidebar), and progressive disclosure come first.
- **Don't** introduce a new font. Five fonts are already loaded (DM Serif Display, Poppins, Work Sans, Manrope, IBM Plex Mono). Each has a fixed role. A sixth would dilute the meaning of the others.
- **Don't** use `--warning-dark` as a text color on `--warning-lightest`. Use the warning text variant `#9A6B0F` for that pairing — `--warning-dark` is a fill color only.
- **Don't** use the chart palette (`blue-dark` through `peach-regular`) for UI accents, button colors, or surface tints. They live inside chart legends, axes, and bars only.
- **Don't** use saturated dark blue (`night`) outside the score card and the login frame. It is an identity color, not a generic surface.
- **Don't** lift cards on hover with translateY or larger shadows. The only hover signal is `shadow-hover` (inset border darkening). Movement on hover breaks selection precision in dense tables.
- **Don't** write em dashes in UI copy. Use commas, colons, periods, or parentheses. Match the rest of the system's punctuation hygiene.
