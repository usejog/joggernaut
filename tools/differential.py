#!/usr/bin/env python3
"""Never laxer than the base: run the base's measure.py and this one on the same histories
and fail where this one gives a reading, a pass or a speed verdict the base refuses or fails.

  differential.py BASE_MEASURE_PY [--seeds N] [--history runs.jsonl ...]

"Laxer", for compare: the base stops (an error, not valid, or not enough runs) and this one
gives a reading or a verdict; or the base gives only a descriptive reading and this one a
verdict. For split: on one commit's runs, where one of them didn't pass, this one counts
more commits whose every check passed than the base does. Refusing more is allowed.

The histories: random ones (seeded, so a failure reproduces), each --history file (split
whole, and compared older half against newer half), and, through check_args, every compare
and split the selftest runs. Both scripts run in this process, so a case costs milliseconds.
"""
import contextlib
import importlib.util
import io
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = os.path.join(ROOT, "skills/ci-measure/scripts/measure.py")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def call(mod, argv):
    """(exit code, stdout, stderr), as the command line would give them."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = mod.main(argv) or 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        except Exception:  # a crash: say so, never take it for a refusal
            import traceback
            code = 99
            err.write(traceback.format_exc())
    return code, out.getvalue(), err.getvalue()


STOPS = ("not_enough_runs", "not_valid")


def compare_level(code, out):
    """0: stopped (refused, not valid, not enough runs); 1: a descriptive reading; 2: a verdict."""
    if code:
        return 0, None
    res = json.loads(out)
    vc = res["verdict_code"]
    if vc in STOPS:
        return 0, vc
    return (1 if vc.endswith("_descriptive") else 2), vc


def laxer_compare(base, head, argv):
    """A message if head is laxer than base on this compare, else None (or "usage" when the
    base doesn't take one of the flags)."""
    argv = [x for x in argv if x != "--json"] + ["--json"]
    bc, bo, be = call(base, argv)
    if bc and ("usage:" in be or bc == 99):
        return "usage"  # a flag the base doesn't take, or the base crashed: nothing to compare
    hc, ho, he = call(head, argv)
    if hc == 99:
        return "head crashed: %s" % he.strip().splitlines()[-1]
    bl, bv = compare_level(bc, bo)
    hl, hv = compare_level(hc, ho)
    STATS[(bl, hl)] = STATS.get((bl, hl), 0) + 1
    if hl > bl:
        return "base %s, head %s" % (bv or "refused: " + be.strip().splitlines()[-1][:160], hv)
    return None


def split_fails(mod, path, extra):
    """(all-passed commits, runs that failed) from split, or None when it stops."""
    code, out, _ = call(mod, ["split", "--in", path, "--json"] + extra)
    if code:
        return None
    res = json.loads(out)
    return res.get("wait_all_workflows_commits") or 0, res["ended_runs"] - res["passed_runs"]


def laxer_split(base, head, path, extra=()):
    """Head reads the file with its flags; the base reads the runs head should have selected
    (by display name as head does; by file, which the base can't select, those runs unfiltered).
    Head must not count fewer failed runs, and per commit with a run the base reads that didn't
    pass, not more all-passed commits."""
    rows = [json.loads(l) for l in open(path) if l.strip()]
    extra, base_extra, mine = list(extra), list(extra), rows
    if "--workflow" in extra:
        k = extra.index("--workflow")
        w = extra[k + 1]
        if any(os.path.basename(r.get("path") or "") == w for r in rows):
            # A run with no file but its workflow's id is that workflow's (GitHub's id names it).
            ids = {r.get("workflow_id"): os.path.basename(r["path"]) for r in rows
                   if r.get("path") and r.get("workflow_id") is not None}
            file_of = lambda r: os.path.basename(r.get("path") or "") or ids.get(r.get("workflow_id"), "")
            names = {r.get("name") for r in rows if file_of(r) == w}
            mine = [r for r in rows if file_of(r) == w or (not file_of(r) and r.get("name") in names)]
            base_extra = extra[:k] + extra[k + 2:]
        else:
            mine = [r for r in rows if r.get("name") == w]
    with tempfile.TemporaryDirectory() as t:
        pb, ph = os.path.join(t, "b.jsonl"), os.path.join(t, "h.jsonl")
        write(pb, mine)
        b, h = split_fails(base, pb, base_extra), split_fails(head, path, extra)
        if b and h and h[1] < b[1]:
            return "base counts %d failed runs, head %d" % (b[1], h[1])
        for sha in sorted({r.get("head_sha") for r in mine if r.get("conclusion") != "success"} - {None}):
            write(pb, [r for r in mine if r.get("head_sha") == sha])
            write(ph, [r for r in rows if r.get("head_sha") == sha])
            b, h = split_fails(base, pb, base_extra), split_fails(head, ph, extra)
            b, h = (b or (0, 0))[0], (h or (0, 0))[0]
            STATS[("split", b < h)] = STATS.get(("split", b < h), 0) + 1
            if h > b:
                return "commit %s: base counts %d all-passed, head %d" % (sha, b, h)
    return None


STATS = {}
_MODS = {}


def mods(base_path):
    if base_path not in _MODS:
        _MODS[base_path] = (load(base_path, "measure_base"), load(HEAD, "measure_head"))
    return _MODS[base_path]


def check_args(base_path, args, cwd=None):
    """For the selftest: the same compare or split it ran, on the base and on head. args are
    measure.py's own (the subcommand first). Returns a message when head is laxer."""
    base, head = mods(base_path)
    old = os.getcwd()
    try:
        if cwd:
            os.chdir(cwd)
        if args[0] == "compare":
            msg = laxer_compare(base, head, list(args))
            return None if msg == "usage" else msg
        if args[0] == "split" and "--in" in args:
            i = args.index("--in")
            extra = [x for k, x in enumerate(args[1:], 1) if k not in (i, i + 1) and x != "--json"]
            if os.path.isfile(args[i + 1]):
                return laxer_split(base, head, args[i + 1], extra)
        return None
    finally:
        os.chdir(old)


# ---------------------------------------------------------------- random histories

T0 = 1795000000  # a fixed start, so a seed gives the same file


def stamp(s):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0 + s))


