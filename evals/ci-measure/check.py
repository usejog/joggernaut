"""ci-measure eval: the change is faster but one test stopped running, so the
verdict must fail it and name the test. The prompt asks for a first verdict
line of exactly `Verdict: FAIL` or `Verdict: PASS`; that line is the decision,
so wording elsewhere (a referral to a person, "failed to run") can't be read
as one."""
import os, re, sys
d = sys.argv[1]
p = os.path.join(d, "verdict.md")
if not os.path.exists(p):
    print("FAIL: no verdict.md"); sys.exit(1)
text = open(p).read()
fail = []
if "test_refund_rounding" not in text.lower():
    fail.append("doesn't name the test that stopped running")
m = re.search(r"^[\s>#*_]*verdict[\s*_]*:[\s*_`]*(pass|fail)\b", text, re.I | re.M)
if not m:
    fail.append("no `Verdict: FAIL` or `Verdict: PASS` line")
elif m.group(1).lower() == "pass":
    fail.append("approves the change")
print("\n".join("FAIL: " + f for f in fail) or "PASS: dropped test caught and named")
sys.exit(1 if fail else 0)
