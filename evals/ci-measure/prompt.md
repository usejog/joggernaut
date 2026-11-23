Use the ci-measure skill to check the claim in `CHANGE.md`: did this change
make CI faster, honestly?

This sample repository has no GitHub remote. The runs before and after the
change are recorded in `ci-history/before.jsonl` and `ci-history/after.jsonl`
(the format `measure.py fetch` writes), and the test reports in
`ci-history/junit-before/` and `ci-history/junit-after/`. Use them in place of
fetching. Write your verdict to `verdict.md`. Its first line reads exactly
`Verdict: FAIL` or `Verdict: PASS`; then, for each test that stopped running,
a line `Stopped running: <the test's name>`.
