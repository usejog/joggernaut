# Python installs: uv in place of pip

For a job that spends minutes of its setup in `pip install`. The four rules
in `SKILL.md` apply to every step here, and each change is its own pull
request.

## 1. When the swap applies

Swap only where pip installs a complete, exact set: every package,
dependencies included, pinned to one version (a compiled requirements file,
`pip-compile` style), from the default index or indexes named in the file
itself. Anything else can let uv and pip install different code, so leave
it out of this recipe:

- ranges or unpinned dependencies: uv's docs say pip and uv "will yield
  different resolutions" in some cases. Pinning is its own pull request,
  measured on its own, before any swap.
- settings in `pip.conf` or `PIP_*` variables, `--find-links`, or several
  indexes: uv reads none of pip's settings, and takes a package's versions
  from the first index that has it where pip combines them (uv's docs).
- a project installed with Poetry or PDM: it keeps its tool; moving it is
  a person's call.

## 2. The swap, with no cache yet

`pip install -r requirements.txt` becomes
`uv pip install --python "$(command -v python)" -r requirements.txt`, so uv
installs into the interpreter the tests run with and not into a virtual
environment it finds on its own. If the file carries hashes, add
`--require-hashes`: pip then requires a hash for every package, and uv
checks only the hashes given unless told to. Install uv with
`astral-sh/setup-uv` and `enable-cache: false`: its default turns caching
on for GitHub-hosted runners, and a cache is the next pull request, not
this one. setup-uv is a new third-party action, so name it in the pull
request for the person to weigh. Drop `setup-python`'s `cache: pip`, which
caches pip's own cache folder, which uv doesn't use.

Check the installed set on CI, in the job, with the same command on both
sides: after the install, save `python -m pip list --format=freeze`
(names and versions only) from runs before the change and from the
branch's runs. They must match exactly, pip and setuptools included. If a
package is missing or differs, stop, and fix the requirements first in a
pull request of their own.

## 3. Then cache uv's cache

A separate pull request turns setup-uv's `enable-cache: true` on. It saves
uv's whole cache, keyed on the runner, the Python version and a hash of the
requirements, constraints, `pyproject.toml` and lock files (setup-uv's
caching docs); `prune-cache: true` drops what is cheap to fetch again, an
effect on speed uv's docs say "is dependent on the packages being
installed". `SKILL.md` step 3's checks apply as to any cache: saved on the
default branch, near the size cap.

## 4. Measure

As `SKILL.md` step 5 says. uv's gain differs with the cache: Hugo van
Kemenade's lint job gained nothing once it had one. So compare the job
over cold runs and over warm runs apart (`compare --job JOB --cache-state
FILE --cache miss`, then `--cache hit`), with the installed sets matching.

## Why this works: reasoning

This is reasoning from how CI works, not a measurement.

- On an ephemeral runner every job installs into a new environment, so the
  installer's own speed is paid on every run, cache or not.
- With an exact, complete set from the same indexes, both installers fetch
  the same packages, and the matching lists show it on CI.

## What others measured

As their authors reported them; we didn't reproduce them.

- Hugo van Kemenade moved python/blurb's lint and test workflows to
  uv-based actions on GitHub Actions: "around 1.5 times as fast"; lint with
  no cache 60s → 37s, with a cache 11s → 11s.

Sources and grades: `references/evidence.md`.
