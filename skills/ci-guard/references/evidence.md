# Evidence for ci-guard

Public posts this skill relies on, each re-read at its link. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | Pre-push hook runs format, lint and type check on changed files in under 9 seconds: "Put it in a hook rather than a line in AGENTS.md, because agents skip steps." | A |
| [Marc (Kumiko), DEV, Nov 2026](https://dev.to/marc_kumiko/our-coding-agents-skipped-the-pre-push-hook-on-118-of-411-pushes-27j0) | Agents skipped the pre-push hook on 118 of 411 push commands in agent transcripts; all of them still had to pass CI before merging. | A |
| [Stripe, "Minions" part 1, stripe.dev, 9 Feb 2026](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) | At most two rounds of CI per agent task, "since CI runs cost tokens, compute, and time". Company practice; no CI-time figure for the cap. | C |
| [Jonathan Muszkat, Selenios, 13 Oct 2026](https://me.jonymusky.com/blog/merge-queue-ai-ci-tax) | Updates that brought a pull request up to date with main were 51% of its CI minutes; `gh pr update-branch` was on the list of commands agents could run without asking. After the move to GitHub's merge queue, updated pull requests open under 4 hours went from 82% to 27%; in the queue's first week keeping pull requests current cost 6% more for those and 22% less for pull requests open 4 to 24 hours, and 9% of queue entries failed. The team then added an AGENTS-file rule ("Do not merge `main` into a PR branch … just to bring it up to date"). | A |
| [Tw93 (@HiTw93), 10 Nov 2026](https://x.com/HiTw93/status/2120164408945152470) | An agent piped a suite into tail and reported a red run as green (one incident, an anecdote). | D |
