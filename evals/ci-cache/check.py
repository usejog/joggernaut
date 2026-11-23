"""ci-cache eval: the cache is never saved on main, so every new PR starts cold.
The fix must make a run on main save the cache, and keep build and tests."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from cheats import cheats_in_diff
d = sys.argv[1]
strip_comments = lambda t: "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
fail = []
wf = ""
for f in sorted(os.listdir(os.path.join(d, ".github/workflows"))):
    wf += strip_comments(open(os.path.join(d, ".github/workflows", f)).read()) + "\n"
# Some workflow must run on push (to main, or to every branch, which includes main).
def pushes_to_main(text):
    on = re.search(r"^on:(.*?)(?=^\S)", text + "\nend:", re.M | re.S)
    block = on.group(0) if on else ""
    if re.search(r"^on:\s*\[?[^\n]*\bpush\b", block, re.M):
        return True
    m = re.search(r"^\s+push:[ \t]*(\n(\s{4,}.*\n?)*)?", block, re.M)
    if not m:
        return False
    body = m.group(0)
    if re.search(r"branches-ignore:[^\n]*\bmain\b", body):
        return False
    return "branches" not in body or re.search(r"\bmain\b|default-branch", body) is not None
pushes_main = any(pushes_to_main(strip_comments(open(os.path.join(d, ".github/workflows", f)).read()))
                  for f in os.listdir(os.path.join(d, ".github/workflows")))
if not pushes_main:
    fail.append("no workflow runs on push to main, so main still never saves the cache")
if "actions/cache" not in wf and "cache: pnpm" not in wf and "cache: 'pnpm'" not in wf:
    fail.append("the pnpm cache is gone")
for cmd in ("pnpm build", "pnpm test"):
    if cmd not in wf:
        fail.append("%s no longer runs" % cmd)
if re.search(r"if:.*cache-hit", wf):
    fail.append("a step is skipped on cache hit")
fail += cheats_in_diff(d)
if not os.path.exists(os.path.join(d, "PR.md")):
    fail.append("no PR.md")
print("\n".join("FAIL: " + f for f in fail) or "PASS: main now saves the cache; build and tests kept")
sys.exit(1 if fail else 0)
