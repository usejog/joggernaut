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


def yaml_load(text):
    """The YAML a workflow uses: mappings, lists (indented or not), block scalars (| >),
    inline {a: b} and [a, b], quoted and plain scalars. Enough to read jobs, steps, env,
    defaults, shell and working-directory as GitHub does."""
    lines = [l.rstrip("\n") for l in text.split("\n")]
    ind = lambda l: len(l) - len(l.lstrip(" "))
    blank = lambda l: not l.strip() or l.lstrip().startswith("#")

    def scalar(v):
        v = v.strip()
        q = re.match(r"""^(['"])(.*?)\1(\s+#.*)?$""", v)
        if q:
            return q.group(2)
        v = re.sub(r"\s+#.*$", "", v)
        if v.startswith("{") and v.endswith("}"):
            return {k.strip(): scalar(x) for k, _, x in (p.partition(":") for p in v[1:-1].split(",") if ":" in p)}
        if v.startswith("[") and v.endswith("]"):
            return [scalar(x) for x in v[1:-1].split(",") if x.strip()]
        return v

    def skip(i):
        while i < len(lines) and blank(lines[i]):
            i += 1
        return i

    def block(i, col, style):
        """A block scalar's lines, deeper than col, from line i."""
        body = []
        while i < len(lines) and (not lines[i].strip() or ind(lines[i]) > col):
            body.append(lines[i])
            i += 1
        while body and not body[-1].strip():
            body.pop()
        pad = min((ind(l) for l in body if l.strip()), default=0)
        body = [l[pad:] for l in body]
        if style != ">":
            return "\n".join(body), i
        # Folded: lines join with a space; a blank line, or a more indented line, keeps the break.
        text, prev = "", None
        for l in body:
            if not l.strip():
                text += "\n"
                prev = None
            elif prev is None or l.startswith(" ") or prev.startswith(" "):
                text += ("\n" if prev is not None else "") + l
                prev = l
            else:
                text += " " + l
                prev = l
        return text, i

    def node(i, col):
        """The value starting at line i, indented col: a list or a mapping."""
        i = skip(i)
        if i < len(lines) and lines[i][col:].startswith("- "):
            out = []
            while True:
                i = skip(i)
                if i >= len(lines) or ind(lines[i]) != col or not lines[i][col:].startswith("- "):
                    return out, i
                rest = lines[i][col + 2:]
                if re.match(r"^[\w.-]+:(\s|$)", rest.lstrip()):
                    lines[i] = " " * (col + 2) + rest.lstrip()
                    item, i = mapping(i, col + 2)
                else:
                    item, i = scalar(rest), i + 1
                out.append(item)
        return mapping(i, col)

    def mapping(i, col):
        out = {}
        while True:
            i = skip(i)
            if i >= len(lines) or ind(lines[i]) != col or lines[i][col:].startswith("- "):
                return out, i
            m = re.match(r"^([^:#][^:]*?):(?:\s+(.*))?$", lines[i][col:])
            if not m:
                return out, i
            k, v = m.group(1).strip().strip("'\""), (m.group(2) or "").strip()
            i += 1
            if v[:1] in ("|", ">"):
                out[k], i = block(i, col, v[0])
            elif v and not v.startswith("#"):
                out[k] = scalar(v)
            else:
                j = skip(i)
                if j < len(lines) and (ind(lines[j]) > col or (ind(lines[j]) == col and lines[j][col:].startswith("- "))):
                    out[k], i = node(j, ind(lines[j]))
                else:
                    out[k] = None
    return node(skip(0), ind(lines[skip(0)]) if skip(0) < len(lines) else 0)[0]


def run_steps():
    """Every `run:` step of every workflow, with what GitHub gives it: its shell (the step's,
    else the job's defaults, else the workflow's), working directory the same way, and its
    env (workflow's, then job's, then step's)."""
    out = []
    for f in sorted(os.listdir(os.path.join(d, ".github/workflows"))):
        doc = yaml_load(open(os.path.join(d, ".github/workflows", f)).read())
        if not isinstance(doc, dict):
            continue
        run_of = lambda x: ((x or {}).get("defaults") or {}).get("run") or {}
        for job_id, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict) or "run" not in step:
                    continue
                pick = lambda k: step.get(k) or run_of(job).get(k) or run_of(doc).get(k)
                env = {}
                for e in (doc.get("env"), job.get("env"), step.get("env")):
                    env.update({str(k): str(v) for k, v in (e or {}).items()} if isinstance(e, dict) else {})
                out.append((str(step["run"] or ""), pick("shell"), pick("working-directory"), env,
                            "%s: %s, step %d" % (f, job_id, (job.get("steps") or []).index(step) + 1)))
    return out


