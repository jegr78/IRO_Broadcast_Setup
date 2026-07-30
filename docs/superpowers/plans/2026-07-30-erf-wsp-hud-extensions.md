# ERF WSP HUD Extensions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three league-agnostic fields to the relay HUD (per-team brand colours, a qualifying best-lap time, the relay race/qualifying mode) plus the matching base-HUD slots, so the machine-local `profiles/erf-wsp/` overlay can render the WSP design (issue #555) with no WSP specifics in base code.

**Architecture:** Pure parser functions in `src/relay/racecast-feeds.py` read two new Configuration-tab colour columns and a new `Quali Times` sheet tab; the existing roster join carries the values into `/hud/data`. `src/obs/hud.html` gains one box slot and one text slot per tile and publishes the colours as CSS custom properties, so the profile's overlay CSS decides what consumes them. `mode` comes straight from `relay.mode` at the route, not from `HudSource`.

**Tech Stack:** Python 3 stdlib only (no pytest — every test file is a runnable script), vanilla HTML/CSS/JS for the overlay page.

**Spec:** `docs/superpowers/specs/2026-07-30-erf-wsp-hud-extensions-design.md`
**Issue:** #555 · **Branch:** `feat/555-erf-wsp-hud-extensions` (already created, spec committed)

## Global Constraints

- **Edit only under `src/`** (plus `tests/`, `docs/`). `dist/`, `runtime/` are generated; `tools/` is maintainer-only.
- **All code and docs in English.** (Chat with the user is German.)
- **The relay is deliberately dependency-light** — `racecast-feeds.py` must not import shared modules under `src/scripts/`, and outbound HTTP there keeps its own `User-Agent` (it is exempt from the `http_util` guard).
- **No hardcoded secrets, machine paths, or real IPs anywhere — including tests.**
- **No new CLI flag may be removed/renamed later without grepping `tools/` and `.github/`.**
- **No WSP-specific literal (colour, label, font, geometry) may enter `src/`.** Everything league-specific lives in `profiles/erf-wsp/overlay/`.
- **`profiles/*` is gitignored** (only `example`, `demo`, `solo-*` ship) → Tasks 1–7 are the PR; Task 8 is machine-local and never committed.
- Tests must run on any machine and in CI (the matrix includes Windows).
- Every task ends green on `python3 tools/run-tests.py` and `python3 tools/lint.py`.

---

### Task 1: Sheet parsers — colours + quali times (pure functions)

**Files:**
- Modify: `src/relay/racecast-feeds.py` (add constants + 3 functions near `parse_config_roster:1716`; extend `parse_config_roster`)
- Test: `tests/test_hud.py`

**Interfaces:**
- Consumes: existing `asset_key` (:1567), `split_team_label` (:1630), `csv`, `io`, `re`.
- Produces:
  - `sanitize_css_color(v) -> str` — a safe CSS colour string or `""`.
  - `normalize_quali_lap(v) -> str` — display lap string.
  - `parse_quali_times(text) -> dict[str, str]` — `{asset_key(team): lap}`.
  - `parse_config_roster(text)` entries gain `"bgColor"` and `"textColor"` (always present, `""` when unset).
  - Constants `TEAM_BG_COLOR_HEADERS`, `TEAM_TEXT_COLOR_HEADERS`, `QUALI_TEAM_HEADERS`, `QUALI_LAP_HEADERS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hud.py`, before the `if __name__ == "__main__":` runner:

```python
# ---------- Brand tile colours + quali times (issue #555) ----------

def t_sanitize_css_color_accepts_plausible_values():
    assert m.sanitize_css_color("#C00000") == "#C00000"
    assert m.sanitize_css_color("  #fff ") == "#fff"
    assert m.sanitize_css_color("#12345678") == "#12345678"
    assert m.sanitize_css_color("rgb(200, 0, 0)") == "rgb(200, 0, 0)"
    assert m.sanitize_css_color("rgba(200,0,0,.5)") == "rgba(200,0,0,.5)"
    assert m.sanitize_css_color("white") == "white"


def t_sanitize_css_color_rejects_everything_else():
    # The gate that keeps a sheet cell from smuggling a resource fetch into the
    # custom property the HUD sets on its slots.
    assert m.sanitize_css_color("url(http://x/y.png)") == ""
    assert m.sanitize_css_color("red; background: url(http://x)") == ""
    assert m.sanitize_css_color("var(--x)") == ""
    assert m.sanitize_css_color("#12345") == ""       # not 3/4/6/8 hex digits
    assert m.sanitize_css_color("") == ""
    assert m.sanitize_css_color(None) == ""


def t_normalize_quali_lap_verbatim_and_fixes():
    assert m.normalize_quali_lap("1:38.973") == "1:38.973"      # verbatim
    assert m.normalize_quali_lap(" 1:38,973 ") == "1:38.973"    # comma -> dot
    assert m.normalize_quali_lap("0:01:38,973") == "1:38.973"   # sheets duration
    assert m.normalize_quali_lap("00:01:38.973") == "1:38.973"
    assert m.normalize_quali_lap("0:1:38.973") == "1:38.973"
    assert m.normalize_quali_lap("98.973") == "98.973"          # no conversion
    assert m.normalize_quali_lap("1:02:03.400") == "1:02:03.400"  # non-zero hour kept
    assert m.normalize_quali_lap("") == ""
    assert m.normalize_quali_lap(None) == ""


QUALI_CSV = (
    "Team,Best Lap\n"
    "Tavernello Racing #6,1:38.973\n"
    "N3XUS Racing,1:39,104\n"          # comma decimal, no embedded number
    "Trrack Design Racing #51,0:01:40.512\n"   # sheets duration formatting
    ",1:00.000\n"                      # no team -> skipped
    "Ghost Racing,\n"                  # no lap -> skipped
)


def t_parse_quali_times_keys_by_asset_key_of_stripped_name():
    q = m.parse_quali_times(QUALI_CSV)
    assert q == {"tavernello-racing": "1:38.973",
                 "n3xus-racing": "1:39.104",
                 "trrack-design-racing": "1:40.512"}, q


def t_parse_quali_times_tolerates_missing_pieces():
    assert m.parse_quali_times("") == {}
    assert m.parse_quali_times("Team,Something\nX,1:2.3\n") == {}   # no lap header
    assert m.parse_quali_times("Foo,Best Lap\nX,1:2.3\n") == {}     # no team header
    assert m.parse_quali_times("Team,Best Lap\n") == {}             # header only
    # A Configuration CSV accidentally pointed at this parser yields nothing
    # rather than garbage (no 'Best Lap' column there).
    assert m.parse_quali_times(CONFIG_CSV) == {}


def t_parse_quali_times_first_row_per_team_wins():
    q = m.parse_quali_times("Team,Best Lap\nA Team #1,1:38.000\nA Team #2,1:39.000\n")
    assert q == {"a-team": "1:38.000"}, q


CONFIG_CSV_COLORS = (
    "Teams,Number,Brand Name,BG Color,Text Color\n"
    "OVO eSports,111,Porsche,#FFFFFF,#111111\n"
    "Feel Good,303,BMW,rgb(0,80,160),white\n"
    "Ghost,7,Audi,url(http://evil/x.png),#00FF00\n"   # rejected -> blank bg
)


def t_parse_config_roster_reads_tile_colors():
    r = m.parse_config_roster(CONFIG_CSV_COLORS)
    assert r["OVO eSports"]["bgColor"] == "#FFFFFF"
    assert r["OVO eSports"]["textColor"] == "#111111"
    assert r["Feel Good"]["bgColor"] == "rgb(0,80,160)"
    assert r["Feel Good"]["textColor"] == "white"
    # implausible value is dropped, the rest of the row survives
    assert r["Ghost"]["bgColor"] == ""
    assert r["Ghost"]["textColor"] == "#00FF00"
    assert r["Ghost"]["brandKey"] == "audi"


def t_parse_config_roster_colors_blank_without_columns():
    # Every existing league has no colour columns -> keys present, values blank.
    r = m.parse_config_roster(CONFIG_CSV)
    assert r["OVO eSports #111"]["bgColor"] == ""
    assert r["OVO eSports #111"]["textColor"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_hud.py`
