# Python installs: uv's cache, and uv in place of pip

For a job that spends minutes of its setup installing Python packages. The
four rules in `SKILL.md` apply to every step here, and each change is its
own pull request.

## 1. A job that already uses setup-uv: cache uv's cache

`astral-sh/setup-uv` saves uv's whole cache to the GitHub Actions cache,
keyed on the runner, the Python version and a hash of the requirements,
constraints, `pyproject.toml` and lock files (setup-uv's caching docs).
Which events its default, `enable-cache: auto`, caches on depends on the
version pinned; read that version's docs, and keep any events it or the
workflow leaves out of the cache left out. `prune-cache: true` drops
pre-built wheels and keeps those built from source. `SKILL.md` step 3's
checks apply as to any cache. Leave out a job that runs unpinned tools
with `uvx`, or installs from a `--find-links` folder whose wheels are
rebuilt under the same names: a restored cache can keep an older tool or
wheel than a fresh run would use.

## 2. A job that installs with pip: offer uv to a person

First, `SKILL.md` step 3's own fix, `setup-python`'s `cache: pip`, with
step 3's checks (cost included), kept only if step 5 says it pays.

Swapping pip for uv changes how packages are found, built and checked, so
it is a person's call. uv's docs list where the two differ: they can
resolve the same requirements differently; uv reads none of pip's settings
(`pip.conf`, `PIP_*`) and has its own (`uv.toml`, `[tool.uv]`, `UV_*`); it
takes a package's versions from the first index that has it; it checks
only the hashes given unless told `--require-hashes`, where pip requires a
hash for every package once any requirement carries `--hash`; it treats
`Requires-Python` upper bounds differently. Matching lists of names and versions can't show that
the same files were installed.

Give the person:

- the install step's seconds on cold and warm runs, from the saved runs'
  step times, as a ceiling on what the swap can save (part of that time
  can be compiling a package under either installer);
- which of the differences above apply to this job: its requirements (a
  complete, exact set, or ranges), its index settings and its hashes;
- that `astral-sh/setup-uv` is a new third-party action, and the uv
  version it would pin.

On a yes, the swap is its own pull request: setup-uv with
`enable-cache: false`, every pip setting and hash mode the job relies on
carried over (`--require-hashes` where its requirements carry hashes), and
uv installing into the interpreter the tests run with (`--python` with its
path). Caching uv's cache, as step 1 says, is a later one.

## 3. Measure

As `SKILL.md` step 5 says. uv's gain differs with the cache: Hugo van
Kemenade's lint job gained nothing from uv once it had one.

## What others measured

As their authors reported them; we didn't reproduce them.

- Hugo van Kemenade moved python/blurb's lint and test workflows to
  uv-based tools, timed on his fork's GitHub Actions runs: "around 1.5
  times as fast"; lint with no cache 60s → 37s, with a cache 11s → 11s.

Sources and grades: `references/evidence.md`.
