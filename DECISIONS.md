# Decisions

Choices about what Joggernaut says and does, who made each one, and why.
Newest first. An entry changes no skill, rule or README by itself: a pull
request that applies one is separate, and shows the wording before and after.

## 27 Nov 2026 · Cite only a team's own measurement of its own CI

**Decision.** A number Joggernaut cites as a result is one a team measured on
its own CI and published first person. A vendor's benchmark of its own
product is never cited as a result, Jog's and GitHub's included. This doesn't
touch citing vendor docs for how a feature behaves, which the rules already
do.

**Why.** A reader can check a team's own baseline, workload and result. A
vendor's benchmark of its own product can't be checked that way.

**Who decided.** An agent, not a person: Claude Opus 5.5 (Anthropic), working
for Joggernaut's maintainer, Matt Gapp. Claude Fable 5.2 (Anthropic) and Codex
Astra (OpenAI) were each asked separately and agreed. The maintainer asked on
27 Nov 2026 that agents settle such questions with other agents' opinions
rather than wait on him; he didn't make this choice. Their words:

- Claude Fable 5.2: "AGREE — citing only teams' own measurements is the
  stricter, more honest rule and removes nothing true."
- Codex Astra: "AGREE — Cite the team that measured the change in its own CI
  so readers can check the baseline, workload and result."

## 27 Nov 2026 · Affected tests only on pull requests, only behind a full gate

**Decision.** Joggernaut may offer a recipe that runs only the tests a change
affects on a pull request, for faster feedback. The recipe refuses to set
itself up unless a merge queue or a required full-suite run gates the
revision that actually merges. Rule 4 stands: the full suite gates every
merge.

**Why.** With a full run required on what merges, an untested change can't
land, so the faster feedback costs no correctness.

**Who decided.** An agent, not a person, the same way as the entry above.
Their words:

- Claude Fable 5.2: "AGREE — a recipe that refuses unless a merge queue or a
  required full run gates merge can't let an untested change land, so it
  loses no correctness."
- Codex Astra: "AGREE — Offer affected-tests-only feedback on PRs only when a
  required full-suite pass gates the revision that actually merges, including
  through a merge queue."

**Not decided here.** Whether to offer a tracked quarantine of flaky tests. It
would change rule 4's "Never quarantine a test", so it stays the maintainer's
call.
