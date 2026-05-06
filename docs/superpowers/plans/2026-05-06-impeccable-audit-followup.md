# Handoff: Impeccable Audit Follow-up

**Date:** 2026-05-06  
**Status:** Harden + adapt + optimize + toolchain + polish landed — only the optional `:advanced` Closure slice remains  
**Source:** `$impeccable audit` run in Codex thread  
**Scope:** Frontend technical UI audit; harden + adapt + optimize + toolchain + polish applied 2026-05-06

## Context

Product context was loaded from `PRODUCT.md` and `DESIGN.md`.

Register: `product`.

The UI is an internal Pipo Saude variable remuneration platform for RevOps/Admin, Finance, Sales Managers, EVs, and CNs. The design direction is a restrained "editorial ledger": dependable, precise, dense where operational finance needs density, and serious about money without becoming cold or decorative.

This audit was evaluation-only. No project files were edited.

## Audit Score

| Dimension | Score | Key Finding |
|---|---:|---|
| Accessibility | 2/4 | Several visible controls are `div` click handlers or low-contrast badges |
| Performance | 2/4 | Production build passes, but `main.js` is 3.1 MB with `:simple` optimizations |
| Responsive | 2/4 | CSS breakpoints are good, but many inline fixed grids bypass them |
| Theming | 2/4 | CSS vars and CLJS tokens diverge, with hard-coded colors in views |
| Anti-Patterns | 3/4 | Mostly disciplined product UI, with a few design-system rule leaks |
| **Total** | **11/20** | **Acceptable, significant work needed** |

## Anti-pattern Verdict

The UI does not read as obviously AI-generated. It has a real design spine: restrained editorial ledger, dense tables, quiet surfaces, no gradient text, no glassmorphism, and no generic SaaS hero pattern.

The main risk is design-system drift. Raw inline styles and ad hoc chips/tabs recreate components outside the design system.

## Findings

### P1: Badge and Status Text Contrast Fails WCAG AA

**Location:** `frontend/resources/public/css/pipo-design.css`

Examples:

- `.badge-review`
- `.badge-approved`
- `.badge-contested`
- `.badge-resolved`
- `.badge-paid`
- `.badge-pending`
- `.delta-up`
- `.delta-down`

Measured contrast ratios:

- `success-dark` `#17A66D` on `success-lightest` `#D4F8E7`: `2.74:1`
- `danger-dark` `#F04646` on `danger-lightest` `#FFDEDE`: `2.96:1`
- `warning-text` `#9A6B0F` on `warning-lightest` `#FFEEC2`: `4.07:1`

These are below WCAG AA for normal text. The text is also small, around 11px, so the failure matters in daily finance workflows where status certainty is important.

**Recommendation:** Darken semantic text colors used on light semantic badge backgrounds, or increase text size/weight only if that preserves the design system. Prefer token-level fixes so all badges update consistently.

Suggested command: `$impeccable harden`

### P1: Clickable `div` Controls Are Keyboard-inaccessible

**Locations:**

- `frontend/src/app/views/revops/policies.cljs`
- `frontend/src/app/views/revops/contestations.cljs`
- `frontend/src/app/views/ev/validation.cljs`
- `frontend/src/app/views/revops/achievements.cljs`
- `frontend/src/app/views/revops/appraisal_review.cljs`
- `frontend/src/app/views/revops/cn_appraisal.cljs`
- `frontend/src/app/views/revops/cn_goals.cljs`
- `frontend/src/app/views/revops/ev_bonus.cljs`
- `frontend/src/app/views/revops/leadership_appraisal.cljs`
- `frontend/src/app/views/revops/settings.cljs`
- `frontend/src/app/views/revops/users.cljs`

Patterns found:

- Filter chips implemented as `[:div {:class (str "chip" ...) :on-click ...}]`
- Tabs implemented as `[:div {:class (str "tab" ...) :on-click ...}]`
- Toggle implemented as `[:div {:class (str "tog" ...) :on-click ...}]`
- Notification rows implemented as clickable `div`

The design system already has a stronger tab implementation in `frontend/src/app/ds/tabs.cljs`, but several screens bypass it.

**Impact:** Keyboard users cannot reliably focus or activate these controls. Screen readers may not announce role, state, or selected tab/filter.

