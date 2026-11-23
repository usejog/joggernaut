Use the ci-cache skill: setup is slow on this repository's pull requests,
and the dependency cache seems to miss on every new pull request.

This sample repository has no GitHub remote. Its recorded run history is in
`ci-history/runs.jsonl` and the cache lines from its logs, plus the list of
caches, are in `ci-history/cache-lines.txt`: use them in place of fetching.
The maintainers have already approved adding runs on `main` if the fix
needs them. Make the one fix the skill calls for by editing the files here (don't commit
or push), and write the pull request description you would open to `PR.md`.
