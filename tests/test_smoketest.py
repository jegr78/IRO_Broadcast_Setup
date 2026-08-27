#!/usr/bin/env python3
"""Stdlib unit checks for the post-update smoke test. Run: python3 tests/test_smoketest.py"""
import importlib.util
import json
import re
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *rel))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


st = _load("smoketest", ("src", "scripts", "smoketest.py"))


# ---------------------------------------------------------------- parsing

def t_parse_rcq():
    assert st.parse_rcq("rcq 1080 60") == (1080, 60)
    assert st.parse_rcq("some noise\nrcq 720 30\nmore") == (720, 30)
    # yt-dlp prints "NA" for a missing field on some formats.
    assert st.parse_rcq("rcq NA NA") is None
    assert st.parse_rcq("") is None
    assert st.parse_rcq("rcq") is None


def t_parse_js_runtimes():
    line = "[debug] JS runtimes: deno-2.9.5\n[debug] [youtube] [jsc] JS Challenge Providers: deno"
    assert st.parse_js_runtimes(line) == "deno-2.9.5"
    assert st.parse_js_runtimes("nothing here") is None


def t_ladder_max_height():
    q = ["audio_only", "160p30", "360p30", "480p30", "720p60", "1080p60", "worst", "best"]
    assert st.ladder_max_height(q) == 1080
    assert st.ladder_max_height(["audio_only", "worst", "best"]) == 0
    assert st.ladder_max_height(["480p"]) == 480
    assert st.ladder_max_height([]) == 0


def t_topical_match():
    assert st.topical_match("🔴 LIVE iRacing 🏁 RUMO AOS 1.000 INSCRITOS!")
    assert st.topical_match("GT7 Daily Races")
    assert st.topical_match("LMU Daytona 8 Hours")
    # Language-independent: the game name carries the match, not English words.
    assert st.topical_match("Porsche Cup e GR86 no iRacing")
    assert not st.topical_match("La Plata, Missouri, USA | LIVE Train Camera")
    assert not st.topical_match("Tarkov KORD Breach grinding!")
    assert not st.topical_match("")
    # Substring hits inside an unrelated word must not count (#: "lmu" in "alumni").
    assert not st.topical_match("alumni reunion stream")


# ------------------------------------------------------------- acceptance

def t_accept_youtube():
    ok, why = st.accept_youtube(1080, "GT7 Daily Races", "SomeChannel")
    assert ok and why == ""
    ok, why = st.accept_youtube(480, "GT7 Daily Races", "SomeChannel")
    assert not ok and "480" in why
    ok, why = st.accept_youtube(1080, "Train Camera", "Railcam")
    assert not ok and "topic" in why.lower()
    # A VOD resolves to a muxed 360p format, which is exactly why VODs are unusable.
    ok, why = st.accept_youtube(360, "iRacing race replay", "Chan")
    assert not ok
    ok, why = st.accept_youtube(None, "GT7", "Chan")
    assert not ok and "resolution" in why.lower()


def t_accept_twitch():
    q = ["audio_only", "480p30", "720p60", "1080p60", "best"]
    ok, why = st.accept_twitch("twitch", q, "Le Mans Ultimate")
    assert ok and why == ""
    ok, why = st.accept_twitch("twitch", ["480p30"], "Le Mans Ultimate")
    assert not ok and "480" in why
    ok, why = st.accept_twitch("twitch", q, "Just Chatting")
    assert not ok and "categ" in why.lower()
    ok, why = st.accept_twitch(None, q, "iRacing")
    assert not ok and "plugin" in why.lower()


# -------------------------------------------------------------- discovery

def t_youtube_live_search_url():
    u = st.youtube_live_search_url("sim racing live")
    assert u.startswith("https://www.youtube.com/results?")
    assert "search_query=sim+racing+live" in u
    # The live filter is what keeps VODs out of the result set.
    assert st.YOUTUBE_LIVE_FILTER in u


def t_twitch_query_shape():
    body = st.twitch_category_query("Gran Turismo 7", first=4)
    assert "Gran Turismo 7" in body["query"]
    assert "first:4" in body["query"]
    # A quote in the category name must not be able to break out of the GraphQL string.
    body = st.twitch_category_query('Ev"il', first=1)
    assert 'Ev"il' not in body["query"]
    assert st.TWITCH_CLIENT_ID and st.TWITCH_GQL_URL.startswith("https://")


