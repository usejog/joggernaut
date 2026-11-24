# Evidence for ci-guard

Public posts this skill relies on, each re-read at its link on 23 Nov 2026. Numbers are as
the source states them; we did not reproduce them.

Grades: **A** measured, first person, named repository or company; **B**
measured, first person, unnamed; **C** vendor or company figures without a
measured CI result; **D** opinion, a prompt or a restatement.

| Source | What it reports | Grade |
|---|---|---|
| [Owen Gretzinger (@owengretzinger), Boardy, 30 Oct 2026](https://x.com/owengretzinger/status/2116291924219060319) | Pre-push hook runs format, lint and type check on changed files in under 9 seconds: "Put it in a hook rather than a line in AGENTS.md, because agents skip steps." | A |
| [Marc (Kumiko), DEV, Nov 2026](https://dev.to/marc_kumiko/our-coding-agents-skipped-the-pre-push-hook-on-118-of-411-pushes-27j0) | Agents skipped the pre-push hook on 118 of 411 push commands in agent transcripts; most stated reasons cited an allowed exception (not verified by the author); all of them still had to pass CI before merging. | A |
| [Stripe, "Minions" part 1, stripe.dev, 9 Feb 2026](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) | At most two rounds of CI per agent task, "since CI runs cost tokens, compute, and time". Company practice; no CI-time figure for the cap. | C |
| [Jonathan Muszkat, Selenios, 13 Oct 2026](https://me.jonymusky.com/blog/merge-queue-ai-ci-tax) | Updates that brought a pull request up to date with main were 51% of its CI minutes; `gh pr update-branch` was on the list of commands agents could run without asking. After the move to GitHub's merge queue, updated pull requests open under 4 hours went from 82% to 27%; in the queue's first week keeping pull requests current cost 6% more for those and 22% less for pull requests open 4 to 24 hours, and 9% of queue entries failed. The team then added an AGENTS-file rule ("Do not merge `main` into a PR branch … just to bring it up to date"). | A |
| [Tw93 (@HiTw93), 10 Nov 2026](https://x.com/HiTw93/status/2120164408945152470) | An agent piped a suite into tail and reported a red run as green (one incident, an anecdote). | D |

## How the platform behaves, from its own docs

Not results: what the vendor documents, re-read on 23 Nov 2026. A claim
marked "GitHub docs" or "Go's docs" in `SKILL.md` rests on one of these.

- [GitHub Docs: events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): for `pull_request`, `GITHUB_SHA` is the last merge commit on `refs/pull/N/merge`, and the default activity types are opened, synchronize and reopened, so a push to a pull request can start every workflow subscribed to `synchronize` (the default), unless a filter skips it, the pull request has a merge conflict, or a run from a fork waits for approval ("Workflows will not run on pull_request activity if the pull request has a merge conflict").
- [GitHub Docs: managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue): required workflows need the `merge_group` trigger, or the queue's required checks never report.
- [GitHub Docs: control jobs with conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions): a job skipped by a condition reports "Success" and doesn't block a merge, even as a required check.
- [GitHub Docs: about protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches): "Any person or integration with write permissions to a repository can set the state of any status check in the repository" unless a required check names the app expected to report it; by default the rules don't apply to admins or roles with the "bypass branch protections" permission.
- [Claude Code docs: hooks](https://code.claude.com/docs/en/hooks): exit code 2 blocks the action, with stderr as the message; for a Stop hook it "Prevents Claude from stopping, continues the conversation"; a Stop hook's input carries `stop_hook_active`, true when Claude is already continuing because of a stop hook; hook commands run in the current directory.
- [Git: githooks, pre-push](https://git-scm.com/docs/githooks#_pre_push): the hook gets one line per ref on stdin, `<local-ref> SP <local-object-name> SP <remote-ref> SP <remote-object-name> LF`; a ref the remote doesn't have yet has "the all-zeroes object name", and a delete has `(delete)` and an all-zeroes local name; a non-zero exit stops the push. Before a hook runs, git changes to "the root of the working tree in a non-bare repository".
- [Git: git-config, core.hooksPath](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corehooksPath): git looks for hooks in that folder "instead of in $GIT_DIR/hooks"; "A relative path is taken as relative to the directory where the hooks are run".
- [Git: git-worktree, configuration file](https://git-scm.com/docs/git-worktree#_configuration_file): "By default, the repository config file is shared across all worktrees."
- [Git: git-diff-tree](https://git-scm.com/docs/git-diff-tree) and [pathspecs](https://git-scm.com/docs/gitglossary#Documentation/gitglossary.txt-aiddefpathspecapathspec): `--quiet` implies `--exit-code`, so the exit status says whether two trees differ under the given pathspecs, without printing (or quoting) a path; `:(exclude)` leaves paths out.
- [Git: git, --no-lazy-fetch](https://git-scm.com/docs/git#Documentation/git.txt---no-lazy-fetch): "Do not fetch missing objects from the promisor remote on demand", the way to test whether an object is local in a partial clone.
- [TypeScript: tsconfig.json](https://www.typescriptlang.org/docs/handbook/tsconfig-json.html): "When input files are specified on the command line, tsconfig.json files are ignored."
- [TypeScript 6.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html), "Specifying Command-Line Files When tsconfig.json Exists is Now an Error": `error TS5112: tsconfig.json is present but will not be loaded if files are specified on commandline.`
- [TypeScript: extends](https://www.typescriptlang.org/tsconfig/extends.html): "All relative paths found in the configuration file will be resolved relative to the configuration file they originated in."
- [TypeScript 5.5 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-5.html), "The ${configDir} Template Variable for Configuration Files": a path in a shared base config can start with `${configDir}`, which stands for the folder of the config that uses it.
- [TypeScript: incremental](https://www.typescriptlang.org/tsconfig/#incremental) and [tsBuildInfoFile](https://www.typescriptlang.org/tsconfig/#tsBuildInfoFile): `incremental` saves "information about the project graph from the last compilation to files stored on disk"; without `outFile` or `outDir` the file defaults to `<config name>.tsBuildInfo` beside the config, and `tsBuildInfoFile` sets where it goes.
- [TypeScript 4.0 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-0.html): "TypeScript 4.0 allows us to use the `noEmit` flag while still leveraging `incremental` compiles."
- [typescript-go README](https://github.com/microsoft/typescript-go): "Incremental build | done" and "Build mode / project references | done"; "For TypeScript 7.0 RC and later, the command name is `tsc`."
- [Bash CHANGES, bash-4.4-rc2](https://git.savannah.gnu.org/cgit/bash.git/tree/CHANGES): "Using ${a[@]} or ${a[*]} with an array without any assigned elements when the nounset option is enabled no longer throws an unbound variable error." Earlier versions, macOS's bash 3.2 among them, throw it.
- [Claude Code docs: environment variables](https://code.claude.com/docs/en/env-vars): `BASH_DEFAULT_TIMEOUT_MS`, "Default timeout for a foreground Bash or PowerShell tool command ... (default: 120000, or 2 minutes)".
