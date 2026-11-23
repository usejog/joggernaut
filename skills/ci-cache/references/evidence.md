# Evidence for ci-cache

Public posts this skill relies on, each re-read at its link on 23 Nov 2026. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | An agent's audit of the last 150 runs found pull-request caches had missed all year because nothing seeded them from main. Its node_modules cache restores in 13 s and replaces a 33 s install. | A |
| [Sean Ireton (@sireton_builds), Sidelab, 4 Nov 2026](https://x.com/sireton_builds/status/2117864723404451924) | Compile cache hit 0% for two weeks after the sccache version changed and the key didn't include it, and main never saved a new cache (main skipped the suite for commits that had already passed); hits went to 88–100% once both were fixed and the cache saved even when a test failed. | A |
| [CloudX engineering blog, 16 Sep 2026](https://www.cloudx.ai/posts/setup-go) | Parallel lint and test jobs shared setup-go's default cache key; test jobs regressed from a 76 s to a 180 s median, and a per-job cache brought the median job runtime to 41 s; the post says the restored cache also let Go reuse test results and run only changed packages' tests. | A |
| [RemitAid on Zenn (in Japanese), 21 Aug 2026](https://zenn.dev/remitaid/articles/fa94cb567f5d1d) | The same shared setup-go key bug, fixed with per-job keys within a wider redesign (separate jobs, per-commit keys, fallback restores); the test job's total (ジョブ合計) on a pull-request run that restored the previous commit's cache went from about 8 minutes to 2 minutes 55 seconds. | A |
| [Linear engineering blog, 21 Sep 2026](https://linear.app/now/ci-bottleneck-reworked) | A node_modules cache took about 28 s to restore against about 7.5 s for a filtered install. | A |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026. A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): a pull request's run can restore caches from its own branch, the default branch and its base branch, and saves to `refs/pull/N/merge`; a saved cache can't be changed; runs from `pull_request_target`, `issue_comment` and `workflow_run` can restore but not create caches by default; a cache unused for 7 days is removed; 10 GB per repository unless raised, then the least recently used caches are deleted first; the action tries an exact key, then a prefix of the key, then `restore-keys`, and restores the newest partial match.
- [actions/setup-go: parallel builds](https://github.com/actions/setup-go/blob/main/docs/advanced-usage.md#parallel-builds): caching is on by default, keyed on `go.mod`; "to avoid race conditions during parallel builds, either use distinct cache keys … or create the cache in only one build and restore it in the other builds."
- [Go: `go test` caching](https://pkg.go.dev/cmd/go#hdr-Test_packages): Go caches successful test results and replays them as `(cached)`; "the idiomatic way to disable test caching explicitly is to use -count=1".
- [Docker Docs: cache with GitHub Actions](https://docs.docker.com/build/ci/github-actions/cache/): `cache-from: type=gha` and `cache-to: type=gha,mode=max` in `docker/build-push-action`.
- [GitHub Docs: managing GitHub Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#configuring-cache-settings-for-your-repository): cache retention and size can be configured per repository (opt-in, on paid plans); the caching docs above give 7 days as the default.
- [actions/setup-node: cache restore](https://github.com/actions/setup-node/blob/main/src/cache-restore.ts): sets `cache-hit` whenever a cache was restored, prefix matches included.
- [actions/setup-python: advanced usage](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md#caching-packages): `cache-hit` reports a hit on the primary key.
- [actions/cache: exact key match](https://github.com/actions/cache/blob/main/src/utils/actionUtils.ts): `isExactKeyMatch` compares with `localeCompare(..., { sensitivity: "accent" })`, which ignores case.