def t_rank_twitch_candidates():
    cands = [{"login": "a", "viewers": 3}, {"login": "b", "viewers": 500},
             {"login": "c", "viewers": 60}]
    # Viewers order the attempts; they never exclude a candidate.
    assert [c["login"] for c in st.rank_by_viewers(cands)] == ["b", "c", "a"]
    assert len(st.rank_by_viewers(cands)) == 3


# ------------------------------------------------------------ source plan

def t_source_plan_is_yt_twitch_yt():
    # Two concurrent googlevideo pullers throttle (#505); SPLIT must never see two.
    assert st.SOURCE_PLAN == ("youtube", "twitch", "youtube")
    rows = st.plan_rows(["yt1", "yt2"], ["tw1"])
    assert rows == [(1, "yt1"), (2, "tw1"), (3, "yt2")]


def t_plan_rows_needs_every_slot():
    assert st.plan_rows(["yt1"], ["tw1"]) is None      # only one YouTube source
    assert st.plan_rows(["yt1", "yt2"], []) is None    # no Twitch source


def t_clear_rows_covers_more_than_it_writes():
    # Row 4 exists in the sheet and is cleared but never rewritten.
    assert set(st.clear_rows(4)) == {1, 2, 3, 4}
    assert set(st.clear_rows(3)) == {1, 2, 3}


# ----------------------------------------------------------- confirmation

def t_confirm_phrase_names_the_profile():
    # Naming the profile is the guard against running the right command on the
    # wrong league — a bare "YES" would not catch that.
    assert st.confirm_phrase("testing") == "CLEAR SCHEDULE testing"
    assert st.confirm_phrase("iro-gtec") == "CLEAR SCHEDULE iro-gtec"
    assert st.phrase_ok("testing", "CLEAR SCHEDULE testing")
    assert st.phrase_ok("testing", "  CLEAR SCHEDULE testing  ")
    assert not st.phrase_ok("testing", "clear schedule testing")
    assert not st.phrase_ok("testing", "YES")
    assert not st.phrase_ok("testing", "CLEAR SCHEDULE iro-gtec")


# --------------------------------------------------------------- rundown

def t_rundown_shape():
    labels = [s.label for s in st.RUNDOWN]
    assert labels[0] == "STANDBY" and labels[-1] == "STANDBY"
    assert labels.count("SPLIT") == 2, "SPLIT must run at BOTH feed parities (#534)"
    assert "NEXT" in labels
    i_next = labels.index("NEXT")
    assert labels.index("SPLIT") < i_next < len(labels) - labels[::-1].index("SPLIT") - 1


def t_arm_precedes_every_split():
    """A SPLIT against an unarmed feed shows a black half — manual arm is default-on."""
    labels = [s.label for s in st.RUNDOWN]
    for i, lab in enumerate(labels):
        if lab == "SPLIT":
            before = labels[:i]
            assert any(b.startswith("ARM") for b in before), f"no ARM before SPLIT at {i}"
            # …and the nearest preceding arm must be followed by a byte wait.
            j = max(k for k, b in enumerate(before) if b.startswith("ARM"))
            assert st.RUNDOWN[j].wait_for_bytes, "ARM must wait for bytes before SPLIT"


def t_no_step_puts_an_unarmed_feed_on_air():
    """Both feeds start paused under manual arm and `event start` arms neither.

    Caught the real thing: the rundown cut to STINT A without ever arming Feed A,
    so the whole first stint pulled nothing and the run went red for a reason that
    had nothing to do with ffmpeg/yt-dlp/deno.
    """
    assert st.arm_violations() == []


def t_arm_violations_sees_a_missing_arm():
    """The guard must actually bite — the same rundown minus its first ARM."""
    stripped = tuple(s for s in st.RUNDOWN if s.relay != "feed/A/activate")
    assert "STINT A" in st.arm_violations(stripped)


def t_arm_violations_sees_the_handover_disarm():
    """A handover disarms the outgoing feed; airing it again without a re-arm is a bug."""
    rundown = (
        st.Step("ARM A", "arm", relay="feed/A/activate"),
        st.Step("STINT A", "macro", scene="Stint", unmute=("Feed A",)),
        st.Step("ARM B", "arm", relay="feed/B/activate"),
        st.Step("NEXT", "relay", relay="next"),
        st.Step("STINT B", "macro", scene="Stint", unmute=("Feed B",)),
        st.Step("BACK TO A", "macro", scene="Stint", unmute=("Feed A",)),
    )
    assert st.arm_violations(rundown) == ["BACK TO A"]