Expected: FAIL — `AttributeError: module 'irofeeds' has no attribute 'sanitize_css_color'`.

- [ ] **Step 3: Implement the parsers**

In `src/relay/racecast-feeds.py`, directly **above** `def parse_config_roster` (:1716), insert:

```python
# Optional per-team tile colours (issue #555): a flat background + text colour per
# car, published by the HUD as --team-bg/--team-fg and consumed by a profile's
# overlay CSS. Header-located like every other Configuration column, so positions
# stay free; absent column or blank cell -> "" and the profile's CSS fallback wins.
TEAM_BG_COLOR_HEADERS = ("bg color", "bg colour", "background color",
                         "background colour")
TEAM_TEXT_COLOR_HEADERS = ("text color", "text colour", "fg color", "fg colour")

# A plausible CSS colour token: #rgb/#rgba/#rrggbb/#rrggbbaa, an rgb()/rgba()
# function, or a bare keyword. Anything else -> "". This is the gate that keeps a
# sheet cell from smuggling a url() (a resource fetch) into the custom property
# the HUD sets on its slots — the sheet is admin-managed, but the overlay renders
# on air and a typo must never turn into a network request.
CSS_COLOR_RE = re.compile(
    r"^(?:#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})"
    r"|rgba?\([0-9.,%\s/]+\)"
    r"|[a-z]{3,20})$", re.I)


def sanitize_css_color(v):
    """A sheet colour cell -> a safe CSS colour string, or '' when implausible."""
    s = (v or "").strip()
    return s if CSS_COLOR_RE.match(s) else ""


# Quali Times tab (issue #555): Team | Best Lap, one row per car, maintained ONCE
# between qualifying and the race. Deliberately NOT the 'Qualifying' tab — that
# name is the qualifying SCHEDULE (DEFAULT_QUALIFYING_TAB).
QUALI_TEAM_HEADERS = ("team", "teams", "team name")
QUALI_LAP_HEADERS = ("best lap", "best-lap", "bestlap", "quali time", "quali", "lap")

# A best lap a Sheets duration format produced ('0:01:38.973'): the hours group is
# dropped when zero, so the HUD shows the broadcast form '1:38.973'.
QUALI_LAP_DURATION_RE = re.compile(r"^(\d{1,2}):(\d{1,2}):(\d{2}(?:\.\d+)?)$")


def normalize_quali_lap(v):
    """A 'Best Lap' cell -> the HUD display string. Verbatim except two
    deterministic fixes: a comma decimal becomes a dot, and a ZERO hours group
    from a Sheets duration-formatted cell is dropped ('0:01:38,973' ->
    '1:38.973'). A non-zero hour is left alone — implausible for a lap, but
    showing the cell beats silently destroying it. No conversion to seconds and
    no reformatting: the sheet stays WYSIWYG, like every other HUD text field."""
    s = (v or "").strip().replace(",", ".")
    mt = QUALI_LAP_DURATION_RE.match(s)
    if mt and not mt.group(1).strip("0"):
        return f"{int(mt.group(2))}:{mt.group(3)}"
    return s


def parse_quali_times(text):
    """Quali Times tab CSV -> {asset_key(team): display_lap}. Keyed by the
    asset_key of the STRIPPED team name (a trailing '#NNN' is peeled first), so
    'Tavernello Racing #6', 'Tavernello Racing' and 'tavernello racing' all hit the
    same entry — robust against number/spelling variants. Columns are located by
    header name; a missing tab, missing header, or either column absent -> {}, so a
    league without this tab is simply unaffected. First row per team wins."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [(h or "").strip().lower() for h in rows[0]]
    ti = next((header.index(h) for h in QUALI_TEAM_HEADERS if h in header), None)
    li = next((header.index(h) for h in QUALI_LAP_HEADERS if h in header), None)
    if ti is None or li is None:
        return {}
    out = {}
    for row in rows[1:]:
        if len(row) <= ti or len(row) <= li:
            continue
        name, _embedded = split_team_label((row[ti] or "").strip())
        key, lap = asset_key(name), normalize_quali_lap(row[li])
        if key and lap:
            out.setdefault(key, lap)
    return out
```

Then extend `parse_config_roster`. After the existing `ni = next(...)` line (:1737) add:

```python
    ci = next((header.index(h) for h in TEAM_BG_COLOR_HEADERS if h in header), None)
    fi = next((header.index(h) for h in TEAM_TEXT_COLOR_HEADERS if h in header), None)
```

and replace the `out[label] = {...}` assignment (:1749-1751) with:

```python
        out[label] = {"number": col_num or embedded,
                      "brandKey": asset_key(brand_raw),
                      "brandName": override or brand_raw,
                      "bgColor": sanitize_css_color(
                          row[ci] if ci is not None and len(row) > ci else ""),
                      "textColor": sanitize_css_color(
                          row[fi] if fi is not None and len(row) > fi else "")}
```

Extend the docstring's first line to mention the two new keys.

- [ ] **Step 4: Update the existing roster assertions**

Nine existing tests assert **exact dict equality** on roster entries and now fail with the two added keys. Add `"bgColor": "", "textColor": ""` to every roster entry literal in these test functions in `tests/test_hud.py`:

