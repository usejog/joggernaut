# Python installs: uv's cache, and uv in place of pip

For a job that spends minutes of its setup installing Python packages. The
four rules in `SKILL.md` apply to every step here, and each change is its
own pull request.

## 1. A job that already installs with uv: cache uv's cache

`astral-sh/setup-uv` saves uv's whole cache to the GitHub Actions cache,
keyed on the runner, the Python version and a hash of the requirements,
constraints, `pyproject.toml` and lock files. Its default, `enable-cache:
auto`, caches on GitHub-hosted runners except for release, tag-push,
`pull_request_target` and `workflow_run` events; leave it at that default
rather than `true` (setup-uv's caching docs). `prune-cache: true` drops
what is cheap to fetch again, an effect on speed uv's docs say "is
dependent on the packages being installed". `SKILL.md` step 3's checks
apply as to any cache.

## 2. A job that installs with pip: offer uv to a person

Swapping pip for uv changes how packages are found, built and checked, so
it is a person's call. uv's docs list where the two differ: they can
resolve the same requirements differently; uv reads none of pip's settings
(`pip.conf`, `PIP_*`) and has its own (`uv.toml`, `[tool.uv]`, `UV_*`); it
takes a package's versions from the first index that has it; it checks
only the hashes given unless told `--require-hashes`, where pip requires a
hash for every package once one has one; it treats `Requires-Python` upper
bounds differently. Matching lists of names and versions can't show that
the same files were installed.

Give the person:

- the install step's seconds on cold and warm runs, from the saved runs'
  step times, as a ceiling on what the swap can save (part of that time
  can be compiling a package under either installer);
- which of the differences above apply to this job: its requirements (a
  complete, exact set, or ranges), its index settings and its hashes;
- that `astral-sh/setup-uv` is a new third-party action, and the uv
  version it would pin.

On a yes, make the swap as its own pull request, installing into the
interpreter the tests run with (`uv pip install --python` naming it), and
cache uv's cache in a later one as step 1 says.

## 3. Measure

As `SKILL.md` step 5 says. uv's gain differs with the cache: Hugo van
Kemenade's lint job gained nothing from uv once it had one.

## What others measured

As their authors reported them; we didn't reproduce them.

- Hugo van Kemenade moved python/blurb's lint and test workflows to
  uv-based actions on GitHub Actions: "around 1.5 times as fast"; lint with
  no cache 60s → 37s, with a cache 11s → 11s.

Sources and grades: `references/evidence.md`.
