# Evidence for ci-slow-tests

Public posts this skill relies on, each re-read at its link on 23 Nov 2026
(rows added on 27 Nov 2026: read that day). Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Rodrigo Roim, OpenAI Developers blog (Core Experimentation team), 14 Oct 2026](https://developers.openai.com/blog/maintaining-software-with-the-gpt-6-family) | Adding a missing mock cut a 63-test suite from 592.6 s to 29.8 s, with all 63 tests retained. | A |
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | Vitest gave every test file a fresh worker that imported the whole app; with `isolate: false`, each shard went from 100 seconds to 35, with a hook that resets state after every file. | A |
| [Linear engineering blog, 21 Sep 2026](https://linear.app/now/ci-bottleneck-reworked) | Turning off Vitest isolation, opt-in for eligible files with teardown, took the slowest shard from roughly 300–379 s to about 195 s. | A |
| [Sean Ireton (@sireton_builds), Sidelab, 4 Nov 2026](https://x.com/sireton_builds/status/2117864723404451924) | After speeding up a slow test, the agent broke the code on purpose to make sure the faster test still catches the bug. | A |
| [Pinterest Engineering, Pinterest's own community summary of its engineering post, 4 Dec 2025](https://community.pinterest.biz/t/from-the-engineering-blog-pinterest-s-journey-to-faster-android-testing/40968) | Android end-to-end tests: "instead of giving each group the same number of tests, we grouped them based on how long they usually take"; "our new system shaved over nine minutes off the total test time, speeding things up by more than 36%". The original Medium post refuses automated reads. | A |
| [StoatFlow (Hartmut Armbruster), 26 Aug 2026, postscript of 10 Oct](https://stoatflow.io/blog/ci-runner-platform-case-study) | GitHub Actions on a third-party runner, the `integration-test` job on the same 8 vCPU: six forks 23m53s, since Gradle "deals test classes to forks round-robin when the task starts"; twelve forks 16m40s–18m16s; 13 groups that "follow functional areas", the three largest "split by measured duration", 10m43s. One run each, as the page gives them. | A |
| [Home Assistant developers' blog, 9 May 2024](https://contributors.home-assistant.io/blog/2024/05/09/improving-ci-test-execution) | "Each pytest job needed to discover all tests"; a separate job now discovers and splits them into 10 groups: "Not doing full-discovery in each test runner saves us 3 hours on each full run!" (runner time). Its monthly figure, "would have saved around 4042 hours", is computed, not measured. | A |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026. A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): each job gets a fresh environment: a new virtual machine, or for single-CPU `ubuntu-slim` a new container on a shared VM (15-minute job limit); `ubuntu-latest` has 4 CPUs on public repositories and 2 on private ones.
- [GitHub Docs: Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing): GitHub rounds the minutes and partial minutes each job uses up to the nearest whole minute.
- [Vitest: `isolate`](https://vitest.dev/config/isolate): defaults to `true`, running each test file in an isolated environment.
- [pytest-split README](https://github.com/jerry-git/pytest-split): `--store-durations` writes `.test_durations` to keep in the repository; a test with no recorded duration gets the average; `duration_based_chunks`, the default, "is **incompatible** with test-order-randomization plugins", which can put some tests in several groups and others in none; `least_duration` is not.
- [Playwright: sharding](https://playwright.dev/docs/test-sharding): `--shard=x/y`; "Playwright Test defaults to file-level granularity, meaning entire test files are assigned to shards".
