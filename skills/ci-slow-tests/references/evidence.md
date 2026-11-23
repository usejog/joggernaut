# Evidence for ci-slow-tests

Public posts this skill relies on, each re-read at its link. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Rodrigo Roim, OpenAI Developers blog (Core Experimentation team), 14 Oct 2026](https://developers.openai.com/blog/maintaining-software-with-the-gpt-6-family) | A missing mock cut a 63-test suite from 592.6 s to 29.8 s, with all 63 tests retained. | A |
| [Linear engineering blog, 21 Sep 2026](https://linear.app/now/ci-bottleneck-reworked) | Turning off Vitest isolation, opt-in for eligible files with teardown, took the slowest shard from roughly 300–379 s to about 195 s. | A |
| [Sean Ireton (@sireton_builds), Sidelab, 4 Nov 2026](https://x.com/sireton_builds/status/2117864723404451924) | After speeding up a slow test, the agent broke the code on purpose to make sure the faster test still catches the bug. | A |