**Recommendation:** Replace clickable `div` chips/tabs/toggles with semantic `button`, `input type=checkbox`, or the existing `app.ds.tabs` component. Add `aria-pressed`, `aria-selected`, `role=tab`, or `aria-current` as appropriate.

Suggested command: `$impeccable harden`

### P1: Responsive Breakpoints Are Undermined by Inline Fixed Grids

**Locations:**

- `frontend/src/app/views/cn/simulator.cljs`
- `frontend/src/app/views/finance/export.cljs`
- `frontend/src/app/views/revops/policy_edit_modal.cljs`
- `frontend/src/app/views/revops/settings.cljs`
- `frontend/src/app/views/revops/teams.cljs`
- `frontend/src/app/views/revops/leadership_appraisal.cljs`
- `frontend/src/app/views/auth/views.cljs`
- `frontend/src/app/views/shared/no_role.cljs`

Examples:

- Inline `:grid-template-columns "1fr 1fr"`
- Inline `:grid-template-columns "1fr 1fr 1fr 1fr"`
- Inline `:grid-template-columns "repeat(3,1fr)"`
- Inline `:grid-template-columns "180px 200px 1fr 1fr 1fr"`
- Inline `:width "120px"` and notification dropdown `:width "380px"`

The global CSS has good responsive shell work, including sidebar collapse and table overflow. Inline grids cannot be targeted by media queries, so smaller viewports can still overflow or squeeze controls.

**Recommendation:** Move repeated inline layout grids into reusable classes or DS layout helpers with responsive rules. Use `minmax`, `auto-fit`, and breakpoint-driven single-column variants for form panels.

Suggested command: `$impeccable adapt`

### P2: Build Passes, But Test and Lint Verification Are Not Healthy

Commands run:

- `npm.cmd run release`: passed.
- `npm.cmd run lint`: failed because `clj-kondo` is not available on PATH.
- `npm.cmd test -- --browsers ChromeHeadless`: first failed in sandbox with `spawn EPERM`; after escalation Chrome launched, but Karma failed with `You need to include some adapter that implements __karma__.start method!`

The production frontend build completed successfully:

```text
shadow-cljs release app
Build completed. 235 files, 0 compiled, 0 warnings
```

The generated bundle observed at `frontend/resources/public/js/compiled/main.js` is about `3,107,812` bytes.

**Recommendation:** Fix the frontend verification toolchain before deeper UI refactors. Add or document local `clj-kondo`, and repair Karma/shadow-cljs test adapter configuration.

Suggested command: `$impeccable harden`

### P2: Bundle Size and Compiler Settings Need Optimization Pass

**Locations:**

- `frontend/shadow-cljs.edn`
- `frontend/package.json`
- `frontend/resources/public/index.html`

Findings:

- `:compiler-options {:optimizations :simple}` is used for the app build.
- `main.js` is about 3.1 MB.
- `recharts`, `@emotion/react`, `@emotion/styled`, and `dayjs` are npm dependencies.
- `recharts` appears used only in `frontend/src/app/views/finance/orcado_realizado.cljs`.
- Many charts elsewhere are SVG-native and do not need Recharts.
- Five external Google font families are loaded from one CSS request.

**Recommendation:** Evaluate `:advanced` optimizations or another production-safe minification path. Audit whether Recharts/Emotion/dayjs are still needed. Consider font subsetting or self-hosting only required weights if performance becomes release-critical.

Suggested command: `$impeccable optimize`

### P2: Token Drift and Hard-coded Values Weaken Theming

**Locations:**

- `frontend/resources/public/css/pipo-design.css`
- `frontend/src/app/ds/tokens.cljs`
- Multiple views under `frontend/src/app/views`

Findings:

- CSS vars and CLJS tokens disagree in places, for example `--success-dark` is `#17A66D` while `app.ds.tokens/success-dark` is `#0F7C50`.
- Views still use raw hex and rgba values for chart strokes, SVG fills, dark-card text, and panel treatments.
- Design docs define a token system, but implementation has two token sources plus inline one-offs.

