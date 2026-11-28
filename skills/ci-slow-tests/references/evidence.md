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
| [Evil Martians (Igor Platonov, Travis Turner), on its client Whop's suite, 3 Sep 2025](https://evilmartians.com/chronicles/the-whop-chop-how-we-cut-a-rails-test-suite-and-ci-time-in-half) | Evil Martians measured the work it was paid to do on Whop's CI (DECISIONS.md, 27 Nov 2026). In `config/environments/test.rb`: `verbose_query_logs` and query log tags off, `log_level = :fatal`; a custom Sentry logger still ran in tests, so the team faked Sentry. "CI Run (16 parallel processes)": "Before: ~4 minutes", "After: ~2 minutes", the three changes together; "Disabling the verbose query logs did the heavy lifting, with the Sentry optimization providing an additional gain." The test count isn't given. | A |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026 (the Rails
entry read on 27 Nov 2026). A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): each job gets a fresh environment: a new virtual machine, or for single-CPU `ubuntu-slim` a new container on a shared VM (15-minute job limit); `ubuntu-latest` has 4 CPUs on public repositories and 2 on private ones.
- [GitHub Docs: Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing): GitHub rounds the minutes and partial minutes each job uses up to the nearest whole minute.
- [Vitest: `isolate`](https://vitest.dev/config/isolate): defaults to `true`, running each test file in an isolated environment.
- [Rails guides: configuring, `config.log_level`](https://guides.rubyonrails.org/configuring.html#config-log-level): "This option defaults to `:debug` for all environments except production, where it defaults to `:info`."
