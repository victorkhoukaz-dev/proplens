# PropLens Design System

> **Scope and source of truth.** This is a documentation-only record of the UI that is currently implemented in this repository. It describes the rendered PropLens manual NFL prop evaluator, not the broader betting-domain logic. The canonical implementation is [`static/index.html`](static/index.html), [`static/styles.css`](static/styles.css), [`static/app.js`](static/app.js), and [`static/phase11.js`](static/phase11.js), served by [`app/main.py`](app/main.py). Values below are implementation values, not a proposed replacement design system.

## 1. Overall Design Philosophy

PropLens is a **calm, dark, analytical workspace** rather than a dense sports-betting dashboard. Its visual character is “focused decision support”: a user does one meaningful task in a spacious two-column screen, sees the outcome beside the input, and is repeatedly reminded of the evidence limits. The product feels polished because it avoids competing navigation, visual noise, and loud success colours; it makes the current workflow easy to scan before it makes it powerful.

- **One job per screen.** The page has one headline, one sequential evaluator form, and one persistent result panel. Supporting education is a quiet three-item footer, not a separate onboarding flow.
- **Progressive disclosure.** The user cannot choose a market until a player is selected, cannot choose a side until a market is selected, and does not see line/odds fields until a side is selected. Empty placeholders state the next prerequisite rather than showing a disabled wall of controls.
- **Measured confidence.** Mint (`--accent`) means selected, enabled, or positive—not celebration. Blue marks neutral informational content and amber marks a neutral/non-positive evidence outcome. Copy is specific about uncertainty.
- **Comfortable desktop density.** Large type and generous 22–78px gaps establish hierarchy, while compact mono numerals make values and labels scan quickly. Cards hold a coherent working area, not every individual datum.
- **Mobile is a reflow, not a different product.** The same page remains present; the evaluator/result columns and paired fields stack. Low-priority top-bar context disappears, while the two actual actions remain reachable.
- **Polished restraint.** There is one subtle radial background glow, soft low-opacity card gradients/shadows, thin blue-gray borders, a very small radius family, and no chart decoration, gradients in buttons, dense sidebars, or animated spectacle.

The patterns work together because the wide, quiet page gives the headline and current decision room to breathe, while the contained cards turn a potentially technical calculation into a short, legible sequence. The mono accent style visually distinguishes data/provenance from prose without creating a second competing visual language.

## 2. Design Tokens

### Implemented CSS custom properties

The global token set is intentionally small and appears in [`static/styles.css`](static/styles.css):

```css
:root {
  --bg: #0b1020;
  --surface: #121a2d; /* Defined but not currently consumed by a selector. */
  --line: #293652;
  --text: #f4f7fb;
  --muted: #98a6bf;
  --accent: #75f0b4;
  --blue: #8bc5ff;
  --amber: #ffd27a;
  --sans: 'DM Sans', sans-serif;
  --mono: 'DM Mono', monospace;
}
```

| Role | Actual value and use |
| --- | --- |
| App background | `#0b1020`, with `radial-gradient(circle at 75% -10%, #1d3653 0, transparent 34%)` on `body` |
| Card gradient | `linear-gradient(145deg, rgba(24,34,56,.95), rgba(14,21,37,.94))` |
| Form/input surface | `#0e1526`; selectable button surface `#101829`; autocomplete surface `#1b2740` |
| Modal surface | `#17223a`; metric hero `#0c1425`; metric cell `rgba(11,16,32,.55)` |
| Primary text | `#f4f7fb`; heading muted second line `#aebad0`; label text `#dce5f5` |
| Supporting text | `#98a6bf`; secondary selectable text `#cbd6e8` |
| Structural border | `#293652`; top/footer divider `rgba(152,166,191,.14)`; modal border `#354561` |
| Mint accent / positive | `#75f0b4`, selected-control background `rgba(117,240,180,.12)`, selected inset focus ring `rgba(117,240,180,.1)` |
| Informational blue | `#8bc5ff`, icon background `rgba(139,197,255,.12)`, projection panel border/background use `.22`/`.055` opacity |
| Amber / neutral result | `#ffd27a`, badge background `rgba(255,210,122,.08)` and border `.4` |
| Danger (library) | `#ff8d9b` text with `#6c3d50` border |
| Success toast | background `#e8fff4`, text `#083524` |
| Error toast | background `#ffe8eb`, text `#701b2a` |