**Recommendation:** Choose one canonical source or enforce a generated mapping between CSS vars and CLJS tokens. Move raw color usages in views to tokens or CSS utility classes, especially semantic colors and chart colors.

Suggested command: `$impeccable harden`

### P2: Finance Chart Accessibility Is Better Than Most, But Still Color-dependent

**Location:** `frontend/src/app/views/finance/dashboard.cljs`

Positive: the cash-flow SVG has `role="img"`, an `aria-label`, a `desc`, and keyboard-focusable chart points with labels.

Risk: bars/line/area rely heavily on color families to distinguish `realizado`, `a apurar`, and `projetado`. Legends exist visually, but assistive tech gets a high-level description rather than a tabular data alternative.

**Recommendation:** Add an accessible data summary or companion table for chart data, especially for the finance dashboard where the chart supports payment decisions.

Suggested command: `$impeccable harden`

## Positive Findings

- The shell uses semantic landmarks: `aside`, `nav`, `main`, `header`.
- Skip-to-content link exists and targets `#main-content`.
- Active sidebar nav uses `aria-current="page"`.
- Sidebar nav links have `aria-label` and `title`, useful when mobile collapses labels.
- Modal has `role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap, Escape close, and focus restoration.
- Table DS supports hidden captions and sortable header buttons with `aria-sort`.
- Reduced-motion preference is respected globally.
- Responsive CSS for the app shell, topbar, sidebar, cards, diff blocks, and touch targets is already present.
- The visual system mostly avoids known AI slop tells: no gradient text, no glassmorphism, no generic hero-metric page, no decorative card-heavy landing page.

## Recommended Order

1. `$impeccable harden`: fix semantic controls, contrast tokens, and test/lint setup.
2. `$impeccable adapt`: migrate inline fixed grids to responsive classes/components.
3. `$impeccable optimize`: reduce bundle size and review compiler/dependency/font strategy.
4. `$impeccable polish`: final consistency pass after fixes.

## Verification Notes

Use `npm.cmd` on Windows rather than `npm` in PowerShell, because `npm.ps1` can be blocked by execution policy.

Successful:

```powershell
npm.cmd run release
```

Failed:

```powershell
npm.cmd run lint
```

Reason: `clj-kondo` is not recognized as a command.

Failed:

```powershell
npm.cmd test -- --browsers ChromeHeadless
```

First failure: sandbox blocked Chrome launch with `spawn EPERM`.  
Second failure after escalation: Karma launched Chrome but reported `You need to include some adapter that implements __karma__.start method!`

## Handoff Guidance

The next agent should start with `PRODUCT.md`, `DESIGN.md`, and this file. The most valuable first slice is not visual redesign. It is a technical accessibility hardening pass that converts ad hoc interactive `div`s to semantic controls and fixes semantic contrast at token level.

Preserve the existing "editorial ledger" direction. The UI is already coherent; the job is to make the implementation as disciplined as the design intent.

## Harden Pass — 2026-05-06

### What changed

- **Contrast tokens.** Added `--success-text:#0F7C50` and `--danger-text:#B91C1C`; bumped `--warning-text` from `#9A6B0F` to `#7A5410`. Routed every text-on-`*-lightest` rule (`.badge-approved`, `.badge-resolved`, `.badge-paid`, `.badge-contested`, `.badge-pending`, `.delta-up`, `.delta-down`, `.btn-danger`, `.nav-item .badge`, `.matrix td.cur`, `.diff .new`) and the inline counterparts in `appraisal_review`, `validation`, `contestations`, `sync_status` views to those new tokens. CLJS `app.ds.badge` now uses `*-dark` (the AA text variants) for foreground; `tokens.cljs` documents the CSS↔CLJS naming drift inline. Verified ratios via `getComputedStyle` in the running app: success ≈ 4.65:1, danger ≈ 5.55:1, warning ≈ 5.95:1 — all above WCAG AA for normal text.
- **Semantic controls.** Replaced clickable `div`s with semantic primitives across the eleven flagged files plus the design-system `notifications` row and the two collapsible row headers in `appraisal_review`:
  - `.chip` → `<button type="button" aria-pressed>` inside `<div role="group">`.
  - `.tab` → `<button type="button" role="tab" aria-selected>` inside `<div role="tablist">`.
  - `.tog` → `<button type="button" role="switch" aria-checked aria-labelledby>` paired with a real `<label>`.
  - Notification rows → `<button>` with full `aria-label`.
  - Disclosure rows (policy / EV) → `<button aria-expanded>`.
  CSS for `.chip`, `.tab`, `.tog` now includes button resets, focus-visible outlines, and dual selectors so either `.active`/`.on` or the matching `aria-*` attribute drives the visual state.
