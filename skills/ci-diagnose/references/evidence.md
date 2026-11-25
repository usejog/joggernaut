# Evidence for ci-diagnose

Public posts this skill relies on, each re-read at its link on 23 Nov 2026. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | An agent pulled the last 150 runs and split every job into waiting, setup and running; it found half the test jobs missing the dependency cache, a bug that had lasted all year. PR wait went from up to 40 minutes to 2, with other changes in the same effort. | A |
| [Rodrigo Roim, OpenAI Developers blog (Core Experimentation team), 14 Oct 2026](https://developers.openai.com/blog/maintaining-software-with-the-gpt-6-family) | Asked Codex for ideas ranked by estimated CI minutes saved per day, from run history; median CI roughly 10 → 4.5 minutes and p90 12.5 → 6 minutes over about 30 pull requests. | A |
| [@LimestoneHQ (Limestone Digital, a vendor), 3 Nov 2026](https://x.com/LimestoneHQ/status/2117568557924094225) | On GitHub's public cli/cli, job time split 3% waiting, 20% setup, 67% running (the other 10% cleanup or unaccounted) (a vendor's measurement, 19 runs). Shows setup isn't always the biggest share. | C |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026. A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): a pull request's run can restore caches from its own branch, the default branch and its base branch, and saves to `refs/pull/N/merge`; a saved cache can't be changed; 10 GB per repository unless raised, then the least recently used caches are deleted first.
- [GitHub Docs: workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): `timeout-minutes` defaults to 360; a workflow skipped by path, branch or commit-message filtering leaves its checks pending, which blocks a pull request that requires them.
- [GitHub Docs: control workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency): by default a group holds at most one pending run, and a newer one cancels it; `cancel-in-progress` also cancels the running one.
- [GitHub Docs: GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): each job gets a fresh environment: a new virtual machine, or for single-CPU `ubuntu-slim` a new container on a shared VM (15-minute job limit); `ubuntu-latest` has 4 CPUs on public repositories and 2 on private ones.
- [GitHub Docs: events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): for `pull_request`, `GITHUB_SHA` is the last merge commit on `refs/pull/N/merge`, and the default activity types are opened, synchronize and reopened, so a push to a pull request can start every workflow subscribed to `synchronize` (the default), unless a filter skips it, the pull request has a merge conflict, or a run from a fork waits for approval ("Workflows will not run on pull_request activity if the pull request has a merge conflict").
- [GitHub Docs: managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue): required workflows need the `merge_group` trigger, or the queue's required checks never report.
- [GitHub Docs: REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api): 5,000 requests an hour for a signed-in user.
- [GitHub Docs: Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing): GitHub rounds the minutes and partial minutes each job uses up to the nearest whole minute.
- [GitHub Docs: Actions limits](https://docs.github.com/en/actions/reference/limits): concurrent jobs on standard hosted runners are capped by plan (Free: 20, of them 5 macOS).
- [GitHub Docs: GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions): "Standard GitHub-hosted runners in public repositories" and "Self-hosted runners" remain free; storage is billed on its own terms.
- [actions/setup-node README](https://github.com/actions/setup-node/blob/main/README.md): "Caching for npm dependencies is automatically enabled when your `package.json` contains either `devEngines.packageManager` field or top-level `packageManager` field set to `npm`, and no explicit cache input is provided." (Breaking changes in V6); V5 "Enabled caching by default with package manager detection if no cache input is provided." `package-manager-cache: false` turns it off.
