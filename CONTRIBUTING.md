# Contributing

## A result

Add a row to [RESULTS.md](RESULTS.md) with a public pull request that shows
runs before and after. See that file for what a row needs.

## A fix to a skill

Open an issue or a pull request. Say what the agent did wrong, on what kind of
repository, and what the skill should have told it. Run
`python3 tools/check.py` before pushing.

## A new skill

A new skill needs all of these:

1. **Evidence.** At least one public source graded A or B (a measured result,
   first person), or an eval that measures the skill's own effect. List every
   source in `references/evidence.md` with its link and grade:
   - **A**: measured, first person, named repository or company;
   - **B**: measured, first person, unnamed;
   - **C**: vendor or company figures without a measured CI result;
   - **D**: opinion, a prompt or a restatement.

   Quote numbers exactly as the source states them, and link the source
   itself, not a post about it.
2. **The four rules.** The skill's `SKILL.md` carries the same rules block as
   [snippets/AGENTS.md](snippets/AGENTS.md); `tools/sync` copies it in.
3. **An eval.** One small sample repository in `evals/<skill>/` with one
   planted cause, a prompt, and a `check.py` that decides by script, not by a
   model, whether the cause was found or fixed, and that fails the run if the
   agent cheated (a retry, a sleep, a longer timeout, a skip, a deleted test).
4. **The format.** A folder `skills/ci-<name>/` with `SKILL.md` using only the
   standard Agent Skills fields (`name`, `description`, `license`,
   `compatibility`, `metadata`, `allowed-tools`), under 500 lines. If it
   measures, it uses `scripts/measure.py` (copied in by `tools/sync`), never
   its own timing code.

## Ground rules

- Public sources only. Nothing from private systems, and no private names,
  ids or numbers.
- No telemetry.
- By contributing you agree your work is licensed under the MIT licence.