- **No visual regressions.** `npm.cmd run release` passes (235 files, 28 compiled, 0 warnings, ~29s). `shadow-cljs watch app` builds clean (29 compiled, 0 warnings). Computed styles match the originals: `.chip` retains the white→black active flip, `.tab` keeps the underline-on-active treatment, `.tog` stays a 34×20 pill that turns black when on.

### Files touched

- `frontend/resources/public/css/pipo-design.css`
- `frontend/src/app/ds/tokens.cljs`
- `frontend/src/app/ds/badge.cljs`
- `frontend/src/app/ds/notifications.cljs`
- `frontend/src/app/views/ev/validation.cljs`
- `frontend/src/app/views/revops/{policies,cn_goals,cn_appraisal,achievements,ev_bonus,leadership_appraisal,users,appraisal_review,contestations,settings,sync_status}.cljs`

### Toolchain status (P2 — still red)

- `npm.cmd run lint` — `clj-kondo` is still missing from PATH. There is no `.clj-kondo/` config at the repo root and no native dependency declared. Two clean ways to fix this without a global install: add `clj-kondo` (npm wrapper, current 2025.10.23) to `frontend/devDependencies` and update the script to `npx clj-kondo --lint src/`, or document the expected install (Scoop/MSYS2/native). Either change is config-only and was left out of this pass; it should be paired with a first run that triages whatever findings surface.
- `npm.cmd test` — still fails the same way the audit reported (`__karma__.start method`). Root cause: no `karma.conf.js` is checked in and the existing `frontend/test/app/ds/tokens_test.cljs` has stale expectations (`bg-main` now `#F6F6F6`, `text-primary` now `#000000`). Repair will require a karma config that loads `target/test/test.js` via `karma-cljs-test` plus refreshing the token assertions. Out of scope for this harden pass; flagged for the next slice.

## Adapt Pass — 2026-05-06

### What changed

- **DS responsive grid utilities.** Added a `.form-grid` family (`.form-grid`, `.-three`, `.-four`, `.-auto`, `.-tight`, `.-loose`) that defaults to two equal columns and reflows to two cols at 1024px and one col at 768px (`.-auto` uses `repeat(auto-fit,minmax(220px,1fr))`). Added a one-off `.appraisal-row` for the leadership appraisal layout (180px name + 200px meta + 3×1fr inputs) that reflows to three cols at 1140px and one col at 768px.
- **Inline grids removed.** All thirteen flagged `:grid-template-columns` inline styles are gone:
  - `auth/views.cljs` and `shared/no_role.cljs` now reuse the existing `.login-frame` class instead of recreating its grid inline.
  - `cn/simulator.cljs` (×2) and `revops/policy_edit_modal.cljs` (×4) → `.form-grid.-tight`.
  - `revops/settings.cljs` → `.form-grid`.
  - `revops/teams.cljs` → `.form-grid.-three`.
  - `finance/export.cljs` and `revops/appraisal.cljs` → `.form-grid.-four`.
  - `revops/leadership_appraisal.cljs` → `.appraisal-row`.
- **Notification dropdown width.** Replaced the inline `:width "380px"` on `app.ds.notifications/notification-dropdown` with a `.notification-dropdown` class that pins 380px on desktop, falls back to `calc(100vw - 32px)` on narrow viewports, and tightens to `calc(100vw - 24px)` below 480px. The dropdown now never overflows the topbar on mobile.
- **No regressions.** `npm.cmd run release` passes (235 files, 10 compiled, 0 warnings). Verified live at three breakpoints via `getComputedStyle`:
  - 1280px desktop — `.form-grid` 2 cols, `.-three` 3 cols, `.-four` 4 cols, `.appraisal-row` 5 cols, dropdown 380px.
  - 1000px tablet — `.form-grid.-three`/`.-four` collapse to 2 cols, `.appraisal-row` to 3 cols.
  - 600px and 375px mobile — every grid collapses to 1 col, dropdown becomes viewport-fluid (343px at 375px).