def t_arm_verdict_rests_on_bytes_not_on_the_arm_call():
    """Manual arm off is a machine setting; the feed self-arms and bytes still decide."""
    assert st.arm_verdict(True, True)[0] == st.PASS
    assert st.arm_verdict(False, True)[0] == st.PASS
    assert "self-armed" in st.arm_verdict(False, True)[1]
    assert st.arm_verdict(True, False)[0] == st.FAIL
    assert st.arm_verdict(False, False)[0] == st.FAIL   # no bytes is a real failure


def t_stream_host_is_the_ssrf_gate():
    """Discovered URLs reach a local yt-dlp WITH the cookie jar and the league
    sheet, so they get the relay's host allow-list before either."""
    assert st.stream_host("https://www.youtube.com/watch?v=x") == "youtube.com"
    assert st.stream_host("https://youtu.be/x") == "youtu.be"
    assert st.stream_host("https://www.twitch.tv/someone") == "twitch.tv"
    # A substring test would pass these; parsing the hostname does not.
    assert st.stream_host("https://evil.example/twitch.tv") == ""
    assert st.stream_host("https://youtube.com@evil.example/x") == ""
    assert st.stream_host("http://169.254.169.254/latest/meta-data") == ""
    assert st.stream_host("file:///etc/passwd") == ""
    assert st.stream_host("") == ""


def t_platform_of_reads_the_hostname():
    assert st.platform_of("https://www.twitch.tv/a") == "twitch"
    assert st.platform_of("https://www.youtube.com/watch?v=a") == "youtube"
    assert st.platform_of("https://evil.example/twitch.tv") == ""


def t_twitch_login_is_no_looser_than_the_canonical_validator():
    """The GQL login lands in a URL and in the sheet, so it is charset-checked.

    `broadcast_chat.twitch_login` EXTRACTS a login from a URL or @handle; this one
    VALIDATES an already-bare login from the API reply. So the invariant is not
    equality but strictness: whatever this accepts, the canonical one accepts
    unchanged. (Equality would fail on "../etc", which the canonical extractor
    happily reduces to "etc".)
    """
    bc = _load("broadcast_chat", ("src", "scripts", "broadcast_chat.py"))
    for value in ("someone", "Some_One", "a" * 25):
        assert st.twitch_login_ok(value)
        assert bc.twitch_login(value) == value.strip().lower(), value
    for value in ("a" * 26, "", "   ", "with space", "semi;colon",
                  "nl\r\njoin #other", "../etc", "a/b"):
        assert not st.twitch_login_ok(value), value


def t_step_error_verdict_treats_a_dead_obs_like_the_read_backs():
    """SPLIT is the only step whose own call surfaces an OBS error; failing hard
    there while every read-back only warns would contradict the classification."""
    assert st.step_error_verdict("obs unavailable")[0] == st.WARN
    assert st.step_error_verdict("OBS unreachable: connection refused")[0] == st.WARN
    assert st.step_error_verdict("manual feed arm disabled")[0] == st.FAIL
    assert st.step_error_verdict("boom")[0] == st.FAIL


def t_program_audio_skips_when_the_endpoint_is_absent():
    """Fan-out off is a machine setting; blaming ffmpeg for it would be a false red."""
    assert st.program_audio_verdict(64000)[0] == st.PASS
    assert st.program_audio_verdict(0, "HTTP 404")[0] == st.SKIP
    assert st.program_audio_verdict(0, "HTTP 503")[0] == st.FAIL
    assert st.program_audio_verdict(12, "")[0] == st.FAIL      # encoder made no frames


def t_split_audio_expectation_follows_the_on_air_feed():
    """The Suzuka regression: SPLIT muted the on-air commentator on even->odd."""
    split = next(s for s in st.RUNDOWN if s.label == "SPLIT")
    a = st.expected_after(split, on_air="Feed A")
    assert a["scene"] == "Splitscreen"
    assert a["muted"]["Feed A"] is False
    assert a["muted"]["Feed B"] is True
    assert a["muted"]["Discord Audio Capture"] is True
    b = st.expected_after(split, on_air="Feed B")
    assert b["muted"]["Feed B"] is False
    assert b["muted"]["Feed A"] is True