`t_parse_config_roster`, `t_parse_config_roster_accepts_brand_name_header`,
`t_parse_config_roster_brand_name_override`, `t_parse_config_roster_ignores_image_columns`,
`t_roster_same_name_different_number_kept_distinct`, `t_roster_number_column`,
`t_roster_embedded_fallback`, `t_roster_column_wins_over_embedded`,
`t_parse_config_roster_team_name_header`.

Example — `t_parse_config_roster` line 74 becomes:

```python
    assert r["OVO eSports #111"] == {"number": "111", "brandKey": "porsche",
                                     "brandName": "Porsche",
                                     "bgColor": "", "textColor": ""}, r
```

Keep the keys always present (never omitted when blank): `parse_config_roster` already emits `brandKey`/`brandName` as `""`, and `HudSource.refresh` compares team dicts for equality to confirm optimistic overrides — a shape that varies by content would break that comparison.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 tests/test_hud.py`
Expected: `ALL PASS`.

- [ ] **Step 6: Lint and commit**

```bash
python3 tools/lint.py
git add src/relay/racecast-feeds.py tests/test_hud.py
git commit -m "feat(hud): read tile colours + a Quali Times tab from the sheet (#555)"
```

---

### Task 2: Join the new fields into `/hud/data`

**Files:**
- Modify: `src/relay/racecast-feeds.py` — `team_entry:1850`, `build_hud_data:1869`
- Test: `tests/test_hud.py`

**Interfaces:**
- Consumes: `parse_quali_times`, `parse_config_roster` (Task 1).
- Produces:
  - `team_entry(raw, roster, quali=None) -> dict` with keys `name, number, brandKey, brandName, label, bgColor, textColor, qualiLap`.
  - `build_hud_data(overlay, roster, quali=None) -> dict` — unchanged top-level keys, richer `teams`.
  - Both new parameters are **optional and trailing**, so every existing caller keeps working.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hud.py`:

```python
def t_team_entry_joins_colors_and_quali_lap():
    roster = m.parse_config_roster(CONFIG_CSV_COLORS)
    quali = m.parse_quali_times("Team,Best Lap\nOVO eSports,1:38.973\n")
    e = m.team_entry("OVO eSports", roster, quali)
    assert e == {"name": "OVO eSports", "number": "111", "brandKey": "porsche",
                 "brandName": "Porsche", "label": "OVO eSports",
                 "bgColor": "#FFFFFF", "textColor": "#111111",
                 "qualiLap": "1:38.973"}, e


def t_team_entry_quali_lap_matches_across_number_variants():
    # The slot value carries '#111', the Quali Times row does not (and vice
    # versa) -> both resolve through asset_key of the stripped name.
    roster = m.parse_config_roster(CONFIG_CSV)
    quali = m.parse_quali_times("Team,Best Lap\nOVO eSports,1:38.973\n")
    assert m.team_entry("OVO eSports #111", roster, quali)["qualiLap"] == "1:38.973"
    quali2 = m.parse_quali_times("Team,Best Lap\nOVO eSports #111,1:38.973\n")
    assert m.team_entry("OVO eSports #111", roster, quali2)["qualiLap"] == "1:38.973"


def t_team_entry_without_quali_map_is_blank():
    roster = m.parse_config_roster(CONFIG_CSV)
    e = m.team_entry("OVO eSports #111", roster)          # no quali argument
    assert e["qualiLap"] == "" and e["bgColor"] == "" and e["textColor"] == ""


def t_build_hud_data_carries_colors_and_quali():
    overlay = m.parse_overlay(OVERLAY_CSV)
    roster = m.parse_config_roster(CONFIG_CSV_COLORS)
    quali = m.parse_quali_times("Team,Best Lap\nOVO eSports,1:38.973\n")
    d = m.build_hud_data(overlay, roster, quali)
    # OVERLAY_CSV puts 'OVO eSports #111' in P1; the roster here is keyed bare.
    assert d["teams"][0]["qualiLap"] == "1:38.973"
    assert d["teams"][0]["bgColor"] == "#FFFFFF"
    # a team with no quali row keeps a blank slot (the HUD hides it)
    assert d["teams"][2]["qualiLap"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_hud.py`
Expected: FAIL — `KeyError: 'qualiLap'` (or a `team_entry() takes 2 positional arguments` TypeError).

- [ ] **Step 3: Implement the join**

Replace `team_entry` (:1850-1866) with:

```python
def team_entry(raw, roster, quali=None):
    """One /hud/data team object from an Overlay slot value + the roster (+ the
    optional Quali Times map). The roster is keyed by the VERBATIM label, so the
    lookup uses the raw slot value first (the per-car identity); a stripped-name
    fallback covers a bare slot value against a roster whose number lives in a
    separate Number column. Displayed 'name' is the stripped form;
    'number'/logo come from the roster (Number column precedence already baked
    in), with the slot's own embedded #NNN as the fallback. 'label' carries the
    verbatim value (with #NNN) so the panel dropdown can offer/select the exact
    car — the HUD ignores it. bgColor/textColor are the optional tile colours;
    qualiLap is looked up by asset_key of the stripped name, so number/spelling
    variants between the two tabs still match (issue #555)."""
    raw = (raw or "").strip()
    name, embedded = split_team_label(raw)
    info = roster.get(raw) or roster.get(name) or {}
    return {"name": name,
            "number": info.get("number") or embedded,
            "brandKey": info.get("brandKey", ""),
            "brandName": info.get("brandName", ""),
            "label": raw,
            "bgColor": info.get("bgColor", ""),
            "textColor": info.get("textColor", ""),
            "qualiLap": (quali or {}).get(asset_key(name), "")}


def build_hud_data(overlay, roster, quali=None):
    """Combine an Overlay map + roster {team: {number, brandKey, brandName,
    bgColor, textColor}} + the optional Quali Times map into /hud/data."""
    return {
        "stint": overlay.get("stint", ""),
        "streamer": overlay.get("streamer", ""),
        "session": overlay.get("session", ""),
        "round": {
            "top": overlay.get("round_top", ""),
            "country": overlay.get("country", ""),
            "flagKey": asset_key(overlay.get("country", "")),
        },
        "teams": [team_entry(n, roster, quali)
                  for n in overlay.get("teams", ["", "", ""])],
        "raceControl": overlay.get("race_control", ""),
        "flag": overlay.get("flag", ""),
    }
```

- [ ] **Step 4: Update the existing team-entry assertions**

Four existing tests assert exact team-entry equality. Add `"bgColor": "", "textColor": "", "qualiLap": ""` to every team-entry literal in: `t_build_hud_data`, `t_build_hud_data_unknown_brand_blank`, `t_team_entry_resolves_per_car_by_verbatim_label`, `t_build_hud_data_team_number_and_strip`.

Example — `t_build_hud_data_unknown_brand_blank` becomes:

