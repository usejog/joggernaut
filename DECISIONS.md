# Decisions

Choices about what Joggernaut says and does, who made each one, and why.
Newest first. An entry changes no skill, rule or README by itself: a pull
request that applies one is separate, and shows the wording before and after.

**Who decided the 27 Nov 2026 entries.** An agent, not a person: Claude Opus
5.5 (Anthropic), working for Joggernaut's maintainer, Matt Gapp, at his
request not to be blocked on him and to use other agents for input or review.
Claude Fable 5.2 (Anthropic) and Codex Astra (OpenAI gpt-6.2-astra, via Codex
CLI) were each asked separately and agreed. The maintainer didn't make these
choices. Each entry quotes the two agents' answers.

## 27 Nov 2026 · A consultancy's measurement of its client's CI, cited as such

**Decision.** As an extension of the entry below, a measurement made by the
people who did the work, on a named team's real CI, and published first
person (a consultancy's write-up of its client, say) may be cited as a
result. The citation names who measured it and on whose CI, says the writer
was paid for the work, and quotes the figure as published, for the changes
it measured together. A number for a change that needs the writer's own
product or tool, paid or free, to make or run is never cited this way; a
tool that only helped find the cause doesn't count against it.

**Why.** The measurement shows what happened on that team's CI, with its own
baseline and workload, which is the reason for the entry below. The first
case is Evil Martians' write-up of its client Whop's Rails suite: its
logging and Sentry changes need no tool of its own.

- Claude Fable 5.2: "AGREE — the measurement is on Whop's real CI with its
  own baseline and workload, which is what the existing entry's "Why" asks
  for, and the people who did the work are the ones reporting it first
  person." Its conditions: record it as an extension, name both and say
  the writer was paid, leave out numbers that depend on the writer's own
  tools, paid or free, and quote the figure as published.
- Codex Astra: "AGREE — Evil Martians measured the change directly on
  Whop's own CI, which gives it the firsthand evidence the rule requires."
  Its conditions: credit Evil Martians as Whop's consultancy, keep the
  exclusion for benchmarks of the writer's own product, and report the
  16-process run as about 4 minutes before and about 2 after, the three
  changes together.

## 27 Nov 2026 · Cite only a team's own measurement of its own CI

**Decision.** A number Joggernaut cites as a result is one a team measured on
its own CI and published first person. A vendor's benchmark of its own
product is never cited as a result, Jog's and GitHub's included. This doesn't
touch citing vendor docs for how a feature behaves, which the rules already
do.

**Why.** A team's own measurement shows readers what happened on CI that team
runs, with its own baseline and workload.

- Claude Fable 5.2: "AGREE — citing only teams' own measurements is the
  stricter, more honest rule and removes nothing true."
- Codex Astra: "AGREE — Cite the team that measured the change in its own CI
  so readers can check the baseline, workload and result."

## 27 Nov 2026 · Affected tests only on pull requests, only behind a full gate

**Decision.** Joggernaut may offer a recipe that runs only the tests a change
affects on a pull request, for faster feedback. The recipe refuses to set
itself up unless the full suite must pass on the revision that actually
merges, through a merge queue that runs the full suite, or a required
full-suite check with branches required to be up to date. Rule 4 stands:
the full suite gates every merge.

**Why.** With the full suite required on what merges, an untested change
can't land, so the faster feedback costs no correctness.

- Claude Fable 5.2: "AGREE — a recipe that refuses unless a merge queue or a
  required full run gates merge can't let an untested change land, so it
  loses no correctness."
- Codex Astra: "AGREE — Offer affected-tests-only feedback on PRs only when a
  required full-suite pass gates the revision that actually merges, including
  through a merge queue."

**Not decided here.** Whether to offer a tracked quarantine of flaky tests. It
would change rule 4's "Never quarantine a test", so it stays the maintainer's
call.
