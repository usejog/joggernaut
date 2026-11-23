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
                   ("Verdict: FAIL\nStopped running: `report::billing::tests.test_billing::test_refund_rounding`", 0)):
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
if "median faster" in r.stdout:
    bad.append("compare: timed-out first attempts still earned a speed verdict\n" + r.stdout)

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