JOBS = ("test", "build", "docs", "gate")
LABELS = (["L"], ["M"], ["N"], ["self-hosted", "L"])


def gen_run(rng, rid, t, side, shape):
    """One run as fetch saves it. shape holds the per-history odds, runners and speeds, with
    the correlations that make a change look faster: which pushes reach which runner, which
    runners fail, which runs a filter skips, and a gate that needs test."""
    attempts = 2 if rng.random() < shape["rerun"] else 1
    jobs, jid = [], rid * 10
    conclusion = "success"
    slow_push = rng.random() < 0.5  # a property of the push: its work is slow wherever it runs
    for att in range(1, attempts + 1):
        clock, test_failed = t + 5, False
        for name in JOBS:
            if rng.random() < shape["absent"][name] or (shape["filter_slow"] == name and slow_push != (side == "before")):
                continue
            jid += 1
            pool = shape["labels"][side][name]
            lab = pool[0] if rng.random() < shape["main_share"] else rng.choice(pool)
            if shape["route_slow"] and len(pool) > 1:  # slow pushes go to one runner, fast ones to another
                lab = pool[slow_push if side == "before" else not slow_push]
            group = rng.choice(shape["groups"])
            outcome = rng.choices(("success", "failure", "cancelled", "skipped", "queued_cancel"),
                                  weights=shape["outcomes"][side])[0]
            if lab[-1] == shape["fails_on"][side] and rng.random() < shape["fail_odds"]:
                outcome = "failure"
            if name == "gate" and shape["gate_needs_test"] and test_failed:
                outcome = rng.choice(("skipped", "queued_cancel"))
            if att < attempts and outcome == "success" and rng.random() < 0.5:
                outcome = "failure"
            base_s = shape["speed"][side].get(lab[-1], 50) * (3 if slow_push and shape["push_matters"] else 1)
            speed = 5 if name == "gate" else base_s * (0.9 + 0.2 * rng.random())
            j = {"id": jid, "name": name, "run_attempt": att, "created_at": stamp(clock), "labels": list(lab),
                 "runner_name": None, "runner_group_id": None, "runner_group_name": None, "steps": []}
            if outcome == "skipped":
                j.update(conclusion="skipped", started_at=None, completed_at=stamp(clock), labels=[])
            elif outcome == "queued_cancel":
                q = clock + 1 + int(rng.random() * 30)
                j.update(conclusion="cancelled", started_at=stamp(q), completed_at=stamp(q))
            else:
                s = clock + 1 + int(rng.random() * 3)
                e = s + max(1, int(speed if outcome == "success" else speed * rng.random()))
                j.update(conclusion=outcome, started_at=stamp(s), completed_at=stamp(e),
                         runner_name="r-%s-%d" % (lab[-1], rng.randrange(3)),
                         runner_group_id=group, runner_group_name=None if group is None else "g%d" % group)
                if name == "test":
                    test_failed = outcome != "success"
                if name in ("test", "gate") and shape["serial"]:
                    clock = e
            jobs.append(j)
        if att == attempts:
            last = [j for j in jobs if j["run_attempt"] == att]
            if any(j["conclusion"] == "failure" for j in last):
                conclusion = "success" if rng.random() < shape["continue"] else "failure"
            elif any(j["conclusion"] == "cancelled" for j in last):
                conclusion = "cancelled"
            if rng.random() < 0.02:
                conclusion = rng.choice(("neutral", "skipped", "timed_out", None, "startup_failure"))
    ends = [j["completed_at"] for j in jobs if j.get("completed_at")]
    pr = rng.choice(shape["prs"])
    event = "pull_request" if rng.random() < shape["pr_share"] else "push"
    wf = ("CI", ".github/workflows/ci.yml") if rng.random() >= shape["other_wf"] else ("Docs", ".github/workflows/docs.yml")
    return {"id": rid, "name": wf[0], "path": wf[1], "workflow_id": 1 if wf[0] == "CI" else 2,
            "event": event, "head_branch": "b%d" % pr, "head_sha": "%040x" % (rid * 7919 % (1 << 60)),
            "head_repo": "o/r", "run_attempt": attempts, "conclusion": conclusion,
            "created_at": stamp(t), "run_started_at": stamp(t + 2), "updated_at": max(ends) if ends else stamp(t + 3),
            "pull_requests": [pr] if event == "pull_request" and rng.random() < 0.9 else [],
            "pull_request_bases": [rng.choice(shape["bases"])] if event == "pull_request" else [],
            "pull_requests_found": [], "head_message": "change", "jobs": jobs}