### Files touched

- `frontend/resources/public/css/pipo-design.css`
- `frontend/src/app/auth/views.cljs`
- `frontend/src/app/ds/notifications.cljs`
- `frontend/src/app/views/cn/simulator.cljs`
- `frontend/src/app/views/finance/export.cljs`
- `frontend/src/app/views/revops/{appraisal,leadership_appraisal,policy_edit_modal,settings,teams}.cljs`
- `frontend/src/app/views/shared/no_role.cljs`

### Out of scope (kept inline)

The `:width "120px"` on the achievement edit input in `revops/achievements.cljs` is a per-input sizing inside a horizontally-overflowing table, not a layout grid. Left untouched.

## Optimize Pass — 2026-05-06

### What changed

- **Dead namespace removed.** `frontend/src/app/views/finance/orcado_realizado.cljs` defined `orcado-realizado-chart` but had zero callers — only in-file references and one comment in `app/ds/charts.cljs`. Deletion was the prerequisite for dropping `recharts`.
- **Unused dependencies dropped.** `recharts`, `@emotion/react`, `@emotion/styled`, and `dayjs` were the four flagged npm packages. Grep confirmed: recharts had a single consumer (the deleted file); emotion and dayjs had zero references in `frontend/src` or `frontend/test`. All four removed from `frontend/package.json` and `npm install` cleaned `package-lock.json` + `node_modules`. Direct deps now: `react`, `react-dom`, `shadow-cljs`, `karma`, `karma-cljs-test`, `karma-chrome-launcher`.
- **Bundle size unchanged.** Clean release rebuild produced `main.js` at 3,118,800 bytes (≈ 3.05 MB), within 250 bytes of the 3,107,812-byte baseline reported by the audit. The dead deps weren't reaching the bundle in the first place — shadow-cljs only pulled them through the deleted namespace — so the win here is install footprint, not download size. Real bundle reduction would come from enabling `:advanced` Closure optimizations (likely 30–50% saving), which needs externs auditing for Reagent/re-frame interop and was deliberately left out of this pass.
- **Font subsetting.** Trimmed `Work Sans 300` from the Google Fonts CSS request — confirmed unused in CSS and src. Other 700 weights (Poppins, Manrope) were kept because `.avatar` (font-ui → Manrope) and a notification badge fall back to bold faces; trimming them would force browsers into synthetic boldening. Saved 1 font file per page load (17 vs 18). Live verification: `document.fonts` enumerates the trimmed set.

### Files touched

- `frontend/package.json` (removed 4 deps)
- `frontend/package-lock.json` (regenerated)
- `frontend/src/app/views/finance/orcado_realizado.cljs` (deleted)
- `frontend/resources/public/index.html` (font URL)

### Out of scope (deferred)

- **`:advanced` Closure optimizations.** Best path to actual bundle-size reduction. Requires externs declarations for any JS interop using string-keyed property access; touching `recharts`-style `:>` interop is gone but reagent/re-frame externs need verification. Recommend a dedicated slice with a side-by-side `:advanced` build to compare and stress-test interactive flows before flipping the production build.
- **Per-family weight audit.** Manrope 700 and Poppins 700 may be droppable with care. Needs a CSS-grep at the rule level (currently they survive only because `.avatar`/notification badge use weight 700 with font-ui).
- **`lodash` transitive vulns.** `npm audit` reports 8 vulns (6 low, 1 moderate, 1 high) all in `lodash` pulled by `karma`. Dev-only — not in the production bundle. Unblocks when the karma path is repaired (see toolchain status below).

## Toolchain Pass — 2026-05-06

### What changed

