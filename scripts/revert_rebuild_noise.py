#!/usr/bin/env python3
"""
Revert files that a bulk rebuild rewrote WITHOUT any real change, so only genuinely changed files stay modified in git.

Why: rebuilding e.g. wrestler profiles for an old season with today's code adds empty keys (`hometown`, `photo_url`, ...)
and a fresh `profile_generated_at` to every file (a 2014 rebuild touched ~12k files, ~1.4k with real changes). Committing
all of that is a huge, meaningless deploy. This compares every modified JSON under a path with its committed (HEAD)
version and `git checkout`s the ones whose only differences are:
  - timestamp keys (profile_generated_at, generated_at, saved_at, last_updated, updated_at, ...), or
  - keys that are NEW in the rebuilt file and empty (null / "" / [] / {}), or NEW and named in --ignore-added.
Anything else (a changed value, a new non-empty key, a different list length) is a REAL change and is left alone.

Only run it on paths that were clean before the rebuild (it discards the file's working-tree changes for noise-only files).

Usage (from repo root):
    .venv/bin/python scripts/revert_rebuild_noise.py frontend/hs-ky-ui/public/data/wrestlers/boys/2014 --dry-run
    .venv/bin/python scripts/revert_rebuild_noise.py frontend/hs-ky-ui/public/data/wrestlers/boys
    .venv/bin/python scripts/revert_rebuild_noise.py <path> --ignore-added grade,hometown   # also treat these new keys as noise
"""
import collections
import json
import subprocess
import sys

TS_KEYS = {"profile_generated_at", "generated_at", "generated_at_utc", "generatedAt", "saved_at", "last_updated", "updated_at",
           "created_at", "computed_at", "built_at"}


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


EXTRA_IGNORED_NEW_KEYS = set()   # set from --ignore-added: new keys treated as noise even when non-empty


def _norm(new, old):
    """`new` with timestamp keys removed and with keys that are absent from `old` AND (empty or in --ignore-added) removed."""
    if isinstance(new, dict):
        o = old if isinstance(old, dict) else {}
        out = {}
        for k, v in new.items():
            if k in TS_KEYS or (k not in o and (_empty(v) or k in EXTRA_IGNORED_NEW_KEYS)):
                continue
            out[k] = _norm(v, o.get(k))
        return out
    if isinstance(new, list):
        o = old if isinstance(old, list) and len(old) == len(new) else [None] * len(new)
        return [_norm(v, ov) for v, ov in zip(new, o)]
    return new


def _strip_ts(x):
    if isinstance(x, dict):
        return {k: _strip_ts(v) for k, v in x.items() if k not in TS_KEYS}
    if isinstance(x, list):
        return [_strip_ts(v) for v in x]
    return x


def main():
    argv = sys.argv[1:]
    if "--ignore-added" in argv:
        i = argv.index("--ignore-added")
        EXTRA_IGNORED_NEW_KEYS.update(k for k in argv[i + 1].split(",") if k)
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    dry = "--dry-run" in argv
    if len(args) != 1:
        sys.exit(__doc__)
    spec = args[0]
    files = [f for f in subprocess.run(["git", "diff", "--name-only", "--", spec],
                                       capture_output=True, text=True, check=True).stdout.split("\n") if f]
    cat = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def head(path):
        cat.stdin.write(f"HEAD:{path}\n".encode())
        cat.stdin.flush()
        hdr = cat.stdout.readline().decode().split()
        if len(hdr) < 3 or hdr[1] == "missing":
            return None
        data = cat.stdout.read(int(hdr[2]))
        cat.stdout.read(1)
        return data

    noise, real, other = [], [], []
    for f in files:
        old = head(f) if f.endswith(".json") else None
        if old is None:
            other.append(f)
            continue
        try:
            oldj, newj = json.loads(old), json.load(open(f, encoding="utf-8"))
        except Exception:
            other.append(f)
            continue
        (noise if _norm(newj, oldj) == _strip_ts(oldj) else real).append(f)

    print(f"modified: {len(files)}   noise-only: {len(noise)}   REAL changes: {len(real)}   non-json/new/unparsed: {len(other)}")
    if noise and not dry:
        for i in range(0, len(noise), 500):
            subprocess.run(["git", "checkout", "--"] + noise[i:i + 500], check=True)
        print(f"reverted {len(noise)} noise-only files")
    by_dir = collections.Counter("/".join(f.split("/")[:-1][-2:]) for f in real)
    print("real changes by folder:", dict(by_dir.most_common(5)))


if __name__ == "__main__":
    main()
