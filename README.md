<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo-light.svg" width="96" height="96" alt="">
  </picture>
</p>

<h1 align="center">Joggernaut</h1>

<p align="center"><b>Find out why your pull requests wait on CI. Let your agent fix the biggest cause, with every test still running.</b></p>

<p align="center"><sub>Agent skills for GitHub Actions CI · jog + juggernaut</sub></p>

<p align="center">
  <img alt="runs in Claude Code" src="https://img.shields.io/badge/runs_in-Claude_Code-2f6f4f">
  <img alt="loads in Codex, Gemini CLI and OpenCode" src="https://img.shields.io/badge/loads_in-Codex_·_Gemini_CLI_·_OpenCode-2f6f4f">
  <img alt="license MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="rule: keep every test" src="https://img.shields.io/badge/rule-keep_every_test-brightgreen">
</p>

Ask your agent to **diagnose my CI**. It reads your recent GitHub Actions
runs (150 take about two minutes), splits the wait into waiting for a
machine, setup and running, and ranks the causes by wait saved. It changes
no tracked file until you say yes. An example of what it prints:

```text
Joggernaut · example: acme/web · 150 PR runs          read-only
PR wait: median 14m 10s, slowest 5% 31m 02s, about 40 pushes a day
  waiting for a machine   0m 40s
  setup                   7m 25s   <- biggest: 52%
  running                 6m 05s
Runner-minutes in failed, timed-out or cancelled runs 38%, catch-up 12%

On the slowest path, by wait saved                a run    a day
> 1  pnpm cache never saved on main: cold PRs  -4m 50s  -3h 13m  ci-cache
  2  tests use 2 of 4 cores                      -2m 10s  -1h 27m  ci-slow-tests
Off the slowest path (runner-minutes, not wait)
  3  old PR runs keep going after a new push     -9 min a run      ci-workflow
  4  seven lint jobs each pay setup              -6 min a run      ci-workflow
  5  checkout.test.ts passes on rerun            1 in 30 runs      ci-flaky-tests
For a person: bigger runners (cost money), a merge queue
```

Say yes to a fix and the matching skill opens one pull request for it. Once
20 runs have finished after the merge, ask your agent to **measure the fix**:
`ci-measure` compares them with 20 or more from before, and checks by name,
from the JUnit reports CI saves, that every test still ran. Where CI saves no
report it can only count tests, and says the check is unverified.

## Start

In Claude Code:

```text
/plugin marketplace add usejog/joggernaut
/plugin install jog@joggernaut
/reload-plugins
/jog:ci-diagnose
```

In any other agent, paste this:

```text
Install the skills from github.com/usejog/joggernaut with the one command
its README's "If you are an agent" table gives for you. Then read the
installed ci-diagnose SKILL.md and diagnose this repository. Change no
tracked file until I say yes.
```

