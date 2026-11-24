#!/usr/bin/env python3
"""Check ci-guard's pre-push template in scratch git repositories, under every
POSIX shell present (on macOS /bin/sh and /bin/bash are bash 3.2; on Ubuntu
/bin/sh is dash). Called by tools/selftest.py; standard library only."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "skills/ci-guard/scripts/pre-push")
# Stub checks: each records its name, and typecheck fails while FAIL_TYPECHECK exists.
CHECKS = """checks() {
  check format    'echo format >>"$LOG"'
  check typecheck 'echo typecheck >>"$LOG"; test ! -e FAIL_TYPECHECK' . ':(exclude)*.md'
}"""
LIMIT = 'limit() { echo limiter >>"$LOG"; "$@"; }'


def shells():
    seen, out = set(), []
    for s in ("/bin/sh", "/bin/bash", "dash", "bash"):
        p = shutil.which(s)
        if p and os.path.realpath(p) not in seen:
            seen.add(os.path.realpath(p))
            out.append(p)
    return out


def hook_text(shell, limiter=False):
    text = open(HOOK).read()
    text, n = re.subn(r"(?ms)^checks\(\) \{\n.*?^\}", lambda m: CHECKS, text, count=1)
    assert n == 1, "the template has no checks() block"
    if limiter:
        text, n = re.subn(r'(?m)^limit\(\) \{ "\$@"; \}$', lambda m: LIMIT, text, count=1)
        assert n == 1, "the template has no default limit()"
    return "#!%s\n" % shell + text.split("\n", 1)[1]


def selftest(bad):
    """Each shell in its own scratch folder, in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    def one(sh):
        mine = []
        with tempfile.TemporaryDirectory() as t:
            try:
                _cases(mine, sh, os.path.realpath(t))
            except Exception as e:  # noqa: BLE001
                mine.append("pre-push (%s): crashed: %r" % (sh, e))
        return sh, mine
    with ThreadPoolExecutor() as pool:
        for sh, mine in pool.map(one, shells()):
            bad.extend(mine)
            if not mine:
                print("ok   pre-push template under %s" % sh)