```python
    assert d["teams"][0] == {"name": "Mystery Team", "number": "0", "brandKey": "",
                             "brandName": "", "label": "Mystery Team #0",
                             "bgColor": "", "textColor": "", "qualiLap": ""}
```

`t_hud_team_override_echo_and_pending` compares two values that both come from `resolve_team`, so it needs no literal update — leave it alone.

- [ ] **Step 5: Run the full suite**

Run: `python3 tests/test_hud.py && python3 tests/test_setup.py`
Expected: `ALL PASS` for both (`test_setup.py` builds a `HudSource` with no colour columns; its stubs stay valid).

- [ ] **Step 6: Lint and commit**

```bash
python3 tools/lint.py
git add src/relay/racecast-feeds.py tests/test_hud.py
git commit -m "feat(hud): carry tile colours + quali lap through the team join (#555)"
```

---

### Task 3: `HudSource` — the fault-tolerant third fetch

**Files:**
- Modify: `src/relay/racecast-feeds.py` — `HudSource` (:5080-5220): `EMPTY`, `__init__`, `refresh`, the `data()` padding, `resolve_team`
- Test: `tests/test_hud.py`

**Interfaces:**
- Consumes: `parse_quali_times`, `build_hud_data(overlay, roster, quali)` (Tasks 1–2).
- Produces: `HudSource(overlay_url, config_url, cache_path, quali_url=None)` — a **keyword-optional trailing** parameter, so the nine existing `HudSource(...)` call sites in `tests/test_hud.py` and `tests/test_setup.py` are untouched. New accessor `HudSource.quali_times() -> dict`.

**Why this task exists separately:** `refresh` is all-or-nothing today — one raising fetch returns `False` and the HUD freezes on last-good data. A third fetch against a tab that **no existing league has** would therefore break every league's overlay. The new fetch gets its own `try/except`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hud.py`:

```python
def _quali_hud(quali_text=None, quali_boom=False):
    """A HudSource with all three tabs stubbed. quali_boom simulates the tab not
    existing (gviz raises), the state of every league that never created it."""
    import tempfile, os as _os
    d = tempfile.mkdtemp()
    hs = m.HudSource("http://overlay", "http://config",
                     _os.path.join(d, "hud.cache.json"), quali_url="http://quali")
    def fetch(url, timeout=10):
        if url == "http://overlay":
            return OVERLAY_CSV
        if url == "http://quali":
            if quali_boom:
                raise RuntimeError("no such sheet tab")
            return quali_text or ""
        return CONFIG_CSV
    hs._fetch = fetch
    return hs


def t_hudsource_reads_quali_times():
    hs = _quali_hud("Team,Best Lap\nOVO eSports,1:38.973\n")
    assert hs.refresh() is True
    assert hs.quali_times() == {"ovo-esports": "1:38.973"}
    assert hs.data()["teams"][0]["qualiLap"] == "1:38.973"


def t_hudsource_refresh_survives_missing_quali_tab():
    # THE regression this task guards: a league without the tab must still get a
    # fully refreshed HUD, not a frozen last-good frame.
    hs = _quali_hud(quali_boom=True)
    assert hs.refresh() is True, "a failing quali fetch must not fail the refresh"
    assert hs.data()["streamer"] == "JeGr"
    assert hs.data()["teams"][0]["qualiLap"] == ""
    assert hs.quali_times() == {}


def t_hudsource_quali_times_preserved_on_overlay_failure():
    hs = _quali_hud("Team,Best Lap\nOVO eSports,1:38.973\n")
    assert hs.refresh() is True
    def boom(url, timeout=10):
        raise RuntimeError("sheet down")
    hs._fetch = boom
    assert hs.refresh() is False
    assert hs.quali_times() == {"ovo-esports": "1:38.973"}   # last-good kept


def t_hudsource_no_quali_url_makes_no_third_fetch():
    import tempfile, os as _os
    d = tempfile.mkdtemp()
    hs = m.HudSource("http://overlay", "http://config",
                     _os.path.join(d, "hud.cache.json"))     # no quali_url
    seen = []
    def fetch(url, timeout=10):
        seen.append(url)
        return OVERLAY_CSV if url == "http://overlay" else CONFIG_CSV
    hs._fetch = fetch
    assert hs.refresh() is True
    assert seen == ["http://overlay", "http://config"], seen


def t_hudsource_empty_and_resolve_team_carry_new_keys():
    # resolve_team feeds the panel's 30 s optimistic echo. If it omitted the new
    # keys, an approved team switch would flash a colourless, quali-less tile.
    keys = {"name", "number", "brandKey", "brandName", "label",
            "bgColor", "textColor", "qualiLap"}
    assert set(m.HudSource.EMPTY["teams"][0]) == keys
    hs = _quali_hud("Team,Best Lap\nFeel Good,1:39.104\n")
    hs.refresh()
    e = hs.resolve_team("Feel Good")
    assert set(e) == keys, e
    assert e["qualiLap"] == "1:39.104", e


def t_hudsource_team_override_padding_shape():
    # An override on slot 2 with fewer than 3 sheet teams pads the list; the pad
    # entries must carry the same key set as a real one.
    hs = _quali_hud()
    hs.refresh()
    hs.set_team_override(2, hs.resolve_team("Ghost #9"), now=1000.0)
    for t in hs.data(now=1001.0)["teams"]:
        assert set(t) == set(m.HudSource.EMPTY["teams"][0]), t
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_hud.py`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'quali_url'`.

- [ ] **Step 3: Implement the HudSource changes**

Replace the `EMPTY` team literal (:5085) with a module-level constant above the class so the four places that need it cannot drift, and use it everywhere:

```python
# The team-entry key set, spelled once. EMPTY, the override padding and
# resolve_team all build from it so a new field cannot be forgotten in one of
# them (a forgotten key blanks a tile for the 30 s of an optimistic echo).
EMPTY_TEAM_ENTRY = {"name": "", "number": "", "brandKey": "", "brandName": "",
                    "label": "", "bgColor": "", "textColor": "", "qualiLap": ""}
```

In `class HudSource`:

```python
    EMPTY = {"stint": "", "streamer": "", "session": "",
             "round": {"top": "", "country": "", "flagKey": ""},
             "teams": [dict(EMPTY_TEAM_ENTRY) for _ in range(3)],
             "raceControl": "", "flag": ""}

    def __init__(self, overlay_url, config_url, cache_path, quali_url=None):
        self.overlay_url = overlay_url
        self.config_url = config_url
        self.quali_url = quali_url      # None = no Quali Times tab configured
        ...                             # (rest of __init__ unchanged)
        self._quali = {}
