#!/usr/bin/env python3
"""Check the eval harness without an agent: every check.py fails on its
untouched sample, and measure.py gives the expected answers on the samples."""
import glob
import re
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = os.path.join(ROOT, "skills/ci-measure/scripts/measure.py")
E = os.path.join(ROOT, "evals")
bad = []


def run(args, cwd=None):
    return subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True)


# measure.py on the recorded histories
r = run([M, "split", "--in", "ci-history/runs.jsonl"], cwd=E + "/ci-diagnose/repo")
if "job that finishes last: test" not in r.stdout:
    bad.append("split: slowest path should be the test job\n" + r.stdout + r.stderr)
r = run([M, "split", "--in", "ci-history/runs.jsonl"], cwd=E + "/ci-flaky-tests/repo")
if "CI / test" not in r.stdout.split("rerun, same commit:")[-1]:
    bad.append("split: rerun flakes not found\n" + r.stdout)
# Catch-up runs: every fourth run only merged main in; a feature merge message must not count.
with tempfile.TemporaryDirectory() as t:
    import json
    rows = [json.loads(l) for l in open(E + "/ci-diagnose/repo/ci-history/runs.jsonl") if l.strip()]
    for i, row in enumerate(rows):
        row["head_message"] = ("Merge branch 'main' into feature-%d" % i if i % 4 == 0
                               else "Merge pull request #%d from x/y" % i if i % 4 == 1 else "Fix the parser")
    with open(t + "/runs.jsonl", "w") as f:
        f.write("".join(json.dumps(row) + "\n" for row in rows))
    r = run([M, "split", "--in", t + "/runs.jsonl", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    want = len([i for i in range(len(rows)) if i % 4 == 0])
    if got.get("catch_up_runs") != want or not 0.1 < got.get("catch_up_share", 0) < 0.5:
        bad.append("split: catch-up runs miscounted\n" + r.stdout + r.stderr)
# Cancelled copies of every run must not change the split (same cohort as the wait);
# a second workflow gives a PR wait across workflows; forks are told apart by repo.
with tempfile.TemporaryDirectory() as t:
    import copy
    rows = [json.loads(l) for l in open(E + "/ci-diagnose/repo/ci-history/runs.jsonl") if l.strip()]
    extra = []
    for row in rows:
        c = copy.deepcopy(row); c["id"] += 100000; c["conclusion"] = "cancelled"
        for j in c["jobs"]:
            j["conclusion"] = "cancelled"; j["steps"] = j["steps"][:2]
            j["completed_at"] = j["steps"][-1]["completed_at"] if j["steps"] else j["started_at"]
        extra.append(c)
    with open(t + "/runs.jsonl", "w") as f:
        f.write("".join(json.dumps(x) + "\n" for x in rows + extra))
    clean = json.loads(run([M, "split", "--in", E + "/ci-diagnose/repo/ci-history/runs.jsonl", "--json"]).stdout)
    mixed = json.loads(run([M, "split", "--in", t + "/runs.jsonl", "--json"]).stdout)
    if clean["slowest_path_split"] != mixed["slowest_path_split"]:
        bad.append("split: cancelled runs changed the slowest-path split")
    if not clean.get("runs_per_day") or not 7 < clean["runs_per_day"] < 10:
        bad.append("split: runs a day wrong: %r" % clean.get("runs_per_day"))
    second = []
    for row in rows:
        c = copy.deepcopy(row); c["id"] += 200000; c["name"] = "E2E"; c["path"] = ".github/workflows/e2e.yml"
        for j in c["jobs"]:
            j["completed_at"] = j["completed_at"].replace("T", "T", 1)
        second.append(c)
    # E2E finishes 5 minutes after CI on every commit.
    def later(v):
        from datetime import datetime, timedelta
        return (datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in second:
        for j in c["jobs"]:
            j["completed_at"] = later(j["completed_at"])
    with open(t + "/two.jsonl", "w") as f:
        f.write("".join(json.dumps(x) + "\n" for x in rows + second))
    two = json.loads(run([M, "split", "--in", t + "/two.jsonl", "--json"]).stdout)
    if not two.get("wait_all_workflows_median") or two["wait_all_workflows_median"] < clean["wait_median"] + 290:
        bad.append("split: PR wait across workflows missed the slower workflow: %r" % two.get("wait_all_workflows_median"))
    forks = []
    for i, row in enumerate(rows[:6]):
        c = copy.deepcopy(row); c["pull_requests"] = []; c["head_branch"] = "main"
        c["head_repo"] = "fork-%d/web" % i; c["head_sha"] = "f%039d" % i
        forks.append(c)
    with open(t + "/forks.jsonl", "w") as f:
        f.write("".join(json.dumps(x) + "\n" for x in forks))
    fk = json.loads(run([M, "split", "--in", t + "/forks.jsonl", "--json"]).stdout)
    if fk.get("pushes_per_pr_max") != 1:
        bad.append("split: fork PRs on branch main were lumped together")
# Tests moved between shard folders are the same tests; a lost matrix copy is not.
with tempfile.TemporaryDirectory() as t:
    def report(folder, names):
        os.makedirs(folder, exist_ok=True)
        cases = "".join('<testcase classname="t.m" name="%s"/>' % n for n in names)
        open(folder + "/r.xml", "w").write('<testsuite name="pytest">%s</testsuite>' % cases)
    names = ["test_%d" % i for i in range(8)]
    for i in range(4):
        report(t + "/before/shard-%d" % i, names[i * 2:i * 2 + 2])
    for i in range(2):
        report(t + "/after/shard-%d" % i, names[i * 4:i * 4 + 4])
    r = run([M, "tests", "--before", t + "/before", "--after", t + "/after"])
    if r.returncode != 0:
        bad.append("tests: re-sharding read as lost tests\n" + r.stdout)
    report(t + "/os/linux", names); report(t + "/os/windows", names[:4])
    report(t + "/moved/linux", names[:4]); report(t + "/moved/windows", names)
    r = run([M, "tests", "--before", t + "/os", "--after", t + "/moved"])
    if r.returncode == 0:
        bad.append("tests: tests moved from the linux leg to the windows leg read as kept")
    report(t + "/rt/py39", names); report(t + "/rt/py312", names[:4])
    report(t + "/rt2/py39", names[:4]); report(t + "/rt2/py312", names)
    r = run([M, "tests", "--before", t + "/rt", "--after", t + "/rt2"])
    if r.returncode == 0:
        bad.append("tests: tests moved from the py39 leg to the py312 leg read as kept")
    report(t + "/f1", names); report(t + "/f2", names)
    r = run([M, "tests", "--before", t + "/f1/r.xml", "--after", t + "/f2/r.xml"])
    if r.returncode != 0:
        bad.append("tests: the same tests in two single report files read as lost\n" + r.stdout)
    report(t + "/n/shard-1-node18", names); report(t + "/n/shard-1-node22", names[:4])
    report(t + "/n2/shard-1-node18", names[:4]); report(t + "/n2/shard-1-node22", names)
    r = run([M, "tests", "--before", t + "/n", "--after", t + "/n2"])
    if r.returncode == 0:
        bad.append("tests: tests moved between node18 and node22 shards read as kept")
    report(t + "/legs/py39", names); report(t + "/legs/py312", names); report(t + "/one/py39", names)
    r = run([M, "tests", "--before", t + "/legs", "--after", t + "/one"])
    if r.returncode == 0:
        bad.append("tests: a lost matrix leg passed")
# Unit checks on the parts with no recorded sample.
import importlib.util
spec = importlib.util.spec_from_file_location("measure", M)
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)
mm.proc()  # measure.py imports subprocess on first use; the fakes below replace its run


def rose_checks(got):
    """The reach checks of a compare --json answer whose misses rose beyond chance."""
    return {x["check"] for x in got.get("reach_checks") or []
            if mm.fails_rose(tuple(x["missed_before"]), tuple(x["missed_after"]))}


def code_of(got):
    """What compare read: the verdict, or for a descriptive answer (--end, --ran) its reading."""
    if got.get("verdict_code") in ("end_descriptive", "ran_descriptive"):
        return got.get("reading_code") or ""
    return got.get("verdict_code") or ""


def end_qualified(got, check, suffix="_fewer_reached"):
    """--end and --ran are descriptive: the reading carries the qualification, and the named check rose."""
    return (got.get("verdict_code") in ("end_descriptive", "ran_descriptive") and suffix in (got.get("reading_code") or "")
            and (check is None or check in rose_checks(got)))
if mm.fails_rose((0, 20), (3, 23)):
    bad.append("fails_rose: 0/20 against 3/23 is within chance (Fisher p = 0.14)")
try:
    mm.fails_rose((250, 1000), (300, 1000))
except OverflowError:
    bad.append("fails_rose: overflows on large samples")
if not mm.fails_rose((0, 20), (6, 20)):
    bad.append("fails_rose: 0/20 against 6/20 should count as a rise")
if mm.fails_rose((1, 10), (5, 10)) or not mm.fails_rose((1, 10), (6, 10)):
    bad.append("fails_rose: 1 of 10 against 5 of 10 is within chance (p = 0.070); 6 of 10 is not")
if not mm.fails_rose((0, 5), (4, 5)) or mm.fails_rose((0, 5), (3, 5)):
    bad.append("fails_rose: at 5 a side, 0 against 4 failures is the smallest rise beyond chance")
# The exact interval. The Mann-Whitney null counts match brute force over every order.
import itertools
import math
from fractions import Fraction
for m in range(1, 7):
    for n in range(1, 7):
        want = [0] * (m * n + 1)
        for after_at in itertools.combinations(range(m + n), n):
            # u counts (before, after) pairs where the after run is the slower one
            want[sum(1 for p in after_at for q in range(m + n) if q < p and q not in after_at)] += 1
        if mm.mann_whitney_counts(m, n, m * n) != want:
            bad.append("mann_whitney_counts(%d, %d) differs from brute force" % (m, n))
# Textbook two-sided 5% critical values of U (Mann and Whitney's table): reject when U <= c.
import random
rng = random.Random(7)
for (m, n), c in {(4, 4): 0, (4, 6): 2, (4, 8): 4, (5, 5): 2, (5, 7): 5, (5, 10): 8, (6, 6): 5,
                  (7, 7): 8, (8, 8): 13, (10, 10): 23, (20, 20): 127}.items():
    xs, ys = [rng.random() for _ in range(m)], [rng.random() for _ in range(n)]
    est, lo, hi, conf = mm.shift_interval(xs, ys)
    d = sorted(y - x for x in xs for y in ys)
    if (lo, hi) != (d[c], d[-c - 1]):
        bad.append("shift_interval: %d and %d a side should use U <= %d" % (m, n, c))
if mm.shift_interval([1, 2, 3], [4, 5, 6])[1:3] != (-math.inf, math.inf):
    bad.append("shift_interval: 3 a side can't give a 95% interval")
# A published worked example: X = (0, 2.2, 5.5, 10.1), Y = (3.2, 7.7, 12.4, 18.9),
# 90% interval [-2.4, 16.7] at coverage 1 - 4/70 (clinicalbiostats.com, "Hodges-Lehmann
# Estimates and Rank-Based Intervals"); the median of the 16 printed differences is 6.2.
est, lo, hi, conf = mm.shift_interval([0, 2.2, 5.5, 10.1], [3.2, 7.7, 12.4, 18.9], Fraction(1, 10))
if (round(est, 6), round(lo, 6), round(hi, 6), round(conf, 6)) != (6.2, -2.4, 16.7, round(1 - 4 / 70, 6)):
    bad.append("shift_interval: the worked example gives %r" % ((est, lo, hi, conf),))
k = mm.KEY.search("Cache not found for input keys: pnpm-Linux-9b2d, pnpm-Linux-")
if not k or k.group(1) != "pnpm-Linux-9b2d":
    bad.append("cachelog: key not read from 'input keys:'")
k = mm.KEY.search("Cache hit occurred on the primary key pnpm-Linux-9b2d, not saving cache.")
if not k or k.group(1) != "pnpm-Linux-9b2d":
    bad.append("cachelog: key not read from 'primary key'")
with tempfile.TemporaryDirectory() as t:
    for side, status in (("before", 'status="run" result="completed"'), ("after", 'status="notrun" result="suppressed"')):
        os.makedirs(t + "/" + side)
        open(t + "/" + side + "/r.xml", "w").write(
            '<testsuites><testsuite name="Math"><testcase classname="Math" name="Adds" %s/></testsuite></testsuites>' % status)
    r = run([M, "tests", "--before", t + "/before", "--after", t + "/after"])
    if r.returncode == 0:
        bad.append("tests: a GoogleTest case that did not run read as kept")
# A job that moved from a slow runner to a fast one is not a speedup.
with tempfile.TemporaryDirectory() as t:
    rows = [json.loads(l) for l in open(E + "/ci-measure/repo/ci-history/before.jsonl") if l.strip()]
    for i, row in enumerate(rows):
        for j in row["jobs"]:
            j["labels"] = ["big"] if i % 2 else ["small"]
    with open(t + "/mixed.jsonl", "w") as f:
        f.write("".join(json.dumps(x) + "\n" for x in rows))
    after = [json.loads(l) for l in open(E + "/ci-measure/repo/ci-history/after.jsonl") if l.strip()]
    for i, row in enumerate(after):
        for j in row["jobs"]:
            j["labels"] = ["big"] if i % 4 else ["small"]
    with open(t + "/mixed-after.jsonl", "w") as f:
        f.write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/mixed.jsonl", "--after", t + "/mixed-after.jsonl"])
    if "different runners" not in r.stdout + r.stderr:
        bad.append("compare: the runner-mix check didn't fire\n" + r.stdout + r.stderr)
    # The same job moved from one self-hosted runner to another: --label self-hosted must not hide it.
    for name, lab in (("small.jsonl", ["self-hosted", "small"]), ("big.jsonl", ["self-hosted", "big"])):
        src = "before.jsonl" if name == "small.jsonl" else "after.jsonl"
        rows2 = [json.loads(l) for l in open(E + "/ci-measure/repo/ci-history/" + src) if l.strip()]
        for row in rows2:
            for j in row["jobs"]:
                j["labels"] = lab
        with open(t + "/" + name, "w") as f:
            f.write("".join(json.dumps(x) + "\n" for x in rows2))
    r = run([M, "compare", "--before", t + "/small.jsonl", "--after", t + "/big.jsonl", "--label", "self-hosted"])
    if r.returncode == 0:
        bad.append("compare: a runner change passed under a shared --label\n" + r.stdout)
    if r.returncode == 0:
        bad.append("compare: accepted runs with different runner mixes\n" + r.stdout)
r = run([M, "compare", "--before", "ci-history/before.jsonl", "--after", "ci-history/after.jsonl"],
        cwd=E + "/ci-measure/repo")
if "verdict: median faster" not in r.stdout:
    bad.append("compare: expected faster\n" + r.stdout + r.stderr)
import json
same = tempfile.mktemp(suffix=".jsonl")
with open(E + "/ci-measure/repo/ci-history/before.jsonl") as f, open(same, "w") as g:
    for line in f:
        rec = json.loads(line)
        rec["id"] += 10 ** 9  # the same timings as new runs
        g.write(json.dumps(rec) + "\n")
r = run([M, "compare", "--before", "ci-history/before.jsonl", "--after", same],
        cwd=E + "/ci-measure/repo")
r2 = run([M, "compare", "--before", "ci-history/before.jsonl", "--after", "ci-history/before.jsonl"],
         cwd=E + "/ci-measure/repo")
if r2.returncode == 0:
    bad.append("compare: the same runs on both sides should be refused")
if "verdict: no measurable change" not in r.stdout:
    bad.append("compare: same runs should show no change\n" + r.stdout)
r = run([M, "compare", "--before", "ci-history/before.jsonl", "--after", "ci-history/after.jsonl",
         "--min-runs", "30"], cwd=E + "/ci-measure/repo")
if "not enough runs yet" not in r.stdout:
    bad.append("compare: expected not enough runs\n" + r.stdout)
# Runs with chosen durations (seconds) and outcomes, in the format fetch writes.
def fake_runs(path, secs, base_id, outcome="success"):
    from datetime import datetime, timedelta
    row0 = json.loads(open(E + "/ci-measure/repo/ci-history/before.jsonl").readline())
    t0 = datetime(2026, 10, 1, 9, 0, 0)
    with open(path, "a") as f:
        for i, s in enumerate(secs):
            start = t0 + timedelta(hours=i)
            end = (start + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
            row = dict(row0, id=base_id + i, conclusion=outcome,
                       created_at=start.strftime("%Y-%m-%dT%H:%M:%SZ"), run_started_at=start.strftime("%Y-%m-%dT%H:%M:%SZ"))
            row["jobs"] = [dict(row0["jobs"][0], id=(base_id + i) * 10, conclusion=outcome,
                                started_at=row["run_started_at"], completed_at=end)]
            f.write(json.dumps(row) + "\n")


def verdict(before, after):
    r = run([M, "compare", "--before", before, "--after", after, "--json"])
    return json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr}


with tempfile.TemporaryDirectory() as t:
    # Most runs faster but the median slower is mixed, not "median faster".
    fake_runs(t + "/mb", [60] * 11 + [120] * 10, 1000)
    fake_runs(t + "/ma", [30] * 10 + [61] * 11, 2000)
    v = verdict(t + "/mb", t + "/ma")
    if v.get("verdict_code") != "mixed":
        bad.append("compare: most runs faster with a slower median should be mixed: %r" % v.get("verdict"))
    fake_runs(t + "/sb", [600, 610, 620, 630, 640], 3000)
    fake_runs(t + "/sa", [700, 705, 712, 720, 731], 4000)
    v = verdict(t + "/sb", t + "/sa")
    if v.get("verdict") != "median slower (5 runs a side)":
        bad.append("compare: 5 slower runs a side should be median slower: %r" % v.get("verdict"))
    # Whole-second ties: identical times are no change, at any count.
    fake_runs(t + "/tb", [600] * 5, 5000)
    fake_runs(t + "/ta", [600] * 5, 6000)
    if verdict(t + "/tb", t + "/ta").get("verdict_code") != "no_change_yet":
        bad.append("compare: identical tied times should be no measurable change")
    # The failure-rate test on the real path: 5 passed before; 5 passed and 6 or 7 failed after.
    # 6 failures is within chance at 5 a side, but any rise in failures withholds a clean "faster".
    for fails, want in ((6, "faster_more_failures"), (7, "not_valid")):
        fake_runs(t + "/fa%d" % fails, [500, 505, 510, 515, 520], 7000 + 100 * fails)
        fake_runs(t + "/fa%d" % fails, [400] * fails, 7050 + 100 * fails, "failure")
        v = verdict(t + "/sb", t + "/fa%d" % fails)
        if v.get("verdict_code") != want:
            bad.append("compare: %d failed after against 0 before should be %s: %r" % (fails, want, v))
    # A failed build whose next job was skipped (no runner, so no labels) still counts
    # under --label: 7 failed beside 5 passed is not valid.
    fails = [json.loads(l) for l in open(t + "/fa7") if l.strip()]
    for row in fails:
        if row["conclusion"] == "failure":
            # build failed, so the measured job, test, was skipped
            row["jobs"] = [dict(row["jobs"][0], name="build"),
                           dict(row["jobs"][0], id=row["id"] * 10 + 1, name=row["jobs"][0]["name"],
                                conclusion="skipped", labels=[], started_at=row["jobs"][0]["completed_at"])]
    open(t + "/skip", "w").write("".join(json.dumps(x) + "\n" for x in fails))
    for flags in (["--label", "ubuntu-latest"], ["--label", "ubuntu-latest", "--job", "test"]):
        r = run([M, "compare", "--before", t + "/sb", "--after", t + "/skip", "--json"] + flags)
        if (json.loads(r.stdout) if r.returncode == 0 else {}).get("verdict_code") != "not_valid":
            bad.append("compare: failed runs with a skipped job dropped out under %s\n%s%s"
                       % (" ".join(flags), r.stdout, r.stderr))
    # A build on one runner fails and the measured test, meant for another, is skipped:
    # the failure still counts under that other runner's label.
    def relabel(src, dst, labels):
        rows2 = [json.loads(l) for l in open(src) if l.strip()]
        for row in rows2:
            for j in row["jobs"]:
                if j["labels"]:
                    j["labels"] = labels if j["name"] != "build" else ["ubuntu-latest"]
        open(dst, "w").write("".join(json.dumps(x) + "\n" for x in rows2))
    relabel(t + "/sb", t + "/sbw", ["windows-latest"])
    relabel(t + "/skip", t + "/skipw", ["windows-latest"])
    r = run([M, "compare", "--before", t + "/sbw", "--after", t + "/skipw", "--json",
             "--label", "windows-latest", "--job", "test"])
    if (json.loads(r.stdout) if r.returncode == 0 else {}).get("verdict_code") != "not_valid":
        bad.append("compare: a failed build on another runner dropped out under --job --label\n" + r.stdout + r.stderr)
    # Unknown runners resolve against a speedup: a green run whose measured job was skipped
    # doesn't dilute the failures, and a same-name job on another runner doesn't clear a
    # failed run whose measured job never ran.
    skipw = [json.loads(l) for l in open(t + "/skipw") if l.strip()]
    failed_row = next(x for x in skipw if x["conclusion"] == "failure")
    docs = dict(failed_row, id=8800, conclusion="success",
                jobs=[dict(failed_row["jobs"][0], conclusion="success"), failed_row["jobs"][1]])
    twin = [dict(x, jobs=x["jobs"] + [dict(x["jobs"][0], id=x["id"] * 10 + 2, name=failed_row["jobs"][1]["name"],
                                          conclusion="success")]) if x["conclusion"] == "failure" else x
            for x in skipw]
    for name, rows2 in (("docs", skipw + [docs]), ("twin", twin)):
        open(t + "/" + name, "w").write("".join(json.dumps(x) + "\n" for x in rows2))
        r = run([M, "compare", "--before", t + "/sbw", "--after", t + "/" + name, "--json",
                 "--label", "windows-latest", "--job", "test"])
        v = json.loads(r.stdout) if r.returncode == 0 else {}
        if (v.get("failed_after") or [0])[0] != 7 or not (v.get("verdict_code") == "not_valid" or (
                v.get("verdict_code") or "").startswith("faster_more_failures")):
            bad.append("compare: %s case hid the failures under --job --label: %r" % (name, v.get("verdict")))
    # Same-name matrix legs: the leg on the asked runner is timed, whichever is listed first.
    def legs(src, dst, ubuntu_secs, first_ubuntu):
        rows2 = []
        for row in (json.loads(l) for l in open(src) if l.strip()):
            win = row["jobs"][0]
            start = win["started_at"]
            end = (datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=ubuntu_secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
            ubu = dict(win, id=win["id"] + 1, labels=["ubuntu-latest"], completed_at=end)
            row["jobs"] = [ubu, dict(win, labels=["windows-latest"])] if first_ubuntu else [dict(win, labels=["windows-latest"]), ubu]
            rows2.append(row)
        open(dst, "w").write("".join(json.dumps(x) + "\n" for x in rows2))
    from datetime import datetime, timedelta
    legs(t + "/sb", t + "/legb", 900, False)
    legs(t + "/sb", t + "/lega0", 300, True)
    lega = [dict(json.loads(l), id=json.loads(l)["id"] + 50000) for l in open(t + "/lega0") if l.strip()]
    open(t + "/lega", "w").write("".join(json.dumps(x) + "\n" for x in lega))
    r = run([M, "compare", "--before", t + "/legb", "--after", t + "/lega", "--json",
             "--label", "windows-latest", "--job", "test"])
    v = json.loads(r.stdout) if r.returncode == 0 else {}
    if v.get("verdict_code") != "no_change_yet" or v.get("after_runs") != 5:
        bad.append("compare: the windows leg wasn't the one timed: %r\n%s" % (v.get("verdict"), r.stderr))
    # Under --label, runs that failed at startup (no jobs, no runner) still count as failures.
    started = [json.loads(l) for l in open(t + "/fa7") if l.strip() and json.loads(l)["conclusion"] == "success"]
    early = [dict(started[0], id=7900 + i, conclusion="startup_failure", jobs=[]) for i in range(7)]
    open(t + "/early", "w").write("".join(json.dumps(x) + "\n" for x in started + early))
    r = run([M, "compare", "--before", t + "/sb", "--after", t + "/early", "--label", "ubuntu-latest", "--json"])
    if (json.loads(r.stdout) if r.returncode == 0 else {}).get("verdict_code") != "not_valid":
        bad.append("compare: startup failures dropped out of the count under --label\n" + r.stdout + r.stderr)
    # The failure check reads every run of the workflow: a cache filter can't drop startup
    # failures that never reached the cache, and a failure before doesn't buy a clean "faster".
    json.dump({str(x["id"]): "hit" for x in started + [json.loads(l) for l in open(t + "/sb") if l.strip()]},
              open(t + "/hits.json", "w"))
    r = run([M, "compare", "--before", t + "/sb", "--after", t + "/early", "--json",
             "--cache", "hit", "--cache-state", t + "/hits.json"])
    v = json.loads(r.stdout) if r.returncode == 0 else {}
    if v.get("verdict_code") != "not_valid":
        bad.append("compare: --cache hit hid startup failures: %r\n%s" % (v.get("verdict"), r.stderr))
    sb1 = [json.loads(l) for l in open(t + "/sb") if l.strip()]
    open(t + "/sb1", "w").write("".join(json.dumps(x) + "\n" for x in sb1 + [dict(sb1[0], id=3999, conclusion="failure")]))
    r = run([M, "compare", "--before", t + "/sb1", "--after", t + "/fa7", "--json"])
    v = json.loads(r.stdout) if r.returncode == 0 else {}
    if (v.get("verdict_code"), v.get("failed_before"), v.get("failed_after")) != ("faster_more_failures", [1, 6], [7, 12]):
        bad.append("compare: a failure before beside 7 after: %r" % v.get("verdict"))
    # The failure check looks at every job and attempt whatever --job says: a green run
    # with a failed sibling job, and a run cancelled after its first attempt failed, count.
    green = [json.loads(l) for l in open(t + "/fa7") if l.strip() and json.loads(l)["conclusion"] == "success"]
    odd = []
    for i in range(7):
        x = dict(green[0], id=9100 + i)
        x["jobs"] = [green[0]["jobs"][0], dict(green[0]["jobs"][0], id=91000 + i, name="experimental", conclusion="failure")]
        odd.append(x)
    for i in range(7):
        x = dict(green[0], id=9200 + i, conclusion="cancelled", run_attempt=2)
        x["jobs"] = [dict(green[0]["jobs"][0], run_attempt=1, conclusion="failure"),
                     dict(green[0]["jobs"][0], id=92000 + i, run_attempt=2, conclusion="cancelled")]
        odd.append(x)
    for name, extra, flags in (("sibling", odd[:7], ["--job", "test"]), ("cancelled", odd[7:], [])):
        open(t + "/" + name, "w").write("".join(json.dumps(x) + "\n" for x in green + extra))
        r = run([M, "compare", "--before", t + "/sb", "--after", t + "/" + name, "--json"] + flags)
        v = json.loads(r.stdout) if r.returncode == 0 else {}
        if v.get("failed_after") != [7, 12] or v.get("verdict_code") != "not_valid":
            bad.append("compare: the %s failures weren't counted: %r %r" % (name, v.get("failed_after"), v.get("verdict")))
    # Whole runs timed on two pools under differently named jobs: refused, not a speedup.
    def pools(src, dst, slow):
        rows2 = [json.loads(l) for l in open(src) if l.strip()]
        for i, x in enumerate(rows2):
            pool = "slow" if i < slow else "fast"
            x["jobs"] = [dict(j, name="test-" + pool, labels=["self-hosted", pool]) for j in x["jobs"]]
        open(dst, "w").write("".join(json.dumps(x) + "\n" for x in rows2))
    pools(t + "/sb", t + "/poolb", 4)
    pools(t + "/sa", t + "/poola", 1)
    r = run([M, "compare", "--before", t + "/poolb", "--after", t + "/poola", "--label", "self-hosted"])
    if r.returncode == 0 or "different sets of runners" not in r.stderr:
        bad.append("compare: a shift between runner pools passed\n" + r.stdout + r.stderr)
    # A job that ran with no labels (routed by group) is no evidence of the runner.
    nogroup = [json.loads(l) for l in open(t + "/sa") if l.strip()]
    for x in nogroup:
        x["jobs"] = x["jobs"] + [dict(x["jobs"][0], id=x["id"] * 10 + 3, name="build", labels=[])]
    open(t + "/nogroup", "w").write("".join(json.dumps(x) + "\n" for x in nogroup))
    r = run([M, "compare", "--before", t + "/sb", "--after", t + "/nogroup", "--label", "ubuntu-latest", "--json"])
    if (json.loads(r.stdout) if r.returncode == 0 else {}).get("verdict_code") != "not_enough_runs":
        bad.append("compare: a job with no labels counted as on the runner\n" + r.stdout + r.stderr)
    # --base leaves out unplaced runs whether they passed or failed: with placed and
    # unplaced runs in the same proportions, the failure rate is the placed runs' rate.
    def based(src, dst, base_id):
        rows2 = []
        for i, x in enumerate(json.loads(l) for l in open(src) if l.strip()):
            for placed in (True, False):
                rows2.append(dict(x, id=base_id + 2 * i + placed, pull_request_bases=["main"] if placed else []))
        open(dst, "w").write("".join(json.dumps(x) + "\n" for x in rows2))
    based(t + "/sb1", t + "/baseb", 60000)
    based(t + "/fa6", t + "/basea", 70000)
    r = run([M, "compare", "--before", t + "/baseb", "--after", t + "/basea", "--base", "main", "--json"])
    v = json.loads(r.stdout) if r.returncode == 0 else {}
    if v.get("failed_before") != [1, 6] or v.get("failed_after") != [6, 11] or v.get("before_runs") != 5:
        bad.append("compare: --base changed the failure rate or the timed runs: %r %r %r\n%s"
                   % (v.get("failed_before"), v.get("failed_after"), v.get("before_runs"), r.stderr))
    # Under --label, a run where no job shows a runner can't be one of the 5.
    nolab = [json.loads(l) for l in open(t + "/sa") if l.strip()][:4]
    extra = dict(nolab[0], id=4999)
    extra["jobs"] = [dict(j, labels=[]) for j in extra["jobs"]]
    open(t + "/nolab", "w").write("".join(json.dumps(x) + "\n" for x in nolab + [extra]))
    r = run([M, "compare", "--before", t + "/sb", "--after", t + "/nolab", "--label", "ubuntu-latest", "--json"])
    if (json.loads(r.stdout) if r.returncode == 0 else {}).get("verdict_code") != "not_enough_runs":
        bad.append("compare: a run with no runner counted toward 5 under --label\n" + r.stdout + r.stderr)
    # The larger side's typical slowest of 5 is the median of its 5-run maxima: with one
    # 10-minute run in 6, five of the six 5-run draws hold it.
    fake_runs(t + "/xb", [60] * 4 + [600], 8000)
    fake_runs(t + "/xa", [60] * 5 + [600], 8100)
    v = verdict(t + "/xb", t + "/xa")
    if v.get("before_tail") != ["slowest run", 600] or v.get("after_tail") != ["typical slowest of 5", 600]:
        bad.append("compare: typical slowest of 5 should be 600 s: %r %r" % (v.get("before_tail"), v.get("after_tail")))
# The typical slowest of k against brute force over every k-run draw.
for _ in range(300):
    n = rng.randint(2, 9); k = rng.randint(1, n - 1)
    xs = [rng.randint(1, 20) for _ in range(n)]
    maxes = sorted(max(c) for c in itertools.combinations(xs, k))
    if mm.tails(xs, xs[:k])[0] != ("typical slowest of %d" % k, maxes[(len(maxes) - 1) // 2]):
        bad.append("tails: typical slowest of %d of %r should be %r" % (k, xs, maxes[(len(maxes) - 1) // 2]))
        break
# fetch, against a fake gh: a window is written only when every run in it has finished and
# all of it fits under --limit; without a window (a diagnosis) the finished runs are kept.
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, re, sys
runs = json.load(open(os.environ["FAKE_RUNS"]))
path = sys.argv[-1]
if path == "rate_limit":
    print(json.dumps({"resources": {"core": {"remaining": 5000, "reset": 0}}}))
elif "/pulls?" in path:
    from urllib.parse import unquote
    head = unquote(re.search(r"[?&]head=([^&]+)", path).group(1))
    print(json.dumps(json.loads(os.environ.get("FAKE_PULLS") or "{}").get(head, [])))
elif "/jobs" in path:
    rid = int(re.search(r"/runs/(\d+)/jobs", path).group(1))
    print(json.dumps([{"jobs": [r for r in runs if r["id"] == rid][0]["jobs"]}]))
else:
    keep = [r for r in runs if "status=completed" not in path or r["status"] == "completed"]
    m = re.search(r"[?&]created=([^&]+)", path)
    if m:
        from urllib.parse import unquote
        value = unquote(m.group(1))
        lo, _, hi = value.rpartition("..") if ".." in value or value.startswith("<") else (value, "", value)
        hi = hi.lstrip("<=")
        hi = hi + "T23:59:59Z" if len(hi) == 10 else hi  # a bare date takes its whole day
        keep = [r for r in keep if (not lo or r["created_at"] >= lo) and r["created_at"] <= hi]
    page = int(re.search(r"[?&]page=(\d+)", path).group(1))
    total = int(os.environ.get("FAKE_TOTAL") or len(keep))  # GitHub lists at most 1,000
    shift = int(os.environ.get("FAKE_SHIFT") or 0)  # new runs arrived: later pages start earlier
    first = max(0, (page - 1) * 100 - shift)
    print(json.dumps({"total_count": total, "workflow_runs": keep[first:first + 100]}))
'''
with tempfile.TemporaryDirectory() as t:
    os.makedirs(t + "/bin")
    open(t + "/bin/gh", "w").write(FAKE_GH)
    os.chmod(t + "/bin/gh", 0o755)
    rows = [dict(r, pull_requests=[{"number": n} for n in r["pull_requests"]])
            for r in (json.loads(l) for l in open(E + "/ci-measure/repo/ci-history/after.jsonl") if l.strip())][:6]
    env = dict(os.environ, PATH=t + "/bin" + os.pathsep + os.environ["PATH"], FAKE_RUNS=t + "/runs.json")

    calls = itertools.count()

    # Outside every window below: a run still going, which only a lost --created would see.
    outside = dict(rows[0], id=99, created_at="2026-09-01T09:00:00Z", status="in_progress")

    def fetch(statuses, *extra):
        listed = [dict(r, status=s) for r, s in zip(rows, statuses)]
        for row in listed:
            if row["status"] is None:
                del row["status"]
        json.dump(listed + [outside], open(t + "/runs.json", "w"))
        out = t + "/out/%d.jsonl" % next(calls)
        r = subprocess.run([sys.executable, M, "fetch", "--repo", "o/r", "--workflow", "ci.yml", "--out", out]
                           + list(extra), cwd=t, env=env, capture_output=True, text=True)
        return r, (sum(1 for _ in open(out)) if os.path.exists(out) else None)
    window = ("--created", "2026-10-01T00:00:00Z..2026-10-08T00:00:00Z")
    r, n = fetch(["completed"] * 5 + ["in_progress"], *window)
    if r.returncode == 0 or n is not None or "haven't finished" not in r.stderr:
        bad.append("fetch: a window with a run still going was written\n" + r.stdout + r.stderr)
    r, n = fetch(["completed"] * 6, "--limit", "5", *window)
    if r.returncode == 0 or n is not None:
        bad.append("fetch: a window larger than --limit was written\n" + r.stdout + r.stderr)
    r, n = fetch(["completed"] * 6, *window)
    if r.returncode != 0 or n != 6:
        bad.append("fetch: a finished window should be written whole (%r runs)\n%s" % (n, r.stderr))
    r, n = fetch(["completed"] * 6, "--limit", "5", "--created", "2026-10-06")
    if r.returncode == 0 or n is not None:
        bad.append("fetch: a one-day window larger than --limit was written\n" + r.stdout + r.stderr)
    env["FAKE_TOTAL"] = "1200"
    r, n = fetch(["completed"] * 6, "--limit", "2000", *window)
    env["FAKE_TOTAL"] = ""
    if r.returncode == 0 or n is not None or "listed 6 of" not in r.stderr:
        bad.append("fetch: a window GitHub listed only in part was written\n" + r.stderr)
    r, n = fetch(["completed"] * 5 + [None], *window)
    if r.returncode == 0 or n is not None:
        bad.append("fetch: a run with no status was taken as finished")
    # Pages that overlap as new runs arrive: each run is kept once.
    many = [dict(rows[0], id=5000 + i, created_at="2026-10-06T%02d:%02d:00Z" % (23 - i // 60, 59 - i % 60))
            for i in range(120)]
    json.dump([dict(r, status="completed") for r in many], open(t + "/many.json", "w"))
    out = t + "/out/many.jsonl"
    r = subprocess.run([sys.executable, M, "fetch", "--repo", "o/r", "--workflow", "ci.yml", "--out", out],
                       cwd=t, env=dict(env, FAKE_RUNS=t + "/many.json", FAKE_SHIFT="7"),
                       capture_output=True, text=True)
    ids = [json.loads(l)["id"] for l in open(out)] if os.path.exists(out) else []
    if r.returncode != 0 or len(ids) != 120 or len(set(ids)) != 120:
        bad.append("fetch: overlapping pages gave %d runs, %d distinct\n%s" % (len(ids), len(set(ids)), r.stderr))
    # A closed pull request drops off its runs: fetch finds its branch from the run's head
    # branch, in any state; a fork's run records none and is never looked up.
    shut = [dict(r, status="completed", pull_requests=[], head_repository={"full_name": "o/r"}) for r in rows]
    shut[1]["head_repository"] = {"full_name": "fork/r"}
    json.dump(shut, open(t + "/shut.json", "w"))
    pulls = {"o:" + shut[0]["head_branch"]: [{"base": {"ref": "main"}}],
             "o:" + shut[1]["head_branch"]: [{"base": {"ref": "main"}}]}
    out = t + "/out/shut.jsonl"
    r = subprocess.run([sys.executable, M, "fetch", "--repo", "o/r", "--workflow", "ci.yml", "--out", out] + list(window),
                       cwd=t, env=dict(env, FAKE_RUNS=t + "/shut.json", FAKE_PULLS=json.dumps(pulls)),
                       capture_output=True, text=True)
    got = [json.loads(l)["pull_request_bases"] for l in open(out)] if os.path.exists(out) else []
    if r.returncode != 0 or not got or got[0] != ["main"] or got[1] != []:
        bad.append("fetch: a closed pull request's branch wasn't found, or a fork's was: %r\n%s" % (got[:2], r.stderr))
    r, n = fetch(["completed"] * 5 + ["queued"])
    if r.returncode != 0 or n != 5:
        bad.append("fetch: without a window, the finished runs should be written (%r runs)\n%s" % (n, r.stderr))
    # A baseline up to a past time keeps the newest --limit runs; all must have finished.
    r, n = fetch(["completed"] * 6, "--limit", "4", "--created", "<=2026-10-08T00:00:00Z")
    if r.returncode != 0 or n != 4:
        bad.append("fetch: a baseline up to a past time should keep its newest 4 runs (%r)\n%s" % (n, r.stderr))
    r, n = fetch(["in_progress"] + ["completed"] * 5, "--limit", "4", "--created", "<=2026-10-08T00:00:00Z")
    if r.returncode == 0 or n is not None:
        bad.append("fetch: a baseline with a run still going was written")
    for open_window in (">=2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z..2999-01-01"):
        r, n = fetch(["completed"] * 6, "--created", open_window)
        if r.returncode == 0 or n is not None:
            bad.append("fetch: a window that hasn't ended (%s) was written" % open_window)
# Tails compare like with like: with no change, 150 runs before and 5 after, the after
# side's slowest run must not look better nearly every time (a max of 150 against a max of 5).
better = 0
for _ in range(400):
    b = [rng.lognormvariate(6, 0.3) for _ in range(150)]
    c = [rng.lognormvariate(6, 0.3) for _ in range(5)]
    (lb, tb), (lc, tc) = mm.tails(b, c)
    better += tc < tb
if (lb, lc) != ("typical slowest of 5", "slowest run") or not 0.3 < better / 400.0 < 0.7:
    bad.append("tails: with no change, the 5-run side looked better in %d of 400 draws" % better)
# Five runs a side are enough for a verdict, named with its count; four are not.
with tempfile.TemporaryDirectory() as t:
    for name, src, keep in (("b5", "before", 5), ("a5", "after", 5), ("b4", "before", 4), ("a4", "after", 4)):
        lines = [l for l in open(E + "/ci-measure/repo/ci-history/%s.jsonl" % src) if l.strip()][:keep]
        open(t + "/" + name, "w").write("".join(lines))
    lines = [json.loads(l) for l in open(t + "/b5")]
    open(t + "/same5", "w").write("".join(json.dumps(dict(x, id=x["id"] + 10 ** 9)) + "\n" for x in lines))
    r = run([M, "compare", "--before", t + "/b5", "--after", t + "/a5"])
    if "verdict: median faster (5 runs a side)" not in r.stdout or "slowest run" not in r.stdout:
        bad.append("compare: 5 runs a side should give a verdict with its count\n" + r.stdout + r.stderr)
    r = run([M, "compare", "--before", t + "/b5", "--after", t + "/same5"])
    if "verdict: no measurable change yet with 5 a side; more runs can tighten this" not in r.stdout:
        bad.append("compare: the same 5 runs should say more runs can tighten it\n" + r.stdout + r.stderr)
    r = run([M, "compare", "--before", t + "/b4", "--after", t + "/a4"])
    if "verdict: not enough runs yet" not in r.stdout or "median" in r.stdout or "slowest" in r.stdout:
        bad.append("compare: 4 runs a side should not get a verdict\n" + r.stdout + r.stderr)
    # 24 runs before against 5 after: the larger side's tail is named for what it is.
    r = run([M, "compare", "--before", E + "/ci-measure/repo/ci-history/before.jsonl", "--after", t + "/a5"])
    if ("before: 24 runs" not in r.stdout or "typical slowest of 5" not in r.stdout.split("after:")[0]
            or "slowest run" not in r.stdout.split("after:")[1]):
        bad.append("compare: unequal sides should show the larger side's typical slowest of 5\n" + r.stdout + r.stderr)
    r = run([M, "compare", "--before", t + "/b4", "--after", t + "/a4", "--min-runs", "4"])
    if r.returncode == 0:
        bad.append("compare: --min-runs 4 should be refused\n" + r.stdout)
r = run([M, "tests", "--before", "ci-history/junit-before", "--after", "ci-history/junit-after"],
        cwd=E + "/ci-measure/repo")
if r.returncode == 0 or "test_refund_rounding" not in r.stdout:
    bad.append("tests: dropped test not caught\n" + r.stdout)
r = run([M, "tests", "--before", "ci-history/junit-before", "--after", "ci-history/junit-before"],
        cwd=E + "/ci-measure/repo")
if r.returncode != 0:
    bad.append("tests: identical reports should pass\n" + r.stdout)

# JUnit with an XML namespace: losing a suite is caught
ns_dir = tempfile.mkdtemp()
for side, suites in (("b", ["a", "b"]), ("c", ["a"])):
    os.makedirs(os.path.join(ns_dir, side, "linux"))
    body = "".join('<t:testsuite name="%s"><t:testcase classname="k" name="x"/></t:testsuite>' % n for n in suites)
    open(os.path.join(ns_dir, side, "linux", "r.xml"), "w").write(
        '<t:testsuites xmlns:t="urn:example">%s</t:testsuites>' % body)
r = run([M, "tests", "--before", ns_dir + "/b", "--after", ns_dir + "/c"])
if r.returncode == 0:
    bad.append("tests: a lost suite in a namespaced report passed\n" + r.stdout + r.stderr)

# A test moved to another file under the same class and name is caught
mv_dir = tempfile.mkdtemp()
for side, f in (("b", "tests/regression.py"), ("c", "tests/smoke.py")):
    os.makedirs(os.path.join(mv_dir, side))
    open(os.path.join(mv_dir, side, "r.xml"), "w").write(
        '<testsuite name="s"><testcase classname="k" file="%s" name="x"/></testsuite>' % f)
r = run([M, "tests", "--before", mv_dir + "/b", "--after", mv_dir + "/c"])
if r.returncode == 0:
    bad.append("tests: a test replaced by another file's test of the same name passed\n" + r.stdout)

# Two same-name jobs in one attempt, one failed and one passed, are not a rerun flake
one = json.loads(open(E + "/ci-diagnose/repo/ci-history/runs.jsonl").readline())
job = dict(one["jobs"][0], run_attempt=1)
one["run_attempt"] = 1
one["jobs"] = [dict(job, conclusion="failure"), dict(job, conclusion="success")]
same = tempfile.mktemp(suffix=".jsonl")
open(same, "w").write(json.dumps(one) + "\n")
r = run([M, "split", "--in", same, "--json"])
if r.returncode != 0 or json.loads(r.stdout).get("rerun_flakes"):
    bad.append("split: two legs of one attempt counted as a rerun flake\n" + r.stdout + r.stderr)

# Fields can't run into each other: class "k::f.py" with no file is not class "k" in file f.py
sep_dir = tempfile.mkdtemp()
for side, attrs in (("b", 'classname="k" file="f.py"'), ("c", 'classname="k::f.py"')):
    os.makedirs(os.path.join(sep_dir, side))
    open(os.path.join(sep_dir, side, "r.xml"), "w").write(
        '<testsuite name="s"><testcase %s name="x"/></testsuite>' % attrs)
r = run([M, "tests", "--before", sep_dir + "/b", "--after", sep_dir + "/c"])
if r.returncode == 0:
    bad.append("tests: a test passed for another whose fields joined to the same text\n" + r.stdout)

# A failed linux leg and a later passing windows leg of the same name are not a rerun flake
two = json.loads(open(E + "/ci-diagnose/repo/ci-history/runs.jsonl").readline())
leg = dict(two["jobs"][0])
two["run_attempt"] = 2
two["jobs"] = [dict(leg, run_attempt=1, conclusion="failure", labels=["ubuntu-latest"]),
               dict(leg, run_attempt=2, conclusion="success", labels=["windows-latest"])]
legs = tempfile.mktemp(suffix=".jsonl")
open(legs, "w").write(json.dumps(two) + "\n")
r = run([M, "split", "--in", legs, "--json"])
if r.returncode != 0 or json.loads(r.stdout).get("rerun_flakes"):
    bad.append("split: legs on different runners counted as a rerun flake\n" + r.stdout + r.stderr)

# A case whose status attribute says failed is a failure; a renamed outer suite is another test
def two_reports(before, after):
    d = tempfile.mkdtemp()
    for side, body in (("b", before), ("c", after)):
        os.makedirs(os.path.join(d, side))
        open(os.path.join(d, side, "r.xml"), "w").write(body)
    return run([M, "tests", "--before", d + "/b", "--after", d + "/c"])
r = two_reports('<testsuite name="s"><testcase classname="k" name="x"/></testsuite>',
                '<testsuite name="s"><testcase classname="k" name="x" status="failed"/></testsuite>')
if r.returncode == 0:
    bad.append("tests: status=\"failed\" passed as a pass\n" + r.stdout)
r = two_reports('<testsuites><testsuite name="orders"><testsuite name="s"><testcase classname="k" name="x"/>'
                '</testsuite></testsuite></testsuites>',
                '<testsuites><testsuite name="search"><testsuite name="s"><testcase classname="k" name="x"/>'
                '</testsuite></testsuite></testsuites>')
if r.returncode == 0:
    bad.append("tests: a test under a renamed outer suite passed for the old one\n" + r.stdout)
r = two_reports('<testsuite name="s"><testcase classname="k" name="x"><skipped/></testcase></testsuite>',
                '<testsuite name="s"><testcase classname="k" name="x"><skipped/></testcase></testsuite>')
if r.returncode == 0 or "tests kept" in r.stdout:
    bad.append("tests: reports where nothing ran were called kept\n" + r.stdout)

# Copies are compared as counts, not by reading order; suite errors count; nesting isn't a name
r = two_reports('<testsuite name="s"><testcase classname="k" name="x"/><testcase classname="k" name="x">'
                '<failure/></testcase></testsuite>',
                '<testsuite name="s"><testcase classname="k" name="x"><failure/></testcase>'
                '<testcase classname="k" name="x"/></testsuite>')
if r.returncode != 0:
    bad.append("tests: the same copies in another order failed\n" + r.stdout)
r = two_reports('<testsuite name="s"><testcase classname="k" name="x"/></testsuite>',
                '<testsuite name="s"><error message="teardown"/><testcase classname="k" name="x"/></testsuite>')
if r.returncode == 0:
    bad.append("tests: a suite-level error passed\n" + r.stdout)
r = two_reports('<testsuites><testsuite name="outer/inner"><testcase classname="k" name="x"/></testsuite></testsuites>',
                '<testsuites><testsuite name="outer"><testsuite name="inner"><testcase classname="k" name="x"/>'
                '</testsuite></testsuite></testsuites>')
if r.returncode == 0:
    bad.append("tests: a suite named outer/inner passed for inner nested in outer\n" + r.stdout)

# Suite errors aren't tests that ran, and a second one, or a declared one, still counts
r = two_reports('<testsuite name="s"><error/><testcase classname="k" name="x"><skipped/></testcase></testsuite>',
                '<testsuite name="s"><error/><testcase classname="k" name="x"><skipped/></testcase></testsuite>')
if r.returncode == 0:
    bad.append("tests: reports where only a suite error 'ran' were called kept\n" + r.stdout)
r = two_reports('<testsuite name="s" errors="0"><testcase classname="k" name="x"/></testsuite>',
                '<testsuite name="s" errors="1"><testcase classname="k" name="x"/></testsuite>')
if r.returncode == 0:
    bad.append("tests: a declared suite error no case explains passed\n" + r.stdout)
r = run([M, "flakebound", "--failures", "3", "--runs", "1100"])
if r.returncode != 0:
    bad.append("flakebound: large run counts must not overflow\n" + r.stderr)

# Declared totals count at every level; declared skips the cases don't mark leave it unverified
for before, after, what in (
        ('<testsuites errors="0"><testsuite name="s"><testcase classname="k" name="x"/></testsuite></testsuites>',
         '<testsuites errors="1"><testsuite name="s"><testcase classname="k" name="x"/></testsuite></testsuites>',
         "a rise in the root's declared errors"),
        ('<testsuite name="o" errors="0"><testsuite name="s"><testcase classname="k" name="x"/></testsuite></testsuite>',
         '<testsuite name="o" errors="1"><testsuite name="s"><testcase classname="k" name="x"/></testsuite></testsuite>',
         "a rise in an outer suite's declared errors"),
        ('<testsuite name="s" errors="0"><testcase classname="k" name="x"><flakyFailure/></testcase></testsuite>',
         '<testsuite name="s" errors="1"><testcase classname="k" name="x"><flakyFailure/></testcase></testsuite>',
         "a declared error beside an unchanged flaky case"),
        ('<testsuite name="s" tests="1" skipped="1"><testcase classname="k" name="x"/></testsuite>',
         '<testsuite name="s" tests="1" skipped="1"><testcase classname="k" name="x"/></testsuite>',
         "declared skips no case marks")):
    r = two_reports(before, after)
    if r.returncode == 0:
        bad.append("tests: %s passed\n%s" % (what, r.stdout))
for before, after, what in (
        ('<testsuite name="s" errors="1"><testcase classname="k" name="x"><error/></testcase></testsuite>',
         '<testsuite name="s" errors="1"><testcase classname="k" name="x"/></testsuite>',
         "a declared error no case explains any more"),
        ('<testsuites><testsuite name="s"><testcase classname="k" name="x"/></testsuite></testsuites>',
         '<testsuites><error/><testsuite name="s"><testcase classname="k" name="x"/></testsuite></testsuites>',
         "a new error on the report root"),
        ('<testsuites><testsuites name="n" errors="0"><testsuite name="s"><testcase classname="k" name="x"/>'
         '</testsuite></testsuites></testsuites>',
         '<testsuites><testsuites name="n" errors="1"><testsuite name="s"><testcase classname="k" name="x"/>'
         '</testsuite></testsuites></testsuites>',
         "a rise on a nested <testsuites>"),
        ('<testsuite name="s" errors="0"><testcase classname="k" name="x"/></testsuite>',
         '<testsuite name="s" errors=" 1 "><testcase classname="k" name="x"/></testsuite>',
         "a declared error written with spaces"),
        ('<testsuite name="s"><testcase classname="" name="t"><error message="collection failure"/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="" name="t"><error message="collection failure"/></testcase></testsuite>',
         "reports where only a collection failure 'ran'")):
    r = two_reports(before, after)
    if r.returncode == 0:
        bad.append("tests: %s passed\n%s" % (what, r.stdout))
for before, after, what in (
        ('<testsuite name="s"><testcase classname="k" name="x"><failure/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="x"><error message="setup"/></testcase></testsuite>',
         "a test that failed an assertion and now only errors"),
        ('<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x"><failure/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x"><error/></testcase></testsuite>',
         "a sibling passing while another test now only errors"),
        ('<testsuite name="s" failures="1" errors="0"><testcase classname="k" name="x"><failure/></testcase>'
         '<testcase classname="k" name="z"><flakyFailure/></testcase></testsuite>',
         '<testsuite name="s" failures="0" errors="1"><testcase classname="k" name="x"/>'
         '<testcase classname="k" name="z"><flakyFailure/></testcase></testsuite>',
         "a fixed assertion offsetting a new unexplained error"),
        ('<testsuites><testsuite name="mod" file="a.py" errors="1"><testcase classname="k" name="x"/></testsuite>'
         '<testsuite name="mod" file="b.py" errors="0"><testcase classname="k" name="y"/></testsuite></testsuites>',
         '<testsuites><testsuite name="mod" file="a.py" errors="0"><testcase classname="k" name="x"/></testsuite>'
         '<testsuite name="mod" file="b.py" errors="1"><testcase classname="k" name="y"/></testsuite></testsuites>',
         "a declared error moving between same-name suites in two files"),
        ('<testsuite name="s"><error type="CleanupError"/><testcase classname="k" name="x"/></testsuite>',
         '<testsuite name="s"><error type="SetupError"/><testcase classname="k" name="x"/></testsuite>',
         "one kind of suite error replacing another")):
    r = two_reports(before, after)
    if r.returncode == 0:
        bad.append("tests: %s passed\n%s" % (what, r.stdout))
# cachelog: messages match from the line's start, so text inside a key can't pass for one
code = ("import importlib.util,sys;s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);"
        "s.loader.exec_module(m);f=lambda l:[x for r,x in m.CACHE_OUTCOMES if r.search(l)][:1];"
        "print(f('Cache restored from key: x cache hit occurred on the primary key old, not saving cache.'));"
        "print(f('Cache hit occurred on the maven-wrapper primary key deps-1, not saving cache.'))")
r = run(["-c", code, M])
if r.stdout.split("\n")[:2] != ["['restore: hit']", "['save: skipped (exact hit)']"]:
    bad.append("cachelog: message patterns misread\n" + r.stdout + r.stderr)
# Pushes a day count pull_request commits only; flakes keep workflow and job apart
mix = [json.loads(l) for l in open(E + "/ci-diagnose/repo/ci-history/runs.jsonl") if l.strip()]
base = len({(tuple(x.get("pull_requests") or []), x.get("head_sha")) for x in mix if x.get("event") == "pull_request"})
extra = dict(mix[0], event="schedule", head_sha="f" * 40, id=1)
mixed = tempfile.mktemp(suffix=".jsonl")
open(mixed, "w").write("".join(json.dumps(x) + "\n" for x in mix + [extra]))
plain = tempfile.mktemp(suffix=".jsonl")
open(plain, "w").write("".join(json.dumps(x) + "\n" for x in mix))
ra = json.loads(run([M, "split", "--in", plain, "--json"]).stdout)
rb = json.loads(run([M, "split", "--in", mixed, "--json"]).stdout)
if ra.get("pushes_per_pr_max") != rb.get("pushes_per_pr_max"):
    bad.append("split: a scheduled run changed pushes per pull request")

for before, after, what in (
        ('<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x"><error type="ZeroDivisionError"/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="y"/></testsuite>',
         "deleting a test that errored"),
        ('<testsuite name="s"><testcase classname="k" name="x" status="failed"><error message="could not collect"/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="x" status="failed"><error message="could not collect"/></testcase></testsuite>',
         "reports whose only case is an <error> under status=failed"),
        ('<testsuite name="s" failures="1"><testcase classname="k" name="a"><flakyFailure/></testcase>'
         '<testcase classname="k" name="b"><failure/></testcase></testsuite>',
         '<testsuite name="s" failures="1"><testcase classname="k" name="a"><failure/></testcase>'
         '<testcase classname="k" name="b"/></testsuite>',
         "a test that recovered on retry now failing for good"),
        ('<testsuite name="s" errors="1"><testcase classname="k" name="x" status="error"/><testcase classname="k" name="y"/></testsuite>',
         '<testsuite name="s" errors="1"><testcase classname="k" name="x"/><testcase classname="k" name="y"/></testsuite>',
         "a declared error no case explains once its status=error case passes")):
    r = two_reports(before, after)
    if r.returncode == 0:
        bad.append("tests: %s passed\n%s" % (what, r.stdout))
for before, after, what in (
        ('<testsuite name="s" errors="1"><testcase classname="k" name="x"><error/></testcase></testsuite>',
         '<testsuite name="s" errors="0"><testcase classname="k" name="y"/></testsuite>',
         "deleting a test that errored, with its declared error"),
        ('<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x"><error/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x"><skipped/></testcase></testsuite>',
         "skipping a test that errored"),
        ('<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x"><flakyError/></testcase></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="y"/></testsuite>',
         "deleting a test that passed on a retry"),
        ('<testsuite name="s"><testcase classname="k" name="y"/><testcase classname="k" name="x" status="broken"/></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="y"/></testsuite>',
         "deleting a broken test"),
        ('<testsuite name="s"><testcase classname="k" name="x"/></testsuite>',
         '<testsuite name="s"><testcase classname="k" name="x"><flakyFailure/></testcase></testsuite>',
         "a test that now passes only on a retry")):
    r = two_reports(before, after)
    if r.returncode == 0:
        bad.append("tests: %s passed\n%s" % (what, r.stdout))
# flakebound: the count fits the rate it prints (shown rounded down), and is never below the
# exact minimum, worked out independently here (one failure: n*ln(0.05)/ln(0.975), rounded up)
from decimal import Decimal as Dd, getcontext as _gc
_gc().prec = 80
for x, n, least in (("1", "61288", 7251910), ("2", "10000000", 123683624), ("1", "33358860", 3947190594),
                    ("1", "2002288363", 236920979641), ("1", "166", 19642), ("3", "100", 480),
                    ("999999", "1000000", 1), ("1", "10" + "0" * 58, 1)):
    r = run([M, "flakebound", "--failures", x, "--runs", n])
    m = re.search(r"interval (\S+) .*\n.*at least (\d+) runs", r.stdout)
    if not m:
        bad.append("flakebound: %s of %s printed no bound\n%s%s" % (x, n, r.stdout, r.stderr))
        continue
    pshown, need = Dd(m.group(1)), int(m.group(2))
    fits = need * (1 - pshown).ln() <= Dd("0.05").ln() if pshown < 1 else need == 1
    if not fits or need < least:
        bad.append("flakebound: %s of %s gave %d runs at %s (exact minimum %d)" % (x, n, need, pshown, least))
# flakebound: exact binomial arithmetic, and no bound from zero failures
r = run([M, "flakebound", "--failures", "3", "--runs", "100"])
if "0.0062" not in r.stdout or "at least 480 runs" not in r.stdout:
    bad.append("flakebound: 3 of 100 should give 0.0062 and 480 runs\n" + r.stdout + r.stderr)
r = run([M, "flakebound", "--failures", "0", "--runs", "50"])
if r.returncode == 0:
    bad.append("flakebound: zero failures should give no bound\n" + r.stdout)

# The ci-measure eval's check reads the decision from an exact first line only
for text, want in (("Verdict: FAIL\nStopped running: test_refund_rounding\nGet a person to approve any removal.", 0),
                   ("Verdict: FAIL\nStopped running: tests.test_billing::test_refund_rounding\nDo not merge.", 0),
                   ("Verdict: PASS\nStopped running: test_refund_rounding", 1),
                   ("**Verdict:** FAIL\nStopped running: test_refund_rounding", 1),
                   ("    Verdict: FAIL\nApproved for merge. test_refund_rounding passed.", 1),
                   ("Approved for merge.\nVerdict: FAIL\nStopped running: test_refund_rounding", 1),
                   ("Verdict: FAIL was the old assessment\nStopped running: test_refund_rounding", 1),
                   ("Verdict: FAIL\nStopped running: test_refund_rounding_new", 1),
                   ("Verdict: FAIL\nStopped running: test_other\ntest_refund_rounding still ran.", 1),
                   ("Verdict: FAIL\nStopped running: test_other (test_refund_rounding still ran)", 1),
                   ("Verdict: FAIL\nStopped running: `report::billing::tests.test_billing::test_refund_rounding`", 0),
                   ("Verdict: FAIL\nStopped running: tests.test_billing.test_refund_rounding", 0),
                   ("Verdict: FAIL\nStopped running: tests/test_billing.py::test_refund_rounding", 0),
                   ("Verdict: FAIL\nStopped running: tests.test_billing.test_refund_rounding_new", 1)):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "verdict.md"), "w").write(text)
    r = run([E + "/ci-measure/check.py", d])
    if (r.returncode != 0) != bool(want):
        bad.append("ci-measure check misjudged %r\n%s" % (text, r.stdout))

# A failed first attempt in the measured cohort makes the result not valid
src = [json.loads(l) for l in open(E + "/ci-measure/repo/ci-history/after.jsonl")]
for rec in src:
    rec["run_attempt"] = 2
    rec["jobs"] = [dict(rec["jobs"][0], run_attempt=1, conclusion="timed_out")] + rec["jobs"]
    for j in rec["jobs"][1:]:
        j["run_attempt"] = 2
rerun = tempfile.mktemp(suffix=".jsonl")
open(rerun, "w").write("".join(json.dumps(x) + "\n" for x in src))
r = run([M, "compare", "--before", "ci-history/before.jsonl", "--after", rerun], cwd=E + "/ci-measure/repo")
if r.returncode != 0 or "verdict: not enough runs yet" not in r.stdout:
    bad.append("compare: timed-out first attempts should leave too few runs, not a verdict\n" + r.stdout + r.stderr)
r = run([M, "compare", "--before", "ci-history/before.jsonl", "--after", "ci-history/after.jsonl",
         "--event", "push"], cwd=E + "/ci-measure/repo")
if r.returncode != 0 or "verdict: not enough runs yet" not in r.stdout:
    bad.append("compare: no comparable runs at all should say not enough runs\n" + r.stdout + r.stderr)

# Reusable workflows. GitHub lists a called workflow's jobs in the caller's run, named
# "CALLER / JOB". A caller's tests sit in called jobs and a short gate job finishes last:
# the slowest path must run through the called jobs, not file their time before the gate.
from datetime import datetime as _dt, timezone as _tz


def _at(t):
    return _dt.fromtimestamp(1793000000 + t, _tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_of(stamp):
    return int(_dt.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_tz.utc).timestamp()) - 1793000000


def _job(name, queued, started, done, setup=10, conclusion="success"):
    steps = [] if conclusion == "skipped" else [
        {"name": "Set up job", "conclusion": "success", "started_at": _at(started), "completed_at": _at(started + setup)},
        {"name": "Run tests", "conclusion": "success", "started_at": _at(started + setup), "completed_at": _at(done)}]
    return {"id": abs(hash((name, queued))) % 10 ** 9, "name": name, "run_attempt": 1, "conclusion": conclusion,
            "created_at": _at(queued), "started_at": _at(started), "completed_at": _at(done),
            "labels": ["ubuntu-latest"], "runner_name": "r", "steps": steps}


def _run(i, jobs, t0, name="CI"):
    return {"id": 70000 + i, "name": name, "path": ".github/workflows/ci.yml", "event": "pull_request",
            "head_branch": "b%d" % i, "head_sha": "%040d" % i, "run_attempt": 1, "head_message": "Fix",
            "head_repo": "o/r", "conclusion": "success", "created_at": _at(t0), "run_started_at": _at(t0),
            "updated_at": _at(t0 + 3000), "pull_requests": [i], "pull_request_bases": ["main"], "jobs": jobs}


def _caller_run(i, t0, python=True, e2e_extra=0):
    # plan (a called workflow) -> Python / unit, Python / integration -> Python / report;
    # E2E / smoke after plan; a gate after everything. With python=False, a path filter
    # skipped the Python suite: its caller shows as one skipped job, as GitHub lists it.
    jobs = [_job("Plan / changes", t0 + 1, t0 + 3, t0 + 20)]
    end = t0 + 20 + 2 + 120 + e2e_extra
    jobs.append(_job("E2E / smoke", t0 + 20, t0 + 22, end))
    if python:
        jobs += [_job("Python / unit (3.12)", t0 + 20, t0 + 25, t0 + 20 + 900),
                 _job("Python / integration", t0 + 20, t0 + 24, t0 + 20 + 400)]
        jobs.append(_job("Python / report", t0 + 920, t0 + 923, t0 + 950, setup=5))
        end = max(end, t0 + 950)
    else:
        jobs.append(_job("Python", t0 + 20, t0 + 20, t0 + 20, conclusion="skipped"))
    jobs.append(_job("All checks pass", end, end + 2, end + 5, setup=1))
    return _run(i, jobs, t0)


with tempfile.TemporaryDirectory() as t:
    full = [_caller_run(i, i * 4000, e2e_extra=10 * i) for i in range(6)]
    out = t + "/called.jsonl"
    open(out, "w").write("".join(json.dumps(x) + "\n" for x in full))
    got = json.loads(run([M, "split", "--in", out, "--json"]).stdout)
    chain = got["slowest_path_chains"][0]
    if chain["jobs"] != ["Plan / changes", "Python / unit (3.12)", "Python / report", "All checks pass"] or chain["runs"] != 6:
        bad.append("split: the slowest path didn't run through the called jobs: %r" % got["slowest_path_chains"])
    sh = got["slowest_path_share"]
    if "upstream" in got["slowest_path_split"] or abs(sum(sh.values()) - 1) > 1e-9 or sh["running"] < 0.9:
        bad.append("split: a called workflow's running time wasn't on the slowest path: %r" % sh)
    # The parts add up to each run's wait: here every run is 955 s from start to the gate's end.
    rows = [json.loads(l) for l in open(out)]
    for row in rows:
        chain_, parts, _ = mm.path_split(row)
        if abs(sum(parts.values()) - mm.run_wall(row)) > 1e-6:
            bad.append("path_split: parts add up to %r, the wait is %r" % (sum(parts.values()), mm.run_wall(row)))
            break
    called = {x["caller"]: x for x in got["called_workflows"]}
    if called.get("Python", {}).get("median") != 930 or called.get("Python", {}).get("runs") != 6:
        bad.append("split: the Python called workflow should span 930 s in 6 runs: %r" % called.get("Python"))
    # A rerun of failed jobs lists the jobs that passed before under the new attempt as GitHub
    # does (python/cpython run 45186939309): newly queued, with their old start and end. They
    # aren't on the new attempt's path, nor in its called workflows' times. Here the rerun
    # starts 30 s after the reused jobs ended, so a link by end time alone would take them.
    re_ = copy.deepcopy(full[0])
    re_["run_attempt"] = 2
    re_["run_started_at"] = _at(985)
    for j in re_["jobs"]:
        j["run_attempt"] = 2
        j["created_at"] = _at(986)
    re_["jobs"] = [j for j in re_["jobs"] if j["name"] != "E2E / smoke"]
    re_["jobs"].append(dict(_job("E2E / smoke", 990, 992, 1100), run_attempt=2))
    chain_, parts, _ = mm.path_split(re_)
    if [j["name"] for j in chain_] != ["E2E / smoke"] or sum(parts.values()) != 115:
        bad.append("path_split: a rerun's path took jobs from the attempt before: %r" % [j["name"] for j in chain_])
    open(t + "/rerun.jsonl", "w").write(json.dumps(re_) + "\n")
    got_re = json.loads(run([M, "split", "--in", t + "/rerun.jsonl", "--json"]).stdout)
    if any(x["caller"] == "Python" or (x["median"] or 0) < 0 for x in got_re["called_workflows"]):
        bad.append("split: a rerun's reused jobs went into its called workflows' times: %r" % got_re["called_workflows"])

    # Links: a need's end stamped a second after the next job was queued still links; a long
    # gap is "between", not "before the first job"; a skipped job is never a link; of two jobs
    # ending in the same second, the one queued first is taken, and the tie is counted.
    def chain_of(jobs):
        got_ = mm.path_split(_run(0, jobs, 0))
        return [j["name"] for j in got_[0]], got_[1], got_[2]
    names, parts, _ = chain_of([_job("build", 1, 2, 301), _job("test", 300, 302, 600)])
    if names != ["build", "test"]:
        bad.append("path_split: a need stamped a second late wasn't linked: %r" % names)
    names, parts, _ = chain_of([_job("build", 1, 2, 600), _job("deploy", 700, 702, 760)])
    if names != ["build", "deploy"] or parts["between"] != 100 or parts["before_first"] != 1:
        bad.append("path_split: a long gap should stay between the jobs: %r %r" % (names, parts))
    names, parts, _ = chain_of([_job("build", 1, 2, 290), _job("docs", 1, 1, 299, conclusion="skipped"),
                                _job("test", 300, 302, 600)])
    if names != ["build", "test"]:
        bad.append("path_split: a skipped job was taken as a link: %r" % names)
    names, parts, ties = chain_of([_job("b", 1, 3, 300), _job("a", 2, 4, 300), _job("gate", 300, 301, 310)])
    if names != ["b", "gate"] or ties != 1:
        bad.append("path_split: a tie should go to the job queued first and be counted: %r %r" % (names, ties))

    # Mixed cohorts: 14 pushes skip the Python suite (about 2.5 min), 6 run it (about 16 min).
    # One median over all 20 is the fast group's, so the headline must be the group that
    # holds most of the wait, with each group's count, median and tail, and the blend named.
    mixed = full + [_caller_run(10 + i, (10 + i) * 4000, python=False) for i in range(14)]
    out = t + "/mixed.jsonl"
    open(out, "w").write("".join(json.dumps(x) + "\n" for x in mixed))
    got = json.loads(run([M, "split", "--in", out, "--json"]).stdout)
    groups = {c["longest_job"]: c for c in got["cohorts"]}
    head = got["headline"] or {}
    if (head.get("longest_job") != "CI / Python / unit (3.12)" or head.get("runs") != 6 or head.get("median") != 955
            or groups.get("CI / E2E / smoke", {}).get("runs") != 14 or got["wait_median"] > 200):
        bad.append("split: cohorts wrong: headline %r, groups %r" % (head, sorted(groups)))
    text = run([M, "split", "--in", out]).stdout
    if ("PR wait, runs whose longest job was CI / Python / unit (3.12) (6 successful runs" not in text
            or "blended, all 20 successful runs" not in text
            or not re.search(r"^ +14 runs .* CI / E2E / smoke$", text, re.M)):
        bad.append("split: the headline should name its group and the blend\n" + text)
    if "Python / unit (3.12)" not in text.split("slowest path of the runs in that headline")[-1].split("job that")[0]:
        bad.append("split: the slowest path should describe the headline group\n" + text)
    text = run([M, "split", "--in", out, "--cohort", "CI / E2E / smoke"]).stdout
    if "PR wait, runs whose longest job was CI / E2E / smoke (14 successful runs" not in text or "chosen with --cohort" not in text:
        bad.append("split: --cohort should choose the headline group\n" + text)
    # The skipped caller isn't a job that took no time: the per-job table counts jobs that ran.
    if any(x["job"] == "CI / Python" for x in got["jobs"]):
        bad.append("split: a skipped job was counted in the jobs table")
    # A group needs 5 runs to be the headline: one slow outlier doesn't head the report, and
    # with no group of 5 the blend is the headline and says so.
    odd = mixed + [_caller_run(40, 40 * 4000, e2e_extra=6000)]
    odd[-1]["jobs"].append(_job("E2E / soak", 40 * 4000 + 20, 40 * 4000 + 22, 40 * 4000 + 7000))
    open(t + "/odd.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in odd))
    got = json.loads(run([M, "split", "--in", t + "/odd.jsonl", "--json"]).stdout)
    if (got["cohorts"][0]["longest_job"] != "CI / E2E / soak" or (got["headline"] or {}).get("longest_job")
            != "CI / Python / unit (3.12)"):
        bad.append("split: a one-run group headed the report: %r" % (got["headline"],))
    few_ = [_caller_run(50 + i, (50 + i) * 4000) for i in range(3)] + [
        _caller_run(60 + i, (60 + i) * 4000, python=False) for i in range(3)]
    open(t + "/few.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in few_))
    text = run([M, "split", "--in", t + "/few.jsonl"]).stdout
    if "PR wait, all 6 successful runs blended" not in text or "no group of them has 5 runs" not in text:
        bad.append("split: with no group of 5 the headline should be the blend, named\n" + text)
    # One group only: the plain line, no blend.
    text = run([M, "split", "--in", t + "/called.jsonl"]).stdout
    if "PR wait (run start to last job done, 6 successful runs)" not in text or "blended" in text:
        bad.append("split: one group should print the plain PR wait line\n" + text)

# Transient GitHub errors: a GET is tried 3 times with backoff; a run whose jobs still can't
# be read is left out and named, never written with no jobs; a rate limit stops with its
# reset time and isn't retried; a 404 isn't retried.
import io
import contextlib
import types


class _FakeGh:
    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, cmd, **kw):
        if cmd[0] != "gh":
            return _real_run(cmd, **kw)
        path = cmd[-1]
        self.calls.append(path)
        for match, answers in self.script:
            if match in path:
                ans = answers.pop(0) if len(answers) > 1 else answers[0]
                if isinstance(ans, tuple):
                    raise subprocess.CalledProcessError(1, cmd, "", ans[1])
                return types.SimpleNamespace(stdout=ans, returncode=0)
        raise AssertionError("unexpected gh call " + path)


_real_run = subprocess.run
_slept = []
mm.sleep = _slept.append
E502 = (1, "gh: Server Error (HTTP 502)")


def _with(fake, fn):
    mm.subprocess.run = fake
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()) as so:
            try:
                return fn(), so.getvalue(), err.getvalue(), None
            except SystemExit as e:
                return None, so.getvalue(), err.getvalue(), e
    finally:
        mm.subprocess.run = _real_run


f = _FakeGh([("x/y", [E502, E502, '{"ok": 1}'])])
got, _, _, ex = _with(f, lambda: mm.gh_get("x/y"))
if got != {"ok": 1} or len(f.calls) != 3 or _slept != [2, 6]:
    bad.append("gh_get: two 502s then an answer should take 3 tries with backoff: %r %r %r" % (got, f.calls, _slept))
f = _FakeGh([("x/y", [E502])])
got, _, err, ex = _with(f, lambda: mm.gh_get("x/y"))
if ex is None or len(f.calls) != 3 or "failed 3 times: HTTP 502" not in err:
    bad.append("gh_get: three 502s should stop, naming them: %r %r" % (f.calls, err))
f = _FakeGh([("x/y", [(1, "gh: error connecting to api.github.com"), '{"ok": 2}'])])
got, _, _, ex = _with(f, lambda: mm.gh_get("x/y"))
if got != {"ok": 2}:
    bad.append("gh_get: a dropped connection should be retried")
f = _FakeGh([("x/y", ['{"cut', '{"ok": 3}'])])
got, _, _, ex = _with(f, lambda: mm.gh_get("x/y"))
if got != {"ok": 3} or len(f.calls) != 2:
    bad.append("gh_get: an answer cut off mid-way should be tried again: %r" % f.calls)
f = _FakeGh([("x/y", [(1, "gh: You have exceeded a secondary rate limit. (HTTP 403)")])])
got, _, err, ex = _with(f, lambda: mm.gh_get("x/y"))
if ex is None or len(f.calls) != 1 or "secondary rate limit" not in err:
    bad.append("gh_get: a secondary rate limit should stop at once: %r %r" % (f.calls, err))
f = _FakeGh([("rate_limit", ['{"resources": {"core": {"remaining": 0, "reset": 1793000000}}}']),
             ("x/y", [(1, "gh: API rate limit exceeded for user ID 1. (HTTP 429)")])])
got, _, err, ex = _with(f, lambda: mm.gh_get("x/y"))
if ex is None or f.calls.count("x/y") != 1 or "resets at" not in err:
    bad.append("gh_get: a primary rate limit on a 429 should stop with its reset time: %r" % err)
f = _FakeGh([("x/y", [(1, "gh: Not Found (HTTP 404)")])])
got, _, _, ex = _with(f, lambda: mm.gh_get("x/y", missing=True))
if got is not None or len(f.calls) != 1:
    bad.append("gh_get: a 404 should not be retried: %r" % f.calls)
f = _FakeGh([("rate_limit", ['{"resources": {"core": {"remaining": 0, "reset": 1793000000}}}']),
             ("x/y", [(1, "gh: API rate limit exceeded for user ID 1. (HTTP 403)")])])
got, _, err, ex = _with(f, lambda: mm.gh_get("x/y"))
if ex is None or f.calls.count("x/y") != 1 or "resets at" not in err:
    bad.append("gh_get: a rate limit should stop at once with its reset time: %r %r" % (f.calls, err))

with tempfile.TemporaryDirectory() as t:
    listed = [{"id": 11, "status": "completed", "conclusion": "success", "event": "push", "created_at": _at(0)},
              {"id": 12, "status": "completed", "conclusion": "failure", "event": "push", "created_at": _at(10)},
              {"id": 13, "status": "completed", "conclusion": "success", "event": "push", "created_at": _at(20)}]
    jobs = json.dumps([{"jobs": [_job("test", 0, 1, 60)]}])

    outs = itertools.count()

    def fetch_with(created, calls=None, failing="/runs/12/jobs"):
        script = [("rate_limit", ['{"resources": {"core": {"remaining": 5000, "reset": 0}}}']),
                  (failing, [E502]), ("/jobs", [jobs]),
                  ("/runs?", [json.dumps({"total_count": 3, "workflow_runs": listed}),
                              json.dumps({"total_count": 3, "workflow_runs": []})])]
        a = types.SimpleNamespace(repo="o/r", workflow="ci.yml", event="push", branch=None, limit=10,
                                  created=created, out=t + "/runs-%d.jsonl" % next(outs))
        cwd = os.getcwd()
        os.chdir(t)
        try:
            fake = _FakeGh(script)
            res = _with(fake, lambda: mm.cmd_fetch(a))
            if calls is not None:
                calls.extend(fake.calls)
            return a.out, res
        finally:
            os.chdir(cwd)
    path, (_, so, err, ex) = fetch_with("<=" + _at(100))
    ids = [json.loads(l)["id"] for l in open(path)] if os.path.exists(path) else []
    if ex is not None or ids != [11, 13] or "left out: run 12 (failure), jobs read failed 3 times: HTTP 502" not in so:
        bad.append("fetch: a run whose jobs can't be read should be left out and named: %r\n%s%s" % (ids, so, err))
    seen = []
    path, (_, so, err, ex) = fetch_with(_at(-100) + ".." + _at(100), seen)
    if ex is None or os.path.exists(path) or "run 12 (failure)" not in err:
        bad.append("fetch: a window read whole was written with a run left out\n" + so + err)
    if any("/runs/13/" in c for c in seen):
        bad.append("fetch: a window read whole kept reading after a run it must refuse")
    # Every run unreadable: more than one in 20.
    path, (_, so, err, ex) = fetch_with("<=" + _at(100), failing="/jobs")
    if ex is None or os.path.exists(path) or "more than one run in 20" not in err:
        bad.append("fetch: a baseline with most runs unreadable was written\n" + so + err)
mm.sleep = mm.time.sleep


# ---- v0.3 fixtures

# Offline reading. GitHub's own answers saved in a folder read the same as fetch's file;
# a run whose jobs can't be read whole is named; a startup failure lists no jobs and stays.
def _raw(rec):
    """A fetched record back in the shape GitHub answers with."""
    r = {k: rec.get(k) for k in ("id", "name", "path", "event", "head_branch", "head_sha", "run_attempt",
                                 "conclusion", "created_at", "run_started_at", "updated_at")}
    r["status"] = "completed"
    r["head_commit"] = {"message": rec.get("head_message") or ""}
    r["head_repository"] = {"full_name": rec.get("head_repo")}
    bases = rec.get("pull_request_bases") or []
    r["pull_requests"] = [{"number": n, "base": {"ref": bases[0] if bases else "main"}} for n in rec.get("pull_requests") or []]
    jobs = [dict(j, run_id=rec["id"]) for j in rec["jobs"]]
    return r, jobs


def _save_dir(folder, recs, slurp_every=2):
    os.makedirs(folder, exist_ok=True)
    raws = [_raw(x) for x in recs]
    json.dump([{"total_count": len(raws), "workflow_runs": [r for r, _ in raws]}], open(folder + "/runs.json", "w"))
    for i, (r, jobs) in enumerate(raws):
        pages = [{"total_count": len(jobs), "jobs": jobs[:3]}, {"total_count": len(jobs), "jobs": jobs[3:]}]
        with open(folder + "/jobs-%d.json" % r["id"], "w") as f:
            # Both shapes gh prints: --slurp's array, and pages one after another.
            f.write(json.dumps(pages) if i % slurp_every == 0 else "".join(json.dumps(x) for x in pages))


NO_PROCESS = r"""
import sys, runpy
BANNED = ("subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.exec", "os.spawn", "os.forkpty")
def hook(ev, args):
    if (ev == "import" and args[0] == "subprocess") or ev in BANNED:
        raise SystemExit("PROCESS: " + ev)
sys.addaudithook(hook)
script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
try:
    runpy.run_path(script, run_name="__main__")
finally:
    if "subprocess" in sys.modules:
        print("PROCESS: subprocess was imported", file=sys.stderr)
"""
with tempfile.TemporaryDirectory() as t:
    src = E + "/ci-diagnose/repo/ci-history/runs.jsonl"
    recs = [json.loads(l) for l in open(src) if l.strip()]
    _save_dir(t + "/saved", recs)
    want = run([M, "split", "--in", src, "--json"]).stdout
    got = subprocess.run([sys.executable, "-c", NO_PROCESS, M, "split", "--runs-dir", t + "/saved", "--json"],
                         capture_output=True, text=True)
    if got.returncode != 0 or "PROCESS" in got.stderr or json.loads(got.stdout or "{}") != json.loads(want):
        bad.append("split --runs-dir: should match the JSONL file and start no process\n" + got.stderr[-2000:])
    for args in (["split", "--runs-dir", t + "/nothing-here"], ["split", "--runs-dir", t + "/junk"]):
        os.makedirs(t + "/junk", exist_ok=True)
        open(t + "/junk/x.json", "w").write("{not json")
        r = subprocess.run([sys.executable, "-c", NO_PROCESS, M] + args, capture_output=True, text=True)
        if r.returncode == 0 or "PROCESS" in r.stderr or "measure.py:" not in r.stderr:
            bad.append("split --runs-dir: a bad folder should stop with a message and no process\n" + r.stderr)
    r = run([M, "compare", "--before", t + "/saved", "--after", t + "/saved"])
    if r.returncode == 0 or "compare reads only files fetch wrote" not in r.stderr:
        bad.append("compare: a folder of saved answers must be refused\n" + r.stderr)
    # A rerun saved without filter=all (latest attempt only) is named; an empty startup failure stays.
    extra = copy.deepcopy(recs[:3])
    extra[0]["run_attempt"] = 2
    for j in extra[0]["jobs"]:
        j["run_attempt"] = 2
    extra[1]["conclusion"], extra[1]["jobs"] = "startup_failure", []
    _save_dir(t + "/edge", extra)
    os.remove(t + "/edge/jobs-%d.json" % extra[1]["id"])
    open(t + "/edge/empty.json", "w").write(json.dumps({"total_count": 0, "jobs": []}))
    r = run([M, "split", "--runs-dir", t + "/edge", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if ("only attempt 2's jobs saved" not in r.stderr or got.get("runs") != 2
            or got.get("ended_runs") != 2 or got.get("passed_runs") != 1):
        bad.append("split --runs-dir: a latest-attempt-only rerun should be named, a startup failure kept\n"
                   + r.stdout[:300] + r.stderr)
src_text = open(M).read()
for phrase in ("auth login", "auth token", "auth status"):
    if phrase in src_text:
        bad.append("measure.py: holds %r, which reads like an auth command to an agent guard" % phrase)
if re.search(r"^import subprocess|^from subprocess", src_text, re.M):
    bad.append("measure.py: imports subprocess at the top; reading saved runs must not load it")


# The runner's own steps keep their bucket whatever --setup-pattern says.
_steps = [("Set up job", 10), ("Install deps", 20), ("Test", 30), ("Post Install deps", 5), ("Complete job", 1)]
_t = 0
_sj = {"started_at": _at(0), "created_at": _at(0), "steps": []}
for n, d in _steps:
    _sj["steps"].append({"name": n, "started_at": _at(_t), "completed_at": _at(_t + d)})
    _t += d
_sj["completed_at"] = _at(_t)
got = mm.job_split(_sj, "install")
if (got["setup"], got["running"], got["cleanup"]) != (30, 30, 6):
    bad.append("job_split: Set up job, Post and Complete job must keep their buckets under a pattern: %r" % got)


# Reusable workflows with gates: a caller job "checks" calls Static, Test and a trailing
# Validation gate; the caller's "verify" gate needs checks. The path runs through Static,
# the gates are the tail, Static is the last job that did work, and without the gates each
# run ends 34 s sooner. Runs where verify does real work have no tail: they count as 0.
def _steps_job(name, queued, started, steps, labels=("ubuntu-latest",)):
    t, out = started, []
    for n, d in steps:
        out.append({"name": n, "conclusion": "success", "started_at": _at(t), "completed_at": _at(t + d)})
        t += d
    return {"id": abs(hash((name, queued, started))) % 10 ** 9, "name": name, "run_attempt": 1,
            "conclusion": "success", "created_at": _at(queued), "started_at": _at(started),
            "completed_at": _at(t), "labels": list(labels), "runner_name": "r", "steps": out}


def _gated(i, verify_work=1):
    t0 = i * 4000
    return _run(i, [
        _steps_job("checks / Static", t0 + 1, t0 + 3, [("Set up job", 2), ("Run actions/checkout@v4", 5),
                                                         ("Typecheck app", 140), ("Typecheck api", 76),
                                                         ("Test exported", 58), ("Complete job", 0)]),
        _steps_job("checks / Test", t0 + 1, t0 + 3, [("Set up job", 2), ("Test", 150)]),
        _steps_job("checks / Validation", t0 + 284, t0 + 294, [("Set up job", 2), ("Check results", 1)]),
        _steps_job("verify", t0 + 297, t0 + 314, [("Set up job", 2), ("Check results", verify_work)]),
    ], t0)


with tempfile.TemporaryDirectory() as t:
    open(t + "/g.jsonl", "w").write("".join(json.dumps(_gated(i)) + "\n" for i in range(6)))
    got = json.loads(run([M, "split", "--in", t + "/g.jsonl", "--json"]).stdout)
    chain = got["slowest_path_chains"][0]["jobs"]
    if chain != ["checks / Static", "checks / Validation", "verify"]:
        bad.append("split: the reusable-workflow path should be Static -> Validation -> verify: %r" % chain)
    if (got["gate_tails"] != [{"jobs": ["checks / Validation", "verify"], "runs": 6}]
            or got["gate_ceiling_median"] != 33 or got["last_working_jobs"] != [["checks / Static", 6]]):
        bad.append("split: gates at the end and the last job that did work: %r %r %r"
                   % (got["gate_tails"], got["gate_ceiling_median"], got["last_working_jobs"]))
    st = [x["step"] for x in got["last_working_job_steps"]["checks / Static"]]
    if st[:5] != ["Set up job", "Run actions/checkout@v4", "Typecheck app", "Typecheck api", "Test exported"]:
        bad.append("split: the last working job's steps, in order: %r" % st)
    text = run([M, "split", "--in", t + "/g.jsonl"]).stdout
    if "last job that did work (before the candidates): checks / Static (6 runs)" not in text:
        bad.append("split: the text should name the last job that did work\n" + text)
    mixed = [_gated(i) for i in range(5)] + [_gated(10 + i, verify_work=30) for i in range(6)]
    open(t + "/m.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in mixed))
    got = json.loads(run([M, "split", "--in", t + "/m.jsonl", "--json"]).stdout)
    if got["gate_ceiling_median"] != 0 or got["gate_ceiling_runs"] != 11:
        bad.append("split: runs with no gate tail should count as 0: %r over %r"
                   % (got["gate_ceiling_median"], got["gate_ceiling_runs"]))
    # Steps that ran side by side (native parallel steps) are marked: they don't add up.
    par = _gated(30)
    st = par["jobs"][0]["steps"]
    # Test exported ran beside Typecheck api (as native parallel steps do); the job's end is unchanged.
    st[4]["started_at"] = st[3]["started_at"]
    open(t + "/p.jsonl", "w").write(json.dumps(par) + "\n")
    got = json.loads(run([M, "split", "--in", t + "/p.jsonl", "--json"]).stdout)
    if not got["last_working_job_steps_overlap"].get("checks / Static"):
        bad.append("split: overlapping steps should be marked: %r" % got["last_working_job_steps_overlap"])


# A rerun of failed jobs: both attempts' rows, as GitHub lists them with filter=all. The
# reused build is one execution (its minutes once) and gives no wait figure (#21).
def _rerun_run(i):
    t0 = i * 4000
    b1 = dict(_job("build", t0, t0 + 10, t0 + 100), run_attempt=1)
    t1 = dict(_job("test", t0 + 100, t0 + 110, t0 + 200, conclusion="failure"), run_attempt=1)
    b2 = dict(b1, run_attempt=2, created_at=_at(t0 + 301), id=b1["id"] + 1)
    t2 = dict(_job("test", t0 + 301, t0 + 310, t0 + 400), run_attempt=2)
    r = _run(i, [b1, t1, b2, t2], t0)
    r["run_attempt"], r["run_started_at"] = 2, _at(t0 + 300)
    return r


rr = _rerun_run(0)
if mm.run_minutes(rr) != 6 or abs(mm.run_minutes(rr, True) - 270 / 60.0) > 1e-9:
    bad.append("run_minutes: a reused job must count once: %r rounded, %r exact"
               % (mm.run_minutes(rr), mm.run_minutes(rr, True)))
with tempfile.TemporaryDirectory() as t:
    plain = _run(1, [_job("build", 4000, 4010, 4100), _job("test", 4100, 4110, 4200)], 4000)
    open(t + "/r.jsonl", "w").write(json.dumps(rr) + "\n" + json.dumps(plain) + "\n")
    got = json.loads(run([M, "split", "--in", t + "/r.jsonl", "--json"]).stdout)
    row = [x for x in got["jobs"] if x["job"] == "CI / build"][0]
    if row["waiting"] != 10 or row["wait_runs"] != 1 or row["runs"] != 2:
        bad.append("split: a reused job's 0 wait must not count (#21): %r" % row)
    if got["passed_after_rerun"] != 1:
        bad.append("split: a run that passed on a rerun should be counted: %r" % got["passed_after_rerun"])


# When most runs fail, the report leads with it.
with tempfile.TemporaryDirectory() as t:
    rs = []
    for i in range(10):
        x = _run(i, [_job("test", i * 4000, i * 4000 + 5, i * 4000 + 100)], i * 4000)
        if i >= 4:
            x["conclusion"] = "failure"
        rs.append(x)
    rs.append(dict(_run(20, [_job("test", 80000, 80005, 80100)], 80000), conclusion="cancelled"))
    open(t + "/f.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in rs))
    first = run([M, "split", "--in", t + "/f.jsonl"]).stdout.splitlines()[0]
    if not first.startswith("MOST RUNS FAIL: 4 of 10 runs that passed or failed passed (40%)") or "1 cancelled" not in first:
        bad.append("split: most runs failing should lead the report: %r" % first)


# compare and the jobs each run ran (#19). A run's work, as the jobs list shows it, is the
# set of jobs it ran. build + integration against build alone must never pass for a speedup
# unnoticed; runs that ran different sets within a side need --ran or --job.
def _work(i, integration, t0=None, integ=90):
    t0 = i * 4000 if t0 is None else t0
    jobs = [_job("build", t0, t0 + 2, t0 + 100)]
    if integration:
        jobs.append(_job("integration", t0 + 100, t0 + 102, t0 + 100 + integ))
    return _run(i, jobs, t0)


with tempfile.TemporaryDirectory() as t:
    def side(name, rows):
        open(t + "/" + name, "w").write("".join(json.dumps(x) + "\n" for x in rows))
        return t + "/" + name
    b = side("b.jsonl", [_work(i, True) for i in range(5)])
    a_ = side("a.jsonl", [_work(100 + i, False) for i in range(5)])
    r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if not got.get("jobs_changed") or code_of(got) != "faster_jobs_changed" or "different jobs" not in got.get("verdict", ""):
        bad.append("compare: sides that ran different jobs must never give a plain verdict\n" + r.stdout + r.stderr)
    b = side("b2.jsonl", [_work(i, True) for i in range(5)] + [_work(10 + i, False) for i in range(3)])
    a_ = side("a2.jsonl", [_work(100 + i, True, integ=60) for i in range(5)] + [_work(110 + i, False) for i in range(5)])
    r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest"])
    if r.returncode == 0 or "ran different sets of jobs" not in r.stderr:
        bad.append("compare: runs with different job sets within a side must refuse a whole-run verdict\n" + r.stdout + r.stderr)
    r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest", "--ran", "integration", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if (got.get("before_runs") != 5 or got.get("after_runs") != 5 or code_of(got) != "faster"
            or got.get("verdict_code") != "ran_descriptive"):
        bad.append("compare --ran: should time the 5 runs a side that ran integration\n" + r.stdout + r.stderr)
    r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest", "--job", "integration",
             "--end", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if got.get("before_median") != 190 or got.get("after_median") != 160:
        bad.append("compare --end: should time from the run's start to the job's end\n" + r.stdout + r.stderr)
    r = run([M, "compare", "--before", b, "--after", a_, "--end"])
    if r.returncode == 0:
        bad.append("compare: --end without --job should be refused")


# flaky: a failure stands alone between two reports where the test passed, on one pull
# request; a broken base fails a stretch of pull requests together; green runs with no
# report are no evidence; a failed run with no report joins the stretch.
def _flaky(seq):
    with tempfile.TemporaryDirectory() as t:
        rows = []
        for i, (pr, st) in enumerate(seq):
            x = _run(i, [_job("test", i * 100, i * 100 + 2, i * 100 + 50)], i * 100)
            x["pull_requests"] = [pr]
            x["conclusion"] = "failure" if st in ("f", "r") else "success"
            rows.append(x)
            if st in ("p", "f"):
                os.makedirs(t + "/rep/%d" % x["id"])
                open(t + "/rep/%d/report.xml" % x["id"], "w").write(
                    '<testsuite name="s"><testcase classname="c" name="T">%s</testcase>'
                    '<testcase classname="c" name="other"/></testsuite>' % ("<failure/>" if st == "f" else ""))
        open(t + "/runs.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in rows))
        r = run([M, "flaky", "--in", t + "/runs.jsonl", "--reports", t + "/rep", "--short", "--json"])
        got = json.loads(r.stdout) if r.returncode == 0 else {"tests": []}
        return ([x for x in got["tests"] if x["test"] == "T"] or [{}])[0], r


for seq, alone, label in (
        ([(1, "p"), (2, "f"), (3, "p"), (4, "f"), (5, "p"), (6, "f"), (7, "p")], 3, "recurring on 3 pull requests"),
        ([(1, "p"), (2, "f"), (3, "f"), (4, "f"), (5, "f"), (6, "p")], 0, "a broken base"),
        ([(1, "p"), (2, "f"), (3, "p"), (2, "f"), (4, "p"), (2, "f"), (5, "p")], 1, "one pull request"),
        ([(1, "p"), (2, "f"), (3, "g"), (4, "f"), (5, "g"), (6, "f"), (7, "p")], 0, "green runs with no report"),
        ([(1, "p"), (2, "f"), (3, "r"), (4, "p"), (5, "f"), (6, "p"), (7, "f"), (8, "p")], 2, "an unread failed run")):
    got, r = _flaky(seq)
    if got.get("alone_on_pull_requests") != alone or got.get("recurring") != (alone >= 3):
        bad.append("flaky: %s should stand alone on %d pull requests: %r\n%s" % (label, alone, got, r.stderr))


# ---- v0.3 review regressions (Opus and Codex Astra on 20e9b66c)

# compare: --ran must leave one job set a side, and --job --end reads the jobs before it.
with tempfile.TemporaryDirectory() as t:
    def side(name, rows):
        open(t + "/" + name, "w").write("".join(json.dumps(x) + "\n" for x in rows))
        return t + "/" + name
    def gate_after(x):
        end = max(mm.ts(j["completed_at"]) for j in x["jobs"]) - 1793000000
        x["jobs"].append(_job("required", end, end + 1, end + 11))
        return x
    b = side("b.jsonl", [gate_after(_work(i, i < 9)) for i in range(10)])
    a_ = side("a.jsonl", [gate_after(_work(100 + i, i < 1)) for i in range(10)])
    for extra in (["--ran", "build"], ["--job", "required", "--end"]):
        r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest"] + extra)
        if r.returncode == 0 or "different sets of jobs" not in r.stderr:
            bad.append("compare %s: a change in the work mix passed for a speedup\n%s%s" % (extra, r.stdout, r.stderr))
    r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest", "--job", "required", "--json"])
    if r.returncode != 0:
        bad.append("compare --job without --end times the job's own duration, whatever ran before it\n" + r.stderr)

# --job --end: a job that varies only after the timed one doesn't move its end, so it is timed.
with tempfile.TemporaryDirectory() as t:
    def tail_job(x, extra):
        if extra:
            end = max(mm.ts(j["completed_at"]) for j in x["jobs"]) - 1793000000
            x["jobs"].append(_job("report", end, end + 1, end + 30))
        return x
    b = t + "/b.jsonl"
    a_ = t + "/a.jsonl"
    open(b, "w").write("".join(json.dumps(tail_job(_work(i, True), i % 2)) + "\n" for i in range(6)))
    open(a_, "w").write("".join(json.dumps(tail_job(_work(100 + i, True, integ=60), i % 3)) + "\n" for i in range(6)))
    r = run([M, "compare", "--before", b, "--after", a_, "--label", "ubuntu-latest", "--job", "integration",
             "--end", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    # Every job a run ran counts for --end (one queued after the timed job can still have held
    # its runner), so a set that varies only after it is refused too: safe, never a false speedup.
    if r.returncode == 0:
        bad.append("compare --end: runs whose job sets differ must be refused\n" + r.stdout)

# --end: a job allowed to fail before the timed one rules the run out, as for a whole run.
with tempfile.TemporaryDirectory() as t:
    def allowed(i, fail_after):
        t0 = i * 4000
        comp = _job("compile", t0, t0 + 1, t0 + (fail_after or 180), conclusion="failure" if fail_after else "success")
        end = mm.ts(comp["completed_at"]) - 1793000000
        return _run(i, [comp, _job("required", end, end + 1, end + 21)], t0)
    open(t + "/b.jsonl", "w").write("".join(json.dumps(allowed(i, 0 if i < 5 else 180)) + "\n" for i in range(25)))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(allowed(100 + i, 0 if i < 5 else 10)) + "\n" for i in range(25)))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--job", "required", "--end", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if got.get("before_runs") != 5 or got.get("after_runs") != 5 or (code_of(got) or "").startswith("faster"):
        bad.append("compare --end: runs with a failed job before the timed one were timed: %r\n%s"
                   % ({k: got.get(k) for k in ("before_runs", "after_runs", "verdict_code")}, r.stderr))

# --ran: the workload's own failures count. Integration starts timing out on its slow runs
# after; the workflow-wide failure share is unchanged, but among runs that started it, it rose.
with tempfile.TemporaryDirectory() as t:
    def integ_run(i, ran, ok, fast=False):
        x = _work(i, ran, integ=10 if fast else 90)
        if ran and not ok:
            x["jobs"][-1]["conclusion"] = "timed_out"
            x["conclusion"] = "failure"
        if not ran and not ok:
            x["jobs"][0]["conclusion"] = "failure"
            x["conclusion"] = "failure"
        return x
    before = ([integ_run(i, True, True) for i in range(65)] + [integ_run(100 + i, True, False) for i in range(25)]
              + [integ_run(200 + i, False, True) for i in range(60)])
    after = ([integ_run(1000 + i, True, True, fast=True) for i in range(5)] + [integ_run(1100 + i, True, False) for i in range(25)]
             + [integ_run(1200 + i, False, True) for i in range(95)])
    # Workflow-wide failures: 25 of 150 before; 25 of 125 after, about the same share.
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--ran", "integration", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if code_of(got) != "not_valid" or got.get("failed_after_job") != [25, 30]:
        bad.append("compare --ran: failures among runs that started the job should be checked: %r\n%s"
                   % ({k: got.get(k) for k in ("verdict_code", "failed_before", "failed_after", "failed_after_job")}, r.stderr))

# The workload a named job picks: a skipped row with a timestamp isn't a start; --job (and --end)
# checks it as --ran does; its cancellations count; a small rise in its failures is reported.
with tempfile.TemporaryDirectory() as t:
    def wl(i, ran, outcome, integ=90):
        x = _work(i, True, integ=integ)
        if not ran:
            x["jobs"][-1] = dict(x["jobs"][-1], conclusion="skipped", steps=[])  # timestamped skip
        elif outcome == "timed_out":
            x["jobs"][-1]["conclusion"], x["conclusion"] = "timed_out", "failure"
        elif outcome == "cancelled":
            x["jobs"][-1]["conclusion"], x["conclusion"] = "cancelled", "cancelled"
        return x
    def other_fail(i):
        x = wl(i, False, "ok")
        x["jobs"][0]["conclusion"], x["conclusion"] = "failure", "failure"
        return x
    # Workflow-wide 35 of 130 failed on both sides; among runs where integration ran, 0/40 -> 35/40.
    before = ([wl(i, True, "ok") for i in range(40)] + [wl(100 + i, False, "ok") for i in range(55)]
              + [other_fail(300 + i) for i in range(35)])
    after = ([wl(1000 + i, True, "ok", integ=10) for i in range(5)] + [wl(1100 + i, True, "timed_out") for i in range(35)]
             + [wl(1200 + i, False, "ok") for i in range(90)])
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    for extra in (["--ran", "integration"], ["--job", "integration", "--end"], ["--job", "integration"]):
        r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json"] + extra)
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        if (got.get("verdict_code") != "not_valid" or got.get("failed_before") != got.get("failed_after")
                or got.get("failed_before_job") != [0, 40] or got.get("failed_after_job") != [35, 40]):
            bad.append("compare %s: failures where the job ran rose 0/40 -> 35/40, the workflow's didn't: %r"
                       % (extra, {k: got.get(k) for k in ("verdict_code", "failed_before", "failed_after",
                                                          "failed_before_job", "failed_after_job")}))
    # Both named: the workload is the runs where both ran.
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--ran", "build",
             "--job", "integration", "--end"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if code_of(got) != "not_valid" or got.get("failed_after_job") != [35, 40]:
        bad.append("compare --ran with --job: the workload is the runs where both ran: %r" % code_of(got))
    after = ([wl(2000 + i, True, "ok") for i in range(75)] + [wl(2100 + i, True, "cancelled") for i in range(25)]
             + [wl(2200 + i, False, "ok") for i in range(115)])
    # Workflow-wide 25 cancelled on both sides; among runs where integration ran, 0 -> 25.
    before = ([wl(3000 + i, True, "ok", integ=95) for i in range(100)] + [wl(3100 + i, False, "ok") for i in range(90)]
              + [dict(wl(3300 + i, False, "ok"), conclusion="cancelled") for i in range(25)])
    open(t + "/b2.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a2.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b2.jsonl", "--after", t + "/a2.jsonl", "--ran", "integration", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if (not (code_of(got) or "").endswith("_more_cancelled")
            or got.get("cancelled_before")[0] != got.get("cancelled_after")[0]
            or got.get("cancelled_after_job") != [25, 100] or got.get("cancelled_before_job") != [0, 100]):
        bad.append("compare --ran: cancellations among the workload's runs should qualify: %r %r"
                   % (code_of(got), got.get("cancelled_after_job")))
    # A small rise in failures doesn't hide a rise in cancellations: both are reported.
    before = ([wl(6000 + i, True, "ok", integ=95) for i in range(99)] + [wl(6100, True, "timed_out")]
              + [wl(6200 + i, False, "ok") for i in range(115)])
    after = ([wl(7000 + i, True, "ok") for i in range(74)] + [wl(7100, True, "timed_out")]
             + [wl(7200 + i, True, "cancelled") for i in range(25)] + [wl(7300 + i, False, "ok") for i in range(115)])
    open(t + "/b4.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a4.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b4.jsonl", "--after", t + "/a4.jsonl", "--ran", "integration", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if code_of(got) != "faster_more_failures_more_cancelled":
        bad.append("compare --ran: more failures and more cancellations should both show: %r" % code_of(got))
    before = [wl(4000 + i, True, "ok") for i in range(5)] + [wl(4100 + i, False, "ok") for i in range(24)] + [
        dict(wl(4200, False, "ok"), conclusion="failure")]
    after = [wl(5000 + i, True, "ok", integ=10) for i in range(5)] + [wl(5100, True, "timed_out")] + [
        wl(5200 + i, False, "ok") for i in range(24)]
    open(t + "/b3.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a3.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b3.jsonl", "--after", t + "/a3.jsonl", "--ran", "integration", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if code_of(got) != "faster_more_failures":
        bad.append("compare --ran: a rise in the workload's failures within chance should be reported: %r %r %r"
                   % (code_of(got), got.get("failed_after_job"), r.stderr[-300:]))

# backend -> integration: after the change, slow backend runs fail before integration starts.
# The runs where both ran show no failure, the backend's runs do (not valid); with --job alone,
# fewer runs reached integration, which qualifies the verdict.
with tempfile.TemporaryDirectory() as t:
    def chain(i, outcome, fast=False):
        t0 = i * 4000
        be = _job("backend", t0, t0 + 1, t0 + (20 if fast else 170))
        jobs = [be]
        if outcome == "ok":
            end = mm.ts(be["completed_at"]) - 1793000000
            jobs.append(_job("integration", end, end + 1, end + 11))
            conc = "success"
        else:
            be["conclusion"], conc = outcome, outcome
            # GitHub lists the job whose need failed, skipped.
            jobs.append(dict(_job("integration", t0 + 170, t0 + 170, t0 + 170), conclusion="skipped",
                             steps=[], started_at=None))
        x = _run(i, jobs, t0)
        x["conclusion"] = conc
        return x
    def other(i, ok=True):
        x = _run(i, [_job("docs", i * 4000, i * 4000 + 1, i * 4000 + 30)], i * 4000)
        if not ok:
            x["jobs"][0]["conclusion"], x["conclusion"] = "failure", "failure"
        return x
    before = [chain(i, "ok") for i in range(40)] + [other(100 + i) for i in range(55)] + [other(200 + i, False) for i in range(35)]
    after = ([chain(1000 + i, "ok", fast=True) for i in range(5)] + [chain(1100 + i, "failure") for i in range(35)]
             + [other(1200 + i) for i in range(90)])
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json",
             "--ran", "backend", "--job", "integration", "--end"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if code_of(got) != "not_valid" or got.get("failed_after_job") != [35, 40]:
        bad.append("compare --ran backend --job integration: the backend's own failures should count: %r %r"
                   % (code_of(got), got.get("failed_after_job")))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--job", "integration", "--end"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if not end_qualified(got, "stopped"):
        bad.append("compare --job --end: runs stopped upstream should qualify the reading: %r %r"
                   % (got.get("reading_code"), rose_checks(got)))

# Only the runs where both named jobs ran show the rise: each job's own runs hold 35 failures of
# 80 on both sides, and among runs where both ran it goes 0/40 -> 35/40.
with tempfile.TemporaryDirectory() as t:
    def two(i, has_a, has_b, ok, fast=False):
        t0, jobs = i * 4000, []
        if has_a:
            jobs.append(_job("a", t0, t0 + 1, t0 + 10))
        if has_b:
            jobs.append(_job("b", t0, t0 + 1, t0 + (10 if fast else 100)))
        x = _run(i, jobs, t0)
        if not ok:
            jobs[-1]["conclusion"], x["conclusion"] = "failure", "failure"
        return x
    before = ([two(i, True, True, True) for i in range(40)] + [two(100 + i, True, False, i >= 35) for i in range(40)]
              + [two(200 + i, False, True, i >= 35) for i in range(40)])
    after = ([two(1000 + i, True, True, True, fast=True) for i in range(5)] + [two(1100 + i, True, True, False) for i in range(35)]
             + [two(1200 + i, True, False, True) for i in range(40)] + [two(1300 + i, False, True, True) for i in range(40)])
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--ran", "a", "--job", "b"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if code_of(got) != "not_valid" or got.get("failed_after_job") != [35, 40]:
        bad.append("compare --ran a --job b: the rise where both ran should count: %r %r"
                   % (code_of(got), got.get("failed_after_job")))
    # Cancellations rise only where integration ran, with --ran backend --job integration.
    def bi(i, cancel, fast=False):
        t0 = i * 4000
        jobs = [_job("backend", t0, t0 + 1, t0 + 20), _job("integration", t0 + 20, t0 + 21, t0 + (30 if fast else 180))]
        x = _run(i, jobs, t0)
        if cancel:
            jobs[1]["conclusion"], x["conclusion"] = "cancelled", "cancelled"
        return x
    def be_only(i, cancel=False):
        x = _run(i, [_job("backend", i * 4000, i * 4000 + 1, i * 4000 + 20)], i * 4000)
        if cancel:
            x["jobs"][0]["conclusion"], x["conclusion"] = "cancelled", "cancelled"
        return x
    before = [bi(i, False) for i in range(40)] + [be_only(100 + i) for i in range(55)] + [be_only(200 + i, True) for i in range(35)]
    after = [bi(1000 + i, False, fast=True) for i in range(5)] + [bi(1100 + i, True) for i in range(35)] + [be_only(1200 + i) for i in range(90)]
    open(t + "/b2.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a2.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b2.jsonl", "--after", t + "/a2.jsonl", "--json",
             "--ran", "backend", "--job", "integration", "--end"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if ((not end_qualified(got, None, "_more_cancelled") and code_of(got) != "not_valid")
            or got.get("cancelled_job_workload") != "integration" or got.get("cancelled_after_job") != [35, 40]):
        bad.append("compare: cancellations where integration ran should qualify, named as integration's: %r %r %r"
                   % (code_of(got), got.get("cancelled_job_workload"), got.get("cancelled_after_job")))
    text = run([M, "compare", "--before", t + "/b2.jsonl", "--after", t + "/a2.jsonl",
                "--ran", "backend", "--job", "integration", "--end"]).stdout
    if "runs where integration ran: cancelled before 0 of 40, after 35 of 40" not in text:
        bad.append("compare: the cancelled counts should be printed under their own workload\n" + text)

# Reach among the runs that list the job: docs-only runs can't dilute it. Before, 36 runs ran
# backend then integration (6 fast, 30 slow); after, the 30 slow ones were cancelled in
# backend, integration listed but never run.
with tempfile.TemporaryDirectory() as t:
    def stage(i, slow, cancel=False):
        t0 = i * 4000
        be = _job("backend", t0, t0 + 1, t0 + (100 if slow else 10))
        end = mm.ts(be["completed_at"]) - 1793000000
        it = _job("integration", end, end + 1, end + 50)
        x = _run(i, [be, it], t0)
        if cancel:
            be["conclusion"], x["conclusion"] = "cancelled", "cancelled"
            it.update(conclusion="skipped", steps=[])
            it["started_at"] = None
        return x
    def docs(i, lists_integration):
        jobs = [_job("docs", i * 4000, i * 4000 + 1, i * 4000 + 5)]
        if lists_integration:  # a path filter's `if:` skipped it, nothing failed
            jobs.append(dict(_job("integration", i * 4000, i * 4000, i * 4000), conclusion="skipped", steps=[],
                             started_at=None))
        return _run(i, jobs, i * 4000)
    for lists in (False, True):
        before = [stage(i, i >= 6) for i in range(36)] + [docs(100 + i, lists) for i in range(94)]
        after = ([stage(1000 + i, False) for i in range(6)] + [stage(1100 + i, True, cancel=True) for i in range(30)]
                 + [docs(1200 + i, lists) for i in range(94)])
        open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
        open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
        r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--job", "integration", "--end"])
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        if (not end_qualified(got, "stopped") or not (got.get("reading_code") or "").startswith("faster")
                or got.get("not_reaching_after") != [30 + 94 * lists, 36 + 94 * lists] or got.get("not_reaching_before") != [94 * lists, 36 + 94 * lists]):
            bad.append("compare --job --end: runs stopped before the job should qualify (docs list it: %s): %r %r"
                       % (lists, code_of(got), got.get("not_reaching_after")))

# All green: a condition skips integration on the slow runs after. Of the runs that list it,
# more didn't run it, which qualifies the verdict. The same with a called workflow's job,
# where GitHub lists the skipped caller as one job.
with tempfile.TemporaryDirectory() as t:
    def cond(i, slow, skip, name="integration", caller=None):
        t0 = i * 4000
        be = _job("build", t0, t0 + 1, t0 + (100 if slow else 10))
        end = mm.ts(be["completed_at"]) - 1793000000
        if skip:
            it = dict(_job(caller or name, end, end, end), conclusion="skipped", steps=[], started_at=None)
        else:
            it = _job(name, end, end + 1, end + 11)
        return _run(i, [be, it], t0)
    for name, caller in (("integration", None), ("Python / integration", "Python")):
        before = [cond(i, i >= 6, False, name) for i in range(36)]
        after = [cond(1000 + i, False, False, name) for i in range(6)] + [
            cond(1100 + i, True, True, name, caller) for i in range(30)]
        open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
        open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
        r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--job", name, "--end"])
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        if not end_qualified(got, "listed" if caller else "listed by name") or got.get("not_reaching_after") != [30, 36]:
            bad.append("compare --job %s --end: a condition skipping it on the slow runs should qualify: %r %r"
                       % (name, code_of(got), got.get("not_reaching_after")))

# Four ways runs miss the timed job after the change; each must qualify a faster verdict.
#   moved:   12 failures a side, after rather than before the job (workflow failures unchanged);
#   leg:     a dynamic matrix leaves the postgres leg out of the slow runs (--ran backend);
#   nested:  a nested caller "CI / Python" is skipped, listed as one job;
#   docs:    94 docs runs list the job as skipped on both sides, and slow runs are cancelled upstream.
with tempfile.TemporaryDirectory() as t:
    def shaped(i, slow, miss, shape):
        t0 = i * 4000
        be = _job("backend", t0, t0 + 1, t0 + (100 if slow else 10))
        end = mm.ts(be["completed_at"]) - 1793000000
        target = {"leg": "integration (postgres)", "nested": "CI / Python / integration"}.get(shape, "integration")
        jobs = [be]
        if shape == "leg":
            jobs.append(_job("integration (sqlite)", end, end + 1, end + 11))
        if not miss:
            jobs.append(_job(target, end, end + 1, end + 11))
        elif shape == "nested":
            jobs.append(dict(_job("CI / Python", end, end, end), conclusion="skipped", steps=[], started_at=None))
        elif shape in ("moved", "docs"):
            be["conclusion"] = "failure" if shape == "moved" else "cancelled"
            jobs.append(dict(_job(target, end, end, end), conclusion="skipped", steps=[], started_at=None))
        x = _run(i, jobs, t0)
        if shape == "moved" and not miss and slow and i < 1000:
            # before: the slow runs fail after integration, as many as fail before it after
            jobs.append(dict(_job("report", end + 12, end + 13, end + 14), conclusion="failure"))
            x["conclusion"] = "failure"
        if miss and shape in ("moved", "docs"):
            x["conclusion"] = be["conclusion"]
        return x
    def docs_run(i):
        jobs = [_job("docs", i * 4000, i * 4000 + 1, i * 4000 + 5),
                dict(_job("integration", i * 4000, i * 4000, i * 4000), conclusion="skipped", steps=[], started_at=None)]
        return _run(i, jobs, i * 4000)
    for shape, extra in (("moved", []), ("leg", ["--ran", "backend"]), ("nested", []), ("docs", [])):
        target = {"leg": "integration (postgres)", "nested": "CI / Python / integration"}.get(shape, "integration")
        before = [shaped(i, i >= 6, False, shape) for i in range(36)]
        after = [shaped(1000 + i, False, False, shape) for i in range(6)] + [
            shaped(1100 + i, True, True, shape) for i in range(30)]
        if shape == "docs":
            before += [docs_run(5000 + i) for i in range(94)]
            after += [docs_run(6000 + i) for i in range(94)]
        open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
        open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
        r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--job", target, "--end"] + extra)
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        want = {"moved": "stopped", "leg": "ran", "nested": "listed", "docs": "stopped"}[shape]
        reading = got.get("reading_code") or ""
        # Never a bare faster reading; the intended check rose; with failures moved, the
        # workflow's failure count is the same on both sides.
        ok = (got.get("verdict_code") == "end_descriptive" and want in rose_checks(got)
              and (not reading.startswith("faster") or "_fewer_reached" in reading))
        if not ok or (shape == "moved" and got.get("failed_before") != got.get("failed_after")):
            bad.append("compare --job --end (%s): runs missing the job after should qualify through %s: %r %r %r %r"
                       % (shape, want, code_of(got), got.get("reading_code"), rose_checks(got),
                          (got.get("failed_before"), got.get("failed_after"))))

# --ran integration --job backend: backend's own time never changes, but integration stops running
# on the slow ones after, so the runs where both ran are the fast ones. The "job" check sees it.
with tempfile.TemporaryDirectory() as t:
    def bk(i, slow, integ):
        t0 = i * 4000
        jobs = [_job("backend", t0, t0 + 1, t0 + (100 if slow else 10))]
        if integ:
            end = mm.ts(jobs[0]["completed_at"]) - 1793000000
            jobs.append(_job("integration", end, end + 1, end + 11))
        return _run(i, jobs, t0)
    before = [bk(i, i >= 6, True) for i in range(36)]
    after = [bk(1000 + i, i >= 6, i < 6) for i in range(36)]
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json",
             "--ran", "integration", "--job", "backend"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if (not (code_of(got) or "").endswith("_fewer_reached") or "job" not in rose_checks(got)
            or got.get("verdict_code") != "ran_descriptive"):
        bad.append("compare --ran integration --job backend: the workload losing integration should qualify: %r %r"
                   % (code_of(got), rose_checks(got)))

# --ran's workload changes with the change, three ways, each with a whole-run or job verdict:
#   widened: a path filter runs preview on 36 faster pushes too (more reached it);
#   planner: a matrix planner fails on the slow pushes after, before the postgres leg is listed;
#   nested:  the direct row CI / Python / integration is skipped on the slow pushes, while 94 docs
#            runs list only the skipped caller CI / Python on both sides (only the by-name count sees it).
with tempfile.TemporaryDirectory() as t:
    def pushes(i, slow, has, kind):
        t0 = i * 4000
        be = _job("backend", t0, t0 + 1, t0 + (100 if slow else 10))
        end = mm.ts(be["completed_at"]) - 1793000000
        jobs = [be]
        if kind == "widened":
            if has:
                jobs.append(_job("preview", t0, t0 + 1, t0 + 5))
        elif kind == "planner":
            plan = _job("planner", t0, t0 + 1, t0 + 3)
            jobs.insert(0, plan)
            if has:
                jobs.append(_job("integration (postgres)", end, end + 1, end + 31))
            else:
                plan["conclusion"] = "failure"
        elif kind == "nested":
            jobs.append(_job("CI / Python / integration", end, end + 1, end + (91 if slow else 31)) if has else
                        dict(_job("CI / Python / integration", end, end, end), conclusion="skipped", steps=[], started_at=None))
        x = _run(i, jobs, t0)
        if kind == "planner" and not has:
            x["conclusion"] = "failure"
        return x
    def docs_parent(i):
        return _run(i, [_job("docs", i * 4000, i * 4000 + 1, i * 4000 + 5),
                        dict(_job("CI / Python", i * 4000, i * 4000, i * 4000), conclusion="skipped", steps=[],
                             started_at=None)], i * 4000)
    cases = {
        # before: preview on the 12 slow pushes only; after: on all 48 (36 fast ones too)
        "widened": ([pushes(i, True, True, "widened") for i in range(12)] + [pushes(100 + i, False, False, "widened") for i in range(36)],
                    [pushes(1000 + i, True, True, "widened") for i in range(12)] + [pushes(1100 + i, False, True, "widened") for i in range(36)],
                    ["--ran", "preview"], "more"),
        "planner": ([pushes(i, i >= 6, True, "planner") for i in range(36)] + [_run(200 + i, [_job("x", (200 + i) * 4000, (200 + i) * 4000 + 1, (200 + i) * 4000 + 2, conclusion="failure")], (200 + i) * 4000) for i in range(30)],
                    [pushes(1000 + i, False, True, "planner") for i in range(6)] + [pushes(1100 + i, True, False, "planner") for i in range(30)]
                    + [_run(1200 + i, [_job("x", (1200 + i) * 4000, (1200 + i) * 4000 + 1, (1200 + i) * 4000 + 2)], (1200 + i) * 4000) for i in range(30)],
                    ["--ran", "integration (postgres)"], "fewer"),
        "nested": ([pushes(i, i >= 6, True, "nested") for i in range(36)] + [docs_parent(300 + i) for i in range(94)],
                   [pushes(1000 + i, i >= 6, i < 6, "nested") for i in range(36)] + [docs_parent(1300 + i) for i in range(94)],
                   ["--ran", "backend", "--job", "CI / Python / integration"], "fewer"),
    }
    for kind, (before, after, extra, way) in cases.items():
        for x in before + after:
            x["conclusion"] = x.get("conclusion") or "success"
        open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
        open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
        r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json"] + extra)
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        code = code_of(got) or ""
        if kind == "nested":
            ok = (code.startswith("faster") and "_fewer_reached" in code
                  and got.get("fewer_reached_by") in ("listed", "listed by name"))
        else:
            ok = code.startswith("faster") and ("_%s_reached" % way) in code
        if kind in ("widened", "planner"):  # one widens, one shrinks: both reach wordings run
            head_ = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl"] + extra).stdout.splitlines()[:1]
            if head_ != ["measure: run (start to last job done), runs that ran job %s" % extra[1]]:
                bad.append("compare --ran: the heading should name the whole-run measure: %r" % head_)
        if not ok:
            bad.append("compare %s (%s): a changed workload passed for a speedup: %r %r %r\n%s"
                       % (" ".join(extra), kind, code, got.get("reach_checks"), got.get("failed_before"), r.stderr[-300:]))

# A matrix planner that fails before the postgres leg is listed: 12 failures a side, after the leg
# before the change and in the planner after. Only "missed with a failure" sees it; the job's own
# duration (--job, a verdict) must carry the qualification.
with tempfile.TemporaryDirectory() as t:
    def pl(i, slow, outcome):
        t0 = i * 4000
        plan = _job("planner", t0, t0 + 1, t0 + 3)
        jobs = [plan]
        if outcome == "planner_fails":
            plan["conclusion"] = "failure"
        else:
            jobs.append(_job("integration (postgres)", t0 + 3, t0 + 4, t0 + (94 if slow else 14)))
            if outcome == "fails_after":
                jobs.append(dict(_job("report", t0 + 95, t0 + 96, t0 + 97), conclusion="failure"))
        x = _run(i, jobs, t0)
        x["conclusion"] = "success" if outcome == "ok" else "failure"
        return x
    def green_docs(i):
        return _run(i, [_job("docs", i * 4000, i * 4000 + 1, i * 4000 + 5)], i * 4000)
    before = ([pl(i, False, "fails_after") for i in range(12)] + [pl(100 + i, False, "ok") for i in range(4)]
              + [pl(200 + i, True, "ok") for i in range(20)] + [green_docs(300 + i) for i in range(94)])
    after = ([pl(1000 + i, False, "ok") for i in range(24)] + [pl(1100 + i, True, "planner_fails") for i in range(12)]
             + [green_docs(1300 + i) for i in range(94)])
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json", "--job", "integration (postgres)"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if (got.get("failed_before") != got.get("failed_after")
            or got.get("fewer_reached_by") != ("all" if "all" in rose_checks(got) else "missed with a failure")
            or not (got.get("verdict_code") or "").startswith("faster")
            or ("_fewer_reached" if "all" in rose_checks(got) else "_missed_with_failure") not in got.get("verdict_code")):
        bad.append("compare --job: a planner failing before the leg should qualify through missed-with-a-failure: %r %r %r"
                   % (got.get("verdict_code"), got.get("fewer_reached_by"), (got.get("failed_before"), got.get("failed_after"))))
    # A run cancelled while queued (no jobs at all) also counts as missed with a failure.
    after2 = after[:24] + [dict(_run(1500 + i, [], (1500 + i) * 4000), conclusion="cancelled") for i in range(12)] + after[36:]
    open(t + "/a2.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after2))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a2.jsonl", "--json", "--job", "integration (postgres)"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    mwf = [x for x in got.get("reach_checks") or [] if x["check"] == "missed with a failure"]
    if not mwf or mwf[0]["missed_after"][0] != 12:
        bad.append("compare: a run cancelled before any job should count as missed with a failure: %r" % mwf)

# A canary allowed to fail runs on an experimental runner where it fails: on 12 fast pushes
# before, 12 slow ones after. Those runs aren't timed, but which runner the canary used still
# shows the mix changed, so the runner check must refuse.
with tempfile.TemporaryDirectory() as t:
    def canary(i, slow, fails):
        t0 = i * 4000
        jobs = [dict(_job("build", t0, t0 + 1, t0 + (100 if slow else 10)), labels=["self-hosted"])]
        c = dict(_job("canary", t0, t0 + 1, t0 + 5), labels=["self-hosted", "experimental"] if fails else ["self-hosted"])
        if fails:
            c["conclusion"] = "failure"
        jobs.append(c)
        return _run(i, jobs, t0)
    before = [canary(i, False, True) for i in range(12)] + [canary(100 + i, True, False) for i in range(24)]
    after = ([canary(1000 + i, False, False) for i in range(12)] + [canary(1100 + i, True, True) for i in range(12)]
             + [canary(1200 + i, True, False) for i in range(12)])
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--label", "self-hosted"])
    if r.returncode == 0:
        bad.append("compare: a canary on two runners, failing on different pushes, passed the runner check\n" + r.stdout)

# A short window under --ran: not enough runs stays the verdict, and its timings stay hidden.
with tempfile.TemporaryDirectory() as t:
    open(t + "/b.jsonl", "w").write("".join(json.dumps(_work(i, True)) + "\n" for i in range(4)))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(_work(100 + i, True, integ=10)) + "\n" for i in range(4)))
    got = json.loads(run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--json",
                          "--ran", "integration"]).stdout or "{}")
    if got.get("verdict_code") != "not_enough_runs" or got.get("before_median") is not None or got.get("after_median") is not None:
        bad.append("compare --ran: a short window must stay not_enough_runs with hidden timings: %r %r %r"
                   % (got.get("verdict_code"), got.get("before_median"), got.get("after_median")))
# A runner pool only failed runs used, without --label: the labels differ, so it refuses.
with tempfile.TemporaryDirectory() as t:
    def smoke(i, slow, fails, pool):
        t0 = i * 4000
        x = _run(i, [_job("build", t0, t0 + 1, t0 + (100 if slow else 10)),
                     dict(_job("smoke", t0, t0 + 1, t0 + 5), labels=[pool],
                          conclusion="failure" if fails else "success")], t0)
        x["conclusion"] = "failure" if fails else "success"
        return x
    before = [smoke(i, False, True, "ubuntu-latest") for i in range(12)] + [smoke(100 + i, True, False, "ubuntu-latest") for i in range(24)]
    after = ([smoke(1000 + i, False, False, "ubuntu-latest") for i in range(12)] + [smoke(1100 + i, True, True, "new-pool") for i in range(12)]
             + [smoke(1200 + i, True, False, "ubuntu-latest") for i in range(12)])
    open(t + "/b.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in before))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in after))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl"])
    if r.returncode == 0 or "runner labels differ" not in r.stderr:
        bad.append("compare: a pool only failed runs used should refuse without --label\n" + r.stdout + r.stderr)

# Runner-minutes: two matrix legs with one name, same seconds, in one attempt are two executions.
two = _run(0, [_job("Test", 0, 1, 61), dict(_job("Test", 0, 1, 61), id=5)], 0)
if mm.run_minutes(two) != 2 or abs(mm.run_minutes(two, True) - 2.0) > 1e-9:
    bad.append("run_minutes: same-name legs in one attempt are two executions: %r" % mm.run_minutes(two))


# Steps side by side: detected by intervals, and the job's parts are elapsed time.
def _job_steps(spans, end):
    return {"created_at": _at(0), "started_at": _at(0), "completed_at": _at(end), "name": "j",
            "steps": [{"name": n, "started_at": _at(a), "completed_at": _at(b)} for n, a, b in spans]}
if mm.overlap_seconds(_job_steps([("a", 0, 50), ("b", 20, 60)], 120)) != 30:
    bad.append("overlap_seconds: 0-50 and 20-60 overlap for 30 s")
if mm.overlap_seconds(_job_steps([("a", 0, 50), ("b", 50, 60), ("c", 60, 61)], 120)) != 0:
    bad.append("overlap_seconds: steps one after another don't overlap")
if mm.overlap_seconds(_job_steps([("a", 0, 60), ("b", 10, 30), ("c", 20, 40)], 120)) != 30:
    bad.append("overlap_seconds: a three-way overlap counts once")
got = mm.job_split(_job_steps([("Set up job", 0, 2), ("a", 2, 60), ("b", 2, 60)], 60))
if got["running"] != 58 or got["setup"] != 2 or got["other"] != 0:
    bad.append("job_split: parallel steps must count elapsed time, not their sum: %r" % got)

# Running wins over setup where they overlap: a cache restore beside the tests is test time.
got = mm.job_split(_job_steps([("Set up job", 0, 2), ("Restore cache", 2, 40), ("Test", 2, 60)], 60))
if got["running"] != 58 or got["setup"] != 2:
    bad.append("job_split: running should win where it overlaps setup: %r" % got)

# Gates: a long job whose one step has a setup word, or a step with no times, is never a gate.
for steps, label in (([("Set up job", 2), ("Install and run e2e tests", 600)], "a setup word"),):
    ch = [_steps_job("work", 0, 1, [("Set up job", 1), ("Test", 100)]), _steps_job("e2e", 102, 103, steps)]
    if mm.tail_gates(_run(0, ch, 0), ch)[0]:
        bad.append("tail_gates: a job with %s was taken for a gate" % label)
ch = [_steps_job("work", 0, 1, [("Test", 100)]), _steps_job("e2e", 102, 103, [("Run", 120)])]
ch[1]["steps"][0]["completed_at"] = None
if mm.tail_gates(_run(0, ch, 0), ch)[0]:
    bad.append("tail_gates: a job with an untimed step was taken for a gate")
with tempfile.TemporaryDirectory() as t:
    x = _run(0, [_job("build", 0, 1, 100)], 0)
    x["jobs"][0]["steps"] = []
    open(t + "/s.jsonl", "w").write(json.dumps(x) + "\n")
    r = run([M, "split", "--in", t + "/s.jsonl"])
    if r.returncode != 0:
        bad.append("split: a last job with no steps listed crashed the text\n" + r.stderr[-800:])

# Offline reading: a listing and jobs saved at different attempts are named; a run GitHub lists
# no jobs for (startup failure on a rerun, a fork run waiting for approval) is read whole from
# its empty, named page; a short jobs page is named; a job without run_id is refused.
with tempfile.TemporaryDirectory() as t:
    src = [json.loads(l) for l in open(E + "/ci-diagnose/repo/ci-history/runs.jsonl") if l.strip()][:30]
    recs = copy.deepcopy(src)
    recs[0]["run_attempt"] = 2                                     # listing says 2, jobs are attempt 1
    recs[1]["conclusion"], recs[1]["run_attempt"], recs[1]["jobs"] = "startup_failure", 2, []
    recs[2]["conclusion"], recs[2]["jobs"] = "action_required", []
    _save_dir(t + "/d", recs)
    r = run([M, "split", "--runs-dir", t + "/d", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if ("listing says attempt 2" not in r.stderr or got.get("runs") != 29 or str(recs[1]["id"]) in r.stderr
            or str(recs[2]["id"]) in r.stderr):
        bad.append("split --runs-dir: attempts and empty job pages misread (%r runs)\n%s" % (got.get("runs"), r.stderr))
    short = copy.deepcopy(src[:3])
    _save_dir(t + "/s", short)
    p_ = t + "/s/jobs-%d.json" % short[0]["id"]
    pages = mm.json_values(open(p_).read())
    flat = [x for v in pages for x in (v if isinstance(v, list) else [v])]
    open(p_, "w").write(json.dumps(flat[:1]))                       # the second page lost
    r = run([M, "split", "--runs-dir", t + "/s", "--json"])
    if "jobs saved" not in r.stderr:
        bad.append("split --runs-dir: a run with a jobs page missing should be named\n" + r.stderr)
    open(t + "/s/bad.json", "w").write(json.dumps({"total_count": 1, "jobs": [{"id": 1}]}))
    r = run([M, "split", "--runs-dir", t + "/s"])
    if r.returncode == 0 or "without run_id" not in r.stderr:
        bad.append("split --runs-dir: a job without run_id should be refused by name\n" + r.stderr)
# flaky also starts no process with a folder of saved answers
with tempfile.TemporaryDirectory() as t:
    recs = [json.loads(l) for l in open(E + "/ci-diagnose/repo/ci-history/runs.jsonl") if l.strip()][:5]
    _save_dir(t + "/d", recs)
    os.makedirs(t + "/rep/%d" % recs[0]["id"])
    open(t + "/rep/%d/failed.txt" % recs[0]["id"], "w").write("T\n")
    r = subprocess.run([sys.executable, "-c", NO_PROCESS, M, "flaky", "--runs-dir", t + "/d", "--reports", t + "/rep"],
                       capture_output=True, text=True)
    if r.returncode != 0 or "PROCESS" in r.stderr or ":: T" not in r.stdout:
        bad.append("flaky --runs-dir: should read failed.txt and start no process\n" + r.stdout + r.stderr[-1500:])


# flaky, the evidence: per workflow file and base; empty folders aren't evidence; a report of a
# run not read stops it; artifact folders by id don't change a test's name; a retry that passed
# is a failure; an XML that isn't JUnit is named and skipped.
def _flaky_rows(rows, reports, *extra):
    with tempfile.TemporaryDirectory() as t:
        open(t + "/runs.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in rows))
        os.makedirs(t + "/rep")
        for rid, files in reports.items():
            for rel, text in files.items():
                os.makedirs(os.path.dirname(t + "/rep/%d/%s" % (rid, rel)), exist_ok=True)
                open(t + "/rep/%d/%s" % (rid, rel), "w").write(text)
        r = run([M, "flaky", "--in", t + "/runs.jsonl", "--reports", t + "/rep", "--json"] + list(extra))
        return (json.loads(r.stdout) if r.returncode == 0 else None), r


def _rep(status, retried=False):
    inner = "<failure/>" if status == "f" else ("<flakyFailure/>" if retried else "")
    return ('<testsuite name="s"><testcase classname="c" name="T">%s</testcase></testsuite>' % inner)


def _fr(i, pr, ok, base="main", path=".github/workflows/ci.yml", event="pull_request"):
    x = _run(i, [_job("test", i * 100, i * 100 + 2, i * 100 + 50)], i * 100)
    x.update(pull_requests=[pr] if event == "pull_request" else [], conclusion="success" if ok else "failure",
             pull_request_bases=[base], path=path, event=event, head_branch="b%d" % pr)
    return x


# A release branch broken for three of its pull requests, main's passing between them.
rows, reps = [], {}
for i, (pr, base, st) in enumerate([(1, "main", "p"), (10, "release", "p"), (2, "main", "p"), (10, "release", "f"),
                                    (3, "main", "p"), (11, "release", "f"), (4, "main", "p"), (12, "release", "f"),
                                    (5, "main", "p"), (13, "release", "p")]):
    rows.append(_fr(i, pr, st == "p", base))
    reps[rows[-1]["id"]] = {"r.xml": _rep(st)}
got, r = _flaky_rows(rows, reps)
t_ = [x for x in (got or {"tests": []})["tests"] if x["test"].endswith("T")]
if not t_ or t_[0]["recurring"] or t_[0]["alone_on_pull_requests"] != 0:
    bad.append("flaky: a broken release branch was taken for a recurring flake: %r\n%s" % (t_, r.stderr))
# An empty folder for an unread failed run isn't evidence: it stays unread.
rows = [_fr(0, 1, True), _fr(1, 2, False), _fr(2, 3, False), _fr(3, 4, True)]
reps = {rows[0]["id"]: {"r.xml": _rep("p")}, rows[1]["id"]: {"r.xml": _rep("f")}, rows[3]["id"]: {"r.xml": _rep("p")}}
base_got, _ = _flaky_rows(rows, reps)
os_got, r = _flaky_rows(rows, dict(list(reps.items()) + [(rows[2]["id"], {"sub/.keep": ""})]))
if not base_got or not os_got or base_got["tests"][0]["alone_on_pull_requests"] != 0 \
        or os_got["tests"][0]["alone_on_pull_requests"] != 0:
    bad.append("flaky: an empty report folder turned an unread failed run into evidence\n" + r.stderr)
# A report of a run not read stops it.
got, r = _flaky_rows(rows[:2], dict(list(reps.items())[:2] + [(999999, {"r.xml": _rep("f")})]))
if got is not None or "isn't among the finished runs" not in r.stderr:
    bad.append("flaky: a report of a run not read should stop it\n" + r.stderr)
# Artifact folders by id, a retry that passed, and an XML that isn't JUnit.
rows = [_fr(i, i + 1, True) for i in range(5)]
reps = {rows[0]["id"]: {"410/junit.xml": _rep("p")}, rows[1]["id"]: {"411/junit.xml": _rep("p", retried=True),
                                                                      "411/coverage.xml": "<coverage/>"},
        rows[2]["id"]: {"412/junit.xml": _rep("p")}, rows[3]["id"]: {"413/attempt-2/junit.xml": _rep("p", True)},
        rows[4]["id"]: {"414/junit.xml": _rep("p")}}
got, r = _flaky_rows(rows, reps)
t_ = (got or {"tests": []})["tests"]
if (len(t_) != 1 or t_[0]["failed_runs"] != 2 or t_[0]["alone_on_pull_requests"] != 2
        or not any("coverage.xml" in x for x in got["xml_not_junit"])):
    bad.append("flaky: artifact folders, retries or a non-JUnit XML misread: %r\n%s" % (got, r.stderr))
# The same broken release branch read with no bases recorded (saved answers of closed pull
# requests): each unplaced pull request is lined up alone, so none stands alone.
rows, reps = [], {}
for i, (pr, base, st) in enumerate([(1, "main", "p"), (10, "release", "p"), (2, "main", "p"), (10, "release", "f"),
                                    (3, "main", "p"), (11, "release", "f"), (4, "main", "p"), (12, "release", "f"),
                                    (5, "main", "p"), (13, "release", "p")]):
    rows.append(_fr(i, pr, st == "p", base))
    rows[-1]["pull_request_bases"] = []
    reps[rows[-1]["id"]] = {"r.xml": _rep(st)}
got, r = _flaky_rows(rows, reps)
t_ = [x for x in (got or {"tests": []})["tests"] if x["test"].endswith("T")]
if not t_ or t_[0]["recurring"] or t_[0]["alone_on_pull_requests"] != 0 or got.get("runs_without_base") != 10:
    bad.append("flaky: runs with no base recorded were lined up across bases: %r\n%s" % (t_, r.stderr))
# Two workflow files with one display name keep their own lines.
rows = [_fr(0, 1, True, path="a.yml"), _fr(1, 2, False, path="b.yml"), _fr(2, 3, True, path="a.yml")]
reps = {x["id"]: {"r.xml": _rep("p" if x["conclusion"] == "success" else "f")} for x in rows}
got, r = _flaky_rows(rows, reps)
if not got or got["tests"][0]["alone_on_pull_requests"] != 0:
    bad.append("flaky: another workflow file's passes stood around a failure: %r" % got)


# ---- second review round (Codex Astra on 3bb89c11)

# --job --end reads the jobs before it on the run's clock: a faster runner for them isn't a speedup.
with tempfile.TemporaryDirectory() as t:
    def pair(i, fast):
        t0 = i * 4000
        bj = _job("build", t0, t0 + 2, t0 + (20 if fast else 200))
        if fast:
            bj["labels"] = ["big-runner"]
        end = mm.ts(bj["completed_at"]) - 1793000000
        return _run(i, [bj, _job("required", end, end + 1, end + 2)], t0)
    open(t + "/b.jsonl", "w").write("".join(json.dumps(pair(i, False)) + "\n" for i in range(5)))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(pair(100 + i, True)) + "\n" for i in range(5)))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--job", "required", "--end",
             "--label", "ubuntu-latest"])
    if r.returncode == 0:
        bad.append("compare --end: jobs before the timed one moved to another runner, and it passed\n" + r.stdout)
    # Cancelled runs are counted on each side.
    rows = [_work(200 + i, True) for i in range(5)] + [dict(_work(300 + i, True), conclusion="cancelled") for i in range(3)]
    open(t + "/c.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in rows))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/c.jsonl", "--job", "build", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    if got.get("cancelled_after") != [3, 8] or got.get("cancelled_before") != [0, 5]:
        bad.append("compare: cancelled runs should be counted a side: %r %r" % (got.get("cancelled_before"), got.get("cancelled_after")))

# --end: a job before the timed one moved to a pool another job already used; and a build
# queued beside the timed job on a one-slot pool, held the slot first in most runs before.
with tempfile.TemporaryDirectory() as t:
    def pooled(i, fast):
        t0 = i * 4000
        lint = _job("lint", t0, t0 + 1, t0 + 6)
        lint["labels"] = ["big-runner"]
        bj = _job("build", t0, t0 + 2, t0 + (20 if fast else 200))
        if fast:
            bj["labels"] = ["big-runner"]
        end = mm.ts(bj["completed_at"]) - 1793000000
        return _run(i, [lint, bj, _job("required", end, end + 1, end + 2)], t0)
    open(t + "/b.jsonl", "w").write("".join(json.dumps(pooled(i, False)) + "\n" for i in range(10)))
    open(t + "/a.jsonl", "w").write("".join(json.dumps(pooled(100 + i, True)) + "\n" for i in range(10)))
    r = run([M, "compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--job", "required", "--end",
             "--label", "ubuntu-latest"])
    if r.returncode == 0:
        bad.append("compare --end: a job before it changed runner, and it passed\n" + r.stdout)

    def slot(i, build_first, has_build=True):
        t0 = i * 4000
        jobs = []
        if has_build:
            jobs.append(_job("build", t0, t0 + 1, t0 + 181))
        start = t0 + (181 if build_first else 1)
        jobs.append(_job("required", t0, start, start + 19))
        return _run(i, jobs, t0)
    open(t + "/b2.jsonl", "w").write("".join(json.dumps(slot(i, i < 9, has_build=i < 9)) + "\n" for i in range(10)))
    open(t + "/a2.jsonl", "w").write("".join(json.dumps(slot(100 + i, i < 1, has_build=i < 1)) + "\n" for i in range(10)))
    r = run([M, "compare", "--before", t + "/b2.jsonl", "--after", t + "/a2.jsonl", "--job", "required", "--end"])
    if r.returncode == 0:
        bad.append("compare --end: work that held the slot before the timed job was left out\n" + r.stdout)

    # A larger share cancelled after qualifies a faster verdict.
    # A share cancelled after that rose beyond chance (0 of 10 before, 15 of 20 after) qualifies
    # a faster verdict; one more cancelled run (1 of 11) doesn't.
    fast = [_work(300 + i, True, integ=10) for i in range(5)]
    open(t + "/b3.jsonl", "w").write("".join(json.dumps(_work(200 + i, True)) + "\n" for i in range(10)))
    for n_gone, want in ((15, "faster_more_cancelled"), (1, "faster")):
        gone = [dict(_work(400 + i, True), conclusion="cancelled") for i in range(n_gone)]
        open(t + "/a3.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in fast + gone))
        r = run([M, "compare", "--before", t + "/b3.jsonl", "--after", t + "/a3.jsonl", "--json"])
        got = json.loads(r.stdout) if r.returncode == 0 else {}
        if code_of(got) != want:
            bad.append("compare: %d cancelled after should give %s: %r\n%s" % (n_gone, want, code_of(got), r.stderr))

# Steps: a stamp past the job's end is clipped; a zero-length step overlaps nothing; a step of the
# repository's named "Post results" is work, so its job is no gate.
got = mm.job_split(_job_steps([("Test", 0, 70)], 60))
if got["running"] != 60:
    bad.append("job_split: a step's time must be clipped to its job: %r" % got)
if mm.overlap_seconds(_job_steps([("a", 0, 60), ("b", 20, 20)], 60)):
    bad.append("overlap_seconds: a zero-length step overlaps nothing")
ch = [_steps_job("work", 0, 1, [("Test", 100)]), _steps_job("report", 102, 103, [("Set up job", 1), ("Post results", 120)])]
if mm.tail_gates(_run(0, ch, 0), ch)[0]:
    bad.append("tail_gates: a 120 s step named Post results was taken for runner cleanup")
ch = [_steps_job("work", 0, 1, [("Test", 100)]),
      _steps_job("gate", 102, 103, [("Set up job", 1), ("Run actions/checkout@v4", 2), ("Check", 1),
                                     ("Post Run actions/checkout@v4", 3), ("Complete job", 0)])]
if [j["name"] for j in mm.tail_gates(_run(0, ch, 0), ch)[0]] != ["gate"]:
    bad.append("tail_gates: an action's own post step should be the runner's")

# Offline: an empty page whose count says jobs are missing is named; a rerun that failed to start
# keeps its first attempt's jobs.
with tempfile.TemporaryDirectory() as t:
    recs = [json.loads(l) for l in open(E + "/ci-diagnose/repo/ci-history/runs.jsonl") if l.strip()][:30]
    recs = copy.deepcopy(recs)
    recs[0]["jobs"] = []
    recs[1]["conclusion"], recs[1]["run_attempt"] = "startup_failure", 2
    _save_dir(t + "/d", recs)
    open(t + "/d/jobs-%d.json" % recs[0]["id"], "w").write(json.dumps({"total_count": 7, "jobs": []}))
    r = run([M, "split", "--runs-dir", t + "/d", "--json"])
    if "0 of its 7 jobs saved" not in r.stderr or str(recs[1]["id"]) in r.stderr:
        bad.append("split --runs-dir: an empty page counting 7 jobs, or a failed restart, misread\n" + r.stderr)

# flaky: a failed run whose report doesn't show the test is unknown, not a pass; branches pushed
# aren't pull requests; --short refuses names it can't tell apart; a run with no jobs page saved
# still lines up.
rows = [_fr(0, 1, True), _fr(1, 2, False), _fr(2, 3, False), _fr(3, 4, True)]
reps = {rows[0]["id"]: {"r.xml": _rep("p")}, rows[1]["id"]: {"r.xml": _rep("f")},
        rows[2]["id"]: {"failed.txt": "U\n"}, rows[3]["id"]: {"r.xml": _rep("p")}}
got, r = _flaky_rows(rows, reps)
t_ = [x for x in (got or {"tests": []})["tests"] if x["test"].endswith("T")]
if not t_ or t_[0]["alone_on_pull_requests"] != 0:
    bad.append("flaky: a failed run whose report doesn't show the test was taken as evidence: %r" % t_)
rows, reps = [], {}
for i, (b_, st) in enumerate([(b, x) for b in (1, 2, 3) for x in "pfp"]):
    x = _fr(i, b_, st == "p", event="push")
    rows.append(x)
    reps[x["id"]] = {"r.xml": _rep(st)}
got, r = _flaky_rows(rows, reps)
t_ = (got or {"tests": [{}]})["tests"][0]
if t_.get("recurring") or t_.get("alone_on_pull_requests") != 0 or t_.get("alone_on_other_branches") != 3:
    bad.append("flaky: pushed branches were counted as pull requests: %r" % t_)
# Closed pull requests as fetch saves them (no numbers, the base recorded) are pull requests: a
# flake standing alone on three of them recurs. With no base recorded, a pull request's own
# pass, fail, pass on its own line never stands alone.
rows, reps = [], {}
for i, (pr, st) in enumerate([(1, "p"), (2, "f"), (3, "p"), (4, "f"), (5, "p"), (6, "f"), (7, "p")]):
    x = _fr(i, pr, st == "p")
    x["pull_requests"] = []
    rows.append(x)
    reps[x["id"]] = {"r.xml": _rep(st)}
got, r = _flaky_rows(rows, reps)
t_ = (got or {"tests": [{}]})["tests"][0]
if not t_.get("recurring") or t_.get("alone_on_pull_requests") != 3:
    bad.append("flaky: closed pull requests (no numbers) weren't counted as pull requests: %r" % t_)
rows, reps = [], {}
for i, (pr, st) in enumerate([(p_, x) for p_ in (1, 2, 3) for x in "pfp"]):
    x = _fr(i, pr, st == "p")
    x["pull_request_bases"] = []
    rows.append(x)
    reps[x["id"]] = {"r.xml": _rep(st)}
got, r = _flaky_rows(rows, reps)
t_ = (got or {"tests": [{}]})["tests"][0]
if t_.get("recurring") or t_.get("alone_on_pull_requests") != 0:
    bad.append("flaky: a pull request with no base stood alone on its own passes: %r" % t_)
# --short over every report: T of Unit passing and T of Integration failing, in separate reports,
# can't be matched by the short name.
rows = [_fr(i, i + 1, i % 2 == 0) for i in range(5)]
unit = '<testsuite name="s"><testcase classname="Unit" name="T"/></testsuite>'
integ = '<testsuite name="s"><testcase classname="Integration" name="T"><failure/></testcase></testsuite>'
reps = {x["id"]: {"u.xml": unit} if x["conclusion"] == "success" else {"i.xml": integ} for x in rows}
got, r = _flaky_rows(rows, reps, "--short")
if got is not None or "can't tell apart" not in r.stderr:
    bad.append("flaky --short: one short name over two classes in separate reports should stop it\n" + r.stdout)
# --short accepts one test in several matrix legs and in per-run report file names.
rows = [_fr(i, i + 1, i % 2 == 0) for i in range(7)]
reps = {}
for x in rows:
    st = "p" if x["conclusion"] == "success" else "f"
    reps[x["id"]] = {"junit-linux/results-%d.xml" % x["id"]: _rep(st), "junit-windows/results-%d.xml" % x["id"]: _rep("p")}
got, r = _flaky_rows(rows, reps, "--short")
if got is None:
    bad.append("flaky --short: one test in two matrix legs was refused\n" + r.stderr)
got, r = _flaky_rows(rows, reps)
t_ = [x for x in (got or {"tests": []})["tests"] if "junit-linux" in x["test"]]
if not t_ or t_[0]["alone_on_pull_requests"] != 3:
    bad.append("flaky: per-run report file names should not split a test: %r" % (got or {}).get("tests"))
# A rerun's passing report doesn't separate: the failed attempt's report may be missing.
rows = [_fr(0, 1, True), _fr(1, 2, False), _fr(2, 3, True), _fr(3, 4, True)]
rows[2]["run_attempt"] = 2
reps = {rows[0]["id"]: {"r.xml": _rep("p")}, rows[1]["id"]: {"r.xml": _rep("f")},
        rows[2]["id"]: {"attempt-2/r.xml": _rep("p")}, rows[3]["id"]: {"r.xml": _rep("p")}}
got, r = _flaky_rows(rows, reps)
if not got or got["tests"][0]["alone_on_pull_requests"] != 0:
    bad.append("flaky: a rerun's passing report was taken as a pass around a failure: %r" % got)
# A single-attempt run that failed on another test, with T passing, still separates T's failures.
rows, reps = [], {}
for i, st in enumerate("pfpfpfp"):
    x = _fr(i, i + 1, False)  # every run failed: on U where T passed
    rows.append(x)
    reps[x["id"]] = {"r.xml": '<testsuite name="s"><testcase classname="c" name="T">%s</testcase>'
                              '<testcase classname="c" name="U">%s</testcase></testsuite>'
                              % ("<failure/>" if st == "f" else "", "" if st == "f" else "<failure/>")}
got, r = _flaky_rows(rows, reps)
t_ = [x for x in (got or {"tests": []})["tests"] if x["test"].endswith("::T")]
if not t_ or t_[0]["alone_on_pull_requests"] != 3:
    bad.append("flaky: a failed run showing T passing should separate T's failures: %r" % t_)
# --short keeps the leg: T passing on Linux never separates T's failures on Windows.
rows, reps = [], {}
for i in range(7):
    x = _fr(i, i + 1, i % 2 == 0)
    rows.append(x)
    leg = "junit-linux" if i % 2 == 0 else "junit-windows"
    reps[x["id"]] = {"%s/r.xml" % leg: _rep("p" if i % 2 == 0 else "f")}
got, r = _flaky_rows(rows, reps, "--short")
if not got or any(x["alone_on_pull_requests"] for x in got["tests"]):
    bad.append("flaky --short: a pass in another leg separated failures: %r\n%s" % (got, r.stderr))
# failed.txt in a shard folder matches its JUnit test (both shard-blanked); a failed.txt at the
# run's root beside a leg's reports is named as matching nothing.
rows, reps = [], {}
for i in range(7):
    x = _fr(i, i + 1, i % 2 == 0)
    rows.append(x)
    reps[x["id"]] = ({"tests-shard-%d/r.xml" % (i % 3): _rep("p")} if i % 2 == 0
                     else {"tests-shard-%d/failed.txt" % (i % 3): "T\n"})
got, r = _flaky_rows(rows, reps, "--short")
if not got or [x["alone_on_pull_requests"] for x in got["tests"]] != [3]:
    bad.append("flaky: failed.txt in a shard folder should match its JUnit test: %r\n%s" % (got, r.stderr))
reps = {x["id"]: ({"test-results/r.xml": _rep("p")} if i % 2 == 0 else {"failed.txt": "T\n"})
        for i, x in enumerate(rows)}
got, r = _flaky_rows(rows, reps, "--short")
if not got or got.get("failed_txt_names_no_report_shows") != ["T"]:
    bad.append("flaky: a failed.txt name no report shows should be named: %r" % (got,))
# The unmatched-name note is per workflow: workflow A's JUnit says nothing of workflow B's failed.txt.
rows, reps = [], {}
for i in range(4):
    x = _fr(i, i + 1, i % 2 == 0, path="a.yml" if i % 2 == 0 else "b.yml")
    rows.append(x)
    reps[x["id"]] = ({"r.xml": _rep("p")} if i % 2 == 0 else
                     {"failed.txt": "s::c::T\n", "u.xml": '<testsuite name="s"><testcase classname="c" name="U"/></testsuite>'})
got, r = _flaky_rows(rows, reps)
if not got or got.get("failed_txt_names_no_report_shows") != ["s::c::T"]:
    bad.append("flaky: another workflow's JUnit hid an unmatched failed.txt name: %r" % (got or {}).get("failed_txt_names_no_report_shows"))
# --short tells legs apart: posix.T on Linux and win.T on Windows are two short names.
rows = [_fr(i, i + 1, True) for i in range(2)]
reps = {rows[0]["id"]: {"linux/r.xml": '<testsuite name="s"><testcase classname="posix" name="T"/></testsuite>',
                        "windows/r.xml": '<testsuite name="s"><testcase classname="win" name="T"/></testsuite>'},
        rows[1]["id"]: {"linux/r.xml": '<testsuite name="s"><testcase classname="posix" name="T"/></testsuite>'}}
got, r = _flaky_rows(rows, reps, "--short")
if got is None:
    bad.append("flaky --short: tests in two legs with one name were refused\n" + r.stderr)
# --short is per workflow: c.T in a.yml and other.T in b.yml are fine.
rows = [_fr(0, 1, True, path="a.yml"), _fr(1, 2, True, path="b.yml")]
got, r = _flaky_rows(rows, {rows[0]["id"]: {"r.xml": '<testsuite name="s"><testcase classname="c" name="T"/></testsuite>'},
                            rows[1]["id"]: {"r.xml": '<testsuite name="s"><testcase classname="other" name="T"/></testsuite>'}},
                     "--short")
if got is None:
    bad.append("flaky --short: one name in two workflows was refused\n" + r.stderr)
# A workflow with failed.txt and no JUnit is named: it shows no pass to stand failures between.
rows = [_fr(0, 1, True, path="a.yml"), _fr(1, 2, False, path="b.yml")]
got, r = _flaky_rows(rows, {rows[0]["id"]: {"r.xml": _rep("p")}, rows[1]["id"]: {"failed.txt": "T\n"}})
if not got or got.get("workflows_with_no_junit_pass_evidence") != ["b.yml"]:
    bad.append("flaky: a workflow with failed.txt only should be named: %r" % (got,))
# --short counts a skipped namesake: Unit.T passed and Integration.T skipped in one report.
rows = [_fr(0, 1, True), _fr(1, 2, False)]
both = ('<testsuite name="s"><testcase classname="Unit" name="T"/>'
        '<testcase classname="Integration" name="T"><skipped/></testcase></testsuite>')
got, r = _flaky_rows(rows, {rows[0]["id"]: {"r.xml": both}, rows[1]["id"]: {"failed.txt": "T\n"}}, "--short")
if got is not None or "can't tell apart" not in r.stderr:
    bad.append("flaky --short: a skipped namesake should make the short name ambiguous\n" + r.stdout)
# A run whose first attempt failed, rerun green, with no report: unknown, not a pass.
rows = [_fr(0, 1, True), _fr(1, 2, False), _fr(2, 3, True), _fr(3, 4, True)]
rows[2]["run_attempt"] = 2
reps = {rows[0]["id"]: {"r.xml": _rep("p")}, rows[1]["id"]: {"r.xml": _rep("f")}, rows[3]["id"]: {"r.xml": _rep("p")}}
got, r = _flaky_rows(rows, reps)
if not got or got["tests"][0]["alone_on_pull_requests"] != 0:
    bad.append("flaky: a rerun run with no report was taken as evidence: %r" % got)
two_classes = ('<testsuite name="s"><testcase classname="a" name="T"><failure/></testcase>'
               '<testcase classname="b" name="T"/></testsuite>')
rows = [_fr(0, 1, False)]
got, r = _flaky_rows(rows, {rows[0]["id"]: {"r.xml": two_classes}}, "--short")
if got is not None or "can't tell apart" not in r.stderr:
    bad.append("flaky --short: names it can't tell apart should stop it\n" + r.stderr)
with tempfile.TemporaryDirectory() as t:
    recs = [_fr(0, 1, True), _fr(1, 2, False), _fr(2, 3, False), _fr(3, 4, True)]
    _save_dir(t + "/d", recs)
    os.remove(t + "/d/jobs-%d.json" % recs[2]["id"])   # its jobs page not saved: still a failed run in line
    os.makedirs(t + "/rep")
    for x, st in ((recs[0], "p"), (recs[1], "f"), (recs[3], "p")):
        os.makedirs(t + "/rep/%d" % x["id"])
        open(t + "/rep/%d/r.xml" % x["id"], "w").write(_rep(st))
    r = run([M, "flaky", "--runs-dir", t + "/d", "--reports", t + "/rep", "--json"])
    got = json.loads(r.stdout) if r.returncode == 0 else {"tests": [{}]}
    if got["tests"][0].get("alone_on_pull_requests") != 0:
        bad.append("flaky --runs-dir: a run with no jobs page dropped out of the line: %r\n%s" % (got, r.stderr))



# split: workflows by file (#7), pull_request_target (#14), mixed headline groups (#23),
# steps clipped to their job and overlap by how much (#35).
def _split(t, rows, *flags):
    open(t + "/runs.jsonl", "w").write("".join(json.dumps(x) + "\n" for x in rows))
    r = run([M, "split", "--in", t + "/runs.jsonl"] + list(flags))
    return r


with tempfile.TemporaryDirectory() as t:
    # #7: a.yml and b.yml are both named CI; b fails. With a passing Lint, the commit didn't pass.
    rows = []
    for k, (path, name, ok) in enumerate((("a.yml", "CI", True), ("b.yml", "CI", False), ("lint.yml", "Lint", True))):
        x = _run(k, [_job("test", 100 * k, 100 * k + 1, 100 * k + 60, conclusion="success" if ok else "failure")],
                 100 * k, name=name)
        x.update(path=".github/workflows/" + path, conclusion="success" if ok else "failure",
                 head_sha="%040d" % 7, pull_requests=[7], head_branch="b7")
        rows.append(x)
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    if got.get("wait_all_workflows_commits") != 0 or len(got.get("workflows") or []) != 3:
        bad.append("split #7: two files named CI, one failing, counted as a passing commit: %r %r"
                   % (got.get("wait_all_workflows_commits"), got.get("workflows")))
    # #7: a commit with a run that names no workflow file is left out, not counted as two workflows.
    rows2 = copy.deepcopy(rows[:1]) + copy.deepcopy(rows[:1])
    rows2[1].update(id=rows2[1]["id"] + 50, created_at=_at(3600), run_started_at=_at(3600))
    del rows2[1]["path"]
    got = json.loads(_split(t, rows2, "--json").stdout or "{}")
    if got.get("wait_all_workflows_commits") != 0 or got.get("wait_all_workflows_unplaced_commits") != 1 \
            or len(got.get("workflows") or []) != 1 or "1 commits left out" not in _split(t, rows2).stdout:
        bad.append("split #7: a run with no workflow file made a second workflow: %r %r"
                   % (got.get("wait_all_workflows_commits"), got.get("wait_all_workflows_unplaced_commits")))
    # ... unless its workflow id was saved: then that is its workflow.
    rows_id = copy.deepcopy(rows2)
    rows_id[0]["workflow_id"], rows_id[1]["workflow_id"] = 17, 35
    rows_id[1]["name"] = "Lint"
    legacy = copy.deepcopy(rows_id[1])
    legacy.update(id=legacy["id"] + 700, path=".github/workflows/legacy.yml", conclusion="failure",
                  head_sha="%040d" % 998, pull_requests=[998])
    del legacy["workflow_id"]
    got = json.loads(_split(t, rows_id + [legacy], "--json").stdout or "{}")
    if got.get("wait_all_workflows_commits") != 1 or got.get("wait_all_workflows_unplaced_commits") != 0 \
            or len(got.get("workflows") or []) != 3:  # CI, Lint (id 35) and the older legacy.yml
        bad.append("split #7: a run with its workflow id but no file wasn't placed: %r %r"
                   % (got.get("wait_all_workflows_commits"), got.get("wait_all_workflows_unplaced_commits")))
    # ... and one 48 hours later, outside the commit's window, changes nothing.
    rows3 = [rows[0], rows[2]] + copy.deepcopy(rows2[1:])
    rows3[-1].update(created_at=_at(200 + 48 * 3600), run_started_at=_at(200 + 48 * 3600))
    got = json.loads(_split(t, rows3, "--json").stdout or "{}")
    if got.get("wait_all_workflows_commits") != 1 or got.get("wait_all_workflows_unplaced_commits") != 0:
        bad.append("split #7: a run with no file outside the commit's window left the commit out: %r %r"
                   % (got.get("wait_all_workflows_commits"), got.get("wait_all_workflows_unplaced_commits")))
    # #14: a run with no pull-request number (a fork's, or a closed pull request's) is keyed by
    # repository and branch, and counted, with the note in the output.
    def fork_runs(specs):
        out = []
        for i, (prs, base, sha) in enumerate(specs):
            x = _run(i, [_job("test", 3000 * i, 3000 * i + 1, 3000 * i + 60)], 3000 * i)
            x.update(head_repo="fork/r", head_branch="fix", head_sha="%040d" % sha, pull_requests=prs,
                     pull_request_bases=base)
            out.append(x)
        return out
    for specs, want in (((([5], ["main"], 1), ([5], ["main"], 2)), (2, 0)),
                        ((([], ["main"], 1), ([], [], 2)), (2, 2))):
        got = json.loads(_split(t, fork_runs(specs), "--json").stdout or "{}")
        text = _split(t, fork_runs(specs)).stdout
        if (got.get("pr_commits"), got.get("pr_runs_keyed_by_branch")) != want \
                or (want[1] > 0) != ("carried no pull-request number" in text):
            bad.append("split #14: fork runs %r keyed as %r, not %r"
                       % (specs, (got.get("pr_commits"), got.get("pr_runs_keyed_by_branch")), want))
    # --workflow a.yml selects the file a.yml, not also another file whose display name is a.yml;
    # a renamed workflow is one workflow and one set of jobs.
    rows = []
    for k, (path, name, ok) in enumerate((("a.yml", "CI", True), ("b.yml", "a.yml", False))):
        x = _run(k, [_job("test", 9000 * k, 9000 * k + 1, 9000 * k + 120)], 9000 * k, name=name)
        x.update(path=".github/workflows/" + path, conclusion="success" if ok else "failure")
        rows.append(x)
    got = json.loads(_split(t, rows, "--json", "--workflow", "a.yml").stdout or "{}")
    if (got.get("passed_runs"), got.get("ended_runs")) != (1, 1):
        bad.append("split: --workflow a.yml pooled another file named a.yml: %r" % ((got.get("passed_runs"), got.get("ended_runs")),))
    rows = [_run(k, [_job("test", 9000 * k, 9000 * k + 1, 9000 * k + 120)], 9000 * k, name=n)
            for k, n in enumerate(("CI", "Checks"))]
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    if got.get("job_sets") != 1 or got.get("workflows") != ["Checks"]:
        bad.append("split: a renamed workflow made two sets or two workflows: %r %r" % (got.get("job_sets"), got.get("workflows")))
    # Runs saved with no file still count under --workflow ci.yml by their display name, and
    # a missing file doesn't make another set of jobs.
    rows = []
    for k, ok in enumerate((True, False, False)):
        x = _run(k, [_job("test", 9000 * k, 9000 * k + 1, 9000 * k + 60 * (k + 1))], 9000 * k, name="ci.yml")
        x.update(conclusion="success" if ok else "failure")
        if k:
            del x["path"]
        rows.append(x)
    got = json.loads(_split(t, rows, "--json", "--workflow", "ci.yml").stdout or "{}")
    text = _split(t, rows, "--workflow", "ci.yml").stdout
    if not text.startswith("2 runs named ci.yml"):
        bad.append("split: the runs left out should be said first\n" + text)
    # ... and with the workflow's id saved, they take its file: 1 of 3 passed, as before.
    for x in rows:
        x["workflow_id"] = 42
    got_id = json.loads(_split(t, rows, "--json", "--workflow", "ci.yml").stdout or "{}")
    if (got_id.get("passed_runs"), got_id.get("ended_runs"), got_id.get("runs_left_out_no_file")) != (1, 3, 0):
        bad.append("split: runs with no file but the workflow's id weren't placed: %r"
                   % ((got_id.get("passed_runs"), got_id.get("ended_runs"), got_id.get("runs_left_out_no_file")),))
    if (got.get("passed_runs"), got.get("ended_runs"), got.get("runs_left_out_no_file")) != (1, 1, 2) \
            or "2 runs named ci.yml have no workflow file saved" not in text:
        bad.append("split: --workflow by file should leave out runs with no file, and say so first: %r\n%s"
                   % ((got.get("passed_runs"), got.get("ended_runs"), got.get("runs_left_out_no_file")), text))
    rows = [_run(k, [_job("test", 9000 * k, 9000 * k + 1, 9000 * k + 60 + 540 * k)], 9000 * k) for k in range(2)]
    del rows[0]["path"]
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    lint_fail = _run(5, [_job("lint", 45000, 45001, 45030, conclusion="failure")], 45000, name="Lint")
    lint_fail.update(path=".github/workflows/lint.yml", conclusion="failure")
    got2 = json.loads(_split(t, rows + [lint_fail], "--json").stdout or "{}")
    if got.get("job_sets") != 1 or got2.get("job_sets") != 1:
        bad.append("split: a run with no file, or another workflow's failure, made another set of jobs: %r %r"
                   % (got.get("job_sets"), got2.get("job_sets")))
    # Two workflows told apart only by their saved ids (one with no file) are two sets of jobs.
    rows = [_run(k, [_job("test", 9000 * k, 9000 * k + 1, 9000 * k + (60 if k < 3 else 600))], 9000 * k) for k in range(5)]
    for k, x in enumerate(rows):
        x["workflow_id"] = 17 if k < 3 else 35
        if k >= 3:
            del x["path"]
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    # An older failed run of ci.yml with no id doesn't make id 35 unplaceable: ci.yml's id is 17.
    old_ci = copy.deepcopy(rows[0])
    old_ci.update(id=old_ci["id"] + 900, conclusion="failure", head_sha="%040d" % 999, pull_requests=[999])
    del old_ci["workflow_id"]
    got2 = json.loads(_split(t, rows + [old_ci], "--json").stdout or "{}")
    if got.get("job_sets") != 2 or got2.get("job_sets") != 2:
        bad.append("split: workflows told apart by id made one set of jobs: %r %r" % (got.get("job_sets"), got2.get("job_sets")))
    # One file on two events is two checks: a passing pull_request_target run doesn't hide a failing
    # pull_request run of the same file. One commit seen by number and by branch is one push.
    # A path with its ref (build.yml@main) is still build.yml.
    two_ev = []
    for k, (ev, name, ok, path, prs) in enumerate((("pull_request_target", "Triage", True, "ci.yml@main", [42]),
                                                   ("pull_request", "Tests", False, "ci.yml", [42]),
                                                   ("pull_request", "Lint", True, "lint.yml", []))):
        x = _run(k, [_job("test", 10 * k, 10 * k + 1, 10 * k + 10)], 10 * k, name=name)
        x.update(event=ev, path=".github/workflows/" + path, conclusion="success" if ok else "failure",
                 head_sha="%040d" % 42, pull_requests=prs, head_branch="b42")
        two_ev.append(x)
    got = json.loads(_split(t, two_ev, "--json").stdout or "{}")
    if got.get("wait_all_workflows_commits") != 0 or got.get("pr_commits") != 1:
        bad.append("split: one file on two events, or one commit by number and branch: %r %r"
                   % (got.get("wait_all_workflows_commits"), got.get("pr_commits")))
    # #14: a repository whose pull-request workflow runs on pull_request_target alone.
    rows = []
    for i in range(6):
        x = _run(i, [_job("test", 30000 * i, 30000 * i + 1, 30000 * i + 60)], 30000 * i)
        x["event"] = "pull_request_target"
        x["pull_requests"] = [i % 3]
        rows.append(x)
    r = _split(t, rows, "--json")
    got = json.loads(r.stdout or "{}")
    if got.get("pr_commits") != 6 or got.get("pushes_per_pr_max") != 2 or not got.get("runs_per_day"):
        bad.append("split #14: pull_request_target runs weren't pull-request runs: %r %r"
                   % (got.get("pr_commits"), got.get("pushes_per_pr_max")))
    # #23: every run's longest job is build; three of six also ran lint. One headline group,
    # two job sets: said so, with the commonest set's median.
    rows = []
    for i in range(6):
        t0 = 4000 * i
        jobs = [_job("build", t0, t0 + 1, t0 + 600 + i)]
        if i % 2:
            jobs.append(_job("lint", t0, t0 + 1, t0 + 700 + i))
            jobs[-1]["name"] = "lint"
        rows.append(_run(i, jobs, t0))
    for row in rows:  # make build the longest job by median: lint runs shorter
        for j in row["jobs"]:
            if j["name"] == "lint":
                j["completed_at"] = _at(_ts_of(j["started_at"]) + 20)
                j["steps"][-1]["completed_at"] = j["completed_at"]
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    text = _split(t, rows).stdout
    head = got.get("headline") or {}
    if (head.get("commonest_set") or {}).get("median") != 602 or head["commonest_set"].get("jobs") != ["build"] \
            or head.get("job_sets") != 2 or (head.get("commonest_set") or {}).get("runs") != 3 \
            or (head.get("commonest_set") or {}).get("tied_with") != 1 or len(got.get("cohorts") or []) != 1 \
            or "ran 2 different sets of jobs" not in text or "tied with 1 other set" not in text:
        bad.append("split #23: a headline group mixing two job sets wasn't flagged: %r\n%s" % (head, text))
    # A rerun of failed jobs lists the jobs that passed before under its own attempt: the run
    # ran one set of jobs, and its wait covers only the rerun, which split says.
    rows = []
    for i in range(6):
        t0 = 5000 * i
        rows.append(_run(i, [_job("build", t0, t0 + 1, t0 + 300), _job("test", t0 + 300, t0 + 301, t0 + 900)], t0))
    last = rows[-1]
    last.update(run_attempt=2, run_started_at=_at(25000 + 1000))
    for j in last["jobs"]:
        j["run_attempt"] = 2
    tj = last["jobs"][1]
    tj.update(created_at=_at(26000), started_at=_at(26001), completed_at=_at(26600))
    tj["steps"] = [dict(x, started_at=_at(26001), completed_at=_at(26600)) for x in tj["steps"]]
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    text = _split(t, rows).stdout
    no_start = copy.deepcopy(rows)
    del no_start[-1]["run_started_at"]
    if (got.get("headline") or {}).get("job_sets") != 1 or (got.get("headline") or {}).get("reruns") != 1 \
            or "1 of the headline's runs passed on a rerun" not in text \
            or "1 from their creation" not in _split(t, no_start).stdout:
        bad.append("split #23: a rerun's carried-over jobs made another set, or the rerun wasn't named: %r\n%s"
                   % (got.get("headline"), text))
    # #35: a step stamped 10 s past its 60 s job shows clipped in the step table; a one-second
    # step inside another sets the overlap flag, and the amount says it is one second.
    rows = []
    for i in range(5):
        # Three runs overlap (by 1, 1 and 9 s) in jobs of 60, 61 and 62 s; two don't, in 100 s jobs.
        t0 = 5000 * i
        j = _job("test", t0, t0, t0 + (60 + i if i < 3 else 100))
        j["steps"] = [{"name": "Set up job", "conclusion": "success", "started_at": _at(t0), "completed_at": _at(t0 + 5)},
                      {"name": "Run tests", "conclusion": "success", "started_at": _at(t0 + 5), "completed_at": _at(t0 + 70)}]
        if i < 3:
            j["steps"].append({"name": "Note", "conclusion": "success", "started_at": _at(t0 + 20),
                               "completed_at": _at(t0 + (29 if i == 2 else 21))})
        rows.append(_run(i, [j], t0))
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    text = _split(t, rows).stdout
    steps = {x["step"]: x["median"] for x in (got.get("last_working_job_steps") or {}).get("test", [])}
    if steps.get("Run tests") != 57 or (got.get("last_working_job_steps_overlap_seconds") or {}).get("test") != 1 \
            or (got.get("last_working_job_steps_overlap_job_seconds") or {}).get("test") != 61 \
            or "in 3 of its 5 runs its steps overlapped" not in text:
        bad.append("split #35: steps not clipped to their job, or the overlap not measured: %r %r\n%s"
                   % (steps, got.get("last_working_job_steps_overlap_seconds"), text))
    # Two steps that overlap only after the job ended don't overlap in it; an untimed first
    # "Test" leaves the second as its #2.
    for row in rows:
        j = row["jobs"][0]
        t0 = _ts_of(j["started_at"])
        j["completed_at"] = _at(t0 + 60)
        j["steps"] = [{"name": "Set up job", "conclusion": "success", "started_at": _at(t0), "completed_at": _at(t0 + 5)},
                      {"name": "Test", "conclusion": "skipped", "started_at": None, "completed_at": None},
                      {"name": "Test", "conclusion": "success", "started_at": _at(t0 + 5), "completed_at": _at(t0 + 70)},
                      {"name": "Late", "conclusion": "success", "started_at": _at(t0 + 62), "completed_at": _at(t0 + 69)}]
    got = json.loads(_split(t, rows, "--json").stdout or "{}")
    occ = [(x["step"], x["occurrence"]) for x in (got.get("last_working_job_steps") or {}).get("test", [])]
    late = [x["median"] for x in (got.get("last_working_job_steps") or {}).get("test", []) if x["step"] == "Late"]
    if ("Test", 2) not in occ or ("Test", 1) in occ or late != [0] \
            or (got.get("last_working_job_steps_overlap") or {}).get("test"):
        bad.append("split #35: occurrence or out-of-job overlap wrong: %r %r" % (occ, got.get("last_working_job_steps_overlap")))


# every check.py fails on its untouched sample (the planted cause is there)
for case in sorted(glob.glob(E + "/ci-*/")):
    name = os.path.basename(case.rstrip("/"))
    work = tempfile.mkdtemp(prefix="joggernaut-selftest-")
    try:
        shutil.copytree(case + "repo", work, dirs_exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(["git", "add", "-A"], cwd=work, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "sample"], cwd=work, check=True)
        r = run([case + "check.py", work])
        first = (r.stdout.strip().splitlines() or [""])[0]
        if r.returncode == 0:
            bad.append("%s: check.py passes on the untouched sample\n%s" % (name, r.stdout))
        elif not first.startswith("FAIL"):
            bad.append("%s: check.py crashed\n%s%s" % (name, r.stdout, r.stderr[-2000:]))
        else:
            print("ok   %-15s untouched sample fails: %s" % (name, first))
    finally:
        shutil.rmtree(work)

# ci-guard's pre-push template, in scratch git repositories under each shell present
import selftest_hook  # noqa: E402
selftest_hook.selftest(bad)

for b in bad:
    print("FAIL " + b)
print("selftest: %d problem(s)" % len(bad))
sys.exit(1 if bad else 0)