def _cases(bad, sh, t):
    env = dict(os.environ, HOME=t, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               LOG=os.path.join(t, "log"), TMPDIR=t)
    for k in list(env):
        if k.startswith("GIT_") and k not in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL") \
                and not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_")):
            del env[k]
    remote, work = os.path.join(t, "remote.git"), os.path.join(t, "work")

    def git(*a, cwd=work, check=True):
        r = subprocess.run(["git"] + list(a), cwd=cwd, env=env, capture_output=True, text=True)
        if check and r.returncode:
            raise RuntimeError("git %s: %s" % (" ".join(a), r.stderr))
        return r.stdout.strip()

    def write(path, text, cwd=work):
        p = os.path.join(cwd, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)

    def log():
        if not os.path.exists(env["LOG"]):
            return []
        ran = open(env["LOG"]).read().split()
        os.remove(env["LOG"])
        return ran

    def hook(lines, args=("origin", remote), cwd=work, limiter=False, raw=None):
        p = os.path.join(t, "hook")
        open(p, "w").write(hook_text(sh, limiter))
        os.chmod(p, 0o755)
        data = raw if raw is not None else "".join(l + "\n" for l in lines)
        r = subprocess.run([sh, p] + list(args), cwd=cwd, env=env, capture_output=True,
                           text=True, input=data)
        return r.returncode, r.stderr, log()

    def expect(what, got, want_rc, want_log, err_has=(), err_lacks=()):
        rc, err, ran = got
        if rc != want_rc or ran != want_log or any(s not in err for s in err_has) \
                or any(s in err for s in err_lacks):
            bad.append("pre-push (%s): %s: exit %d, ran %s\n%s" % (sh, what, rc, ran, err))

    def line(ref, new, old, src=None):
        return "%s %s %s %s" % (src or ref, new, ref, old)

    git("init", "-q", "--bare", "-b", "main", remote, cwd=t)
    git("init", "-q", "-b", "main", work, cwd=t)
    git("remote", "add", "origin", remote)
    write("src/a.ts", "export const a = 1\n")
    write("README.md", "x\n")
    git("add", "-A"); git("commit", "-qm", "one")
    git("push", "-q", "origin", "main")
    main = git("rev-parse", "HEAD")
    Z = "0" * len(main)

    # A new branch that changes only the README: typecheck is skipped, format runs.
    git("checkout", "-qb", "docs"); write("README.md", "y\n"); git("commit", "-qam", "docs")
    docs = git("rev-parse", "HEAD")
    expect("README-only new branch", hook([line("refs/heads/docs", docs, Z)]),
           0, ["format"], ["skip typecheck"])
    expect("README-only, remote at main", hook([line("refs/heads/docs", docs, main)]),
           0, ["format"], ["skip typecheck"])

    # A .ts change: both run.
    git("checkout", "-qb", "code", "main"); write("src/a.ts", "export const a = 2\n")
    git("commit", "-qam", "code")
    code = git("rev-parse", "HEAD")
    expect(".ts change", hook([line("refs/heads/code", code, Z)]), 0, ["format", "typecheck"],
           ["format: queued", "format: ok in "], err_lacks=["WARNING", "waiting for a slot"])
    # A failing check fails the push, and the other checks still run.
    write("FAIL_TYPECHECK", "")
    expect("failing check", hook([line("refs/heads/code", code, Z)]),
           1, ["format", "typecheck"], ["typecheck: FAILED", "FAILED: typecheck"])
    os.remove(os.path.join(work, "FAIL_TYPECHECK"))

    # Names git would quote, or split on a newline: still changes typecheck reads.
    for i, name in enumerate(("src/é.ts", "src/a\nb.ts", "src/q\"uote.ts")):
        git("checkout", "-qb", "odd%d" % i, "main"); write(name, "export const e = 1\n")
        git("add", "-A"); git("commit", "-qm", "odd")
        odd = git("rev-parse", "HEAD")
        git("checkout", "-q", "code")
        expect("odd path %r" % name, hook([line("refs/heads/odd", odd, Z)]), 0, ["format", "typecheck"])

    # A submodule pointer that moves: a change typecheck must not skip.
    git("checkout", "-qb", "sub", "main")
    git("update-index", "--add", "--cacheinfo", "160000,%s,vendor/api" % main)
    git("commit", "-qm", "gitlink")
    sub = git("rev-parse", "HEAD")
    git("checkout", "-q", "code")
    expect("gitlink change", hook([line("refs/heads/sub", sub, Z)]), 0, ["format", "typecheck"])

    # The remote has a commit this clone never fetched (someone fixed a type error there),
    # and this push replaces it with a README-only change: the range is unknown, so all run.
    unseen = "1" * len(main)
    expect("remote tip not fetched", hook([line("refs/heads/docs", docs, unseen)]),
           0, ["format", "typecheck"], ["running every check", "doesn't have"])
    # Several refs: an unknown one on either line runs everything; a later line can't clear it.
    for lines in ([line("refs/heads/x", docs, unseen), line("refs/heads/docs", docs, main)],
                  [line("refs/heads/docs", docs, main), line("refs/heads/x", docs, unseen)]):
        expect("multi-ref, one unknown", hook(lines), 0, ["format", "typecheck"], ["running every check"])
    # A new branch pushed to a URL: no remote-tracking branch to compare with.
    expect("new branch to a URL", hook([line("refs/heads/docs", docs, Z)], args=(remote, remote)),
           0, ["format", "typecheck"], ["running every check"])
    # Several known refs: any one that needs a check runs it, once.
    expect("multi-ref union", hook([line("refs/heads/docs", docs, Z), line("refs/heads/code", code, Z)]),
           0, ["format", "typecheck"])
    # A local source with spaces in it (git keeps it as typed) still parses.
    expect("source with spaces", hook([line("refs/heads/code", code, Z, src="HEAD@{1 day ago}")]),
           0, ["format", "typecheck"], err_lacks=["unreadable"])
    expect("unreadable line", hook(["garbage"]), 0, ["format", "typecheck"], ["unreadable input"])

    # Deletes only (either hash length), nothing to push, and tags: nothing runs.
    for z in ("0" * 40, "0" * 64):
        expect("delete only", hook([line("refs/heads/gone", z, main, src="(delete)")]), 0, [])
    expect("no refs", hook([], raw=""), 0, [])
    git("tag", "-a", "-m", "v1", "v1", code)
    tag = git("rev-parse", "v1")
    expect("annotated tag", hook([line("refs/tags/v1", tag, Z)]), 0, [], ["not checked: refs/tags/v1"],
           err_lacks=["WARNING: the checks"])

    # Pushing a commit that isn't HEAD (HEAD is code): warned, by ref.
    expect("pushed commit isn't HEAD", hook([line("refs/heads/docs", docs, Z)]),
           0, ["format"], ["WARNING: the checks read the working tree at HEAD %s; refs/heads/docs gets %s"
                           % (code, docs)])
    # Untracked and uncommitted files: warned.
    write("src/new.ts", "export const n = 1\n")
    write("src/a.ts", "export const a = 3\n")
    expect("untracked and dirty", hook([line("refs/heads/code", code, Z)]),
           0, ["format", "typecheck"], ["untracked files", "src/new.ts", "uncommitted changes"])
    os.remove(os.path.join(work, "src/new.ts")); git("checkout", "-q", "--", "src/a.ts")

    # A job limiter: each check is queued, goes through it, and says when it runs.
    expect("limiter", hook([line("refs/heads/code", code, Z)], limiter=True),
           0, ["limiter", "format", "limiter", "typecheck"],
           ["typecheck: queued", "typecheck: running: "])

    # --all, no arguments, or a stop hook's JSON on stdin: every check, on the working tree.
    for args in (("--all",), ()):
        expect("working-tree mode %r" % (args,), hook([], args=args, raw='{"hook_event_name":"Stop"}'),
               0, ["format", "typecheck"])

    # A legacy .git/hooks/pre-push gets git's exact input, including none at all,
    # and its failure blocks the push; it never runs in working-tree mode.
    legacy = os.path.join(work, ".git/hooks/pre-push")
    open(legacy, "w").write('#!/bin/sh\necho "$1 $2" >"$LOG.args"\ncat >"$LOG.legacy"\nexit "${LEGACY_EXIT:-0}"\n')
    os.chmod(legacy, 0o755)

    def legacy_got():
        p = env["LOG"] + ".legacy"
        if not os.path.exists(p):
            return None
        got = open(p).read()
        os.remove(p)
        return got
    for data in ("", line("refs/heads/code", code, Z) + "\n"):
        hook([], raw=data)
        got = legacy_got()
        if got != data:
            bad.append("pre-push (%s): the legacy hook got %r for %r" % (sh, got, data))
    hook([], args=("--all",))
    if legacy_got() is not None:
        bad.append("pre-push (%s): the legacy hook ran in working-tree mode" % sh)
    env["LEGACY_EXIT"] = "1"
    expect("legacy hook fails", hook([line("refs/heads/code", code, Z)]), 1, ["format", "typecheck"])
    env["LEGACY_EXIT"] = "0"

    # Real pushes through a relative core.hooksPath, from a linked worktree, two branches
    # at once: the worktree runs its own checkout's hook, then the legacy hook.
    os.makedirs(os.path.join(work, ".githooks"))
    hp = os.path.join(work, ".githooks/pre-push")
    open(hp, "w").write(hook_text(sh))
    os.chmod(hp, 0o755)
    git("add", ".githooks"); git("commit", "-qm", "hook")
    git("config", "core.hooksPath", ".githooks")
    wt = os.path.join(t, "wt")
    git("worktree", "add", "-q", "-b", "two", wt, "HEAD")
    write("src/b.ts", "export const b = 1\n", cwd=wt)
    git("add", "-A", cwd=wt); git("commit", "-qm", "b", cwd=wt)
    r = subprocess.run(["git", "push", "-q", "origin", "two", "docs"], cwd=wt, env=env,
                       capture_output=True, text=True)
    sent = legacy_got() or ""
    ran = log()
    if r.returncode != 0 or ran != ["format", "typecheck"] or sent.count("\n") != 2 \
            or "refs/heads/two" not in sent or "refs/heads/docs" not in sent:
        bad.append("pre-push (%s): real two-branch push from a worktree: exit %d, ran %s, "
                   "legacy got %r\n%s" % (sh, r.returncode, ran, sent, r.stderr))
    # Then a README-only push to the branch the remote now has: typecheck skipped.
    write("README.md", "z\n", cwd=wt); git("commit", "-qam", "readme", cwd=wt)
    r = subprocess.run(["git", "push", "-q", "origin", "two"], cwd=wt, env=env,
                       capture_output=True, text=True)
    ran = log()
    if r.returncode != 0 or ran != ["format"] or "skip typecheck" not in r.stderr:
        bad.append("pre-push (%s): real README-only push: exit %d, ran %s\n%s"
                   % (sh, r.returncode, ran, r.stderr))

    # A SHA-256 repository: 64-digit names parse, and a .ts change runs typecheck.
    s256 = os.path.join(t, "s256")
    if subprocess.run(["git", "init", "-q", "--object-format=sha256", s256], env=env,
                      capture_output=True).returncode == 0:
        write("README.md", "x\n", cwd=s256)
        git("add", "-A", cwd=s256); git("commit", "-qm", "one", cwd=s256)
        git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=s256)
        write("src/a.ts", "export const a = 1\n", cwd=s256)
        git("add", "-A", cwd=s256); git("commit", "-qm", "ts", cwd=s256)
        tip = git("rev-parse", "HEAD", cwd=s256)
        expect("SHA-256 repository", hook([line("refs/heads/main", tip, "0" * 64)], cwd=s256),
               0, ["format", "typecheck"], err_lacks=["running every check"])


if __name__ == "__main__":
    problems = []
    selftest(problems)
    for b in problems:
        print("FAIL " + b)
    sys.exit(1 if problems else 0)