def t_expected_after_plain_macro():
    stint_a = next(s for s in st.RUNDOWN if s.label == "STINT A")
    e = st.expected_after(stint_a, on_air="Feed A")
    assert e["scene"] == "Stint"
    assert e["visible"][("Stint", "Feed A")] is True
    assert e["visible"][("Stint", "Feed B")] is False
    assert e["muted"]["Feed A"] is False


def t_rundown_targets_exist_in_the_shipped_collection():
    """Drift guard: a renamed scene/source in OBS must fail here, not on air."""
    with open(os.path.join(ROOT, "src", "obs", "GT_Racing_Endurance.json"),
              encoding="utf-8") as fh:
        coll = json.load(fh)
    scenes = {s["name"]: {i["name"] for i in (s.get("settings") or {}).get("items") or []}
              for s in coll.get("sources", []) if s.get("id") == "scene"}
    inputs = {s["name"] for s in coll.get("sources", [])}
    for scene in st.rundown_scenes():
        assert scene in scenes, f"scene {scene!r} is not in the shipped collection"
    for scene, source in st.rundown_obs_targets():
        assert source in scenes[scene], f"{source!r} is not an item of scene {scene!r}"
    for name in st.rundown_audio_inputs():
        assert name in inputs, f"audio input {name!r} is not in the shipped collection"


def _relay_source():
    with open(os.path.join(ROOT, "src", "relay", "racecast-feeds.py"),
              encoding="utf-8") as fh:
        return fh.read()


def _route_segments(path):
    """Path segments the relay matches on, minus the feed letter (feed/B/activate
    -> feed, activate). The relay routes on a split path list, so every one of
    these appears as a quoted literal in its source."""
    return [seg for seg in path.split("/") if seg not in ("A", "B", "POV")]


def _assert_route_exists(src, path, where):
    for seg in _route_segments(path):
        assert f'"{seg}"' in src, f"relay route segment {seg!r} missing for {where}"


def t_rundown_relay_paths_exist_in_the_relay():
    """Drift guard: a renamed relay route must fail here, not mid-rundown.

    Checks EVERY segment as a quoted literal. The first version only tested the
    leading segment ("/feed" in src), which even the invented route
    feed/B/voellig-erfunden passed — it guarded nothing.
    """
    src = _relay_source()
    for step in st.RUNDOWN:
        if step.relay:
            _assert_route_exists(src, step.relay, step.label)
    assert any(s.relay == "feed/B/activate" for s in st.RUNDOWN)
    assert any(s.relay == "timer/stop" for s in st.RUNDOWN)   # panel PAUSE == timer/stop
    assert not any(s.relay == "timer/pause" for s in st.RUNDOWN)


def t_the_route_guard_actually_bites():
    """Guard the guard: an invented route must be rejected."""
    src = _relay_source()
    for bogus in ("feed/B/voellig-erfunden", "timer/gibtsnicht", "obs/nichtda"):
        try:
            _assert_route_exists(src, bogus, "bogus")
        except AssertionError:
            continue
        raise AssertionError(f"the route guard accepted {bogus!r}")


def t_orchestrator_relay_paths_exist_in_the_relay():
    """The rundown is not the only caller: _smoke_apply/_observe hardcode
    obs/scene, obs/source, obs/audio, obs/split-audio, obs/state and more. They
    are exactly as rename-prone, so they are read straight out of the call sites
    rather than mirrored into a list that could drift."""
    with open(os.path.join(ROOT, "src", "racecast.py"), encoding="utf-8") as fh:
        orchestrator = fh.read()
    paths = set(re.findall(r'_smoke_relay_(?:get|post)\(\s*f?"([a-z0-9/_-]+)"', orchestrator))
    assert {"obs/scene", "obs/source", "obs/audio", "obs/split-audio", "obs/state",
            "status"} <= paths, f"call sites changed shape: {sorted(paths)}"
    src = _relay_source()
    for path in sorted(paths):
        _assert_route_exists(src, path, "orchestrator")


def t_state_mismatches():
    split = next(s for s in st.RUNDOWN if s.label == "SPLIT")
    exp = st.expected_after(split, on_air="Feed B")
    good = {"scene": "Splitscreen",
            "sources": [{"scene": "Splitscreen", "source": "Feed A", "enabled": True},
                        {"scene": "Splitscreen", "source": "Feed B", "enabled": True}],
            "audio": [{"input": "Feed A", "muted": True},
                      {"input": "Feed B", "muted": False},
                      {"input": "Discord Audio Capture", "muted": True}]}
    assert st.state_mismatches(exp, good) == []
    # The Suzuka failure mode: on-air feed silently muted by the macro.
    bad = json.loads(json.dumps(good))
    bad["audio"][1]["muted"] = True
    msgs = st.state_mismatches(exp, bad)
    assert len(msgs) == 1 and "Feed B" in msgs[0] and "live" in msgs[0]
    # A wrong scene is reported on its own.
    assert any("scene expected" in m
               for m in st.state_mismatches(exp, {**good, "scene": "Stint"}))
    # An unreadable item is reported, never counted as a match.
    assert st.state_mismatches(exp, {"scene": "Splitscreen"})