### Radius, shadows, spacing, and layers

- **Radius scale in use:** `7px` small library action; `8px` mark/icon and market controls; `9px` inputs, player selection, toast; `10px` search/metric/container controls; `14px` metric hero; `15px` modal; `17px` empty-state icon; `18px` principal cards; `99px` chips/badges. Do not introduce large rounded “pill-card” containers.
- **Shadows:** working cards use `0 20px 60px rgba(0,0,0,.15)`; modals use a much stronger `0 25px 80px rgba(0,0,0,.45)`; toasts use `0 8px 30px rgba(0,0,0,.25)`. Borders establish separation first; shadow is secondary.
- **Repeated spacing values:** `7–15px` within small controls; `18–28px` within a card; `42–46px` between page regions; `78px` top workspace breathing room on desktop. Common concrete gaps: `8`, `10`, `14`, `15`, `18`, `20`, `22`, `25`, `28`, `32`, `42`, `46`, `48`, `78px`.
- **Sizing conventions:** top bar `74px` desktop / `62px` mobile; icon button `32×32px`; brand mark `28×28px`; input padding `12px`; full primary button padding `14px`; fixed stake control width `130px`; result panel min-height `600px` desktop / `420px` at `≤850px`.
- **Opacity conventions:** very light visual hierarchy uses `.055`, `.08`, `.1`, `.12`, `.14`, `.15`, `.22`, `.4`, `.45`, `.55`, `.72`, `.94`, `.95`. Use translucent accent backgrounds for selection, never opaque neon panels.
- **z-index:** autocomplete container `3`; modal backdrop `10`; toast container `20`. No other explicit elevation scale exists.

**Current inconsistency to preserve consciously or consolidate later:** the newer projection-library and benchmark rules are inline `<style>` blocks in `index.html`, not in `styles.css`. They repeat raw token values rather than only using variables. They are real current styles and must not be overlooked when reproducing the look.

## 3. Typography

Fonts are loaded from Google Fonts: **DM Sans** weights `400, 500, 600, 700` for prose/UI, and **DM Mono** weights `400, 500` for numerical/data/provenance cues. There is no local fallback beyond `sans-serif`/`monospace`.

| Level | Actual implementation | Use |
| --- | --- | --- |
| Product name | 20px, 700 DM Sans, `letter-spacing: -.5px` | Top-left brand only |
| Product context | 10px, 500 DM Mono, `.11em` tracking, muted | Small all-caps product descriptor |
| Eyebrow | 11px, 500 DM Mono, `.14em` tracking, mint | Section provenance / step label, all-caps source text |
| Page title | `clamp(34px, 5vw, 56px)`, line-height `1.03`, `-2.5px` tracking | One high-impact page title; muted `<span>` supplies the second thought |
| Card/modal H2 | 23px, `-.7px` tracking | Primary card and modal heading |
| Result title | 25px | The evaluated prop summary only |
| Card H3 | 13px; supporting explainer H3 15px | Result sub-sections / footer explanation heading |
| Body lead | 17px, line-height `1.65`, muted | Intro explanation |
| Body text | 14px, modal line-height `1.55`; empty-state line-height `1.6` | Explanatory copy |
| Labels/controls | 13px, 600 | Form labels and segmented/market controls |
| Help / table-like data | 11–12px; line-height `1.45–1.55` | Helper text, metadata, metric labels, warnings |
| Data display | 17px 500 DM Mono; hero 42px 500 DM Mono, `-2px` tracking | Metrics, prices, EV, numerical values |
| Chip/badge | 10–11px DM Mono, evidence badge `.06em` tracking | Provenance, compact status, source labels |

