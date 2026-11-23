# Evidence for ci-cache

Public posts this skill relies on, each re-read at its link. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | An agent's audit of the last 150 runs found pull-request caches had missed all year because nothing seeded them from main. Its node_modules cache restores in 13 s and replaces a 33 s install. | A |
| [Sean Ireton (@sireton_builds), Sidelab, 4 Nov 2026](https://x.com/sireton_builds/status/2117864723404451924) | Compile cache hit 0% for two weeks after the sccache version changed and the key didn't include it; hits went to 88–100% once fixed. | A |
| [CloudX engineering blog, 16 Sep 2026](https://www.cloudx.ai/posts/setup-go) | Parallel lint and test jobs shared setup-go's default cache key; test jobs regressed from a 76 s to a 180 s median, and a per-job cache brought the median job runtime to 41 s; the post says the restored cache also let Go reuse test results and run only changed packages' tests. | A |
| [RemitAid on Zenn (in Japanese), 21 Aug 2026](https://zenn.dev/remitaid/articles/fa94cb567f5d1d) | The same shared setup-go key bug, fixed with per-job keys within a wider redesign (separate jobs, per-commit keys, fallback restores); a pull-request run went from about 8 minutes to 2 minutes 55 seconds. | A |
| [Linear engineering blog, 21 Sep 2026](https://linear.app/now/ci-bottleneck-reworked) | A node_modules cache took about 28 s to restore against about 7.5 s for a filtered install. | A |
