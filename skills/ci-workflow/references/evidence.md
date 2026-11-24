# Evidence for ci-workflow

Public posts this skill relies on, each re-read at its link on 23 Nov 2026. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Linear engineering blog, 21 Sep 2026](https://linear.app/now/ci-bottleneck-reworked) | Seven small checks folded into two jobs that run the tasks concurrently, paying setup twice instead of seven times: roughly 87,000 runner-minutes a month saved, 11.8% of total CI usage (based on June usage). | A |
| [Tw93 (@HiTw93), ten-step prompt, 2 Nov 2026](https://x.com/HiTw93/status/2117254652404044064) | A ten-step prompt: pull the last 50 runs and split queue, setup and run; cancel superseded runs but never on main; path filters can leave a required check pending. No measured result of its own; cited for the checklist. | D |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026. A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: control workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency): by default a group holds at most one pending run, and a newer one cancels it; `cancel-in-progress` also cancels the running one.
- [GitHub Docs: workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): `timeout-minutes` defaults to 360; a workflow skipped by path, branch or commit-message filtering leaves its checks pending, which blocks a pull request that requires them; steps marked `background`, or grouped under `parallel:`, run at once, "every step in the group runs as a background step, with an implicit `wait` at the end of the group", a failed background step fails the job at the next `wait` or `wait-all` that includes it, and at most 10 background steps run at once in a job ([changelog, 25 Jun 2026](https://github.blog/changelog/2026-06-25-actions-steps-can-now-be-run-in-parallel/)).
- [GitHub Docs: control jobs with conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions): a job skipped by a condition reports "Success" and doesn't block a merge, even as a required check.
- [GitHub Docs: Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing): GitHub rounds the minutes and partial minutes each job uses up to the nearest whole minute.
- [GitHub Docs: GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): each job gets a fresh environment: a new virtual machine, or for single-CPU `ubuntu-slim` a new container on a shared VM (15-minute job limit); `ubuntu-latest` has 4 CPUs on public repositories and 2 on private ones. Self-hosted runners can keep state between jobs.
- [actions/checkout README](https://github.com/actions/checkout#usage): one commit is fetched by default; `fetch-depth: 0` fetches all history; `filter` makes a partial clone; depth and filter are separate inputs.
- [GitHub blog: partial and shallow clones](https://github.blog/open-source/git/get-up-to-speed-with-partial-clone-and-shallow-clone/): a blobless clone (`--filter=blob:none`) downloads all commits and trees, and blobs only as they are checked out.
- [GitHub Docs: workflow cancellation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation): on cancel, "the server re-evaluates `if` conditions for all currently running jobs … the condition `if: always()` would evaluate to true and the job continues to run."
- [GitHub Docs: troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks): "Successful check statuses are success, skipped, and neutral"; "Required checks must pass on the latest commit SHA."
