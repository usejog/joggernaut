"""ci-diagnose eval: the cold pnpm cache must rank first, above the tiny lint jobs,
and nothing tracked may change (the skill is read-only)."""
import re, subprocess, sys, os
d = sys.argv[1]
fail = []
p = os.path.join(d, "diagnosis.md")
if not os.path.exists(p):
    print("FAIL: no diagnosis.md"); sys.exit(1)
text = open(p).read().lower()
# Fix #1 as a numbered list item ("1. ...") or as a table row ("| 1 | ...").
m = re.search(r"^\s*(?:[#*>\-\s]*)(?:\*\*)?1[.)]\s*(.+)$|^\s*\|\s*(?:#\s*)?1\s*\|\s*(.+)$", text, re.M)
first = (m.group(1) or m.group(2)) if m else ""
if not re.search(r"cache|cold|install", first):
    fail.append("fix #1 is not the cold cache: %r" % first[:120])
if not re.search(r"main|default branch|pull_request|push", text):
    fail.append("doesn't say the cache is never saved on main")
if not re.search(r"lint|tiny|small job|seven", text):
    fail.append("doesn't mention the tiny lint jobs")
changed = subprocess.run(["git", "-C", d, "diff", "--stat", "sample"], capture_output=True, text=True).stdout.strip() or \
    subprocess.run(["git", "-C", d, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
if changed:
    fail.append("changed tracked files: " + changed.replace("\n", "; "))
print("\n".join("FAIL: " + f for f in fail) or "PASS: cold cache ranked first; read-only")
sys.exit(1 if fail else 0)