Use DM Sans for readable intent and DM Mono for values, identifiers, small labels, and trust/evidence cues. The design does **not** use oversized all-caps headings or a generic 12/14/16/20 type scale everywhere; the large page title and 42px EV metric are intentional exceptions.

## 4. Application Shell & Layout

The shell is a simple full-page layout—there is **no sidebar, breadcrumb, secondary nav rail, sticky header, or dashboard grid**.

```text
body (dark radial glow)
└─ .app-shell
   ├─ .topbar (max 1240px, 74px)
   └─ main.workspace (max 1120px)
      ├─ .intro (max 700px)
      ├─ .evaluator-grid (two cards)
      └─ .how-it-works (three short columns)
```

- The top bar is centered at `max-width: 1240px`, horizontally padded `28px` (`18px` at `≤850px`). It has only a bottom divider; it is not fixed or sticky.
- Main content is centered at `max-width: 1120px`, desktop padding `78px 28px 48px`; its title block maxes at `700px` and copy at `620px`.
- The desktop task grid is `minmax(0,1fr) minmax(380px,.88fr)` with a `22px` gap. At a 1280px viewport it rendered as approximately `554px` evaluator + `488px` result.
- Principal cards have `28px` padding, 1px border, 18px radius, and the shared deep gradient. The right result panel uses flex centering until it contains results.
- The explanatory footer starts `46px` below the cards, has `28px` top padding and a light divider. It has three equal columns with a `32px` gap.
- Normal document scrolling is used. Modal backdrops are `position: fixed; inset: 0`; the visible CSS does not set a scroll lock or internal max-height/overflow rule for modal content.

## 5. Navigation

Navigation is intentionally minimal and action-based:

- The brand is the only route link and returns to `/`.
- Right-aligned top-bar items are: a read-only bankroll chip, text button **Projection library**, text button **Import projections**, and bordered gear icon for settings.
- Text actions have no container or border and hover from primary text to mint. The gear is a 32px bordered icon button. Action spacing is `14px` (`8px` mobile).
- There is no active/inactive page-navigation state, sidebar grouping, collapsed nav, breadcrumbs, tabs across pages, or mobile hamburger menu.
- The import modal has local two-tab navigation: `Upload file` and `Paste text`. A tab is simple text with `6px 0` padding and a `2px` bottom border; active is mint and inactive is muted. This is appropriate for mutually exclusive content inside one contained operation, not for primary app navigation.

At `≤850px`, the brand-context label and bankroll chip are hidden; the two text actions and settings remain. At `≤560px`, action text reduces to `12px` and the bar remains horizontal. Future family apps should use similarly short, high-value global navigation and reserve sidebars for genuinely multi-section workflows.

## 6. Cards, Panels & Containers

### Canonical working card

Use `.evaluator-card` / `.result-panel` for the main paired task-and-outcome relationship: 28px padded, 18px radius, deep gradient, `--line` border, subtle large shadow. A card header uses `.card-heading`: split left/right content, 25px bottom margin, 20px bottom padding, and divider.

### Result hierarchy

- Empty result: visually centered narrow (`max-width:330px`) message, blue 52px square-ish icon tile (`17px` radius), H2, muted explanatory paragraph. It explains what will appear rather than saying only “No data.”
- Populated result: evidence badge → summary → large metric hero → two-column metric grid → bordered explanatory sections. The `metric-hero` is more prominent through a darker solid surface, 19px padding, 14px radius, and 42px mint/amber mono number—not a heavier shadow.
- `metric-box`: 13px padding, 10px radius, line border, translucent dark background. Keep a 2-column grid (`10px` gap) until mobile.

### Supporting containers

