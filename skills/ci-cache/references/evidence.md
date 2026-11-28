# Evidence for ci-cache

Public posts this skill relies on, each re-read at its link on 23 Nov 2026
(rows added on 27 Nov 2026: read that day). Numbers are as
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
| [Acecore (Gui), 17 Nov 2026](https://systems.acecore.net/en/insights/gradle-cache-ci-measurement/) | The DaysChat Android Gradle job on one commit "took 16 minutes 20 seconds on the initial run and 6 minutes 16 seconds on the rerun", the restore taking 62 seconds; "It reused 194 Gradle tasks"; "This 1 pair of runs was measured using a PR-specific cache." The measuring paragraph doesn't name the CI. "In the final configuration, only main saves the shared cache, and PRs restore it in read-only mode", not measured. | A |
| [Picnic (Oksana Evseeva), 24 Jul 2024](https://jobs.picnic.app/blogs/improving-maven-build-times) | The Maven build cache extension on TeamCity: "Instead of 10 minutes 4 seconds, the build that was fully cached took only 1 minute 22 seconds", a case the post calls "quite a rare case"; the cache is off "for builds on default branches supporting continuous deployments, and in release builds". | A |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026 (entries
added on 27 Nov 2026: read that day). A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): a pull request's run can restore caches from its own branch, the default branch and its base branch, and saves to `refs/pull/N/merge`; a saved cache can't be changed; runs from `pull_request_target`, `issue_comment` and `workflow_run` can restore but not create caches by default; a cache unused for 7 days is removed; 10 GB per repository unless raised, then the least recently used caches are deleted first; the action tries an exact key, then a prefix of the key, then `restore-keys`, and restores the newest partial match.
- [actions/setup-go: parallel builds](https://github.com/actions/setup-go/blob/main/docs/advanced-usage.md#parallel-builds): caching is on by default, keyed on `go.mod`; "to avoid race conditions during parallel builds, either use distinct cache keys … or create the cache in only one build and restore it in the other builds."
- [Go: `go test` caching](https://pkg.go.dev/cmd/go#hdr-Test_packages): Go caches successful test results and replays them as `(cached)` only for the same test binary and cacheable flags; "Tests that open files within the package's module or that consult environment variables only match future runs in which the files and environment variables are unchanged" (only what the test process itself opens is tracked, so a subprocess's reads are not); "the idiomatic way to disable test caching explicitly is to use -count=1".
- [Docker Docs: cache with GitHub Actions](https://docs.docker.com/build/ci/github-actions/cache/): `cache-from: type=gha` and `cache-to: type=gha,mode=max` in `docker/build-push-action`.
- [GitHub Docs: managing GitHub Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#configuring-cache-settings-for-your-repository): cache retention and size can be configured per repository (opt-in, on paid plans); the caching docs above give 7 days as the default.
- [actions/setup-node: cache restore](https://github.com/actions/setup-node/blob/main/src/cache-restore.ts): sets `cache-hit` whenever a cache was restored, prefix matches included.
- [actions/setup-python: advanced usage](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md#caching-packages): `cache-hit` reports a hit on the primary key.
- [actions/cache: exact key match](https://github.com/actions/cache/blob/main/src/utils/actionUtils.ts): `isExactKeyMatch` compares with `localeCompare(..., { sensitivity: "accent" })`, which ignores case.
- [gradle/actions: setup-gradle](https://github.com/gradle/actions/blob/main/docs/setup-gradle.md) and [its distribution notes](https://github.com/gradle/actions/blob/main/DISTRIBUTION.md): "Caching is enabled by default"; writes the cache only from jobs on the default branch unless `cache-read-only` says otherwise; "Avoid using `actions/cache` configured to cache the Gradle User Home" and `setup-java`'s `cache: gradle`, which "may interfere"; `cache-provider: basic` is "A fully open-source (MIT) caching implementation" and "free for all repositories (public and private)"; the default, Enhanced Caching, is proprietary, "currently available as a Free Preview for private repositories", and "We plan to introduce usage-based pricing for large-scale commercial organizations in the future."
- [actions/setup-java: caching](https://github.com/actions/setup-java#caching-packages-dependencies): `cache: maven` stores `~/.m2/repository`, keyed on a hash of the build files.
- [Maven build cache extension: overview](https://maven.apache.org/extensions/maven-build-cache-extension/concepts.html): "calculates a key from module inputs, stores outputs in the cache, and transparently restores them later".