def gen_shape(rng):
    """Mostly tidy histories (one runner a job, few failures) with one or two twists, so most
    cases get past the runner checks to a verdict; some wild ones."""
    wild = rng.random() < 0.25
    one = lambda: [rng.choice(LABELS)] + ([rng.choice(LABELS)] if wild or rng.random() < 0.4 else [])
    labels = {"before": {n: one() for n in JOBS}}
    labels["after"] = {n: list(v) for n, v in labels["before"].items()}
    for n in JOBS:
        if rng.random() < (0.5 if wild else 0.15):
            labels["after"][n] = one()
    canary = rng.random() < 0.3
    if canary:
        # A canary runner that always fails, a different one each side: only failed runs show it.
        a, b, c = rng.sample([x[-1] for x in LABELS[:3]], 3)
        c = c if rng.random() < 0.5 else b  # the same canary both sides: seen in failed runs only
        labels["before"]["test"], labels["after"]["test"] = [[a], [b]], [[a], [c]]
    speeds = lambda: {k: rng.choice((10, 30, 100)) for k in ("L", "M", "N")}
    sp = speeds()
    sp_after = dict(sp) if rng.random() < 0.4 else {k: max(5, v // rng.choice((1, 2, 5))) for k, v in sp.items()}
    ok = [rng.choice((90, 97, 100)) if not wild else 70] + [rng.choice((0, 2, 8)), rng.choice((0, 1, 5)),
                                                           rng.choice((0, 1, 5)), rng.choice((0, 1, 5))]
    ok_after = list(ok) if rng.random() < 0.6 else [ok[0]] + [rng.choice((0, 2, 10)) for _ in range(4)]
    fails_on = {s: rng.choice((None, labels[s]["test"][-1][-1], rng.choice(LABELS)[-1])) for s in labels}
    if canary:
        fails_on = {"before": b, "after": c}
    return {"rerun": rng.choice((0, 0, 0.05, 0.2)), "continue": rng.choice((0, 0, 0.5, 1)),
            "absent": {n: rng.choice((0, 0, 0, 0.1, 0.4)) for n in JOBS},
            "filter_slow": rng.choice((None, None, None) + JOBS),
            "route_slow": rng.random() < 0.3, "push_matters": rng.random() < 0.6,
            "main_share": rng.choice((0.5, 0.9, 1.0)), "fail_odds": 1.0 if canary else rng.choice((0.3, 1.0)), "fails_on": fails_on,
            "gate_needs_test": rng.random() < 0.5, "serial": rng.random() < 0.5,
            "labels": labels, "groups": rng.choice(([None], [1], [1], [1, 2], [1, None])),
            "outcomes": {"before": ok, "after": ok_after},
            "speed": {"before": sp, "after": sp_after},
            "prs": list(range(1, rng.choice((3, 10, 40)))), "pr_share": rng.choice((1, 1, 1, 0.8)),
            "other_wf": rng.choice((0, 0, 0, 0.1)), "bases": rng.choice((["main"], ["main"], ["main", "release"]))}


def gen_compare(rng, seed):
    shape = gen_shape(rng)
    sides = {}
    for k, side in enumerate(("before", "after")):
        n = rng.choice((8, 16, 30))
        sides[side] = [gen_run(rng, seed * 1000 + k * 500 + i, (k * 100 + i) * 3600, side, shape) for i in range(n)]
    cache = {str(r["id"]): rng.choice(("hit", "miss")) for rs in sides.values() for r in rs}
    tl = shape["labels"]["before"]["test"][0][-1]
    flag_sets = [[], ["--job", "test"], ["--job", "test", "--ran", "gate"], ["--ran", "gate"],
                 ["--job", "test", "--label", tl], ["--job", "test", "--end"], ["--label", tl]]
    if shape["other_wf"]:  # two workflows in the file: every reading names one
        flag_sets = [f + ["--workflow", "CI"] for f in flag_sets]
    for _ in range(4):
        f = []
        if rng.random() < 0.6:
            f += ["--job", rng.choice(("test", "build", "gate"))]
            if rng.random() < 0.3:
                f += ["--end"]
        if rng.random() < 0.4:
            f += ["--ran", rng.choice(("gate", "gate", "test", "build", "docs"))]
        if rng.random() < 0.5:
            # Mostly the label the measured job (or test) usually runs on, so runs get timed.
            j = f[1] if f and f[0] == "--job" else "test"
            f += ["--label", shape["labels"]["before"][j][0][-1] if rng.random() < 0.8
                  else rng.choice(("L", "M", "self-hosted"))]
        if rng.random() < 0.3:
            f += ["--cache", rng.choice(("hit", "miss"))]
        if shape["other_wf"] or rng.random() < 0.2:
            f += ["--workflow", "CI"]
        if len(shape["bases"]) > 1 and rng.random() < 0.5:
            f += ["--base", "main"]
        flag_sets.append(f)
    return sides, cache, flag_sets


def gen_split(rng, seed):
    """Runs of several workflows on a few commits. A commit can be seen under two pull requests,
    a fork, or a branch alone (its pull request closed by the fetch); a file can run on two
    events, be named with an at sign, or be saved with no file; runs can fail, be cancelled or
    still be going."""
    rows, rid = [], seed * 1000
    files = rng.choice(([("CI", "ci.yml")], [("CI", "ci.yml"), ("Lint", "lint.yml")],
                        [("CI", "ci.yml"), ("CI", "integration.yml"), ("Lint", "lint.yml")],
                        [("CI", "ci.yml"), ("CI", "ci.yml" + "@" + "integration.yml")]))  # a legal file name
    owners = [(1, "b1", "o/r"), (2, "b2", "o/r"), (3, "b1", "fork/r")]
    for c in range(rng.choice((2, 5, 10))):
        sha = "%040x" % (seed * 100 + c)
        t = c * 7200
        for pr, branch, repo in rng.sample(owners, rng.choice((1, 1, 2, 3))):
            for k, (name, f) in enumerate(files):
                for event in rng.sample(("pull_request", "pull_request_target", "push"), rng.choice((1, 1, 2, 3))):
                    rid += 1
                    concl = rng.choices(("success", "failure", "cancelled", None, "skipped"), weights=(80, 12, 4, 2, 2))[0]
                    s = t + rng.randrange(60) + (rng.choice((0, 0, 0, 90000)))
                    e = s + rng.choice((10, 30, 120))
                    path = rng.choice((f, f, f, f + "@refs/heads/" + branch, None))
                    rows.append({"id": rid, "name": name, "path": path and ".github/workflows/" + path,
                                 "workflow_id": k + 1 if rng.random() < 0.7 else None, "event": event, "head_branch": branch, "head_sha": sha,
                                 "head_repo": repo, "run_attempt": rng.choice((1, 1, 1, 2)), "conclusion": concl,
                                 "created_at": stamp(s), "run_started_at": stamp(s), "updated_at": stamp(e),
                                 "pull_requests": [pr] if repo == "o/r" and rng.random() < 0.6 else [],
                                 "pull_request_bases": ["main"], "pull_requests_found": [], "head_message": "x",
                                 "jobs": [{"id": rid * 10, "name": "j", "run_attempt": 1,
                                           "conclusion": concl if concl != "skipped" else "success",
                                           "created_at": stamp(s), "started_at": stamp(s + 1), "completed_at": stamp(e),
                                           "labels": ["L"], "runner_name": "r", "runner_group_id": 1,
                                           "runner_group_name": "g", "steps": []}]})
    return rows


def write(path, rows):
    with open(path, "w") as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))