```

Add `self._quali = {}` next to `self._roster = {}` (:5097).

In `refresh`, wrap the third fetch on its own:

```python
    def refresh(self, timeout=10):
        # The Quali Times tab (issue #555) is OPTIONAL and fetched on its own:
        # refresh() is otherwise all-or-nothing, so a league that never created
        # the tab would fail every refresh and freeze the whole overlay on
        # last-good data. Failure here = keep the last-good map, log once.
        quali = self._quali
        if self.quali_url:
            try:
                quali = parse_quali_times(self._fetch(self.quali_url, timeout))
            except Exception as e:
                if not self._quali_warned:
                    LOG.warning("quali times unavailable (%s: %s) — tile lap "
                                "times stay blank", type(e).__name__, e)
                    self._quali_warned = True
        try:
            overlay = parse_overlay(self._fetch(self.overlay_url, timeout))
            config_text = self._fetch(self.config_url, timeout)
            roster = parse_config_roster(config_text)
            roster_full = parse_team_full_labels(config_text)
            vocab = parse_config_vocab(config_text)
            cue_presets = parse_cue_presets(config_text)
            rc_note_presets = parse_rc_note_presets(config_text)
            data = build_hud_data(overlay, roster, quali)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return False
        with self.lock:
            self._data = data
            self._quali = quali
            ...                         # (rest of the with-block unchanged)
```

Add `self._quali_warned = False` in `__init__` (next to `self._quali = {}`) so a permanently absent tab logs once per relay run, not every poll.

In `data()`, replace the padding literal (:5182) with:

```python
                    teams.append(dict(EMPTY_TEAM_ENTRY))
```

Add the accessor next to `roster_names` (:5201):

```python
    def quali_times(self):
        """The Quali Times map {asset_key: lap}, last-good (empty when the tab is
        absent/unreachable)."""
        with self.lock:
            return dict(self._quali)
```

Replace `resolve_team`'s return (:5215-5219) so the panel echo carries every field:

```python
        label = (label or "").strip()
        name, embedded = split_team_label(label)
        with self.lock:
            info = self._roster.get(label) or self._roster.get(name) or {}
            lap = self._quali.get(asset_key(name), "")
        return {"name": name,
                "number": info.get("number") or embedded,
                "brandKey": info.get("brandKey", ""),
                "brandName": info.get("brandName", ""),
                "label": label,
                "bgColor": info.get("bgColor", ""),
                "textColor": info.get("textColor", ""),
                "qualiLap": lap}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_hud.py && python3 tests/test_setup.py`
Expected: `ALL PASS` for both.

- [ ] **Step 5: Lint and commit**

```bash
python3 tools/lint.py
git add src/relay/racecast-feeds.py tests/test_hud.py
git commit -m "feat(hud): optional Quali Times source with an isolated fetch (#555)"
```

---

### Task 4: Relay wiring — CLI flag, sheet URL, `mode` on `/hud/data`

**Files:**
- Modify: `src/relay/racecast-feeds.py` — argparse (:9481), HUD URL block (:9748-9754), `/hud/data` route (:8407-8413)
- Test: `tests/test_hud.py`

**Interfaces:**
- Consumes: `HudSource(..., quali_url=...)` (Task 3).
- Produces: CLI flag `--quali-times-tab` (default `Quali Times`); `/hud/data` gains a top-level `"mode"` of `"race"` or `"qualifying"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hud.py`:

The relay builds its argparser inline in `main()`, so assert the default through the module constant — that keeps the test independent of `main()`'s structure:

```python
def t_quali_times_tab_is_its_own_tab():
    # A NEW sheet tab, never the qualifying SCHEDULE tab (which owns 'Qualifying').
    assert m.DEFAULT_QUALI_TIMES_TAB == "Quali Times"
    assert m.DEFAULT_QUALI_TIMES_TAB != m.DEFAULT_QUALIFYING_TAB
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_hud.py`
Expected: FAIL — `AttributeError: module 'irofeeds' has no attribute 'DEFAULT_QUALI_TIMES_TAB'`.

- [ ] **Step 3: Add the constant, the flag and the URL**

Next to `DEFAULT_QUALIFYING_TAB` (:1064) add:

```python
# Quali Times tab (issue #555): per-car best lap shown in the race tiles. A
# SEPARATE tab from DEFAULT_QUALIFYING_TAB above, which is the qualifying
# SCHEDULE (URL/Streamer/Stint) — the two must never share a name.
DEFAULT_QUALI_TIMES_TAB = "Quali Times"
```

After the `--config-tab` argument (:9482) add:

```python
    ap.add_argument("--quali-times-tab", default=DEFAULT_QUALI_TIMES_TAB,
                    help="Google-Sheet tab with per-car qualifying best laps "
                         "(default 'Quali Times'). Absent tab = blank lap slots.")
```

In the HUD URL block (:9748-9753) replace the `HudSource(...)` construction with:

```python
        overlay_url = base + quote(args.overlay_tab)
        config_url = base + quote(args.config_tab)
        quali_url = base + quote(args.quali_times_tab)
        hud_cache = os.path.join(runtime, "hud.cache.json")
        hud_source = HudSource(overlay_url, config_url, hud_cache,
                               quali_url=quali_url)
```

(The whole block is already gated on `not args.sheet_csv_url`, so a custom CSV URL disables the quali source with the rest of the HUD — same rule as the POV/qualifying/crew sources.)

In the `/hud/data` route (:8410-8413) add the mode line:

```python
                    data = hud_source.data()           # already a shallow copy
                    data["povActive"] = relay.pov_active()
                    data["povName"] = relay.pov_name()
                    # Race vs qualifying, so a profile's overlay CSS can gate on
                    # body[data-mode] (issue #555). Relay state, like povActive —
                    # deliberately not part of HudSource.
                    data["mode"] = relay.mode
                    return self._send(data)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/test_hud.py && python3 tests/test_pov.py`
Expected: `ALL PASS` for both.

- [ ] **Step 5: Verify the flag is not referenced anywhere stale**

Run: `grep -rn "quali-times-tab\|quali_times_tab" src tools .github tests`
Expected: only the definition, the URL build, and this plan/spec. (Per the repo rule: a CLI flag's callers include `tools/` and `.github/`, which the test suite never exercises.)

- [ ] **Step 6: Lint and commit**

```bash
python3 tools/lint.py
git add src/relay/racecast-feeds.py tests/test_hud.py
git commit -m "feat(relay): --quali-times-tab + mode on /hud/data (#555)"
```

---

### Task 5: Base HUD — tile bar slot, quali slot, colour properties, mode, clock

**Files:**
- Modify: `src/obs/hud.html` (CSS ~:66-70, slots :260-271, `fmtClock`:321, `setTeam`:385, `tick`:526)
- Test: `tests/test_overlay.py` (the ordered slot-id list at :227-255), `tests/test_hud.py`

**Interfaces:**
- Consumes: `/hud/data` team fields `bgColor`, `textColor`, `qualiLap` and top-level `mode` (Tasks 1–4).
- Produces (the profile-facing contract): slots `#teamN-bar` (box) and `#teamN-quali` (text) for N in 1..3; custom properties `--team-bg` / `--team-fg` set on every slot of a tile; `document.body[data-mode="race|qualifying"]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_overlay.py`, extend the expected id list in `t_ob_extract_slots_from_real_hud` — each tile is now **six** slots in DOM order (`bar` first so the colour bar paints *behind* logo/number/name):

