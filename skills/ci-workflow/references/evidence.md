# Evidence for ci-workflow

Public posts this skill relies on, each re-read at its link. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Linear engineering blog, 21 Sep 2026](https://linear.app/now/ci-bottleneck-reworked) | Seven small checks folded into two jobs that run the tasks concurrently, paying setup twice instead of seven times: roughly 87,000 runner-minutes a month saved, 11.8% of total CI usage (based on June usage). | A |
| [Tw93 (@HiTw93), ten-step prompt, 2 Nov 2026](https://x.com/HiTw93/status/2117254652404044064) | A ten-step prompt: pull the last 50 runs and split queue, setup and run; cancel superseded runs but never on main; path filters can leave a required check pending. No measured result of its own; cited for the checklist. | D |