def run_generated(base_path, seeds):
    base, head = mods(base_path)
    found = []
    with tempfile.TemporaryDirectory() as t:
        for seed in seeds:
            rng = random.Random(seed)
            sides, cache, flag_sets = gen_compare(rng, seed)
            write(t + "/b.jsonl", sides["before"])
            write(t + "/a.jsonl", sides["after"])
            json.dump(cache, open(t + "/c.json", "w"))
            for f in flag_sets:
                argv = ["compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl"] + f
                if "--cache" in f:
                    argv += ["--cache-state", t + "/c.json"]
                msg = laxer_compare(base, head, argv)
                if msg and msg != "usage":
                    found.append("compare seed %d %s: %s" % (seed, " ".join(f), msg))
            write(t + "/s.jsonl", gen_split(rng, seed))
            for extra in ([], ["--workflow", "CI"], ["--workflow", "ci.yml"]):
                msg = laxer_split(base, head, t + "/s.jsonl", extra)
                if msg:
                    found.append("split seed %d %s: %s" % (seed, " ".join(extra), msg))
    return found


def run_history(base_path, path):
    """A real fetched history: split whole, and compare its older half against its newer half
    under the plain, --job, --ran and --label readings of its commonest job and label."""
    base, head = mods(base_path)
    found = []
    msg = laxer_split(base, head, path)
    if msg:
        found.append("split %s: %s" % (os.path.basename(path), msg))
    rows = sorted((json.loads(l) for l in open(path) if l.strip()), key=lambda r: r.get("created_at") or "")
    wfs = {}
    for r in rows:
        wfs[r.get("name")] = wfs.get(r.get("name"), 0) + 1
    with tempfile.TemporaryDirectory() as t:
        for wf in sorted(wfs, key=lambda k: -wfs[k])[:2]:
            rs = [r for r in rows if r.get("name") == wf]
            write(t + "/b.jsonl", rs[:len(rs) // 2])
            write(t + "/a.jsonl", rs[len(rs) // 2:])
            jobs, labels = {}, {}
            for r in rs:
                for j in r.get("jobs", []):
                    jobs[j.get("name")] = jobs.get(j.get("name"), 0) + 1
                    for lab in j.get("labels") or []:
                        labels[lab] = labels.get(lab, 0) + 1
            top = sorted(jobs, key=lambda k: -jobs[k])[:3]
            lab = max(labels, key=labels.get) if labels else None
            flag_sets = [[]] + [["--job", n] for n in top] + [["--ran", n] for n in top[:2]]
            if lab:
                flag_sets += [["--label", lab]] + [["--job", n, "--label", lab] for n in top[:2]]
            for f in flag_sets:
                argv = ["compare", "--before", t + "/b.jsonl", "--after", t + "/a.jsonl", "--workflow", wf] + f
                msg = laxer_compare(base, head, argv)
                if msg and msg != "usage":
                    found.append("compare %s %s %s: %s" % (os.path.basename(path), wf, " ".join(f), msg))
    return found


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    base_path, seeds, histories = argv[0], 300, []
    rest = argv[1:]
    while rest:
        if rest[0] == "--seeds":
            seeds, rest = int(rest[1]), rest[2:]
        elif rest[0] == "--history":
            histories.append(rest[1])
            rest = rest[2:]
        else:
            print("unknown argument %r" % rest[0])
            return 2
    found = run_generated(base_path, range(seeds))
    for h in histories:
        found += run_history(base_path, h)
    for x in found[:20]:
        print("laxer: " + x)
    print("differential: %d case(s) laxer than the base; levels (base, head): %s"
          % (len(found), json.dumps({str(k): v for k, v in sorted(STATS.items(), key=str)})))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