```python
                   "team1-bar", "team1-logo", "team1-num", "team1-name",
                   "team1-brand", "team1-quali",
                   "team2-bar", "team2-logo", "team2-num", "team2-name",
                   "team2-brand", "team2-quali",
                   "team3-bar", "team3-logo", "team3-num", "team3-name",
                   "team3-brand", "team3-quali",
```

and append a new test at the end of the file, before the runner:

```python
def t_ob_team_bar_is_a_box_slot_before_the_logo():
    # The tile colour bar must be the FIRST slot of its tile: the slots are
    # absolutely-positioned siblings, so DOM order is the paint order — a bar
    # after the logo would cover logo/number/model (issue #555).
    with open(os.path.join(ROOT, "src", "obs", "hud.html"), encoding="utf-8") as f:
        slots = ob.extract_slots(f.read())
    ids = [s["id"] for s in slots]
    for n in (1, 2, 3):
        assert ids.index(f"team{n}-bar") < ids.index(f"team{n}-logo")
    by = {s["id"]: s for s in slots}
    assert by["team1-bar"]["props"] == list(ob.KIND_BOX)
    assert by["team1-quali"]["props"] == list(ob.KIND_TEXT)


def t_hud_page_publishes_team_colors_and_mode():
    # The base HUD must expose the colours as custom properties and the mode as a
    # body attribute — and contain NO league colour literal of its own.
    with open(os.path.join(ROOT, "src", "obs", "hud.html"), encoding="utf-8") as f:
        html = f.read()
    assert "--team-bg" in html and "--team-fg" in html
    assert "dataset.mode" in html
    assert "qualiLap" in html
    # the bar carries no background in base — a profile decides
    assert "background: var(--team-bg)" not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/test_overlay.py`
Expected: FAIL — the slot-id list mismatch (`team1-bar` missing).

- [ ] **Step 3: Add the slots and their default geometry**

In `src/obs/hud.html`, after the `.team-brand` rules (~:66-70) add:

```css
  /* Tile colour bar + quali lap (issue #555). The bar is a plain box slot with
     NO background in base — a profile paints it with var(--team-bg), which
     setTeam() publishes from the sheet's per-team colours. It is the FIRST slot
     of its tile in the DOM so it paints behind logo/number/name. The quali lap
     shares the brand row's box but is right-aligned, so brand text (left) and
     lap time (right) coexist on one line. Positions here are the provisional
     default look; a league places them in the overlay builder. */
  .team-bar { width: 391px; height: 60px; }
  #team1-bar { left: 318px; top: 1006px; }
  #team2-bar { left: 762px; top: 1006px; }
  #team3-bar { left: 1206px; top: 1006px; }
  .team-quali { height: 22px; width: 250px; font-size: 16px; color: #cfd6df;
    justify-content: flex-end; overflow: hidden; white-space: nowrap; }
  #team1-quali { left: 453px; top: 1064px; }
  #team2-quali { left: 896px; top: 1064px; }
  #team3-quali { left: 1340px; top: 1064px; }
```

Then rewrite the three tile slot blocks (:260-271) so each tile reads bar → logo → num → name → brand → quali:

```html
  <div id="team1-bar" class="el team-bar" data-edit="Team 1 bar" data-edit-kind="box"></div>
  <div id="team1-logo" class="el team-logo" data-edit="Team 1 logo" data-edit-kind="box" data-edit-props="align,valign"><img alt=""></div>
  <div id="team1-num" class="el team-num white" data-edit="Team 1 number" data-edit-kind="text"></div>
  <div id="team1-name" class="el team-name white" data-edit="Team 1 name" data-edit-kind="text" data-edit-props="teamNameMax,teamNameMin"></div>
  <div id="team1-brand" class="el team-brand white" data-edit="Team 1 brand name" data-edit-kind="text"></div>
  <div id="team1-quali" class="el team-quali white" data-edit="Team 1 quali lap" data-edit-kind="text"></div>
  <div id="team2-bar" class="el team-bar" data-edit="Team 2 bar" data-edit-kind="box"></div>
  <div id="team2-logo" class="el team-logo" data-edit="Team 2 logo" data-edit-kind="box" data-edit-props="align,valign"><img alt=""></div>
  <div id="team2-num" class="el team-num white" data-edit="Team 2 number" data-edit-kind="text"></div>
  <div id="team2-name" class="el team-name white" data-edit="Team 2 name" data-edit-kind="text" data-edit-props="teamNameMax,teamNameMin"></div>
  <div id="team2-brand" class="el team-brand white" data-edit="Team 2 brand name" data-edit-kind="text"></div>
  <div id="team2-quali" class="el team-quali white" data-edit="Team 2 quali lap" data-edit-kind="text"></div>
  <div id="team3-bar" class="el team-bar" data-edit="Team 3 bar" data-edit-kind="box"></div>
  <div id="team3-logo" class="el team-logo" data-edit="Team 3 logo" data-edit-kind="box" data-edit-props="align,valign"><img alt=""></div>
  <div id="team3-num" class="el team-num white" data-edit="Team 3 number" data-edit-kind="text"></div>
  <div id="team3-name" class="el team-name white" data-edit="Team 3 name" data-edit-kind="text" data-edit-props="teamNameMax,teamNameMin"></div>
  <div id="team3-brand" class="el team-brand white" data-edit="Team 3 brand name" data-edit-kind="text"></div>
  <div id="team3-quali" class="el team-quali white" data-edit="Team 3 quali lap" data-edit-kind="text"></div>
```

- [ ] **Step 4: Publish the colours and the lap in `setTeam`**

Replace `setTeam` (:385-404) with:

