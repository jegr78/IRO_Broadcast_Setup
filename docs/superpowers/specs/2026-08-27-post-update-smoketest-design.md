# Post-update smoke test (`racecast smoketest`) — design

**Status:** design agreed 2026-08-27, not yet implemented.
**Problem:** after a toolchain update (pacman `-Syu` on the Arch broadcast box bumped
ffmpeg 8→9, yt-dlp, streamlink, deno, kernel), nothing in the repo answers "do the core
event functions still work?". `tools/e2e.py` deliberately cannot: its synthetic mode
prepends no-op stubs for `yt-dlp`, `streamlink`, `ffmpeg` and `deno` (`_stub_tools_bin`)
and drives fake schedule URLs, so it asserts the relay's HTTP surface and never touches
the external tools. `--real-league` uses the real PATH but only runs the non-mutating
`REAL_LEAGUE_CHECKS` against a league whose stints are not live outside an event.

## Shape

One shipped CLI command, `racecast smoketest`, that stands up a **real event** marked as
fictional and drives a scripted director rundown against it while asserting the result of
every step. The subject under test is the production path itself, not a re-implementation
of it — this is why the command orchestrates `event start`/`event stop` rather than
invoking `yt-dlp`/`streamlink`/`ffmpeg` on its own.

It ships (not a `tools/` maintainer script) because the machine that has the updated
toolchain is the broadcast box, and that box holds only the two binaries, `.env`,
`profiles/` and `runtime/` — no repo.

## Run sequence

1. **Guards.** Refuse when a relay or static streams are running (`--force` overrides),
   mirroring `freeport` and `profile use`. Then require the typed confirmation phrase
   `CLEAR SCHEDULE <profile>`. No `--yes` bypass: the command clears and overwrites the
   active profile's Schedule column, and a bypass flag ends up in a wrapper script where
   it defeats the guard. Naming the profile in the phrase is what protects against running
   the right command against the wrong league.
2. **Toolchain fingerprint.** Record versions of `yt-dlp`, `streamlink`, `ffmpeg`, `deno`
   plus yt-dlp's own JS-runtime line (`[debug] JS runtimes: deno-x.y.z`). Not a test — a
   note, so a red run can be diffed against the last green one. Note that deno is the only
   available JS challenge provider on the box (`bun/node/quickjs unavailable`), so there is
   no fallback if it breaks. The JS-runtime line is read off a stream discovery has
   ALREADY proven live, not off a hardcoded video id: the run then does not depend on one
   stranger's clip staying up, and spends no request at all when discovery finds nothing.
3. **Discovery — three live sources, ordered YouTube, Twitch, YouTube.**
   - YouTube: yt-dlp against the live-filtered search URL
     (`.../results?search_query=<term>&sp=EgJAAQ%3D%3D`).
   - Twitch: the category listing from the public `gql.twitch.tv` endpoint using the public
     web-player Client-ID (the same one streamlink embeds) — stdlib HTTP only, no API key,
     no new dependency. yt-dlp has no Twitch directory extractor, so this is the only
     dependency-free path.
   - Search terms and categories: built-in defaults, overridden by an optional `Smoke` tab
     in the league sheet, so the vocabulary can change without cutting a release.
4. **Acceptance.** Each candidate must pass before it is written:
   - YouTube: resolve in the relay's own command form
     (`yt-dlp -g -f "b[height<=1080]/b" --no-warnings --no-playlist --print "rcq %(height)s %(fps)s" --cookies <jar> -- <url>`);
     require a manifest and height >= 720, plus a sim-racing keyword in title/channel.
     Game names (GT7, iRacing, ACC, LMU, rFactor, Assetto Corsa) are language-independent,
     so the keyword gate does not misfire on non-English titles.
   - Twitch: `streamlink --json <url>` (pulls nothing); require plugin `twitch`, a quality
     >= 720p in the ladder, and a reported category in the sim-racing list. The category
     comes from the source, so the topical criterion is verified rather than guessed.
   - Viewer count orders candidates; it never excludes one (a 3-viewer channel serves the
     same 1080p60 transport stream as a 500-viewer one).
   - At most **three attempts per platform**; then `[SKIP]`, not a failure. Each attempt is
     a real request, and an uncapped walk down the list is how an IP gets throttled.
