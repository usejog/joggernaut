#!/usr/bin/env python3
"""Check the eval harness without an agent: every check.py fails on its
untouched sample, and measure.py gives the expected answers on the samples."""
import glob
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
        c = copy.deepcopy(row); c["id"] += 200000; c["name"] = "E2E"
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
    for fails, want in ((6, "faster"), (7, "not_valid")):
        fake_runs(t + "/fa%d" % fails, [500, 505, 510, 515, 520], 7000 + 100 * fails)
        fake_runs(t + "/fa%d" % fails, [400] * fails, 7050 + 100 * fails, "failure")
        v = verdict(t + "/sb", t + "/fa%d" % fails)
        if v.get("verdict_code") != want:
            bad.append("compare: %d failed after against 0 before should be %s: %r" % (fails, want, v))
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
elif "/jobs" in path:
    rid = int(re.search(r"/runs/(\d+)/jobs", path).group(1))
    print(json.dumps([{"jobs": [r for r in runs if r["id"] == rid][0]["jobs"]}]))
else:
    keep = [r for r in runs if "status=completed" not in path or r["status"] == "completed"]
    page = int(re.search(r"[?&]page=(\d+)", path).group(1))
    print(json.dumps({"total_count": len(keep), "workflow_runs": keep[(page - 1) * 100:page * 100]}))
'''
with tempfile.TemporaryDirectory() as t:
    os.makedirs(t + "/bin")
    open(t + "/bin/gh", "w").write(FAKE_GH)
    os.chmod(t + "/bin/gh", 0o755)
    rows = [json.loads(l) for l in open(E + "/ci-measure/repo/ci-history/after.jsonl") if l.strip()][:6]
    env = dict(os.environ, PATH=t + "/bin" + os.pathsep + os.environ["PATH"], FAKE_RUNS=t + "/runs.json")

    calls = itertools.count()

    def fetch(statuses, *extra):
        json.dump([dict(r, status=s, pull_requests=[{"number": n} for n in r["pull_requests"]])
                   for r, s in zip(rows, statuses)], open(t + "/runs.json", "w"))
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
    if "verdict: not enough runs yet" not in r.stdout:
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

for b in bad:
    print("FAIL " + b)
print("selftest: %d problem(s)" % len(bad))
sys.exit(1 if bad else 0)
