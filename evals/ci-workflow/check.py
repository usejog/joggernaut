"""ci-workflow eval: fold the seven tiny lint jobs, and keep every lint and
the tests running. If the agent also adds cancel-in-progress, it must not
cancel runs on main.

Every lint must still run, and fail its step when it fails: each `run:` step
is executed in a fresh copy with the shell GitHub would use (bash -e, or bash
-eo pipefail with `shell: bash`) against a stub `pnpm` that records the
scripts it is asked to run and fails the one named in $FAIL_SCRIPT. A
loop over the lints, run in the background, passes only if a failing lint
still fails the step."""
import os, re, shutil, subprocess, sys, tempfile
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


# A `defaults: run: shell:` stands for every step that names none.
default_shell = None
for f in sorted(os.listdir(os.path.join(d, ".github/workflows"))):
    m_ = re.search(r"^\s*defaults:\s*\n\s+run:\s*\n(?:\s+\S.*\n)*?\s+shell:\s*(\S+)",
                   strip_comments(open(os.path.join(d, ".github/workflows", f)).read()) + "\n", re.M)
    default_shell = default_shell or (m_.group(1) if m_ else None)


def run_steps(text):
    """Each step's `run:` value and its `shell:` (None when unset): a one-line value, or a block
    scalar (| or >) of the lines indented past the `run` key. Sibling keys of the step sit at
    the key's own column."""
    lines, out = text.split("\n"), []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*(?:-\s+)?)run:\s*(.*)$", line)
        if not m:
            continue
        col, value = len(m.group(1)), m.group(2).strip()
        indent = lambda l: len(l) - len(l.lstrip())
        if value[:1] in ("|", ">"):
            block, j = [], i + 1
            while j < len(lines) and (not lines[j].strip() or indent(lines[j]) > col):
                block.append(lines[j])
                j += 1
            pad = min((indent(l) for l in block if l.strip()), default=0)
            body = [l[pad:] for l in block]
            script = " ".join(l.strip() for l in body if l.strip()) if value[0] == ">" else "\n".join(body)
        else:
            script = value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"" else value
        # The step's other keys sit at the key's column, between the step's `- ` and the next
        # line as shallow as that dash.
        key_col = lambda l: indent(l) + (2 if l.lstrip().startswith("- ") else 0)
        start = i
        while not lines[start].lstrip().startswith("- ") and start > 0 and (
                not lines[start - 1].strip() or key_col(lines[start - 1]) >= col):
            start -= 1
        end = i + 1
        while end < len(lines) and (not lines[end].strip() or indent(lines[end]) > col - 2):
            end += 1
        shell, cwd, env = None, None, {}
        for j in range(start, end):
            l = lines[j]
            if key_col(l) != col:
                continue
            mm = re.match(r"^\s*(?:-\s+)?(shell|working-directory|env):\s*(.*)$", l)
            if not mm:
                continue
            k, v = mm.group(1), mm.group(2).strip().strip("'\"")
            if k == "shell":
                shell = v
            elif k == "working-directory":
                cwd = v
            elif v.startswith("{"):
                env.update((a.strip(), b.strip().strip("'\"")) for a, b in
                           (x.split(":", 1) for x in v.strip("{}").split(",") if ":" in x))
            else:
                for l2 in lines[j + 1:end]:
                    if not l2.strip() or key_col(l2) <= col:
                        break
                    a, _, b = l2.strip().partition(":")
                    env[a.strip()] = b.strip().strip("'\"")
        out.append((script, shell or default_shell, cwd, env))
    return out


# GitHub's shells: unset is `bash -e {0}`; `shell: bash` adds pipefail; `shell: sh` is `sh -e`.
SHELLS = {None: ["bash", "-e", "-c"], "bash": ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"],
          "sh": ["sh", "-e", "-c"], "bash {0}": ["bash", "-c"], "sh {0}": ["sh", "-c"]}
# Stubs: a package manager records the script it was asked to run (`pnpm run lint:ts`, or
# `pnpm lint:ts`) and fails when it is $FAIL_SCRIPT; npx and node do nothing.
PM = ('#!/bin/sh\nwhile [ $# -gt 0 ]; do case $1 in -*) shift ;; *) break ;; esac; done\n'
      'case ${1:-} in run|run-script) shift; while [ $# -gt 0 ]; do case $1 in -*) shift ;; *) break ;; esac; done ;;'
      ' exec|dlx|install|i|ci|add) exit 0 ;; esac\n'
      '[ -n "${1:-}" ] || exit 0\necho "$1" >>"$LOG"\n[ "$1" != "${FAIL_SCRIPT:-}" ]\n')
NOOP = '#!/bin/sh\nexit 0\n'
LINTS = ["lint:%s" % j for j in ["ts", "css", "md", "yaml", "json", "spell", "licenses"]]
steps = run_steps(wf)
with tempfile.TemporaryDirectory() as t:
    os.makedirs(t + "/bin")
    for tool, body in (("pnpm", PM), ("npm", PM), ("yarn", PM), ("npx", NOOP), ("node", NOOP)):
        open(t + "/bin/" + tool, "w").write(body)
        os.chmod(t + "/bin/" + tool, 0o755)

    def execute(fail_script=""):
        """Every step, in a fresh copy of the repository, as GitHub runs it (expressions
        blanked): its exit status, and the lint scripts it asked a package manager to run."""
        got = []
        work = tempfile.mkdtemp(dir=t)
        shutil.copytree(d, work, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
        for k, (step, shell, sub, extra) in enumerate(steps):
            if shell not in SHELLS:
                got.append(("shell %s can't be run here" % shell, set()))
                continue
            log = "%s/log%d" % (t, k)
            env = dict(extra, PATH=t + "/bin:/usr/bin:/bin", HOME=t, LOG=log, FAIL_SCRIPT=fail_script)
            try:
                rc = subprocess.run(SHELLS[shell] + [re.sub(r"\$\{\{[^}]*\}\}", "", step)],
                                    cwd=os.path.join(work, sub) if sub else work, env=env,
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
            fail.append("a step fails with every lint passing (exit %s): %s" % (rc, steps[k][0].strip()[:80]))
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