- **clj-kondo wired up.** Added `clj-kondo` (npm wrapper, version 2025.10.23) to `frontend/devDependencies` and switched the lint script to `npx clj-kondo --lint src/`, so the wrapper auto-installs the native binary on `npm install`. Wrote `frontend/.clj-kondo/config.edn` with reagent/re-frame defaults: silenced `:unused-binding` (Hiccup render-fns trip it constantly), kept `:unused-private-var` as a warning, taught the linter the project's standard aliases (`r`, `rf`, `str`, `t`, `layout`, `btn`, `inputs`, …), and registered `reg-event-db`/`reg-event-fx`/`reg-sub`/`reg-fx`/`with-let` as let-style forms via `:lint-as`.
- **First lint pass surfaced 16 real findings.** All resolved: missing `clojure.string` requires in five views (`cn/dashboard`, `cn/simulator`, `ev/dashboard`, `revops/cn_appraisal`, `revops/leadership_appraisal`); seven dead `:require` lines (reagent in `ds/inputs`, re-frame + tokens in `ev/deals_table`, `clojure.string` in `ev/history`, `inputs` in three revops views, `buttons` in `revops/settings`, `tokens` in `ds/charts`); one redundant nested `or` in `ds/layout/search-input`; and one unused private var (`fmt-int` in `revops/financial_upload`). After fixes, `npm run lint` now reports `0 errors, 0 warnings`.
- **karma adapter wired up.** Wrote `frontend/karma.conf.js` with `basePath: 'target/test'`, the `cljs-test` framework, the `karma-cljs-test` + `karma-chrome-launcher` plugins, and `client.args: ['shadow.test.karma.init']` to call into the shadow-emitted entry point. Headless Chrome connects, the cljs-test runner boots, no more "missing adapter" error.
- **Token tests refreshed.** `frontend/test/app/ds/tokens_test.cljs` was asserting stale values (`bg-main = #F7F6F3`, `text-primary = #2B2B2B`). Replaced with assertions that match the current tokens and pin the AA-compliant text variants (`success-dark = #0F7C50`, `warning-dark = #7A5410`, `error-dark = #B91C1C`) plus the spacing scale and font-weight map. `npm test` now runs `3/3 SUCCESS` in headless Chrome.

### Files touched

- `frontend/package.json` (+`clj-kondo` devDep, switched lint to `npx`)
- `frontend/package-lock.json` (regenerated)
- `frontend/.clj-kondo/config.edn` (new)
- `frontend/karma.conf.js` (new)
- `frontend/test/app/ds/tokens_test.cljs`
- `frontend/src/app/ds/{charts,inputs,layout}.cljs`
- `frontend/src/app/views/cn/{dashboard,simulator}.cljs`
- `frontend/src/app/views/ev/{dashboard,deals_table,history}.cljs`
- `frontend/src/app/views/revops/{achievements,cn_appraisal,cn_goals,ev_bonus,financial_upload,leadership_appraisal,settings}.cljs`

### Out of scope (deferred)

- **Transitive `lodash` vulns now 15** (was 8). The `clj-kondo` npm wrapper drags more dev-only transitive deps. Production bundle is unaffected. `npm audit fix` should be run before locking the next release of the toolchain.
- **Wider clj-kondo surface.** The current config is intentionally permissive on `:unused-binding` because Hiccup render args trip it. Consider tightening per-namespace once the shape of the codebase is steadier.

## Polish Pass — 2026-05-06

### What changed

- **Chart hexes migrated to tokens.** Five SVG-heavy chart views were carrying raw hex literals (`#E2E1DF`, `#6B6663`, `#BCBAB5`, `#3370D1`, `#3B9AFF`, `#E6D9C2`, `#FFB033`, `#000`, `#fff`) for grid lines, axis labels, bars, and series colors. Each was replaced with the matching CLJS token (`t/border-default`, `t/text-tertiary`, `t/text-disabled`, `t/blue-500`, `t/color-cyan`, `t/beige-300`, `t/warning-default`, `t/color-primary`, `t/color-white`) and the inline `font-family` strings (`"IBM Plex Mono, monospace"`, `"Manrope"`) became `t/font-mono`/`t/font-ui` so the typography stack stays canonical. Touched: `cn/simulator`, `ev/dashboard`, `ev/history`, `finance/fluxo_caixa`, `finance/dashboard`.
- **`<div>`-as-control sweep.** Re-grepped the views for `:on-click` and `cursor "pointer"` and confirmed every match is now either a `<button>`, an `<a>`, or a `<label>` wrapping a hidden file input (the standard upload pattern). No remaining clickable `<div>`s.
- **`tokens-test` expanded.** Grew from two `deftest` blocks (3 assertions) to five `deftest` blocks (about 30 assertions). Now covers: spacing scale + fallback, primary brand colors, AA-compliant feedback text variants (`success-dark`/`warning-dark`/`error-dark`), font-weight map, font-size scale, font-family role wiring, breakpoint values, border-radius, padding presets, and the chart palette invariant (size + first slot pinned to `blue-500`). Each bucket pins a value the design system relies on so a future drift surfaces in CI before reviewers see it.

