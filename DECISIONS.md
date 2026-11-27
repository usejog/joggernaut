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
