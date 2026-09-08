#!/usr/bin/env python3
"""SessionStart hook: one line per roadmap under ./ge that is in progress, paused, stopped or has open calls.
Exit 0 always; under 1 s (reads files only; no guard command is run). One bad roadmap does not hide the rest."""
import json, os, sys
from pathlib import Path

def main():
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    try:
        raw = sys.stdin.read()
        cwd = json.loads(raw).get("cwd") if raw.strip() else None
    except Exception:
        cwd = None
    try:
        root = Path(cwd or os.getcwd()).resolve()  # the payload's cwd may be relative or hold a symlink
        if not (root / "ge").is_dir(): return 0
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts")); os.chdir(root)
        import ge
        names = [d.name for d in sorted((root / "ge").iterdir()) if (d / "roadmap.md").is_file()]
    except Exception as e:
        print(f"ge: could not read ./ge ({e})")
        return 0
    for name in names:
        try:
            _, done, total, state, calls = ge.roadmap_state(name)
        except Exception as e:
            print(f"ge: could not read roadmap {name} ({e})")
            continue
        if state == "idle" and calls == 0: continue
        if state.startswith("in progress ("): what = "is working on " + state[len("in progress ("):-1]
        elif state.startswith("paused: "): what = "is paused (" + state[len("paused: "):] + ")"
        elif state == "stopped": what = "is stopped"
        else: what = "is idle"
        waiting = f", {calls} decision{'s' if calls != 1 else ''} waiting for you" if calls else ""
        print(f"ge: {name} {what}, {done} of {total} tasks done{waiting}. /ge-status {name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
