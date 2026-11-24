# Measuring, in short

The same in every skill's folder, so a skill installed alone can measure.
`MEASURE` below means `python3 <this skill's folder>/scripts/measure.py`: the
copy beside this file, not a script in the repository being measured. Run it
from the root of the repository being measured; it writes to `.joggernaut/`
there and adds that folder to `.git/info/exclude`, so nothing gets committed.

Needs Python 3.9+ and the GitHub CLI, logged in (`gh auth status`). If `gh`
isn't logged in, stop and ask the person to run `gh auth login`.

## When the agent may not run the script's GitHub calls

Some teams guard what their agents run. `fetch` and `cachelog` run `gh`, and
`fetch` runs `git` to check that its output isn't tracked. Everything else
only reads files. To describe runs without letting the script call
anything, save GitHub's own answers with plain GET calls you run yourself,
then point `split` (or `flaky`) at the folder: with a folder, the script
never imports `subprocess` and starts no process. Whether a guard may allow
the file at all is the person's policy; ask, and don't work around a guard.

```sh
mkdir -p .joggernaut/saved   # untracked: git ls-files .joggernaut must list nothing
gh api --method GET --paginate --slurp repos/OWNER/NAME/actions/workflows/ci.yml/runs \
  -f event=pull_request -f status=completed -f per_page=100 \
  -f created='START..YYYY-MM-DDTHH:MM:SSZ' > .joggernaut/saved/runs.json   # a few days; every page in one file
# then, for each run id in it (filter=all keeps the attempts before a rerun):
gh api --method GET --paginate --slurp repos/OWNER/NAME/actions/runs/RUN_ID/jobs \
  -f filter=all -f per_page=100 > .joggernaut/saved/jobs-RUN_ID.json
MEASURE split --runs-dir .joggernaut/saved
```

Files are told apart by what they hold, so names don't matter. A run with
no jobs saved, fewer jobs than its pages' count, or only its latest
attempt's jobs is left out and named; more than one in 20 stops it. This is
for describing runs. `compare` refuses a folder: a saved listing can't show
the query that filled it (a listing of successes alone is complete by its
own count, with every failure missing), so a verdict reads only files
`fetch` wrote.

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
longest job each one ran, lists the groups (the six with the most of the
wait; `--json` has all) with each one's run count, median, slowest runs and
share of the total wait, and heads with the group of 5 runs or more that
holds the most of the wait (`--cohort JOB` picks another). The median over
all of them comes last, labelled as a blend; it is no group's wait. The
slowest path is the chain of jobs that decided when each run ended, read
from the jobs' times; it runs through the jobs of called (reusable)
workflows, which GitHub lists in the caller's run as `CALLER / JOB`.

If GitHub answers a read with a server error (HTTP 5xx), drops the
connection or cuts the answer off, `fetch` tries twice more, waiting a few
seconds between tries. A run whose jobs still can't be read is left out
and named (`left out: run N (failure), jobs read failed 3 times: HTTP
502`), never written without its jobs. If more than one run in 20 (or more
than one, in a short fetch) can't be read, `fetch` stops: fetch again
later. A window read whole (`START..END`, the after side below) stops at
the first such run and isn't written, since the run left out could be a
failure the comparison must count: fetch it again.
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
  leave it out. A failed or cancelled run that stopped before that line
  (before checkout, or in it) stays: it is never timed, and its failure or
  cancellation counts.

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

Runs that ran different jobs did different work. `compare` reads a run's
work, as far as the jobs list shows it, as the set of jobs it ran (names
with counts, so matrix legs count):

- one set on both sides: whole runs compare as before;
- one set on each side, different between them: the verdict ends in
  `_jobs_changed` (`faster_jobs_changed`, say) and is never a plain one. It
  holds only if the workflow's diff explains every difference (jobs
  folded, split or renamed) and every removed job's work still runs (the
  tests compared by name, below); otherwise the mix of pull requests
  changed, not the CI;
- several sets within a side (a path filter, an `if:`): `compare` refuses a
  whole-run verdict, since the median would move with the mix, and lists
  the before side's sets. Time one job's own duration with `--job`: that
  is the verdict. `--ran JOB` times whole runs that ran that job (it must
  leave one set a side), a descriptive reading only (`ran_descriptive`,
  the reading in `reading`): which runs ran a job can change with the
  change itself (a path filter moved from slow pushes to fast ones keeps
  every count), so it is never a verdict. Either way the named job picks a
  workload, the runs where it ran: failures and cancellations are checked among those runs as well as
  over the whole workflow, so a job whose slow runs start failing or being
  cancelled can't leave only its fast ones to time.

The same jobs can still run different tests (per-pull-request test
selection inside a job); only `MEASURE tests` shows that, and only for the
reports compared, and it passes a run that ran more tests. Where selection
can vary inside a job, a speed verdict needs every timed run to have run the
same tests: compare each run's report with one reference run's both ways
(`--before A --after B`, then `--before B --after A`; both pass only when
the names match). If they all match, the verdict stands; if timing only the
matching runs would mean dropping rows from the files, don't build such
files (the failure rate must read every run): report the timings as
unverified instead (issue #32 tracks a tool check). The same holds for a step that
runs on some runs only (an `if:` on a step, such as a site build on some
paths): if the timed runs didn't all run the same steps (the run file records
each step's conclusion; a skipped step shows `skipped`), report the timings
as unverified, for the same reason. A step a cache hit skips is the cache's
effect: time hits and misses apart, each with both options
(`--cache-state STATE.json --cache hit`, then `--cache-state STATE.json --cache miss`). `compare` also counts each side's runs cancelled with no
failure (a newer push, a concurrency group): they are in neither the
timings nor the failure rate. When the share cancelled rose beyond chance
(the failure check's one-sided exact test), over the workflow or among a
named job's runs, a faster (also with more failures) or mixed verdict ends in
`_more_cancelled`: if the change makes slow
runs get cancelled, the runs left are the fast ones. Equal shares can still
hide which runs finished (issue #33): read the cancelled runs before calling
it faster. `--job NAME --end` times that
job from the run's start to its end, on the run's clock (its queue and the
jobs before it count), not the job's own duration, so the same job-set rule
applies to it over every job the runs ran (a job queued beside it can hold
its runner), and every job's runner must match on both sides. Its reading is
descriptive only (`end_descriptive`; the reading itself is in `--json` as
`reading`): a job's end moves with which runs reached it, their queue
order and their runners, more than any check can pin down. Report it beside
the job's own duration (`--job` alone) and the whole run's wait, which give
the verdict.

`compare` needs at least 5 successful comparable runs a side. Those are the
runs it times; `--label`, `--job` and `--cache` choose them. The failure rate
it reports reads every finished run of the workflow and event in each file,
whatever those filters say, so a filter can't hide or dilute a failure; a job
named with `--job` or `--ran` is checked among its own runs as well (both
named: each one's runs and the runs where both ran, the worst counting). When fewer
runs reached the named job after than chance explains, a faster or mixed
verdict ends in `_fewer_reached`; when more did (a filter or a matrix that
widened), in `_more_reached`. Either way the runs timed may not be like the
runs before, so say why. Runs can miss a job in several ways (a failure or
cancellation before it, a condition, a matrix leg left out, a skipped
caller), and no one count sees them all without other traffic diluting it,
so several are checked, and a change in any counts: among the runs that list
the job (or a caller of it, or it by name), among the runs where the other
named job ran (both ways, with `--ran` and `--job`), and among all runs
(the runs that missed it, those that missed it with a failure or
cancellation in the run, and those that list it and did). `--json` lists each
(`reach_checks`); the text prints each. If
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
