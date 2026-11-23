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

Write `.joggernaut/baseline.md`: workflow, job and runner label measured,
run count, median and slowest 5%, the tests that ran (from the JUnit report
CI saves, or the runner's count if there is none), and these commands.

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

`compare` needs 20 successful comparable runs a side and reports the failure
rate on both sides. If more runs fail after than chance explains (a one-sided
test at 5%), the result is not valid; a smaller rise is printed, and you
report it. Report
its verdict as printed. `tests` fails if any test stopped running, was newly
skipped or newly fails.

**If there aren't 20 runs yet**, say "not enough runs yet", write the exact
commands above into the pull request so anyone can finish the measurement,
and stop. Never trigger runs to fill the count without asking: runs cost money.

## Break-it probe

For any change to tests or test setup: on a local throwaway branch (never
pushed, so it starts no CI run), re-plant a bug the suite caught before
(revert a fix, flip a condition), run the affected tests, and confirm they
fail for that reason. Report it, then delete the branch.