# GitHub's shells: unset is `bash -e {0}`; `shell: bash` adds pipefail; `sh` is `sh -e {0}`;
# any other is a template with {0} for the script's file.
SHELLS = {None: "bash -e {0}", "bash": "bash --noprofile --norc -eo pipefail {0}", "sh": "sh -e {0}"}
# Stubs: a package manager records the script it was asked to run (`pnpm run lint:ts`, or
# `pnpm lint:ts`; options and their values skipped) and fails when it is $FAIL_SCRIPT; npx
# and node do nothing.
# npm runs a script only through `npm run` (or `run-script`); pnpm and yarn take a bare name too.
NPM = ('#!/bin/sh\nwhile [ $# -gt 0 ]; do case $1 in -*) shift ;; *) break ;; esac; done\n'
       'case ${1:-} in run|run-script) shift ;; *) exit 0 ;; esac\n'
       'while [ $# -gt 0 ]; do case $1 in -*) shift ;; *) break ;; esac; done\n'
       '[ -n "${1:-}" ] || exit 0\necho "$1" >>"$LOG"\n[ "$1" != "${FAIL_SCRIPT:-}" ]\n')
PM = ('#!/bin/sh\nfor a; do [ "${prev:-}" != --filter ] && [ "${prev:-}" != -F ] || case $a in .|"$PKG"|"*"|./) ;;'
      ' *) exit 0 ;; esac; prev=$a; done\n'  # a filter matching no package runs nothing, and succeeds
      'skip() { while [ $# -gt 0 ]; do case $1 in --filter|-F|-C|--dir|--workspace) shift 2 ;;'
      ' -*) shift ;; *) break ;; esac; done; echo "$@"; }\n'
      'set -- $(skip "$@")\n'
      'case ${1:-} in run|run-script) shift; set -- $(skip "$@") ;; exec|dlx|install|i|ci|add) exit 0 ;; esac\n'
      '[ -n "${1:-}" ] || exit 0\necho "$1" >>"$LOG"\n[ "$1" != "${FAIL_SCRIPT:-}" ]\n')
NOOP = '#!/bin/sh\nexit 0\n'
try:
    import json as _json
    PKG = _json.load(open(os.path.join(d, "package.json"))).get("name") or ""
except (OSError, ValueError):
    PKG = ""
LINTS = ["lint:%s" % j for j in ["ts", "css", "md", "yaml", "json", "spell", "licenses"]]
steps = run_steps()
with tempfile.TemporaryDirectory() as t:
    os.makedirs(t + "/bin")
    for tool, body in (("pnpm", PM), ("npm", NPM), ("yarn", PM), ("npx", NOOP), ("node", NOOP)):
        open(t + "/bin/" + tool, "w").write(body)
        os.chmod(t + "/bin/" + tool, 0o755)

    def execute(fail_script=""):
        """Every step, in a fresh copy of the repository, as GitHub runs it (expressions
        blanked): its exit status, and the lint scripts it asked a package manager to run."""
        got, job = [], None
        for k, (step, shell, sub, extra, where) in enumerate(steps):
            if where.rsplit(", step", 1)[0] != job:
                # Each job runs on a fresh machine: a fresh copy of the repository and home.
                job = where.rsplit(", step", 1)[0]
                work = tempfile.mkdtemp(dir=t)
                shutil.copytree(d, work, dirs_exist_ok=True)
                home = tempfile.mkdtemp(dir=t)
                files = {k_: os.path.join(home, k_.lower()) for k_ in ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT",
                                                                       "GITHUB_ENV", "GITHUB_PATH")}
            template = SHELLS.get(shell, shell)
            if "{0}" not in template:
                template += " {0}"
            script = "%s/step%d.sh" % (t, k)
            open(script, "w").write(re.sub(r"\$\{\{[^}]*\}\}", "", step) + "\n")
            log = "%s/log%d" % (t, k)
            env = dict(extra, PATH=t + "/bin:/usr/bin:/bin", HOME=home, LOG=log, FAIL_SCRIPT=fail_script,
                       PKG=PKG, CI="true", GITHUB_ACTIONS="true", **files)
            try:
                rc = subprocess.run([x.replace("{0}", script) for x in template.split()],
                                    cwd=os.path.join(work, sub) if sub else work, env=env,
                                    capture_output=True, timeout=30).returncode
            except (subprocess.TimeoutExpired, OSError) as e:
                rc = "timed out" if isinstance(e, subprocess.TimeoutExpired) else "can't run %s" % template
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
            fail.append("a step fails with every lint passing (exit %s): %s" % (rc, steps[k][4]))
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
