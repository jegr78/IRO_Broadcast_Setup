# ERF WSP League Profile — HUD Data Extensions + Overlay — Design

**Date:** 2026-07-30
**Issue:** #555
**Status:** Design approved, pending implementation plan
**Scope:** Three league-agnostic additions to the relay HUD data model (per-team brand
colours, a qualifying best-lap time, the race/qualifying mode), the matching base-HUD
slots, and the new machine-local `profiles/erf-wsp/` league look that consumes them.

## Motivation

The WSP broadcast design (mockups in issue #555) is a lower-third of three podium tiles
plus a bottom-right clock/badge block. The existing HUD already models a 3-car podium
(`teams p1/p2/p3` → `{number, brandKey, brandName}`), the relay race timer, and the league
logo, and per-league overlay CSS is the established customization path. Three data points
the current model does not carry:

1. Each tile's top bar is a **flat colour per brand** (Ferrari red / Porsche white / BMW
   blue — mockups 28/29/31) with a matching text colour.
2. In race mode each tile shows the car's **qualifying best lap** (`1:38.973`).
3. The bottom-right block and the quali-time row differ between **race and qualifying**
   (mockups 21 vs 22), and the HUD has no knowledge of the relay's mode.

Everything else in the mockups is either already modelled, an OBS graphic, or the sim's
own in-game HUD.

## Principle

**No WSP specifics in base code.** The base HUD only *exposes* data and geometry;
`profiles/erf-wsp/overlay/` does all styling. Every core change below is a league-agnostic
capability that any profile can consume or ignore.

## Decisions locked in brainstorming (2026-07-30)

- **Quali times live in their own Sheet tab, `Quali Times`** (`Team | Best Lap`), read like
  the crew roster and matched by `asset_key`. **The name must not be `Qualifying`** — that
  is already `DEFAULT_QUALIFYING_TAB` (`src/relay/racecast-feeds.py:1064`), the qualifying
  *schedule* tab. The issue's working name would have collided.
- **Brand colours are two new Configuration-tab columns** (`BG Color`, `Text Color`), per
  team row, joined through the existing roster — no third parser, no new join. Per-row
  rather than per-brand keeps it explicit and allows a team-specific livery colour.
- **The class badge is the existing `session` slot.** The director picks `HYPERCAR` /
  `QUALIFYING` from the Setup dropdown (Configuration `Session` vocabulary). Zero core
  code, and no English literal enters the league-agnostic base HUD. `Overlay.png` must
  therefore ship an **empty** red badge bar (the mockup skeleton has `HYPERCAR` baked in).
- **The HUD clock drops a zero hour, always** (`12:10`, not `0:12:10`). Chosen over a
  mode-gated variant with the trade-off understood: it also changes the **final hour** of a
  race for existing leagues (`0:59:12` → `59:12`). Scoped to `src/obs/hud.html` only — the
  crew-facing pages (`cockpit.html:587`, `race-control.html:442`) keep `h:mm:ss`; they are
  not on air and would drag wiki screenshots along for no broadcast benefit.
- **Best Lap format: verbatim, with two deterministic fixes** (see the format contract
  below). Comma decimals are normalized to a dot; the sheet column is documented as
  plain-text formatted.
- **Maintenance model:** quali times are entered **once between qualifying and the race**;
  brand colours are static. No panel control, no live typing during the show.

## Non-goals

- **No live timing.** The left leaderboard (1–8), sector box, track map, speed and delta in
  the mockups are the **sim's in-game HUD**. The podium stays **manually curated** (the
  producer picks p1/p2/p3); positions are static.
- **No `flag-status` use.** SAFETY CAR / RED FLAG are full-bar **OBS image graphics**
  toggled by the director on the badge position (the N24 path), like the existing
  `Flag Safety Car.png` / `Flag Red.png`. Out of `/hud/data` scope.
- **No "COMMENTARY BY …" banner** — dropped from the WSP design; the `streamer` slot goes
  unused in this profile.
- No new panel control, no new webhook action, no Companion button.

## Sheet contract (what the league maintains)

### New tab `Quali Times`

| Team | Best Lap |
|---|---|
| `Tavernello Racing #6` | `1:38.973` |

