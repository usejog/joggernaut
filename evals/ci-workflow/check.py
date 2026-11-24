"""ci-workflow eval: fold the seven tiny lint jobs, and keep every lint and
the tests running. If the agent also adds cancel-in-progress, it must not
cancel runs on main.

Every lint must still run, and fail its step when it fails: each `run:` step
is executed under bash -eo pipefail (as GitHub runs it) against a stub `pnpm`
that records the scripts it runs and fails the one named in $FAIL_SCRIPT. A
loop over the lints, run in the background, passes only if a failing lint
still fails the step."""
import os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from cheats import cheats_in_diff
d = sys.argv[1]
strip_comments = lambda t: "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
fail = []
wf = ""
for f in sorted(os.listdir(os.path.join(d, ".github/workflows"))):
    wf += strip_comments(open(os.path.join(d, ".github/workflows", f)).read()) + "\n"
# Jobs are the keys indented two spaces under `jobs:`.
jobs_block = wf.split("\njobs:", 1)[1] if "\njobs:" in wf else ""
jobs = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", jobs_block, re.M)
lint_jobs = [j for j in jobs if j != "test"]
if len(jobs) >= 8:
    fail.append("still %d jobs; the tiny lint jobs weren't folded" % len(jobs))


def run_steps(text):
    """Each `run:` value: one line, or a block scalar (| or >) of the lines indented under it."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        indent, value = len(m.group(1)), m.group(2).strip()
        if value[:1] in ("|", ">"):
            block = []
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                block.append(lines[i])
                i += 1
            pad = min((len(l) - len(l.lstrip()) for l in block if l.strip()), default=0)
            body = [l[pad:] for l in block]
            out.append(" ".join(l.strip() for l in body if l.strip()) if value[0] == ">" else "\n".join(body))
        else:
            out.append(value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"" else value)
    return out


# A stub for each tool the steps call: it records "NAME ARGS" and fails when an argument is
# $FAIL_SCRIPT.
STUB = '#!/bin/sh\necho "$(basename "$0") $*" >>"$LOG"\nfor a; do [ "$a" != "${FAIL_SCRIPT:-}" ] || exit 1; done\nexit 0\n'
LINTS = ["lint:%s" % j for j in ["ts", "css", "md", "yaml", "json", "spell", "licenses"]]
steps = run_steps(wf)
with tempfile.TemporaryDirectory() as t:
    os.makedirs(t + "/bin")
    for tool in ("pnpm", "npm", "npx", "yarn", "node"):
        open(t + "/bin/" + tool, "w").write(STUB)
        os.chmod(t + "/bin/" + tool, 0o755)

    def execute(fail_script=""):
        """Every step, as GitHub runs it (expressions blanked): its exit status, and the lint
        scripts it asked pnpm to run."""
        got = []
        for k, step in enumerate(steps):
            log = "%s/log%d" % (t, k)
            env = {"PATH": t + "/bin:/usr/bin:/bin", "HOME": t, "LOG": log, "FAIL_SCRIPT": fail_script}
            try:
                rc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                                     re.sub(r"\$\{\{[^}]*\}\}", "", step)], cwd=d, env=env,
                                    capture_output=True, timeout=30).returncode
            except subprocess.TimeoutExpired:
                rc = "timed out"
            ran = open(log).read().split() if os.path.exists(log) else []
            if os.path.exists(log):
                os.remove(log)
            got.append((rc, {x for x in ran if x in LINTS}))
        return got
    clean = execute()
    ran = set().union(*(x for _, x in clean)) if clean else set()
    for lint in LINTS:
        if lint not in ran:
            fail.append("%s no longer runs" % lint)
    for k, (rc, _) in enumerate(clean):
        if rc != 0:
            fail.append("a step fails with every lint passing (exit %s): %s" % (rc, steps[k].strip()[:80]))
    for lint in sorted(ran & set(LINTS)):
        # The skill's own failure probe: a failing lint must fail a step that ran it.
        if not any(rc != 0 for rc, x in execute(lint) if lint in x):
            fail.append("%s can fail without failing its step (a dropped exit code)" % lint)
if "pnpm test" not in wf:
    fail.append("tests no longer run")
m = re.search(r"cancel-in-progress:\s*(.+)", wf)
if m and m.group(1).strip() in ("true", "'true'", '"true"'):
    fail.append("cancel-in-progress is always true, so runs on main get cancelled too")
g = re.search(r"concurrency:\s*\n\s+group:\s*(.+)", wf)
if g and not re.search(r"run_id|run_number|github\.sha|event_name", g.group(1)):
    fail.append("pushes to main share one concurrency group, so a pending run on main gets replaced")
if not re.search(r"^\s*push:", wf, re.M):
    fail.append("main no longer runs CI")
fail += cheats_in_diff(d)
if not os.path.exists(os.path.join(d, "PR.md")):
    fail.append("no PR.md")
print("\n".join("FAIL: " + f for f in fail) or "PASS: %d jobs, every lint and the tests kept" % len(jobs))
sys.exit(1 if fail else 0)
