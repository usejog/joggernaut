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
and ask before writing there.

```sh
MEASURE fetch --repo OWNER/NAME --workflow ci.yml --event pull_request --limit 150 \
  --out .joggernaut/before.jsonl   # several workflows: before-<name>.jsonl each
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

```sh
MEASURE fetch --repo OWNER/NAME --workflow ci.yml --event pull_request \
  --created '>=YYYY-MM-DDTHH:MM:SSZ' --out .joggernaut/after.jsonl   # the merge time
# keep only runs that tested the fix: pull requests into the same branch (not
# ones that check out the PR head), or commits with the fix in their history
MEASURE compare --before .joggernaut/before.jsonl --after .joggernaut/after.jsonl \
  --label RUNNER-LABEL [--job NAME]     # always pass the runner label; add --job when jobs run on different runners
MEASURE tests --before JUNIT-BEFORE --after JUNIT-AFTER   # each downloaded into a new, empty folder
```

`compare` needs at least 5 successful comparable runs a side and reports the
failure rate on both sides. If more runs fail after than chance explains (a
one-sided test at 5%), the result is not valid; a smaller rise is printed, and
you report it. Report its verdict as printed, with the run count it names, for
example "median faster (5 runs a side)". `tests` fails if any test stopped
running, was newly skipped or newly fails.

**If there aren't 5 runs a side yet**, say "not enough runs yet", write the
exact commands above into the pull request so anyone can finish the
measurement, and stop. Never trigger runs to fill the count without asking:
runs cost money.

**If the verdict is "no measurable change yet"**, the change may be real but
smaller than the run-to-run noise at this count. Say so, and mark it
provisional. To measure again, choose the larger count first (20 a side, say),
wait until it is there, and report that comparison and how many times you
compared. Running `compare` again and again until it says "faster" would make
a chance result look like a real one.

## How compare decides, and why 5

The verdict comes from the Hodges-Lehmann estimate of how far the times moved
(the median of every after-minus-before difference) and its exact 95%
Mann-Whitney confidence interval (Bauer, 1972): two of those differences,
picked by the exact distribution of the rank-sum count under "no change".

- **median faster**: the whole interval is below zero and the median fell.
- **median slower**: the whole interval is above zero and the median rose.
- **mixed**: the interval excludes zero, but the median moved the other way
  or not at all, as when a change makes most runs faster and the middle one
  slower. Report both numbers; don't call it faster.
- **no measurable change yet**: the interval includes zero.

We chose it over a bootstrap and over a permutation test on the medians:

- A bootstrap interval is a large-sample approximation: nothing guarantees
  its 95% with 5 runs a side.
- The exact interval holds its 95% at any count. Excluding zero is a
  two-sided rank-sum test at 5% that the after runs tend to be faster (or
  slower); that part needs no assumption about how the times are spread.
  Read as a size, the interval assumes the change moves times without
  reshaping them, which is why the median must agree before the verdict
  says "median". Ties, common with whole-second times, only make it more
  cautious.
- A permutation test on the medians gives a yes or no, not a size, and its
  interval would need a search over shifts. The rank interval gives both.

The floor follows from the method. With 3 runs a side no 95% interval can
rule out "no change": every after run beating every before run happens by
chance 1 time in 20, and a 95% interval allows 1 in 40 on each side. With 4 a
side it can, but only if all 16 pairs agree. At 5 a side, 2 of the 25 pairs
may disagree, so 5 is the fewest that leaves room for ordinary noise.
`--min-runs` refuses less than 5 and takes more.

Few runs still cost something, and the output says what:

- The slowest 5% of under 20 runs is just the slowest run, so below 20 runs
  on the smaller side the tail is "slowest run". The side with more runs
  shows where the slowest of that many of its runs typically falls, so the
  two compare like with like. Either is provisional below 100 runs a side.
- The failure-rate test has little power with few runs: with 5 runs before,
  none failed, and 5 passed after, it takes 7 failed after to count as beyond
  chance. `compare` prints how many would count. Name the cause of every
  failure after the change whatever the test says.

## Break-it probe

For any change to tests or test setup: on a local throwaway branch (never
pushed, so it starts no CI run), re-plant a bug the suite caught before
(revert a fix, flip a condition), run the affected tests, and confirm they
fail for that reason. Report it, then delete the branch.
