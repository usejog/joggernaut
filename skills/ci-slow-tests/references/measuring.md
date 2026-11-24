# Measuring, in short

The same in every skill's folder, so a skill installed alone can measure.
`MEASURE` below means `python3 <this skill's folder>/scripts/measure.py`: the
copy beside this file, not a script in the repository being measured. Run it
from the root of the repository being measured; it writes to `.joggernaut/`
there and adds that folder to `.git/info/exclude`, so nothing gets committed.

Needs Python 3.9+ and the GitHub CLI, logged in (`gh auth status`). If `gh`
isn't logged in, stop and ask the person to run `gh auth login`.

## Baseline, before any change

If `git ls-files .joggernaut` lists anything, the folder is tracked: stop
and ask before writing there. Pick the `--created` time before you look, a
few hours ago, so every run up to it has finished. Reuse a saved baseline only
if the commands it records fetched this way; otherwise record it again.

```sh
MEASURE fetch --repo OWNER/NAME --workflow ci.yml --event pull_request --limit 150 \
  --created '<=YYYY-MM-DDTHH:MM:SSZ' \
  --out .joggernaut/before.jsonl &&   # several workflows: before-<name>.jsonl each
MEASURE split --in .joggernaut/before.jsonl
```

`split` heads its output with the PR wait of one group of runs. Runs that
ran different jobs (a path filter, an `if:`, a suite skipped on docs-only
pushes) wait different times, so it groups the successful runs by the
longest job each one ran, lists every group with its run count, median,
slowest runs and share of the total wait, and heads with the group that
holds the most of the wait (`--cohort JOB` picks another). The median over
all of them comes last, labelled as a blend; it is no group's wait. The
slowest path is the chain of jobs that decided when each run ended, read
from the jobs' times; it runs through the jobs of called (reusable)
workflows, which GitHub lists in the caller's run as `CALLER / JOB`.

If GitHub answers a read with a server error (HTTP 5xx), drops the
connection or cuts the answer off, `fetch` tries twice more, waiting a few
seconds between tries. A run whose jobs still can't be read is left out
and named (`left out: run N (failure), jobs read failed 3 times: HTTP
502`), never written without its jobs. A window read whole
(`START..END`, the after side below) isn't written at all then, since the
run left out could be a failure the comparison must count: fetch it again.
A rate limit stops `fetch` at once, with the time it resets.