```js
  // Per-tile colours (issue #555) are published as CUSTOM PROPERTIES on the
  // tile's own slots, so one generic profile rule serves all three tiles and no
  // colour literal lives in the base HUD. Set via style.setProperty (never string
  // concatenation into CSS text), so a sheet value cannot escape into a new
  // declaration; the relay already rejects implausible colours server-side.
  const TEAM_PARTS = ["bar", "logo", "num", "name", "brand", "quali"];
  function setTeamColors(n, bg, fg) {
    for (const part of TEAM_PARTS) {
      const el = document.getElementById("team" + n + "-" + part);
      if (!el) continue;
      if (bg) el.style.setProperty("--team-bg", bg);
      else el.style.removeProperty("--team-bg");
      if (fg) el.style.setProperty("--team-fg", fg);
      else el.style.removeProperty("--team-fg");
    }
  }
  function setTeam(i, team) {
    const n = i + 1;                 // slot ids are 1-based (team1..team3)
    const name = (team && team.name) || "";
    const number = (team && team.number) || "";
    const numEl = document.getElementById("team" + n + "-num");
    numEl.textContent = number;
    numEl.classList.toggle("empty", !number);
    const nameEl = document.getElementById("team" + n + "-name");
    nameEl.textContent = name;
    nameEl.classList.toggle("empty", !name);
    const brandEl = document.getElementById("team" + n + "-brand");
    const brandName = (team && team.brandName) || "";
    brandEl.textContent = brandName;
    brandEl.classList.toggle("empty", !brandName);
    setText("team" + n + "-quali", (team && team.qualiLap) || "");
    // The bar is the tile's chrome: it follows the tile's presence, not one field.
    document.getElementById("team" + n + "-bar").classList.toggle("empty", !name);
    setTeamColors(n, (team && team.bgColor) || "", (team && team.textColor) || "");
    const logoEl = document.getElementById("team" + n + "-logo");
    const img = logoEl.querySelector("img");
    if (team && team.brandKey) { img.src = `/hud/assets/brands/${team.brandKey}`; logoEl.classList.remove("empty"); }
    else { img.removeAttribute("src"); logoEl.classList.add("empty"); }
    fitName(nameEl);
  }
```

- [ ] **Step 5: Publish the mode and shorten the clock**

In `fmtClock` (:321-325) replace the return with:

```js
  function fmtClock(s) {
    s = Math.max(0, Math.ceil(s));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    const mm = h ? String(m).padStart(2, "0") : String(m);
    // A zero hour is dropped (12:10, not 0:12:10) — short sessions read as
    // mm:ss on air, and so does the final hour of a race (issue #555).
    return (h ? h + ":" : "") + mm + ":" + String(x).padStart(2, "0");
  }
```

In `tick` (:543-545) add the mode attribute right after the POV lines:

```js
      // Race vs qualifying for the profile CSS (e.g. hide the quali lap during
      // qualifying itself). Absent/unknown -> attribute cleared.
      if (d.mode) document.body.dataset.mode = d.mode;
      else delete document.body.dataset.mode;
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tests/test_overlay.py && python3 tests/test_hud.py`
Expected: `ALL PASS` for both.

- [ ] **Step 7: Verify the rendered page visually**

REQUIRED SUB-SKILL: `ui-visual-verification` (a blocking Stop hook enforces its marker step).

Render `/hud` from a local dev build and confirm with your own eyes:
1. The default endurance look is **unchanged** — the new bar slot is invisible (no background in base) and the quali slot is empty/hidden without a Quali Times tab.
2. With a stubbed `/hud/data` carrying `bgColor`/`textColor`/`qualiLap`, a temporary
   `#team1-bar { background: var(--team-bg) }` in a scratch override CSS paints the bar
   **behind** logo/number/name, and the lap time sits right-aligned on the brand row.
3. The clock shows `mm:ss` under one hour and `h:mm:ss` above it.

- [ ] **Step 8: Lint and commit**

```bash
python3 tools/lint.py
git add src/obs/hud.html tests/test_overlay.py tests/test_hud.py
git commit -m "feat(hud): tile bar + quali lap slots, --team-bg/--team-fg, body[data-mode] (#555)"
```

---

### Task 6: Documentation

**Files:**
- Modify: `src/docs/wiki/Sheet-Template.md` (the new tab + the two Configuration columns)
- Modify: `src/docs/wiki/HUD-Overlays.md` (the profile-facing contract)
- Modify: `CLAUDE.md` (the HUD paragraph in *Architecture → The relay*)
- Test: `tests/test_wiki.py`

**Interfaces:** Consumes the finished behaviour of Tasks 1–5. Produces no code.

- [ ] **Step 1: Document the sheet contract**

In `src/docs/wiki/Sheet-Template.md`, add a `Quali Times` tab section covering:
- Header `Team | Best Lap`, one row per car.
- **Format the `Best Lap` column as plain text** (`Format → Number → Plain text`), otherwise Google Sheets parses `1:38.973` as a duration (38.973 *minutes*) and the CSV export already carries the mangled value. Single-cell rescue: a leading apostrophe `'1:38.973`.
- Accepted input and what the HUD shows: `1:38.973` → verbatim; `1:38,973` → `1:38.973`; `0:01:38,973` → `1:38.973`; empty/unknown team → the slot hides.
- Matching is by team name (a trailing `#NNN` is ignored), so the tab may use either form.
- Maintained **once between qualifying and the race**.
- Explicitly: this is **not** the `Qualifying` tab, which is the qualifying *schedule*.

In the same file's Configuration-tab section, add the optional `BG Color` / `Text Color` columns: per team row, any plain CSS colour (`#C00000`, `rgb(0,80,160)`, `white`); implausible values are ignored; the columns are located by header, so position is free.

- [ ] **Step 2: Document the profile-facing contract**

In `src/docs/wiki/HUD-Overlays.md`, add a short section listing what a per-league overlay can now consume: the `#teamN-bar` and `#teamN-quali` slots, the `--team-bg` / `--team-fg` custom properties (set on every slot of a tile), and `body[data-mode="race|qualifying"]`. Include the two-line example:

```css
#team1-bar, #team2-bar, #team3-bar { background: var(--team-bg); }
body[data-mode="qualifying"] #team1-quali { display: none; }
```

- [ ] **Step 3: Update CLAUDE.md**

In the relay HUD paragraph (the one describing `HudSource`, `BRAND_TEXT_HEADERS` and `/hud/data`), add one sentence: the optional `Quali Times` tab (`--quali-times-tab`, own fault-isolated fetch so a league without it is unaffected), the Configuration `BG Color`/`Text Color` columns surfaced as `teams[].bgColor/textColor`, and `mode` on `/hud/data`.

- [ ] **Step 4: Run the wiki link check**

Run: `python3 tests/test_wiki.py`
Expected: `ALL PASS` (it validates every wiki link and anchor — a renamed heading breaks inbound anchors).

- [ ] **Step 5: Commit**

```bash
git add src/docs/wiki/Sheet-Template.md src/docs/wiki/HUD-Overlays.md CLAUDE.md
git commit -m "docs: Quali Times tab, tile colour columns, overlay contract (#555)"
```

---

### Task 7: Gates and PR

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `python3 tools/run-tests.py`
Expected: every file passes — this is exactly what CI runs.

- [ ] **Step 2: Run the linter**

Run: `python3 tools/lint.py`
Expected: no findings (`--fix` auto-corrects mechanical ones).

- [ ] **Step 3: Build the distributable**