- `player-selected` is a small contextual confirmation panel: 11×13px padding, mint-tinted border/background. Its empty version becomes a dashed border and transparent muted message.
- `projection-benchmark` is an information panel, not a main card: 12px padding, 10px radius, low-opacity blue framing. Its inner cells are compact and visually activate with mint when the matching market is selected.
- Library records are compact list cards: 15px padding, 10px radius, input-dark surface. The active snapshot is distinguished only by a mint border and small ACTIVE pill.

Do not add cards just to break up paragraphs. Use cards for a work unit, an outcome, a compact selected state, or a repeatable saved item.

## 7. Tables & Lists

There is **no data-table component, table library, pagination, sortable header, filter bar, or row-selection table in the current UI**. Do not claim otherwise when applying this system.

The closest canonical list patterns are:

1. **Autocomplete suggestions** (`.suggestion`, generated in `static/app.js`): full-width buttons, 11px vertical / 13px horizontal padding, left player/team/position grouping, right market count, 1px borders joined by removing all but the final row’s bottom border. Hover is `#263552`; the final row has `0 0 9px 9px` bottom radius. It is limited to 10 API matches and appears after a 180ms input debounce.
2. **Projection library** (`renderLibrary()` in `static/phase11.js`): vertical grid with 10px gap; each record has a title/metadata header, secondary count/date copy, optional ACTIVE badge, and wrapped action row. There is an explicit empty state and loading text.
3. **Metric grid**: small label/value cells, not tabular rows. Use it for a few comparable output values only.

For future large data sets, add a table only when the workflow needs comparison across many records. It should inherit the 12–13px UI text, line borders, muted headers, input-dark surfaces, and conservative mint selection; it cannot be copied from an existing table because one does not exist here.

## 8. Forms & Inputs

The evaluator form is the canonical form pattern: label, one control, a concise help line where it prevents an error, then 22px before the next form block.

- **Labels:** block, 13px/600, `#dce5f5`, 9px bottom margin. Optional is a muted normal-weight inline span.
- **Text/number/select/textarea:** `width:100%`, `12px` padding, `9px` radius, `#0e1526` fill, `--line` border, `--text` foreground, no native outline. On focus: mint border and `0 0 0 3px rgba(117,240,180,.1)`.
- **Search:** composed control with muted search glyph, transparent internal input (13px vertical / 10px horizontal padding), and an optional 20px clear button. It uses `autocomplete="off"`, listbox semantics on the results container, and an inline selected-player confirmation.
- **Numeric pairs:** two equal columns with 15px gap; line and odds are hidden until a side is chosen. They stack at `≤560px`.
- **Stake:** a compact right-aligned 130px compound control with a separate `$` prefix. It is optional and visually separated from preceding fields by an 18px top border gap.
- **Choice controls:** market chips wrap in a flex row; Over/Under are equal-width segmented buttons. Unselected is dark; hover shifts border to `#7b9bc5`; active becomes mint text/border/tint.
- **File import and paste:** local modal tabs reveal one path at a time. File accept list is `.csv,.txt,.xlsx,.xlsm`; text uses an eight-row textarea.
- **Validation and disabled behavior:** the primary evaluator starts disabled and enables only when all required sequential inputs are populated. File import enables on chosen file. On API failure, a red toast presents the returned error. There are no red input borders, inline field errors, required asterisks, checkboxes, radio controls, switches, date controls, or autocomplete keyboard navigation in the implementation.

## 9. Buttons & Actions

| Type | Implementation | Correct use |
| --- | --- | --- |
| Primary submit | `.evaluate-button`: full width, 14px padding, 10px radius, mint fill, dark `#0a2118` text, 700 weight | One final high-confidence action per primary card/form |
| Light modal submit | `.modal-card .secondary-button`: full width, 14px padding, `#e3edfb` fill and `#10213a` text | Import/save action inside a modal; despite class name, it is visually prominent |
| Text action | `.text-button`: transparent/borderless, 600 weight, hover mint | Top-bar secondary actions |
| Selection button | `.market-button`, `.side-button`: 9×10px padding, 8px radius, bordered dark surface | Finite in-context choices; active is mint |
| Small library action | `.library-action`: 7×9px, 7px radius, line border | Activate or delete a saved snapshot; danger is pink text/border |
| Icon/close | `.icon-button` (32px square) and `.modal-close` (24px glyph) | A familiar compact action with an `aria-label` |

