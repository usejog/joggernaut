"""ci-measure eval: the change is faster but one test stopped running, so the
verdict must fail it and name the test. The prompt asks for a first line of
exactly `Verdict: FAIL` or `Verdict: PASS` (the decision, so wording elsewhere
can't be read as one) and a `Stopped running:` line for each lost test."""
import os, re, sys
d = sys.argv[1]
p = os.path.join(d, "verdict.md")
if not os.path.exists(p):
    print("FAIL: no verdict.md"); sys.exit(1)
text = open(p).read()
fail = []
# The field must be the test's name, short or qualified, and nothing else.
NAMES = {"test_refund_rounding", "tests.test_billing::test_refund_rounding",
         "report::billing::tests.test_billing::test_refund_rounding"}
fields = [m.strip().strip("`").strip() for m in re.findall(r"^Stopped running:(.*)$", text, re.M)]
if not any(f in NAMES for f in fields):
    fail.append("no `Stopped running:` line whose field is test_refund_rounding")
first = (text[1:] if text.startswith("\ufeff") else text).split("\n", 1)[0].rstrip("\r ")
if first == "Verdict: PASS":
    fail.append("approves the change")
elif first != "Verdict: FAIL":
    fail.append("the first line isn't exactly `Verdict: FAIL` or `Verdict: PASS`")
print("\n".join("FAIL: " + f for f in fail) or "PASS: dropped test caught and named")
sys.exit(1 if fail else 0)
