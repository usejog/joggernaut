# Evidence for ci-measure

Public posts this skill relies on, each re-read at its link on 23 Nov 2026. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Victor Mota (@vimota), 25 Mar 2026](https://x.com/vimota/status/2036931300956021159) | Used local unit-test time as the target: 163 s → about 100 s locally, but 14 → 13 minutes on real CI. The local proxy misled. | B |
| [Sean Ireton (@sireton_builds), Sidelab, 4 Nov 2026](https://x.com/sireton_builds/status/2117864723404451924) | The agent wrote a baseline file with the numbers and the commands to measure them again before changing anything, and proved each fix with a CI run; full CI run 68 minutes (median) → 15 minutes. | A |
| [Shopify/ruby-lsp pull request #4004 (@_st0012), merged 13 Mar 2026](https://github.com/Shopify/ruby-lsp/pull/4004) | CI about 30 → 20 minutes; the test plan states 18,329 tests, the same count, with the same two pre-existing failures (a count, not a by-name list). | A |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026. A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): for `pull_request`, `GITHUB_SHA` is the last merge commit on `refs/pull/N/merge`, and the default activity types are opened, synchronize and reopened, so a push to a pull request can start every workflow subscribed to `synchronize` (the default), unless a filter skips it, the pull request has a merge conflict, or a run from a fork waits for approval ("Workflows will not run on pull_request activity if the pull request has a merge conflict").
- [GitHub Docs: REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api): 5,000 requests an hour for a signed-in user.
