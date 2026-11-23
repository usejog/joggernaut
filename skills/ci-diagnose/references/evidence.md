# Evidence for ci-diagnose

Public posts this skill relies on, each re-read at its link. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | An agent pulled the last 150 runs and split every job into waiting, setup and running; it found half the test jobs missing the dependency cache, a bug that had lasted all year. PR wait went from up to 40 minutes to 2, with other changes in the same effort. | A |
| [Rodrigo Roim, OpenAI Developers blog (Core Experimentation team), 14 Oct 2026](https://developers.openai.com/blog/maintaining-software-with-the-gpt-6-family) | Asked Codex for ideas ranked by estimated CI minutes saved per day, from run history; median CI roughly 10 → 4.5 minutes and p90 12.5 → 6 minutes over about 30 pull requests. | A |
| [@LimestoneHQ (Limestone Digital, a vendor), 3 Nov 2026](https://x.com/LimestoneHQ/status/2117568557924094225) | On GitHub's public cli/cli, job time split 3% waiting, 20% setup, 67% running (the other 10% cleanup or unaccounted) (a vendor's measurement, 19 runs). Shows setup isn't always the biggest share. | C |