Disabled evaluator styling is exactly `opacity:.38; cursor:not-allowed`; the code changes its copy to `Calculating…` while requests run. Import buttons change to `Importing…`; the save-settings action disables but does not change visible text. There are no implemented pressed-state, loading spinner, or generalized focus style for buttons. Add those only as a carefully tested enhancement, not as documented current behavior.

## 10. Modals, Dialogs, Popovers & Menus

Three fixed-center modal dialogs exist: import, projection library, and settings.

- Backdrop: `position:fixed; inset:0; z-index:10; display:grid; place-items:center; padding:20px; background:rgba(3,7,15,.72)`.
- Default modal: `width:min(530px,100%)`, 28px padding, 15px radius, `#17223a` surface, `#354561` border, strong modal shadow. Library widens to `min(720px,100%)`.
- Header: eyebrow, H2, muted explanatory copy; 24px × close glyph at `top:13px; right:16px`.
- Modal fields begin 17px after their preceding label area; import tabs have 22px top / 15px bottom margins. Primary footer actions are simply the full-width action at the end rather than a separate aligned footer.
- Dismissal: the close button works and clicking the exposed backdrop closes. Library deletion uses native `window.confirm()` with explicit permanent-deletion language.

There are no custom dropdown/popover/tooltip components. **Accessibility limitation:** dialogs have `role="dialog"`, `aria-modal="true"`, and labelled titles, but no Escape handling, focus trap, focus restoration, or automated initial focus. Native confirm supplies browser keyboard behavior; custom modals do not yet implement it. Treat these as improvement opportunities, not required family behavior.

## 11. Status & Feedback

- **Evidence badge:** compact mono pill near results. Mint bordered/tinted badge for positive evidence state; `.neutral` swaps to amber. It is a semantic qualifier, not a generic status rainbow.
- **Active snapshot:** ACTIVE mint pill with 4×7px padding, `99px` radius, 10px mono type.
- **Selection:** mint outline/tint/text conveys the currently chosen market, side, or benchmark cell.
- **Success toast:** fixed bottom-right (`right/bottom:20px`, `z-index:20`), pale mint background with dark green text; 11×14px padding, 9px radius, 13px/600, stack gap 9px. Automatically removes after 4.2 seconds.
- **Error toast:** same geometry, pale pink/red background and dark red text. API errors are normalized to the server detail or `Something went wrong.`
- **Progress:** no spinner or skeleton. Buttons lock and replace text during import/evaluation; library shows `Loading projection sets…` as muted helper text.
- **Warnings:** result content uses a titled “Before you bet” section and muted 12px list rather than a red alert box. This calm explanatory approach is central to the product’s evidence-first tone.

## 12. Empty, Loading & Error States

The UI favors guidance that names the next useful action.

- Initial result is a centered icon + “Your evaluation will appear here” explanation.
- Before a player is selected, market area says “Choose a player first”; the selected-player area says “Start by searching a player.”
- No autocomplete match renders “No matching loaded projection.”
- The library has both a loading line and a first-use message: “No saved projection sets yet. Import a weekly projection file to create one.”
- Import/help text tells the user to load a FantasyPoints file if the search is empty.
- Request failures use temporary error toasts; the modal stays available so the user can correct the issue.

There are no dedicated offline, permissions/access, network-retry, or full-screen failure screens. Future apps should retain the concrete, low-alarm tone but implement workflow-specific recovery states where availability matters.

## 13. Icons

There is **no icon library dependency**. Current icons are Unicode glyphs: `P` in the brand mark, `⚙` settings, `⌕` search, `×` clear/close, `→` primary action, and `✦` empty result. They are functional except the decorative result sparkle.

