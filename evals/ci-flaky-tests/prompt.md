Use the ci-flaky-tests skill: the test job on this repository fails now and
then and passes when someone reruns it.

This sample repository has no GitHub remote. Its recorded run history is in
`ci-history/runs.jsonl`, and the failing step's output is in
`ci-history/failure.txt`: use them in place of fetching. Run the tests with
`python3 -m unittest discover -s tests -t . -v`. Fix it the way the skill
says by editing the files here (don't commit or push), and write the pull
request description you would open to `PR.md`.
