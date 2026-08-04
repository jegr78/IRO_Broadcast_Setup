# CLAUDE.md — `tools/` (maintainer scripts, not shipped)

Loaded when working under `tools/`. `tools/` is maintainer-only (build, tokenize,
sync) and is never shipped to producers.

## Standalone binary (PyInstaller)
`tools/build-binary.py` freezes `src/racecast.py` into the `racecast` executable and
`src/racecast_ui.py` into the windowed `racecast-ui` (Control Center launcher) — one
pair per OS; the whole `src/` tree ships as bundled data under `sys._MEIPASS/src/`, so
here-relative path resolution keeps working. In frozen mode (`sys.frozen`), `racecast`
runs bundled scripts **in-process** (importlib + patched argv, string `sys.exit`
payloads go to stderr) and daemons re-invoke the binary itself (`racecast relay run`,
hidden `racecast streams run-feed`) with `PYINSTALLER_RESET_ENVIRONMENT=1` so each
child extracts its own bundle and outlives the parent. `runtime/`, `profiles/` and
`.env` live next to the binary — keep it in its own folder.
`services.py`/`companion_common.py` carry the per-OS process control (Windows: ctypes
PID probe — `os.kill(pid, 0)` would TERMINATE the target there — taskkill/tasklist,
Companion.exe discovery + `RACECAST_COMPANION_EXE` override in `.env`; native Linux:
companion-pi systemd service via `companion_linux.py`; other Linux setups — WSL/Docker/
manual AppImage — remain manual, matching the pre-existing guidance).
Releases: merge the standing **release-please** Release PR (or push a `v*` tag manually
— both work) — `.github/workflows/release.yml` tests, builds, smoke-tests and uploads
`racecast-windows.zip` / `racecast-macos.tar.gz` / `racecast-linux.tar.gz` /
`racecast-linux-arm64.tar.gz` (each contains the `racecast` binary + `.env.example`;
on first run the frozen binary copies it to `.env` — see `ensure_env_file`). The two
Linux archives are built natively on the `ubuntu-latest` (x86-64) and
`ubuntu-24.04-arm` (ARM64) matrix runners; `update.asset_name()` picks the right one
per `platform.machine()` so a self-updating ARM64 binary never fetches the x86-64
archive. release-please tags via GITHUB_TOKEN, which cannot
trigger on-tag workflows, so `release-please.yml` dispatches `release.yml`
explicitly. `ci.yml` runs the suite on all
three OSes for every PR. Unsigned binaries: SmartScreen/Gatekeeper show a
one-time "run anyway" warning.

A separate **preview** channel (`.github/workflows/preview.yml`, helper
`tools/preview_meta.py`) publishes pre-release binaries for testing ahead of a
real release — triggered by the `preview` label on a PR or by `workflow_dispatch`
against a ref. Its tags are `preview-*` (never `v*`), so it never triggers
`release.yml` or release-please; `preview-cleanup.yml` deletes a PR's pre-release
on close.

## End-to-end / regression harness (`tools/e2e.py` + `tools/e2e_checks.py`)
The integration **outer loop** (issue #199): it stands up the relay + Control Center
from `src/` as owned subprocesses and asserts the **live HTTP surface** — the class of
bug the unit suite (pure functions) can't catch. Maintainer-only (`tools/`, not shipped).
`tools/e2e_checks.py` is the pure, import-testable assertion core (free-port,
synthetic-CSV builder, tolerant `http_request`, the `CheckResult`/`run_checks` registry,
the `check_*` callables, `SYNTHETIC_CHECKS`/`REAL_LEAGUE_CHECKS`), unit-tested in
`tests/test_e2e.py`; `tools/e2e.py` owns process lifecycle (spawn, readiness-poll,
guaranteed `finally` teardown — no leaked relays/UI even on failure). Two modes:
- **Synthetic** (`tools/e2e.py`, the default, **CI-runnable**): an ephemeral temp profile +
  an in-process CSV schedule server via `--sheet-csv-url`; spawns an enabled relay + a
  cockpit-disabled relay + the Control Center on free `127.0.0.1` ports; runs 10 checks.
  No real Sheet/cookies/OBS/Tailscale. Because the relay **hard-exits at startup without
  `yt-dlp`/`streamlink` on PATH** (`racecast-feeds.py`), synthetic mode writes **no-op
  stubs** for `yt-dlp`/`streamlink`/`ffmpeg`/`deno` into the temp dir and prepends them
  to the relay's PATH (the fake schedule URLs are never pulled). The dedicated **`e2e`
  CI job** (`.github/workflows/ci.yml`, ubuntu) runs exactly this; the matrix `test` job
  already runs `tests/test_e2e.py` via `run-tests.py`.
- **Real-league** (`--real-league NAME`, **local only — refuses under CI**): drives the
  copied real-league dev build (real Sheet/cookies/`CONSOLE_SECRET`), minting a token for
  a real streamer pulled live from `/schedule/data`. Runs a **non-mutating** subset
  (`REAL_LEAGUE_CHECKS`): it **excludes** `check_submission_pending` (a `POST
  /cockpit/submit` could ping the league's real Discord webhook) and
  `check_cockpit_404_when_disabled` (needs a second relay); `check_chat_round_trip` is
  included (the crew chat is relay-local).

The checks regression-guard the four #191 cockpit bugs (env-clobber via the real
`racecast._set_env_key`, timer `—`, double-"stint" tally, flat `/cockpit/data` shape)
and the #193 own-row submission. Optional **rendered checks** (`--playwright`) use the
Playwright **Python library** (not the MCP) and SKIP when unavailable (CI omits the
flag). Visual helpers, all local-only: `--headed`/`--slowmo` (visible browser),
`--keep` (leave the services up + print the live URLs incl. the cockpit token), and
`--shots DIR` (write a screenshot of each surface — a reproducible, MCP-free tour;
the Control Center shot shows the machine's Tailscale IP, so it is a **local artifact,
never committed**). The local real-league run (copy the deployed instance's
profile/runtime/cookies in, enable cockpit on the copy, set up a Playwright venv, run,
tear down) is captured in the **`racecast-e2e`** skill, which builds on the
**`racecast-local-uat`** skill's data copy-in. Spec/plan:
`docs/superpowers/{specs,plans}/2026-06-17-e2e-regression-harness*.md`.