- Brand mark is `28px` square, 8px radius, 16px DM Mono.
- Settings is a 16px glyph inside a 32px bordered control.
- Result icon is 27px inside a 52px blue-tinted 17px-radius tile.
- Close glyph is 24px with a text label for screen readers.

If an app needs richer icons, choose one consistent outlined icon library and retain current compact sizes, muted/default colour, mint hover/selection, and accessible labels. Do not mix multiple icon visual languages.

## 14. Interaction & Micro-UX

- Search debounces API calls by **180ms**; searching on focus makes a zero-state chooser feel responsive. Selecting a player clears suggestions and reveals only relevant markets.
- Clearing a selection resets all dependent controls and intentionally returns focus to the search input.
- Selecting a market clears the side, hides prices, updates the benchmark highlight, and presets `0.5` for anytime-touchdown. Selecting side reveals prices. This is a strong canonical example of dependency-aware progressive disclosure.
- Selection is visible through mint, not only content changes. Autocomplete and choice buttons have subtle hover border/background feedback; most other controls rely on focus/disabled state rather than animation.
- Evaluation keeps the old result hidden until a valid response; when successful, new result content is announced through `aria-live="polite"` on the result panel. A MutationObserver augments result content with the sizing ceiling/TD clarification after render.
- Projection library loading happens on open; activating a different set clears the player and shows a confirmation toast. Permanent deletion asks for confirmation first.
- Toasts leave automatically after 4.2 seconds; they do not animate or provide manual dismissal.
- No transitions/animations are declared. This makes interaction feel immediate and analytical rather than playful.

## 15. Responsive Design

| Range | Actual behavior |
| --- | --- |
| Large / normal desktop (`>850px`) | 1120px content canvas; two-column evaluator/result grid; three-column explainer; full 74px header, bankroll and brand context visible. |
| Tablet / narrow desktop (`≤850px`) | Evaluator/result grid becomes one column; result minimum height becomes 420px; workspace top padding drops to 48px; explainer remains 3 columns but gap drops to 18px; header horizontal padding becomes 18px; bankroll/context hide. |
| Mobile (`≤560px`) | Workspace `36px 16px`; header 62px; text actions 12px with 8px gaps; card padding 20px; number pair and three explainer blocks each become one column; title tracking becomes `-1.6px`; book chip is kept on one line. |

There are only the two CSS breakpoints above. At exactly 850px, rendered behavior was a single 778.7px work column and still three 247.6px explanatory columns; at 560px the numerical grid and explainer stacked. No sidebar/table/mobile-nav transformation is required because none exists.

## 16. Accessibility

### Existing conventions

- Semantic `header`, `main`, `section`, `form`, `label`, `button`, and input elements are used.
- Text inputs are paired with labels where applicable; controls use `inputmode` for numeric mobile entry.
- Brand, settings, clear, and close controls have `aria-label`s; modal sections use `role="dialog"`, `aria-modal`, and `aria-labelledby`.
- Search declares `aria-autocomplete="list"`; results container declares `role="listbox"`; result and toast areas use `aria-live="polite"`.
- Strong dark/light text contrast is generally intentional; disabled action uses opacity, so verify its contrast if evolving it.

### Current weaknesses (do not normalize them)

- Search lacks `aria-controls`, option roles/IDs, active-descendant management, and keyboard selection.
- The input’s `aria-expanded` is hard-coded false, even when suggestions are visible.
- Modal focus is not trapped/restored and Escape does not dismiss; buttons have no explicit `:focus-visible` treatment beyond native behavior, and menu/modal focus order is not managed.
- Several glyph icons are text characters, not semantic icon assets; market/side groups do not use radio semantics.
- Touch targets for text actions and library actions are not explicitly guaranteed to meet a 44px target.
- No `prefers-reduced-motion` rules exist (currently less consequential because there are no CSS animations).

Future implementations should correct these limitations while keeping the same visual language.

## 17. Reusable Components

This is vanilla DOM code, so these are canonical **CSS/markup/renderer patterns**, not framework components.