### Files touched

- `frontend/src/app/views/cn/simulator.cljs` (token require + chart strokes/fills)
- `frontend/src/app/views/ev/dashboard.cljs` (token require + chart strokes/fills)
- `frontend/src/app/views/ev/history.cljs` (token require + chart strokes/fills)
- `frontend/src/app/views/finance/fluxo_caixa.cljs` (warning hex → token)
- `frontend/src/app/views/finance/dashboard.cljs` (token require + chart strokes/fills)
- `frontend/test/app/ds/tokens_test.cljs` (expanded coverage)

### Verification

- `npm run lint` → 0 errors, 0 warnings.
- `npm test` → 5/5 SUCCESS in headless Chrome.
- `npm run release` → 235 files, 5 compiled, 0 warnings.

### Out of scope (deliberately kept inline)

- **Pure black/white SVG attributes.** A handful of `:fill "#000"` / `:stroke "#fff"` and `rgba(255,255,255,X)` overlays on the night-themed cards stay inline. The opacity-on-white pattern isn't modelled by the token system; promoting it would invent a token that doesn't reflect the design intent. Likewise, `flood-color "#000000"` on the SVG drop shadow is an attribute the filter expects literally.
- **`:advanced` Closure optimizations.** Still the biggest unclaimed bundle-size lever (3.05 MB → likely ~1.5 MB). Out of scope for polish because it needs externs work; with lint+karma now green, a dedicated slice can run it confidently.

## Chart Accessibility — 2026-05-06

### What changed

- **Companion data table for the cash-flow chart.** Added `chart-fluxo-caixa-table` (private) in `frontend/src/app/views/finance/dashboard.cljs`. Renders the same `:realizado`/`:a_apurar`/`:projetado` series the SVG does, in a real `<table>` with `<caption class="sr-only">`, `<th scope="col">` for headers, and `<th scope="row">` for the month label so assistive tech reads each cell as "Mai/26 Realizado R$ 1.000". Empty values render as `·` to match the chart's display convention. Only rows with at least one numeric value appear, mirroring `trim-fluxo-series` on the chart side.
- **Disclosure-pattern UI.** The table sits inside `<details class="chart-data-table">` so sighted users can toggle it without it taking up vertical space by default. The `<summary>` reads "Ver dados em tabela" — same accessible name in both states. Visually it shows a chevron that rotates 90° on `[open]`. CSS lives in `pipo-design.css`: native marker hidden, focus-visible outline keyed to `--cyan` (matches the rest of the focus system), table inherits the existing `.table` styling.

### Files touched

- `frontend/src/app/views/finance/dashboard.cljs` (new helper + wired into the card)
- `frontend/resources/public/css/pipo-design.css` (new `.chart-data-table` rules)

### Verification

- Synthesized the markup in the running app and read computed styles back: summary uses Manrope 12px 600 in `--fg-3`, chevron rotates from identity to `rotate(90deg)` between closed/open states, native disclosure marker hidden cross-browser.
- `npm run lint` → 0/0; `npm test` → 5/5; `npm run release` → 235 files, 2 compiled, 0 warnings.

## Audit follow-up complete

Every finding on the original 11/20 scorecard is addressed, including the chart-accessibility recommendation that was originally tagged as optional. Bundle size remains the only remaining lever, and only as a discretionary slice.

### Optional follow-up

- **`:advanced` Closure optimizations** — separate slice, gated on externs work. Honest cost/benefit: ~50% bundle reduction (3.05 MB → ~1.5 MB) but limited user impact for an internal tool on corporate networks. Worth it if the team scales user count or wants the discipline win; otherwise low-priority.