- Matched to a tile by `asset_key(stripped_team_name)` — `split_team_label` peels a trailing
  `#NNN` first, so `Tavernello Racing #6`, `Tavernello Racing` and `tavernello racing` all
  hit the same key. Robust against number/spelling variants, per the issue.
- Columns are located by header name (case-insensitive), like every other tab. A missing
  header, or a tab that was never created, yields no quali times; a *transient* fetch
  problem never blanks laps already loaded — see Core changes → 1 (Relay parsers + join).
- **The `Best Lap` column must be formatted as plain text** (`Format → Number → Plain
  text`). Otherwise Google Sheets parses `1:38.973` as a duration (38.973 *minutes*) and the
  gviz CSV export already carries the mangled value. Documented as a one-time setup step.

### Configuration tab — two new columns

`BG Color` / `Text Color`, per team row, any CSS colour string (`#C00000`, `#FFFFFF`).
Header-located, so column position stays free; absent column or blank cell = empty string
and the profile's CSS fallback applies.

### Configuration tab — `Session` vocabulary

Gains `HYPERCAR` and `QUALIFYING` (the badge text, chosen in the panel).

### Best Lap format contract

`normalize_quali_lap(cell)` — a pure, unit-tested function:

| Sheet cell | HUD renders | Rule |
|---|---|---|
| `1:38.973` | `1:38.973` | verbatim |
| `1:38,973` | `1:38.973` | comma decimal → dot |
| `0:01:38,973` / `00:01:38,973` | `1:38.973` | zero-hour group dropped |
| `98.973` | `98.973` | verbatim — no conversion, no guessing |
| *empty / team absent* | *(slot hides)* | `.empty` |

Order: `strip()` → `,`→`.` → if the value matches exactly `H:MM:SS[.fraction]` **and**
`H == 0`, reduce to `M:SS[.fraction]` (leading minute zero dropped); otherwise pass through
unchanged. A non-zero hour is left verbatim — a >1 h lap is nonsense, but destroying data is
worse than displaying it. No length or plausibility validation: the tile is a fixed box with
`overflow: hidden`, so CSS already clips, and every other HUD text field is verbatim too.

## Core changes (league-agnostic)

### 1. Relay parsers + join (`src/relay/racecast-feeds.py`)

- `parse_quali_times(text) -> {asset_key: display_string}` — new pure function beside
  `parse_config_roster` (:1716); header-located `Team` / `Best Lap`, values through
  `normalize_quali_lap`, blanks skipped, first occurrence wins.
- `parse_config_roster` additionally reads `BG Color` / `Text Color` into
  `roster[label]["bgColor"/"textColor"]`, using the same `next((header.index(h) …))`
  pattern as `BRAND_TEXT_HEADERS` (:1735).
- `team_entry(raw, roster, quali=None)` (:1850) and
  `build_hud_data(overlay, roster, quali=None)` (:1869) gain an **optional trailing
  argument**, so all existing callers and the nine `HudSource(...)` test call sites stay
  valid. New entry keys: `bgColor`, `textColor`, `qualiLap`.
- `HudSource(overlay_url, config_url, cache_path, quali_url=None)` (:5088). The third fetch
  sits in **its own `try/except`** inside `refresh` (:5118): `refresh` is otherwise
  all-or-nothing, so an unreachable or non-existent `Quali Times` tab — the state of *every*
  existing league — would fail the whole refresh and freeze the entire overlay on last-good
  data. A fetch/parse failure keeps the **last-good** lap map (never rolled back to
  empty) and logs once; a tab that exists but has lost its `Team`/`Best Lap` header
  replaces the map with empty; a tab that was never created simply stays empty. Either
  way, everything else refreshes normally.
- Three places that spell the team-entry keys out literally must gain the new keys, or a
  panel team write flashes a colourless, quali-less tile for up to `OVERRIDE_TTL` (30 s):
  `HudSource.EMPTY` (:5085), the `team_overrides` padding (:5182), and **`resolve_team`**
  (:5206), the optimistic-echo path.
- CLI: `--quali-times-tab` (default `Quali Times`) + the URL derived from `sheet_id` next to
  the existing HUD URLs (:9749). Disabled by a custom `--sheet-csv-url`, exactly like the
  POV / qualifying / crew sources.
- `/hud/data` (:8407) gains `"mode": relay.mode` — one line; `relay` is already in scope
  there, next to `povActive`/`povName`. `mode` deliberately does **not** enter `HudSource`:
  it is relay state, like `povActive`.