| Pattern | Source | Purpose and why it is canonical |
| --- | --- | --- |
| Application shell / top bar | `static/index.html` `.topbar`, `.workspace`; `static/styles.css` | The complete minimal navigation and centered content-width pattern. |
| Evaluator card | `static/index.html` `#evaluator-form`; `static/styles.css` `.evaluator-card`, `.card-heading`, `.form-block` | Best reference for sequential form hierarchy, contextual help, compact chips, and a single strong CTA. |
| Player search + selection | `static/app.js` `searchPlayers`, `selectPlayer`, `clearPlayer`; `.search-field`, `.suggestion`, `.player-selected` | Best pattern for a dependency-driven search and clear selected-state feedback. |
| Market/side selector | `static/app.js` `selectMarket`, `selectSide`; `.market-button`, `.side-button` | Canonical wrap chips and binary segmented selection with mint active state. |
| Benchmark panel | inline style in `static/index.html`; `renderBenchmark` | Compact information panel that lets selected controls and imported data reinforce each other. |
| Result panel | `static/app.js` `renderResult`; `.result-*`, `.metric-*`, `.evidence-badge` | Best hierarchy for an analytical outcome: qualification, headline number, supporting metrics, then explanation/warnings. |
| Modal system | `static/index.html` three `.modal-backdrop`s; `app.js` `openModal/closeModal` | Canonical fixed, contained task dialog and tab treatment. Improve keyboard management when copying. |
| Toast system | `static/app.js` `toast`; `static/phase11.js` `showMessage`; `.toast-container`, `.toast` | Actual success/error feedback geometry and 4.2s lifecycle. Note the duplicated helper implementation. |
| Projection library cards | `static/phase11.js` `renderLibrary`; inline `.library-*` CSS | Canonical compact saved-item list, active state, metadata, and destructive action. |

## 18. Canonical Screens / States

There is one route, so “screens” are important page states and dialogs.

1. **Initial evaluator / empty result** — `static/index.html` lines 21–35. Best overall design reference: page hierarchy, desktop two-column composition, first-use messaging, and supporting explainer.
2. **Selected-player progressive form** — `static/app.js` `selectPlayer`, `selectMarket`, and `selectSide`. Best reference for staged disclosure, selected-state language, benchmark highlighting, and form density.
3. **Evaluated result** — `static/app.js` `renderResult`. Best information hierarchy: evidence qualifier, EV hero, metric grid, transparent support, warning list, optional sizing/TD clarification supplied by `phase11.js`.
4. **Import projections dialog** — `static/index.html` import modal and `.import-tabs`. Best form modal and compact tab pattern.
5. **Projection library dialog** — `static/phase11.js` `renderLibrary`. Best repeatable list, active item, empty/loading state, and destructive-action wording.
6. **Settings dialog** — `static/index.html` settings modal. Best compact configuration form: a small number of clearly explained preferences and one save action.
7. **Mobile reflow** — media rules at the end of `static/styles.css`. Best reference for preserving task order while selectively hiding nonessential header context.

## 19. Libraries & Technical Foundation

- **Server / frontend delivery:** Python FastAPI with `StaticFiles` and `FileResponse` in `app/main.py`. This UI is static HTML/JS, not React/Vue/Svelte.
- **CSS:** one custom hand-authored/minified stylesheet plus two inline style blocks. There is no Tailwind configuration, CSS framework, CSS Modules, Sass, or build step.
- **JavaScript:** vanilla browser APIs (`fetch`, DOM creation, `MutationObserver`, `FormData`, `window.confirm`). There is no component, routing, state, animation, form, table, chart, or icon package.
- **Fonts:** externally loaded Google Fonts—DM Sans and DM Mono.
- **Backend dependencies relevant to UI:** FastAPI, Pydantic, `python-multipart`, Jinja2/Aiofiles in `requirements.txt`; no browser UI package is fundamental to recreating the visual system.