Write `.joggernaut/baseline.md`: workflow, job and runner label measured, run
count, median and the slowest runs as `split` printed them (and the group
they describe, when it prints groups), any runs `fetch` left out, the tests that ran
(from the JUnit report CI saves, or the runner's count if there is none), and
these commands.

## While the pull request is open

Put the baseline and the branch's own runs in the description, marked
**provisional**. Before asking for review, compare the tests that ran on the
branch with the baseline (`MEASURE tests`, below): a lost test fails the
change now, not after merge.

## After merge

Fetch the baseline again by replaying the exact `fetch` command it
recorded (the same range, limit, workflow and event): the same runs, each
now read by this `fetch`, which refuses any still going. Then the window
after the merge:

```sh
MEASURE fetch ...the baseline's recorded options... --out .joggernaut/before.jsonl &&
MEASURE fetch --repo OWNER/NAME --workflow ci.yml --event pull_request \
  --created 'MERGE-TIME..WINDOW-END' --out .joggernaut/after.jsonl   # times as YYYY-MM-DDTHH:MM:SSZ
```

If either `fetch` refuses, stop: anything after it would read an older file.
Then keep the runs that tested the fix's branch, judged from each run's own
record the same way on both sides:

- The branch: `compare --base BRANCH` (the branch the fix merged into)
  keeps only pull request runs whose recorded target is that branch alone
  (`fetch` records it, looking it up by the run's head branch once the pull
  request has closed) and pushes to it. Everything else is left out on
  both sides whether it passed or failed, fork runs included (closed fork
  pull requests can't be found), so a gap in the record can't shift the
  failure rate.
- A pull request run tests its merge commit with the base as it was when
  the run started: the `HEAD is now at … Merge HEAD into BASE` line
  `actions/checkout` prints names that base.
- Leave out workflows that check out the pull request's head instead of
  the merge commit.
- On the after side, also require the fix in that base or commit
  (`git merge-base --is-ancestor FIX_SHA BASE`), with no revert of it there.
- On the after side, a run that passed but prints no such line is unknown:
  leave it out. A failed run that stopped before that line (before
  checkout, or in it) stays: it is never timed, and its failure counts.

Write the kept runs, one line each as `fetch` wrote them, to
`before-fix.jsonl` and `after-fix.jsonl`, and compare those, with the
same `--event` as the fetches (`pull_request` unless you gave another):

```sh
MEASURE compare --before .joggernaut/before-fix.jsonl --after .joggernaut/after-fix.jsonl \
  --event pull_request --base main --label RUNNER-LABEL [--job NAME] &&  # always pass the runner label; add --job when jobs run on different runners
MEASURE tests --before JUNIT-BEFORE --after JUNIT-AFTER   # each downloaded into a new, empty folder
```

Choose the window before looking (a day or two after the merge, say), and
fetch it only once it has ended and every run created in it has finished;
`fetch` refuses it otherwise, and refuses a window with more runs than
`--limit`. Fast runs finish first, so stopping at the fifth run to
finish keeps the fastest of the window and can pass for a speedup with no
change at all.

`compare` times every successful comparable run in each file, whatever jobs
it ran. If `split` shows groups and the two sides hold them in different
mixes (more docs-only pushes after, say), the medians move with the mix:
say so, and time the job the fix changes with `--job`.

`compare` needs at least 5 successful comparable runs a side. Those are the
runs it times; `--label`, `--job` and `--cache` choose them. The failure rate
it reports reads every finished run of the workflow and event in each file,
whatever those filters say, so a filter can't hide or dilute a failure. If
more runs fail after than chance explains (a one-sided test at 5%), the
result is not valid. If more fail after but within chance, the verdict says
"median faster …, but more runs failed after": at a few runs a side the test
can't rule out a real rise, so name each failure's cause before calling it
faster. Report its verdict as printed, with the run count it names, for
example "median faster (5 runs a side)". `tests` fails if any test stopped
running, was newly skipped or newly fails.

**If the window has fewer than 5 a side**, `compare` says "not enough runs
yet" and shows no timings. Say so, choose a longer window (and a longer
baseline, if that side is short), write the exact commands for it into the
pull request so anyone can finish the measurement, and stop.
Never trigger runs to fill the count without asking: runs cost money.

**If the verdict is "no measurable change yet"**, the change may be real but
smaller than the run-to-run noise at this count. Say so. The 95% holds for one
comparison at a count chosen before looking. Each further look adds to the
chance of a false verdict: with both counts chosen before the first look (5,
then 20 a side, say), two looks stay under about 10%. A second count chosen
after seeing the first result makes that comparison exploratory: report it as
exploratory, beside every comparison you made, the first included. Never run
`compare` again and again until it says "faster".

## How compare decides, and why 5

The verdict comes from the Hodges-Lehmann estimate of how far the times moved
(the median of every after-minus-before difference) and its exact 95%
Mann-Whitney confidence interval (Bauer, 1972): two of those differences,
picked by the exact distribution of the rank-sum count under "no change".

- **median faster**: the whole interval is below zero and the median of
  these runs fell.
- **median slower**: the whole interval is above zero and the median of
  these runs rose.
- **mixed**: the interval excludes zero, but the median moved the other way
  or not at all, as when a change makes most runs faster and the middle one
  slower. Report both numbers; don't call it faster.
- **no measurable change yet**: the interval includes zero.

We chose it over a bootstrap and over a permutation test on the medians:

- A bootstrap interval is a large-sample approximation: nothing guarantees
  its 95% with 5 runs a side.
- The exact interval holds its 95% at any count. If nothing changed, it
  wrongly rules out zero at most 5% of the time, however the times are
  spread. When it does rule zero out, the runs changed, but not always by a
  shift: a change that only widens or narrows the spread can tip it too.
  Read as how far the median moved, it assumes the change moves times
  without reshaping them. That is why the observed medians must agree before
  the verdict says "median", and why you report the medians as measured.
  Ties, common with whole-second times, only make it more cautious.
- A permutation test on the medians gives a yes or no, not a size, and its
  interval would need a search over shifts. The rank interval gives both.

The floor follows from the method. With 3 runs a side no 95% interval can
rule out "no change": every after run beating every before run happens by
chance 1 time in 20, and a 95% interval allows 1 in 40 on each side. With 4 a
side it can, but only if all 16 pairs agree. At 5 a side, 2 of the 25 pairs
may disagree, so 5 is the fewest that leaves room for ordinary noise.
`--min-runs` refuses less than 5 and takes more.

At any count, the 95% assumes each run is an independent draw, so that with
no change, which runs came before and which after is down to chance. Runs that
share one busy hour, or one slow runner pool, move together, and five of them
are worth less than five spread out. Let the after window run over more than a
day when you can, and say so when it didn't.

Few runs still cost something:

- The slowest 5% of under 20 runs is just the slowest run, so below 20 runs
  on the smaller side that side shows its "slowest run". The side with more
  runs shows its "typical slowest of 5" (for 5 runs on the other side): the
  median of the slowest of 5 drawn from its runs, so the two compare like
  with like. Both are provisional below 100 runs a side, and which side's is
  lower is weak evidence on its own: with 9 runs against 5, the 5-run side
  shows the lower one 9 times in 14 with no change at all, when no times
  are tied.
- The failure-rate test has little power with few runs: with 5 runs before,
  none failed, and 5 passed after, it takes 7 failed after to count as beyond
  chance. `compare` prints how many failed runs, beside the ones that
  passed, would count. Name the cause of every failure after the change
  whatever the test says.

## Break-it probe

For any change to tests or test setup: on a local throwaway branch (never
pushed, so it starts no CI run), re-plant a bug the suite caught before
(revert a fix, flip a condition), run the affected tests, and confirm they
fail for that reason. Report it, then delete the branch.
