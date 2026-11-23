Use the ci-slow-tests skill: this repository's test step is the slowest part
of its CI, and it is getting slower as tests are added.

This sample repository has no GitHub remote. The test report from the latest
CI run is in `ci-history/junit-latest.xml`: use it in place of fetching. Run
the tests with `python3 -m unittest discover -s tests -t . -v`. Make the one
fix the skill calls for by editing the files here (don't commit or push), and
write the pull request description you would open to `PR.md`.
