# Known causes, and the skill that fixes each

Check each against the workflow files and the numbers from `measure.py split`.
A cause counts only when the numbers show it.

| # | Cause | How to see it | Fixed by |
|---|---|---|---|
| 1 | Dependency cache never saved on the default branch, so pull requests start cold (a pull request can read its base branch's caches but saves only to its own) | Cache step logs say "Cache not found" on most PR runs; no cache-saving run on `main` | ci-cache |
| 2 | Cache key misses the toolchain or tool version (Rust, sccache, Node, RUSTFLAGS), so nothing ever matches | Hit rate near 0% for a key; key built from the lockfile alone | ci-cache |
| 3 | Parallel jobs share one cache key (setup-go's default, for example), and the first to finish saves a cache the others can't use | Same key in several jobs; one job's setup much slower than the rest | ci-cache |
| 4 | The repository's cache size cap evicts entries, so caches go cold | Total cache size near the cap (`gh api repos/OWNER/NAME/actions/cache/usage`) | ci-cache |
| 5 | A cache that is slower than the work it saves (node_modules restore against a filtered install) | Restore step seconds against install seconds | ci-cache |
| 6 | Many tiny jobs each pay checkout, toolchain and install | Jobs whose running time is a small share of their total | ci-workflow |
| 7 | Superseded runs keep going after a newer push | Cancelled share low but runs per PR high; no `concurrency` group | ci-workflow |
| 8 | A `needs` chain that passes no data and gates nothing | Jobs waiting on others with no artifact or output used | ci-workflow |
| 9 | Slow checkout (full history, large repository) | Checkout step seconds; `fetch-depth: 0` | ci-workflow |
| 10 | Tools compiled on every run that ship as prebuilt binaries | Long install steps running `cargo install`, `go install` and the like | ci-workflow |
| 11 | One or a few tests take most of the test step | Per-test times from the JUnit report | ci-slow-tests |
| 12 | Tests use fewer workers than the runner has cores, or reload modules per file | Worker count against `nproc`; per-file setup time | ci-slow-tests |
| 13 | Shards that each pay a long setup | Setup share per shard | ci-slow-tests, ci-workflow |
| 14 | Real sleeps or real network calls in tests | `sleep(` in tests; tests that call a server | ci-slow-tests |
| 15 | Jobs that fail and then pass on a rerun of the same commit | `rerun_flakes` in the split | ci-flaky-tests |
| 16 | Retries, long timeouts or `continue-on-error` hiding failures | Grep the workflow and test config | ci-flaky-tests (find the cause), never by removing the check |
| 17 | Many pushes per pull request, with runs failing on format, lint or type errors | Pushes per PR; failed step names | ci-guard |
| 18 | A large share of minutes in runs that failed, timed out or were cancelled | The failed-or-cancelled share in the split | ci-guard, ci-flaky-tests, ci-workflow (cancelled) |
| 19 | Long waits for a machine | Waiting share on the slowest path | A person: runner size or provider costs money |
| 20 | Path filters on a workflow behind a required check (the check stays pending forever) | `paths:` on a workflow whose job is required | ci-workflow (review only) |
| 21 | Catch-up runs: pull requests merged with main again and again just to stay current, by people or by agents running `gh pr update-branch`, often because branch protection requires branches to be up to date | The `catch-up runs` line in the split; `strict: true` in `gh api repos/OWNER/NAME/branches/BRANCH/protection/required_status_checks` | ci-guard (the agent rule); a person (a merge queue in place of the up-to-date rule) |
| 22 | No cache at all for dependencies or build outputs | Install or compile steps take minutes and no cache step exists | ci-cache |
| 23 | Docker images rebuilt from scratch on every run | `docker build` or `docker/build-push-action` with no `cache-from`; the build step's seconds | ci-cache |
| 24 | A hung job runs until GitHub's 360-minute default | Jobs with no `timeout-minutes`; failed or cancelled jobs far longer than the median | ci-workflow |
| 25 | One shard finishes well after the others | Per-shard running time from the split; per-file test time from the report | ci-slow-tests |

Items for a person, never fixed by a skill: bigger or different runners, new
providers or paid services, and repository settings such as a merge queue.
No skill runs fewer tests before a merge.
