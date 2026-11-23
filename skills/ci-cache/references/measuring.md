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

Write `.joggernaut/baseline.md`: workflow, job and runner label measured, run
count, median and the slowest runs as `split` printed them, the tests that ran
(from the JUnit report CI saves, or the runner's count if there is none), and
these commands.

## While the pull request is open

Put the baseline and the branch's own runs in the description, marked
**provisional**. Before asking for review, compare the tests that ran on the
branch with the baseline (`MEASURE tests`, below): a lost test fails the
change now, not after merge.

## After merge

Keep only runs that tested the fix: pull requests into the same branch (not
ones that check out the PR head), or commits with the fix in their history.
If `fetch` refuses, stop: `compare` would read an older file, so the `&&`
below runs it only after a fetch that succeeded.

```sh
MEASURE fetch --repo OWNER/NAME --workflow ci.yml --event pull_request \
  --created 'MERGE-TIME..WINDOW-END' --out .joggernaut/after.jsonl &&   # times as YYYY-MM-DDTHH:MM:SSZ
MEASURE compare --before .joggernaut/before.jsonl --after .joggernaut/after.jsonl \
  --label RUNNER-LABEL [--job NAME] &&  # always pass the runner label; add --job when jobs run on different runners
MEASURE tests --before JUNIT-BEFORE --after JUNIT-AFTER   # each downloaded into a new, empty folder
```

Choose the window before looking (a day or two after the merge, say), and
fetch it only once it has ended and every run created in it has finished;
`fetch` refuses it otherwise, and refuses a window with more runs than
`--limit`. Fast runs finish first, so stopping at the fifth run to
finish keeps the fastest of the window and can pass for a speedup with no
change at all.

`compare` needs at least 5 successful comparable runs a side and reports the
failure rate on both sides. If more runs fail after than chance explains (a
one-sided test at 5%), the result is not valid; a smaller rise is printed, and
you report it. Report its verdict as printed, with the run count it names, for
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