The fundamental ingredients are the token set, fonts, custom CSS, semantic HTML, and progressive JavaScript behaviors. FastAPI is fundamental to this project’s delivery, but not to adopting the design language in another stack. Scientific/odds libraries are business logic and not design-system dependencies.

## 20. UX Rules & Heuristics

1. Give each primary page one obvious decision/workflow; use a paired outcome panel when result context matters.
2. Lead with a human title and a short transparent explanation; use an all-caps mono eyebrow for provenance, stage, or source—not decoration.
3. Use mint only for the primary action, current selection, active record, or favourable/positive result. Use amber for caution/neutrality and blue for informational framing.
4. Reveal downstream controls only when upstream choices make them meaningful. Explain prerequisites in place.
5. Keep full-width primary actions inside cards; use borderless text actions in the header and compact bordered actions within records.
6. Use DM Mono for values, odds, labels, badges, and compact provenance; let DM Sans carry explanations.
7. Use thin borders and low-opacity dark surfaces before adding shadows. Keep the palette dark, quiet, and limited.
8. Make empty states instructional and concrete: say what will appear, why it is missing, and the next safe action.
9. Keep uncertainty and warnings inside the normal hierarchy. Do not rely on alarming red warning panels for normal caveats.
10. On mobile, stack work in the same logical order and hide only supporting header context; do not remove core actions or force a different workflow.
11. Require confirmation for permanent/destructive actions and name the consequence explicitly.
12. Improve current accessibility gaps when building new work without changing the visual hierarchy.

## 21. Anti-Patterns

Avoid these because they would make a product feel unlike PropLens:

- Bright white pages, glassmorphism, rainbow status chips, saturated gradients, or multiple competing accent colours.
- A heavy persistent sidebar, dashboard-widget sprawl, breadcrumb stacks, or a top bar crowded with low-value controls on a single-task screen.
- Oversized rounded cards everywhere, thick borders, conspicuous drop shadows, or a generic “card for every fact” layout.
- Marketing-style giant uppercase headings, casual display fonts, or using mono for paragraphs instead of analytical data/provenance.
- Showing every field upfront, hiding prerequisites without explanation, or using modal chains for a workflow that should remain visible.
- Giant table grids/pagination for a small focused selection task; conversely, pretending this app has a table pattern when it does not.
- Excessive animation, bouncing success states, automatic optimistic success before a request completes, or spinners that obscure the current task.
- Making destructive actions visually identical to activation actions or deleting without confirmation.
- Copying the current modal keyboard limitations into a new app; retain its visual treatment but implement full accessible dialog behavior.

## Instructions for AI Coding Agents

1. Read this document before designing or restyling the destination UI.
2. Treat the described PropLens visual and UX language as the default: dark analytical canvas, restrained mint/blue/amber semantics, DM Sans + DM Mono pairing, thin borders, modest shadows, and progressive disclosure.
3. Adapt the system to the new application’s business requirements. Do not blindly copy a betting evaluator, its labels, or its domain-specific content.
4. Maintain the documented token values, radius/shadow/spacing character, typography hierarchy, selection treatment, and action hierarchy unless the destination has a justified product-specific need.
5. When this repository is accessible, inspect the canonical paths/states in sections 17 and 18 before inventing variants.
6. Preserve good existing functionality in the destination application. Do not remove workflows, data, validations, or integrations merely to make screens resemble PropLens.
7. Do not change business logic for visual consistency. Separate UI refactoring from calculation, persistence, authorization, or API changes.
8. Make reasonable UX improvements where the new workflow requires them—especially better empty/error states, scalable list/table behavior, and meaningful navigation—while retaining the same family resemblance.
9. Ensure responsive and accessible behavior. Keep the desktop-to-mobile reflow principle, add explicit focus-visible states, keyboard-accessible choices/search, and accessible modal focus handling where this implementation is incomplete.
10. Aim for sibling products, not clones: users should recognize the same calm, evidence-aware, high-clarity product family even when the new app has different screens and tasks.
