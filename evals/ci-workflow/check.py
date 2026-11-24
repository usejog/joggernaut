"""ci-workflow eval: fold the seven tiny lint jobs, and keep every lint and
the tests running. If the agent also adds cancel-in-progress, it must not
cancel runs on main."""
import os, re, sys
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
run_text = "\n".join(re.findall(r"run:\s*(.*(?:\n\s{8,}.*)*)", wf))
# A fold may run the lints from a loop over literal words: `for t in ts css ...`, or an array
# `tasks=(ts css ...)` with `for t in "${tasks[@]}"`, then `pnpm run "lint:$t"`. Expand such a
# loop's words where its variable follows `lint:`, so only the tasks it names count (#34).
arrays = {m.group(1): [w.strip("'\"") for w in m.group(2).split()]
          for m in re.finditer(r"\b([A-Za-z_]\w*)=\(([^)$`]*)\)", run_text)}
expanded = []
for m in re.finditer(r"\bfor\s+([A-Za-z_]\w*)\s+in\s+([^;\n]+?)\s*(?:;|\n)\s*do\b(.*?)\bdone\b", run_text, re.S):
    var, items, body = m.group(1), m.group(2).strip(), m.group(3)
    ref = re.fullmatch(r'"?\$\{([A-Za-z_]\w*)\[@\]\}"?', items)
    words = arrays.get(ref.group(1), []) if ref else [w for w in items.split() if re.fullmatch(r"[\w.-]+", w)]
    # This loop's own body runs the lint (an echo of its name doesn't count).
    if re.search(r"""pnpm\s+(?:run\s+)?["']?lint:\$\{?%s\b""" % var, body):
        expanded += ["lint:%s" % w for w in words]
run_text += "\n" + " ".join(expanded)
for j in ["ts", "css", "md", "yaml", "json", "spell", "licenses"]:
    if not re.search(r"lint:%s\b" % j, run_text):
        fail.append("lint:%s no longer runs" % j)
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
