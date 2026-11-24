# Evals

One small sample repository per skill, each with one planted cause. Every
sample and its CI history is made up; none describes a real project.

| Skill | Sample | Planted cause | Passes when |
|---|---|---|---|
| ci-diagnose | `ci-diagnose/repo` | the pnpm cache is saved only on pull-request branches, so every new PR installs cold; seven tiny lint jobs also each pay setup | the cold cache is ranked first, above the lint jobs, and nothing tracked changed |
| ci-measure | `ci-measure/repo` | a change that is faster but stopped one test running | the verdict fails the change and names the test |
| ci-cache | `ci-cache/repo` | the workflow runs only on pull requests, so main never saves the cache | a run on main saves the cache; build and tests still run |
| ci-workflow | `ci-workflow/repo` | seven 6-second lint jobs each wait for a machine and pay about 50 seconds of setup | fewer than eight jobs, every lint and the tests still run (and any cancel-in-progress spares main) |
| ci-slow-tests | `ci-slow-tests/repo` | the cart tests call a price server that takes half a second a call | the suite runs under 2.5 s with all 17 tests and the same assertions |
| ci-flaky-tests | `ci-flaky-tests/repo` | debounce tests wait on real time with a 10 ms margin | 0 failures in 150 runs (50 with every core busy), no retry, longer sleep or skip |
| ci-guard | `ci-guard/repo` | agents push 5 to 9 times per PR, mostly failing on lint and type checks | a pre-push hook runs lint and type check, the rules cap CI at two rounds, CI keeps every check |

Each `check.py` decides by script, not by a model. Its limits, stated plainly:
the ci-cache and ci-guard checks read the workflow's text, its triggers and
`run:` lines, and don't execute it; the ci-workflow check runs each `run:`
step under bash against a stub `pnpm` that records the scripts it runs, and
fails each lint in turn, so a lint that stops running, or whose failure no
longer fails its step, fails the check (it can't see a step's `if:` or a
matrix); the assertion check compares expected values, so an
assertion rewritten against a constant can pass; the ci-diagnose check looks for the planted cause in free text, and the ci-measure check reads an exact `Verdict:` first line and a `Stopped running:` line the prompt asks for. A passing eval is evidence, not proof: read the agent's diff.
Checks diff against the sample as handed over (the `sample` tag), so an agent
that commits can't hide a change. Every check also fails the
run if the agent added a retry, `continue-on-error`, `|| true`, a skip, a very
long timeout, `--no-verify`, `pull_request_target` or wider permissions
(`lib/cheats.py`).

Run one inside a disposable VM or container: the agent runs commands without
asking for permission, and `evals/run` is not a sandbox.

```sh
export EVALS_IN_DISPOSABLE_MACHINE=1
evals/run ci-cache            # Claude Code, this repository loaded as a plugin
evals/run ci-cache codex      # Codex, with the skills installed for Codex
```

The samples have no GitHub remote; each prompt points the agent at the
recorded history in the sample's `ci-history/` folder instead.

`python3 tools/selftest.py` checks the harness itself without an agent: every
`check.py` must fail on its untouched sample, and `measure.py` must give the
expected answers on the recorded histories.