def t_state_probe():
    split = next(s for s in st.RUNDOWN if s.label == "SPLIT")
    body = st.state_probe(split, on_air="Feed A")
    assert {"scene": "Splitscreen", "source": "Feed B"} in body["sources"]
    assert "Discord Audio Capture" in body["inputs"]


# ---------------------------------------------------------------- verdict

def t_hard_and_soft_classification():
    """Environment problems must not redden a run about the toolchain."""
    assert st.severity_for("feed_a_bytes", False) == st.FAIL
    assert st.severity_for("hud_data", False) == st.FAIL
    assert st.severity_for("obs_standby", False) == st.WARN
    assert st.severity_for("cookies", False) == st.WARN   # setup, not toolchain
    assert st.severity_for("companion", False) == st.WARN
    assert st.severity_for("feed_a_bytes", True) == st.PASS


def t_summarize():
    R = st.Result
    s = st.summarize([R("a", st.PASS, ""), R("b", st.WARN, "meh")])
    assert s["verdict"] == st.WARN and s["counts"][st.WARN] == 1
    s = st.summarize([R("a", st.PASS, ""), R("b", st.FAIL, "boom"), R("c", st.WARN, "")])
    assert s["verdict"] == st.FAIL
    s = st.summarize([R("a", st.PASS, ""), R("b", st.SKIP, "nothing live")])
    assert s["verdict"] == st.SKIP
    assert st.summarize([R("a", st.PASS, "")])["verdict"] == st.PASS
    assert st.summarize([])["verdict"] == st.SKIP


def t_exit_code_skip_is_not_a_failure():
    # "nobody is streaming at 04:00" must not train the operator to ignore red.
    assert st.exit_code(st.PASS) == 0
    assert st.exit_code(st.WARN) == 0
    assert st.exit_code(st.SKIP) == 0
    assert st.exit_code(st.FAIL) == 1


def t_status_readers_match_the_relay_shape():
    """Relay.status(): feeds is a DICT, and live.feed names the on-air one."""
    status = {"feeds": {"A": {"state": "serving", "armed": True, "down": False},
                        "B": {"state": "connecting", "armed": True, "down": False},
                        "POV": {"state": "stopped", "armed": False, "down": False}},
              "live": {"feed": "B", "stint": 2, "mode": "race"},
              "health": {"level": "green", "reasons": []}}
    assert st.feed_serving(status, "A") is True
    assert st.feed_serving(status, "b") is False        # case-insensitive lookup
    assert st.on_air_feed(status) == "Feed B"
    assert st.health_level(status) == "green"
    assert not st.is_drop_sample(status)
    # A serving-but-down feed is not serving.
    status["feeds"]["A"]["down"] = True
    assert st.feed_serving(status, "A") is False
    # Missing/garbage payloads must not raise.
    assert st.feed_serving({}, "A") is False
    assert st.on_air_feed({}) is None
    assert st.on_air_feed({"live": {"feed": "POV"}}) is None
    assert st.health_level({}) == ""
    assert st.is_drop_sample({"health": {"level": "RED"}})


# ---------------------------------------------------------------- history

def t_history_entry():
    e = st.history_entry("2026-08-27T18:00:00Z", st.PASS,
                         tools={"yt-dlp": "2026.08.19", "deno": "2.9.5"},
                         sources=[{"row": 1, "platform": "youtube", "url": "u"}],
                         minutes=5, results=[st.Result("a", st.PASS, "")])
    assert e["ts"] == "2026-08-27T18:00:00Z" and e["verdict"] == st.PASS
    assert e["tools"]["deno"] == "2.9.5"
    assert e["sources"][0]["platform"] == "youtube"
    assert e["minutes"] == 5
    # One line, so `tail -2` compares two runs.
    assert "\n" not in json.dumps(e)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            fn(); print("ok", name)
    print("ALL PASS")
