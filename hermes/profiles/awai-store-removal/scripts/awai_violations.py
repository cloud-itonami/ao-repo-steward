#!/usr/bin/env python3
"""Evidence script for awai-store-removal bot.
Runs verify-awai-state-store-policy.cljk, prints MEASURE lines + next-work pick.
Read-only: never mutates git state. Exits 2 when measurement itself failed."""
import json, os, subprocess, sys, datetime

ROOT = "~/github/com-junkawasaki"
LEDGER = os.path.expanduser("~/.hermes/profiles/awai-store-removal/workspace/removal-ledger.jsonl")
VERIFY = os.path.join(ROOT, "scripts/verify-awai-state-store-policy.cljk")

def out(*a):
    print(*a)

def main():
    try:
        r = subprocess.run(
            ["kbb", "--backend", "sci", VERIFY, "--root", "."],
            cwd=ROOT, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        out("STATUS\tREFUSED\tverify timeout 240s")
        return 2
    if r.returncode not in (0, 1):
        out("STATUS\tREFUSED\tverify rc=%s stderr=%s" % (r.returncode, (r.stderr or "")[:200]))
        return 2
    violations = {}
    scanned = None
    for line in (r.stdout or "").splitlines():
        parts = line.rstrip("\n").split("\t")
        if parts[0] == "SCANNED":
            scanned = parts[1]
        elif parts[0] == "VIOLATION" and len(parts) >= 3:
            path, kinds = parts[1], parts[2]
            repo = path[len(ROOT):].lstrip("/").split("/wrangler")[0]
            violations[repo] = kinds
        elif parts[0] == "VIOLATIONS":
            out("MEASURE\tviolations\t%s" % parts[1])
    if scanned is None:
        out("STATUS\tREFUSED\tno SCANNED line")
        return 2
    out("MEASURE\tscanned\t%s" % scanned)
    out("MEASURE\tviolations_detail\t%s" % json.dumps(violations, ensure_ascii=False))

    # landed = latest ledger row for the repo carries a merge sha.
    # design/mapped/started-incomplete rows do NOT clear a repo (2026-09-19:
    # script used rec.get("merge") which never exists -> every row counted as
    # landed -> false ALL-CLEAN while 9 real violations stood).
    import re
    done = {}
    done_land = {}
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("repo"):
                        sha = None
                        for k in ("merge", "merge_sha"):
                            v = rec.get(k)
                            if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{7,40}", v.strip()):
                                sha = v.strip()
                                break
                        done[rec["repo"]] = sha or "?"
                        if sha:
                            done_land[rec["repo"]] = sha
                except Exception:
                    pass
    out("MEASURE\tledger_landed\t%d" % len(done_land))

    # next pick: violation whose repo has no merged landing row, skip archived manimani
    picks = [k for k in sorted(violations)
             if k not in done_land and "manimani/appview" not in k]
    if not picks:
        out("STATUS\tALL-CLEAN\tno unlanded violation (archived repos excluded)")
        return 0
    next_repo = picks[0]
    out("PICK\t%s\t%s" % (next_repo, violations[next_repo]))
    out("MEASURE\tremaining\t%d" % len(picks))
    return 0

sys.exit(main())
