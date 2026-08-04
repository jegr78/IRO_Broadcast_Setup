#!/usr/bin/env python3
"""Keep bundled, immutable files readable for the life of the process.

A PyInstaller onefile binary extracts the whole `src/` tree into the OS temp
directory and reads from there at runtime. Every OS reaps that directory on a
schedule, and none of them check whether a process still has it in use:

    macOS    com.apple.bsd.dirhelper, daily 03:35, CLEAN_FILES_OLDER_THAN_DAYS=3
    Linux    systemd-tmpfiles-clean.timer, /tmp default age 10d
    Windows  Storage Sense — off by default, so rarely a problem there

The age is per FILE and counted from last access, so the interpreter's shared
libraries survive (they stay mapped) while a page that is only read when
somebody opens it does not. A Control Center left running for a few days then
answers every request with "file not found" even though nothing crashed —
observed after 14 days of uptime, with the whole extracted `src/` emptied.

Reading such a file ONCE into memory removes the failure entirely. That is only
correct for bundle content, which cannot change while we run. Anything meant to
pick up edits — a profile's overlay CSS, downloaded graphics, the Sheet cache —
must keep reading per request and must NOT go through this cache.
"""
import os


class BundleCache:
    """Read-through cache for immutable bundled files, keyed by path."""

    def __init__(self):
        self._data = {}

    def read(self, path):
        """Bytes of *path*, from memory once it has been read successfully.

        Raises OSError only when the file was never read AND is not on disk —
        that is a genuinely missing resource, not an evicted one.
        """
        hit = self._data.get(path)
        if hit is not None:
            return hit
        with open(path, "rb") as fh:
            data = fh.read()
        self._data[path] = data
        return data

    def prewarm(self, paths):
        """Read *paths* now, while the extraction directory is still intact.

        Lazy caching alone would not help a file that nobody touches before the
        cleaner runs. Returns how many were loaded; a missing file is skipped
        rather than raised, so an optional page cannot break startup.
        """
        loaded = 0
        for path in paths:
            try:
                self.read(path)
            except OSError:
                continue
            loaded += 1
        return loaded

    def cached(self, path):
        return path in self._data


def eviction_hint(path):
    """Operator-facing message for a bundled file that is gone at runtime."""
    return (f"bundled file unavailable: {os.path.basename(path)} — the OS "
            "cleaned up this build's temporary extraction directory. "
            "Restart racecast to unpack it again.")