Run: `python3 tools/build.py`
Expected: `dist/GT_Racecast_Package/` + zip, verify step green (tokenization, blanked password, no secrets, preflight present, no shell scripts).

- [ ] **Step 4: Confirm no WSP specifics leaked into `src/`**

Run: `grep -rin "wsp\|hypercar\|nunito\|erf" src/ | grep -v "^src/docs/"`
Expected: no hits. Any hit is a spec violation — a league literal in base code.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/555-erf-wsp-hud-extensions
gh pr create --title "feat(hud): brand tile colours, qualifying best lap, relay mode (#555)" --body "$(cat <<'EOF'
Closes #555 (core part).

League-agnostic HUD data extensions for the ERF WSP design:

- Configuration tab `BG Color` / `Text Color` -> `teams[].bgColor/textColor`,
  published by the HUD as `--team-bg` / `--team-fg` custom properties per tile.
  Implausible values (e.g. a `url()`) are rejected server-side.
- New optional `Quali Times` sheet tab (`Team | Best Lap`) -> `teams[].qualiLap`,
  matched by team name across `#NNN`/spelling variants. **Not** the `Qualifying`
  tab — that name is the qualifying *schedule* (`DEFAULT_QUALIFYING_TAB`). Its
  fetch is isolated, so a league without the tab refreshes normally instead of
  freezing the overlay on last-good data.
- `mode` on `/hud/data` -> `body[data-mode]`, so a profile can gate on
  race vs qualifying in CSS.
- New base-HUD slots `#teamN-bar` (box, unpainted in base) and `#teamN-quali`.
- The HUD clock drops a zero hour (`12:10`), which also shortens the final hour
  of a race.

No WSP specifics in `src/` — the `profiles/erf-wsp/` look is machine-local
(`profiles/*` is gitignored) and ships as a `profile export` zip.

Spec: `docs/superpowers/specs/2026-07-30-erf-wsp-hud-extensions-design.md`
Plan: `docs/superpowers/plans/2026-07-30-erf-wsp-hud-extensions.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for green CI, then squash-merge**

Run: `gh pr checks --watch`
Expected: all jobs green (test matrix on three OSes, lint, e2e, binary-smoke). Merge only after that; ask the user before merging.

---

### Task 8: The `profiles/erf-wsp/` league look (machine-local, NOT in the PR)

**Files (all gitignored — never committed):**
- Create: `profiles/erf-wsp/profile.env`
- Create: `profiles/erf-wsp/overlay/layout-hud.json` + generated `hud.css` (both written by the visual overlay builder)
- Create: `profiles/erf-wsp/overlay/fonts/NunitoSans.woff2`
- Runtime: `runtime/erf-wsp/graphics/` via `racecast graphics`

**Blocked on the user delivering:** the league's `SHEET_ID` (+ `SHEET_PUSH_URL`), and `Overlay.png` with an **empty** red badge bar plus the `SAFETY CAR` / `RED FLAG` bars in the Sheet **Assets** tab.

- [ ] **Step 1: Scaffold the profile**

```bash
python3 src/racecast.py profile new erf-wsp
```
Then set `NAME=ERF WSP`, `SHEET_ID`, `SHEET_PUSH_URL`, `LOGO`, `OBS_COLLECTION` in `profiles/erf-wsp/profile.env`.

- [ ] **Step 2: Pull the graphics**

```bash
python3 src/racecast.py --profile erf-wsp graphics
```
Expected: `runtime/erf-wsp/graphics/Overlay.png` plus the flag/standby graphics named exactly as their Assets-tab labels.

- [ ] **Step 3: Load Nunito Sans**

Control Center → General Settings → overlay font library → add `Nunito Sans` by name. It is not in the `GOOGLE_FONTS` quick-pick, but any valid family name is fetchable. If the mockup's italic looks synthesized rather than a true italic cut, note it and add the italic face separately — a look detail, not a blocker.

- [ ] **Step 4: Lay out the overlay in the builder**

Control Center → Profile → overlay builder, with `Overlay.png` as the backdrop. Place, for each tile: bar over the black placeholder, logo, number, model text (right-aligned), team name, quali lap (right-aligned). Then `session` over the empty red badge bar, and the clock in the WSP block. Measure on the builder canvas or native `/hud` (both 1:1) — **never** the scaled `/hud/preview`.

- [ ] **Step 5: Add the colour + mode rules as advanced CSS**

In the builder's advanced-CSS box:

```css
#team1-bar, #team2-bar, #team3-bar { background: var(--team-bg); }
#team1-num, #team2-num, #team3-num,
#team1-brand, #team2-brand, #team3-brand { color: var(--team-fg); background: none; }
body[data-mode="qualifying"] #team1-quali,
body[data-mode="qualifying"] #team2-quali,
body[data-mode="qualifying"] #team3-quali { display: none; }
```

- [ ] **Step 6: Verify against the mockups**

Render `/hud` with the real sheet and compare against issue #555's `21.png` (race) and `22.png` (qualifying): per-brand tile colours for Ferrari/Porsche/BMW in **any** slot, lap times present in race and gone in qualifying, badge text switching with the `session` dropdown. Fix geometry in the builder, never in `src/`.

- [ ] **Step 7: Export for the production machine**

```bash
python3 src/racecast.py profile export erf-wsp --out erf-wsp-profile.zip
```
Hand the zip over; import there with `racecast profile import erf-wsp-profile.zip`.

---

## Self-Review

**Spec coverage** — every spec section maps to a task: sheet contract → Tasks 1 + 6; `normalize_quali_lap` format table → Task 1; core parsers/join → Tasks 1–2; fault-isolated third fetch and the `EMPTY`/padding/`resolve_team` key set → Task 3; CLI flag + `mode` → Task 4; base-HUD slots, custom properties, `body[data-mode]`, clock → Task 5; docs → Task 6; gates → Task 7; the machine-local profile (incl. the open logo/hashtag detail) → Task 8. Non-goals (live timing, `flag-status`, the commentary banner) are asserted negatively by Task 7 Step 4.

**Naming consistency** — `bgColor` / `textColor` / `qualiLap` (JSON, camelCase, matching `brandKey`/`brandName`); `BG Color` / `Text Color` / `Best Lap` (sheet headers); `--team-bg` / `--team-fg` (CSS); `#teamN-bar` / `#teamN-quali` (slot ids); `sanitize_css_color` / `normalize_quali_lap` / `parse_quali_times` / `quali_times()` / `quali_url` / `--quali-times-tab` / `DEFAULT_QUALI_TIMES_TAB` (Python). Used identically in every task.

**Deliberate risk, accepted by the user** — the clock change (Task 5 Step 5) also shortens the final hour of a race for existing leagues (`0:59:12` → `59:12`). Chosen over a mode-gated variant with that trade-off stated.
