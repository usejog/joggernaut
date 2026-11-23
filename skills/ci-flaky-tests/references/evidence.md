# Evidence for ci-flaky-tests

Public posts this skill relies on, each re-read at its link on 23 Nov 2026. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Rocky Warren, Clipboard engineering blog, 21 Apr 2026](https://www.clipboard.com/resources/blog/agents-cant-iterate-against-tests-that-lie) | Given the error, the stack trace and the code, "nearly all will add a retry or increase timeouts". End-to-end flake rate went from 100% to under 15% in six weeks; the post credits deleting, converting and combining end-to-end tests (174 to 87) with the largest reduction; it also built custom error reports for agents (no figure given). | A |
| [Fritz Meissner, thoughtbot blog, 22 Jun 2026](https://thoughtbot.com/blog/what-it-took-to-use-this-overnight-ai-solution) | Claude Code ran a flaky test group hundreds of times, in growing batches, after prompting not to conclude early, steered by an engineer of over ten years who calls that experience necessary; 60% of CI runs had been failing on the group, which was taken out of CI meanwhile; it went back into CI with 0% failures on main three weeks later. | B |
| [pingdotgg/t3code pull request #22560, merged 21 Oct 2026](https://github.com/pingdotgg/t3code/pull/22560) | A lint rule bans per-test timeouts and unexplained skips; the PR description reports 58 overrides removed across 17 files, and that the genuinely flaky tests all waited on real time, scheduler budgets or renderer frames. Made with Claude Code. | A |