5. **Sheet write — column A only.** Clear the Schedule tab's URL column (all rows), then
   write the three discovered URLs into the first three STINT rows. Those rows are
   located the way the relay locates them (`schedule_layout`: a `URL` header in row 1
   means the data starts at physical row 2, matching `/schedule/data`'s "keyed by
   physical sheet row"), never assumed to start at row 1 — assuming that overwrote a
   real sheet's `URL` header, dropped the tab out of header mode, and made the
   read-back miss the run's own writes. **Streamer and Stint are never touched.**
   This mirrors the panel's own CLEAR URL button ("Clear the URL ONLY — keep Streamer +
   Stint so the slot survives") and is not merely cosmetic: `_schedule_write` rejects a
   streamer or stint outside the Configuration tab vocabulary (`_reject_off_vocab`), so a
   discovered channel name like `UKOG` is not a legal value. Writing one anyway — which the
   CLI's direct webhook path could technically do, since it bypasses `SetupControl` — would
   put a value in the sheet that the relay's own Schedule editor would refuse. Leaving the
   names alone keeps the mutation to a single column and leaves the HUD and cockpit tally
   with real names to display. A foreign stream shown under the name "JeGr" is acceptable in
   a run titled `Smoketest <date>`.

   Writing an empty URL is a supported operation: the guard is `if url and not
   is_channel(url)`, so it only applies to non-empty values, and the local injection comment
   states it outright ("INCLUDING a URL clear (url=\"\")").

   Clearing first makes the confirmation unambiguous: seeing an old URL then proves the CSV
   output is stale rather than merely suggesting it. It also removes the pre-existing hazard
   in the testing sheet where two adjacent stints carried the same URL (two feeds pulling one
   address at handover = 429).

   The sheet is polled **twice**, and both times **per row**: the cleared rows must come back
   EMPTY before the write, and afterwards every row must carry ITS OWN url (`rows_match`). One
   end-state check over the set of served URLs is not enough — a repeat run against a webhook
   that has stopped writing passes it on the previous run's identical rows, without anything
   having happened. Confirming the cleared state first is what makes the transition, rather
   than the end state, the evidence. Either poll timing out is a hard abort, because silently
   testing the previous rows is worse than not testing.

   The webhook's own HTTP answer is never treated as proof either way: Apps Script replies
   through a redirect whose target 404s intermittently *after* the script has already run. A
   reported push error is therefore recorded as diagnostic detail (in the `sheet_write`
   result, not only on stdout, so a `--json` run sees it too) and never retried — the sheet
   decides.

   The sheet's `TEST` column is the operator's own scratch space and is never read by the
   relay — the smoke test does not touch it.
6. **Event.** `event start --title "Smoketest <date>"`. Nothing is disabled: Tailscale,
   Discord (including the voice auto-join), relay, OBS, Companion, scene-collection switch,
   Standby, page refresh. `event stop` at the end runs the post-event report and the Discord
   send, which makes the report path part of what gets covered. The profile's Discord is a
   private test server.
7. **Director rundown.** Actions go to the relay endpoints the panel itself uses
   (`POST /obs/scene`, `/obs/source`, `/obs/audio`, `GET /next`, `GET /timer/*`,
   `GET /feed/<A|B>/activate`). **No token is needed:** the root-path `/obs/*` routes
   carry no auth — loopback/tailnet is the trust boundary there, and the director gate
   applies only under the `/console` mount. The command runs on the producer's own
   machine, so it reaches them directly.
   Driving the real page through Playwright was rejected: it adds a browser dependency on
   the broadcast box for a layer the toolchain update does not touch. The known blind spot
   is that a broken panel button is not detected, only a broken effect behind it.

   Sequence:

   ```
   STANDBY -> INTRO -> ARM A -> (wait for bytes) -> STINT A
     -> HUD on -> STANDINGS on/off -> FLAG YELLOW -> CLEAR
     -> TIMER START/PAUSE/RESET
     -> ARM B -> (wait for bytes) -> SPLIT   [A on air]
     -> NEXT (handover)
     -> STINT B -> ARM A -> (wait for bytes) -> SPLIT   [B on air]
     -> INTERVIEW -> OUTRO -> STANDBY
   ```

   Manual feed arm is default-on (the durable single-puller workflow from #489/#505), so
   BOTH feeds start paused and `event start` arms neither — the director arms the feed
   they are about to cut to. ARM is therefore a rundown step for the on-air feed too, not
   just the off-air one, and it waits for the feed to actually deliver bytes before the
   next step runs. An arm that never delivers within the timeout is a hard failure. A
   handover disarms the outgoing feed, which is why ARM A returns after NEXT.
   `smoketest.arm_violations()` models this state machine and is asserted in CI, so a
   reordered rundown cannot silently put a paused feed on air.

   **SPLIT runs at both feed parities on purpose.** `CONFIG.macros`' SPLIT carries
   `airAudio:true` ("#534: audio resolved server-side"), the fix for the Suzuka bug where
   SPLIT muted the on-air commentator on an even→odd handover. Reading the audio state back
   after SPLIT on each side is the regression test for it.

   **Source order is YouTube, Twitch, YouTube** rather than YouTube, YouTube, Twitch. Both
   orders exercise both transports in both roles; they differ only during SPLIT, where two
   feeds pull at once. With two YouTube feeds that is precisely the concurrent-googlevideo
   state known to throttle within 1-2 minutes (#505), and the relay's feed classifier does
   not distinguish 429 from a generic failure ("anything else (429/403/network/generic) —
   unchanged behaviour"). A known foreign effect that reddens the run in two minutes makes
   it useless for the one question it exists to answer. Behaviour under two parallel
   YouTube pullers deserves its own test, not a place in this spine.

8. **Assertions.** After every step, read back with `POST /obs/state` (current scene, source
   visibility, audio levels) and compare against the expected state. The extra call against
   a local OBS costs nothing and buys attribution: "step 9 SPLIT: expected Feed B live,
   measured Feed B muted" is directly actionable.
   Also observed over the window (default 5 minutes, `--minutes N`): feed state and
   resolution from `/status`, `/hud/data`, MP3 bytes from `/preview/program-audio` (the real
   ffmpeg program-audio service, so the ffmpeg path is covered by the production code),
   classified ERROR lines in the feed logs, the health history without a DROP, the overlay
   pages, OBS on Standby, Companion reachable.
9. **Teardown.** `event stop` in a `finally`. An aborted run must not leave a live relay or
   a switched OBS behind.

## Verdicts

Hard failure is reserved for what is attributable to the toolchain: no feed, no resolution,
no MP3, a classified ERROR, an arm that never delivers, a read-back mismatch. Environment
conditions (OBS not on Standby, Companion unreachable) are warnings — they can stem from a
headless session and have nothing to do with ffmpeg or yt-dlp. A test that goes red for
environmental reasons is a test that gets ignored. "Nothing suitable is live" is `[SKIP]`
with exit 0, not a failure.

## Output

`preflight`-style `[PASS]`/`[WARN]`/`[FAIL]`/`[SKIP]` lines with a summary, plus `--json`
(the pattern `speedtest [--json]` already uses). One line per run appended to
`runtime/<profile>/smoketest-history.jsonl` — timestamp, verdict, tool versions, the sources
used — mirroring `runtime/speedtest-history.jsonl`, so comparing against the last green run
is a `tail -2` rather than a feeling.

## Code layout

- `src/scripts/smoketest.py` — pure logic only: candidate acceptance, topical filtering,
  `rcq` line parsing, fingerprint parsing, the rundown table, verdict aggregation. Mirrors
  the existing pure-store modules (`cue_admin.py`, `cockpit_submissions.py`,
  `chat_admin.py`).
- `src/racecast.py` — the verb, the network calls and the orchestration.
- Outbound HTTP goes through `src/scripts/http_util.py` (house rule, enforced by
  `tests/test_http_util.py`).
- `tests/test_smoketest.py` — the pure logic, plus drift guards asserting that every scene
  and source named in the rundown exists in the shipped OBS collection JSON, and that every
  relay route reached by the run — the rundown's own AND the ones hardcoded in the
  orchestrator, which are read straight out of the call sites — exists in the relay. Each
  route is matched segment by segment as a quoted literal; a guard that only checked the
  leading segment passed even for an invented route, so `t_the_route_guard_actually_bites`
  now guards the guard. That catches a rename in CI without duplicating the panel's `CONFIG`.
- `tests/test_racecast.py` — the orchestration glue with `http_util` stubbed. The pure
  module cannot see this layer, and that is precisely where `http_util.post_json` returning
  the RAW body (unlike `get_json`, which parses) turned every successful webhook write into
  a reported failure.
- A wiki page under `src/docs/wiki/` covering when to run it and how to read the result.

## Deliberately out of scope

- No actual streaming. OBS never starts an output; a real broadcast is an operator action.
- No Control Center button: a visible UI change obliges a matching wiki screenshot refresh
  in the same change, which does not pay for a command run by hand after updates.
- No Twitch API integration (Helix/OAuth) — the public GQL category listing suffices.
- No re-implementation of the relay's command builders. This was the strongest reason to
  make a real event the spine rather than a standalone tools stage: a re-implementation only
  ever tests the re-implementation.
- No four-stint rundown with a second handover. Natural follow-up once the spine stands.
- Behaviour under two concurrent YouTube pullers (#505) belongs in its own test.