You need a repository on GitHub Actions, Python 3.9 or later, and the GitHub
CLI logged in (`gh auth login`). Diagnosis reads your runs through your own
`gh` login, with GET calls only, and triggers no runs; expect your agent to
ask before it runs `gh` and the skill's `measure.py`. A fix you approve
pushes one branch and opens one pull request, which runs your CI as usual.
No telemetry. Other agents and manual installs: [Install](#install).

## Try it in a minute, with no login

The repository carries made-up run histories for its tests. On one, a change
made CI three minutes faster by dropping a test. `ci-measure` catches it:

```text
$ git clone --depth 1 https://github.com/usejog/joggernaut && cd joggernaut/evals/ci-measure/repo
$ python3 ../../../skills/ci-measure/scripts/measure.py compare \
    --before ci-history/before.jsonl --after ci-history/after.jsonl
before: 24 runs, median 11m 10s, slowest 5% 11m 39s
after:  24 runs, median 7m 54s, slowest 5% 8m 18s
verdict: median faster
$ python3 ../../../skills/ci-measure/scripts/measure.py tests \
    --before ci-history/junit-before --after ci-history/junit-after
tests that ran: before 12, after 11
  stopped running: report::billing::tests.test_billing::test_refund_rounding
verdict: FAIL: tests lost or newly failing
```

`measure.py split --in ../../ci-diagnose/repo/ci-history/runs.jsonl` prints
the timing half of a diagnosis; the ranking is your agent's work.

**What it won't do.** It never makes CI faster by hiding failures: no
retries, longer timeouts, skipped tests or quarantines, and no fewer tests
before a merge. Anything that costs money goes on a list for you. And the
numbers below are other teams', not ours: we haven't measured these skills on
anyone's CI yet.

## What other teams measured

Each row is a result its team published. We didn't reproduce them; each
skill links its sources in `references/evidence.md`.

| Team | Result | What they found | Source |
|---|---|---|---|
| OpenAI Core Experimentation | CI median roughly 10 → 4.5 min | Codex ranked ideas by estimated CI minutes saved a day; about 30 PRs | [blog](https://developers.openai.com/blog/maintaining-software-with-the-gpt-6-family) |
| Shopify Ruby LSP | CI about 30 → about 20 min | Test-time work in one PR; the same reported test count, 18,329 | [PR #4004](https://github.com/Shopify/ruby-lsp/pull/4004) |
| Sidelab | Full CI 68 min (median of 5 green runs) → 15 min | Claude with sub-agents; among the fixes, a compile cache at 0% hits for two weeks, 8-core runners (paid, the person's call), tests split over 2 machines | [post](https://x.com/sireton_builds/status/2117864723404451924) |
| OpenAI Core Experimentation | One suite 592.6 s → 29.8 s | One missing mock; all 63 tests still ran | [blog](https://developers.openai.com/blog/maintaining-software-with-the-gpt-6-family) |
| Linear | 7 small jobs → 2 | About 87,000 runner-minutes a month saved, based on June usage | [blog](https://linear.app/now/ci-bottleneck-reworked) |
| Selenios | Catch-up runs were 51% of a PR's CI minutes | Branches brought up to date with main just to stay current, by people and by agents | [post](https://me.jonymusky.com/blog/merge-queue-ai-ci-tax) |

## The four rules every skill follows

1. **Measure CI's own runs, before and after.** At least 20 comparable runs a
   side. A local timing is never the result.
2. **Keep every test running.** Don't hide a failure with a retry, a wider
   timeout, a skip or fewer workers. No test may stop running or newly fail.
3. **One fix per pull request,** with the diff, the baseline and the
   branch's timings marked provisional.
4. **Run the full suite before every merge,** and ask before anything that
   costs money: a bigger runner, a new provider, a paid service.

The full text is in [AGENTS.md](AGENTS.md). To give agents these rules without
the skills, copy [snippets/AGENTS.md](snippets/AGENTS.md) into your
repository's AGENTS.md or CLAUDE.md.

## The skills

| Skill | Use it when | What it measures |
|---|---|---|
| [ci-diagnose](skills/ci-diagnose/SKILL.md) | "Why is CI slow?" Start here; read-only | PR wait; waiting, setup and running per job; minutes in failed, timed-out or cancelled runs and in catch-up runs |
| [ci-measure](skills/ci-measure/SKILL.md) | Before a fix, and "did that help?" | 20+ runs a side, median and slowest 5%; the tests that ran, by name |
| [ci-cache](skills/ci-cache/SKILL.md) | Dependencies reinstall on every PR; a cache never hits | Hit rate per cache key; setup seconds per job |
| [ci-workflow](skills/ci-workflow/SKILL.md) | Short jobs each repeat setup; old runs keep going after a push | PR wait; runner-minutes per PR |
| [ci-slow-tests](skills/ci-slow-tests/SKILL.md) | The test step is most of the wait | Suite time; slowest shard; how many tests ran |
| [ci-flaky-tests](skills/ci-flaky-tests/SKILL.md) | A test passes on rerun | Failures in N runs before and after |
| [ci-guard](skills/ci-guard/SKILL.md) | Agents push again and again to find lint errors, or keep updating branches | Pushes, failed rounds and catch-up runs per PR |

Each skill carries the same `scripts/measure.py` (Python standard library plus
`gh`), so a skill installed on its own still measures.

## Install

**Claude Code:** the plugin, as in [Start](#start). From a shell:
`claude plugin marketplace add usejog/joggernaut` then
`claude plugin install jog@joggernaut`. Skills show up as
`/jog:ci-diagnose`, `/jog:ci-flaky-tests` and so on.

**Codex, Cursor, OpenCode, GitHub Copilot CLI, Amp and others:** `npx skills`
(Node 22.20 or later), naming your agent with `-a`:

```sh
npx skills add usejog/joggernaut -g -y -a codex
```

Replace `codex` with `cursor`, `opencode`, `github-copilot`, `amp` or your
agent's id. In Codex, run a skill as `$ci-diagnose`. `npx skills` sends its
own install telemetry; put `DISABLE_TELEMETRY=1` before the command to turn
it off.

<details>
<summary><b>Gemini CLI, goose, and installing without Node</b></summary>

Gemini CLI (restart it afterwards):

```sh
gemini extensions install https://github.com/usejog/joggernaut
```

With the GitHub CLI instead of Node (goose, Cline and others):

```sh
gh skill install usejog/joggernaut --all --scope user --agent goose
```

Clone and copy, no Node:

```sh
git clone --depth 1 https://github.com/usejog/joggernaut ~/.joggernaut
~/.joggernaut/install
```

It copies the skills to `~/.agents/skills` and never replaces a folder it
didn't install. Add `--claude` to also add the Claude Code plugin.
</details>

**Use one install route per agent.** Several agents read each other's skill
folders, so two routes load the same skills twice.

**For a whole team,** install into the repository: drop `-g`
(`npx skills add usejog/joggernaut -y -a codex -a cursor`) and commit the
files it writes. In Claude Code, declare both in the project and commit
`.claude/settings.json`:
`claude plugin marketplace add usejog/joggernaut --scope project` then
`claude plugin install jog@joggernaut -s project`.

**What we tested.** On a clean machine, Claude Code, Codex, OpenCode and
Gemini CLI (from a local copy) each listed all seven skills. In Claude Code,
each skill ran on a sample repository with a planted cause and passed its
scripted check ([evals](evals/README.md)); the first run of ci-flaky-tests
didn't, and the skill was fixed. For Cursor, GitHub Copilot CLI, Amp and
goose we checked that the files install, not that the agent runs them. Other
agents are untested.

**Uninstall** with the route you used: `claude plugin uninstall jog@joggernaut`,
`npx skills remove ci-diagnose ci-measure ci-cache ci-workflow ci-slow-tests ci-flaky-tests ci-guard -g -y -a codex`
(your agent's id in place of `codex`; drop `-g` for a project install),
`gemini extensions uninstall joggernaut`, or `~/.joggernaut/install --uninstall`.
`gh skill` has no uninstall yet: `gh skill list --agent goose --scope user`
shows the folders to delete. Delete `.joggernaut/` in a repository to drop
its saved runs.

**Privacy.** No telemetry and no account. The skills read GitHub Actions
through your own `gh` login, with GET calls only. (`npx skills` has telemetry
of its own; set `DISABLE_TELEMETRY=1` to turn it off.)

## If you are an agent

Install for the agent you are, with your row below, then read
`ci-diagnose/SKILL.md` from the installed copy and follow it.

| You are | Run |
|---|---|
| Claude Code | `claude plugin marketplace add usejog/joggernaut && claude plugin install jog@joggernaut`, then read the skill file directly (a new plugin loads only after `/reload-plugins` or a restart) |
| Codex | `npx skills add usejog/joggernaut -g -y -a codex` |
| Cursor | `npx skills add usejog/joggernaut -g -y -a cursor` |
| Gemini CLI | `gemini extensions install https://github.com/usejog/joggernaut` |
| OpenCode | `npx skills add usejog/joggernaut -g -y -a opencode` |
| GitHub Copilot CLI | `npx skills add usejog/joggernaut -g -y -a github-copilot` |
| Amp | `npx skills add usejog/joggernaut -g -y -a amp` |
| goose | `gh skill install usejog/joggernaut --all --scope user --agent goose` |
| Cline | `gh skill install usejog/joggernaut --all --scope user --agent cline` |

The skill file is then at `~/.agents/skills/ci-diagnose/SKILL.md` (npx
skills), `~/.claude/plugins/cache/joggernaut/jog/<version>/skills/ci-diagnose/SKILL.md`
(Claude Code), `~/.gemini/extensions/joggernaut/skills/ci-diagnose/SKILL.md`
(Gemini CLI) or your agent's own skills folder (`gh skill`). Stay in the
repository being diagnosed and run the skill's `scripts/measure.py` by its
installed path.

Install only for yourself. Save the diagnosis in `.joggernaut/`, then ask
before editing a tracked file or starting a fix.

## How it works

```text
 ci-diagnose ──► ranked causes ──► one fixer skill ──► pull request ──► ci-measure
 read-only       wait saved a      cache, workflow,     diff + baseline   20+ runs a side,
 150 PR runs     day, slowest      slow tests, flaky,   (provisional)     tests compared
                 path only         guard                                  by name
```

Each folder under `skills/` is a `SKILL.md` in the
[Agent Skills](https://agentskills.io) format, with only the standard fields.
The plugin manifests point at those folders. Each `SKILL.md` keeps two kinds
of support apart: results other teams published (linked and graded A to D in
`references/evidence.md`), and reasoning about how CI works, labelled as
reasoning.

## Credits

The skills rest on public work by these people and teams, each linked from
the skill that cites it: Owen Gretzinger (Boardy), Rodrigo Roim and OpenAI's
Core Experimentation team, Limestone Digital, Victor Mota, Sean Ireton
(Sidelab), Shopify's Ruby LSP team, CloudX, RemitAid, Linear, Jonathan
Muszkat (Selenios), Rocky Warren (Clipboard), Fritz Meissner (thoughtbot),
Marc (Kumiko), Stripe, Tw93, and the t3code maintainers.

## Contributing

Used a skill on your CI? Add a row to [RESULTS.md](RESULTS.md) linking your
public pull request with its runs before and after, slower and inconclusive
results included. New skills need evidence: see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[MIT](LICENSE).

---

<sub>Made by the team behind Jog.</sub>
