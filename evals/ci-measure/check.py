"""ci-measure eval: the change is faster but one test stopped running, so the
verdict must fail it and name the test. The prompt asks for a first line of
exactly `Verdict: FAIL` or `Verdict: PASS`; that line is the decision,
so wording elsewhere (a referral to a person, "failed to run") can't be read
as one."""
import os, re, sys
d = sys.argv[1]
p = os.path.join(d, "verdict.md")
if not os.path.exists(p):
    print("FAIL: no verdict.md"); sys.exit(1)
text = open(p).read()
fail = []
if not re.search(r"\btest_refund_rounding\b", text):
    fail.append("doesn't name the test that stopped running")
first = (text.lstrip("\ufeff").splitlines() or [""])[0].strip()
if first == "Verdict: PASS":
    fail.append("approves the change")
elif first != "Verdict: FAIL":
    fail.append("the first line isn't exactly `Verdict: FAIL` or `Verdict: PASS`")
print("\n".join("FAIL: " + f for f in fail) or "PASS: dropped test caught and named")
sys.exit(1 if fail else 0)
