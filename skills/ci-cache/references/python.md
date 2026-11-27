# Python installs: uv in place of pip, cached the right way

For a job that spends minutes of its setup installing Python packages. The
four rules in `SKILL.md` apply to every step here, and each fix is its own
pull request.

## 1. What the install costs now

From `measure.py split`, take the install step's median seconds, apart for
runs whose cache restored and runs whose cache didn't (`measure.py
cachelog` prints each job's cache lines). Read the install command and what
it installs from:

- a lock (`uv.lock`, `poetry.lock`, `pdm.lock`) or requirements pinned to
  exact versions, ideally with hashes: the same versions on every run;
- requirements with ranges (`>=`, `~=`, none at all): the resolver picks
  versions on each run, so two installers can pick different ones.

`actions/setup-python`'s `cache: pip` caches pip's global cache directory,
keyed on a hash of the dependency file (setup-python README); pip still
runs the install on every run.

## 2. Swap pip for uv, installing the same versions

The swap is one line: `pip install -r requirements.txt` becomes
`uv pip install -r requirements.txt`. uv needs a virtual environment unless
told otherwise: `uv pip install --system` installs into the interpreter
`setup-python` put on the path, which uv's docs call appropriate in CI.
Install uv with `astral-sh/setup-uv`, which uv's docs recommend; it is a new
third-party action and tool, so name it in the pull request for the person
to weigh.

uv's docs say pip and uv can resolve the same requirements to different
versions, both valid; uv doesn't read `pip.conf` or `PIP_*` variables (an
index set there must move to uv's own settings); and with several indexes
uv takes a package's versions from the first index that has it, where pip
combines them. So the swap must not change what gets installed:

1. Before: on CI, in the job, list the installed set with
   `python -m pip freeze --all` after the install, and save it as an
   artifact. After: `uv pip freeze` in the branch's job (`--system` when
   installed that way). Sort both.
2. They must match, apart from the installers themselves (pip, setuptools,
   wheel, which a pip-made environment can carry and a uv-made one may
   not). A test that needed one of those fails visibly; restore it as an
   explicit requirement, never by skipping the test.
3. If any other package or version differs, stop: pinning the versions
   first (exact pins in the requirements file, or a lock) is its own pull
   request, measured on its own. A project that installs with Poetry or
   PDM from their own lock files keeps its tool; moving it to uv is a
   person's call.

## 3. Cache uv's cache

`astral-sh/setup-uv` with `enable-cache: true` saves uv's whole cache to the
GitHub Actions cache. Its key includes the runner, the Python version and a
hash of the files matching `cache-dependency-glob`, by default the
requirements, constraints, `pyproject.toml` and lock files (setup-uv's
caching docs). It doesn't prune by default. With `actions/cache` instead,
key on `uv.lock`, or on `requirements.txt` when using `uv pip`, and run
`uv cache prune --ci` before the save, which uv's docs say reduces the
cache's size, with an effect on speed that "is dependent on the packages
being installed". The checks in `SKILL.md` step 3 apply as to any cache:
saved on the default branch, one key per job where jobs install different
sets, near the size cap.

## 4. Measure cold and warm runs apart

uv's gain differs with the cache. Hugo van Kemenade's lint job on
python/blurb took 60 s with pip and 37 s with uv with no cache, but 11 s
either way with one; the test job went from 1m 58s to 1m 22s with a cache.
So compare like with like, as `references/measuring.md` says
(`--cache-state`), and report the install step and the job, cold and warm,
with the installed sets matching.

## Why this works: reasoning

This is reasoning from how CI works, not a measurement.

- On an ephemeral runner every job installs into a new environment, so
  the installer's own speed is paid on every run, cache or not.
- Comparing the installed set by name and version, from the same job on
  CI, shows the swap changed only how the packages got there; the tests
  then run against the same code.

## What others measured

As their authors reported them; we didn't reproduce them.

- Hugo van Kemenade, python/blurb, on GitHub Actions: "around 1.5 times as
  fast"; test with no cache 2m 0s → 1m 26s, lint with a cache 11 s → 11 s.
- Matia Rašetina, 10 runs a side on GitHub Actions with fresh installs:
  "pip averaged around 73 seconds, while uv averaged about 23.5 seconds."
- Home Assistant, image builds rather than tests: aarch64 1h 24m 53s →
  5m 18s; "In total, we save around 215 hours per month."

Sources and grades: `references/evidence.md`.