`hud.cache.json` written by an older build simply lacks the new keys — every read is a
`.get()` with a default, so no migration.

### 2. Base HUD (`src/obs/hud.html`)

- **New box slot `#teamN-bar`** per tile, placed **before** `#teamN-logo` in the DOM so
  logo/number/model paint on top (the slots are absolutely positioned siblings; DOM order is
  the z-order). Base ships it unstyled — `.el` is `position:absolute; overflow:hidden` with
  no background, so it is invisible until a profile sets `background: var(--team-bg)`.
- **New text slot `#teamN-quali`** rendering `qualiLap`.
- `setTeam` (:385) sets `--team-bg` / `--team-fg` from `bgColor`/`textColor` on the tile's
  own elements, so one generic CSS rule serves all three tiles. No colour literal in base.
  `.empty` is toggled on the new slots by the same rules as the existing ones, so a tile with
  no team stays fully hidden.
- `tick` (:526) sets `document.body.dataset.mode = d.mode || ""`, letting a profile gate
  anything on `body[data-mode="qualifying"]` — the WSP profile hides the quali-time row there.
- `fmtClock` (:321) omits a zero hour.
- Builder slots need no registration: `overlay_build.extract_slots` derives them from the
  `data-edit` markers (`src/scripts/overlay_build.py:270`).

### 3. Profile `profiles/erf-wsp/` (machine-local)

`profiles/*` is gitignored (only `example`, `demo`, `solo-*` ship), so **the PR carries core
+ tests only**; the profile is built locally and handed over as a `racecast profile export`
zip. Contents:

- `profile.env`: `NAME=ERF WSP`, `SHEET_ID`, `SHEET_PUSH_URL`, `LOGO`, `OBS_COLLECTION`.
- `overlay/`: layout measured **1:1 in the visual overlay builder** against the real
  `Overlay.png` (per `overlay-builder-is-1to1-truth`), Nunito Sans in `overlay/fonts/`
  (not in the `GOOGLE_FONTS` quick-pick, but any valid family name is fetchable via the
  Settings typeahead), and the colour/mode rules in the builder's `customCss`:
  tile bar `background: var(--team-bg)`, number/model `color: var(--team-fg)`,
  `body[data-mode="qualifying"] #teamN-quali { display: none }`.
- Graphics through the Sheet **Assets** tab (`racecast graphics`): `Overlay.png` with the
  black tile placeholders, gold accents, 1st/2nd/3rd, WSP block and an **empty** badge bar;
  plus the SAFETY CAR / RED FLAG bars as separate OBS image sources on the badge position.

Open profile-level detail, settled while building: whether the WSP logo comes from the
baked-in `Overlay.png` block or the `league-logo` slot, and where the event hashtag
(`#ERF6HSUZUKA`) lands (an existing `Round title` / `Round bottom` slot, no core change
either way).

## Testing

TDD — failing test first. `tests/test_hud.py` (stdlib, runnable script) covers:

- `normalize_quali_lap` across the format-contract table above.
- `parse_quali_times`: header variants, missing header, empty text, blank rows, duplicate
  teams, `#NNN` stripping, `asset_key` normalization.
- `parse_config_roster` with/without the colour columns (and unchanged behaviour when absent).
- `team_entry` / `build_hud_data` joining quali times and colours, including a team with no
  quali row.
- `resolve_team` returning the full key set (the 30 s echo-flash regression).
- `HudSource.refresh` still succeeding when the quali fetch raises — the freeze-the-overlay
  regression — via the existing `_fetch` monkeypatch seam.

`tests/test_overlay.py`: the new `data-edit` slots are extracted with the right kinds/props.

Gates: `python3 tools/run-tests.py`, `python3 tools/lint.py`, `python3 tools/build.py`.
Visual verification of the rendered HUD per the `ui-visual-verification` skill (blocking
Stop hook). No shared UI surface changes → no wiki screenshot refresh. Docs: the
`Sheet-Template` wiki page gains the `Quali Times` tab (incl. the plain-text formatting
step) and the two Configuration colour columns; `HUD-Overlays` documents the new
`--team-bg`/`--team-fg` custom properties, the `body[data-mode]` hook and the new slots as
the profile-facing contract. `tests/test_wiki.py` guards the links/anchors.
