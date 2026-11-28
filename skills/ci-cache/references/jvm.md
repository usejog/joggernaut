# Gradle, Maven and Android: the cache each build tool expects

For a Java, Kotlin or Android app job, built with Gradle or Maven, that
downloads dependencies on every run. The four rules in `SKILL.md` apply to
every step here, and each change is its own pull request.

## 1. When this applies

Note how the workflow caches today: `gradle/actions/setup-gradle`,
`actions/setup-java` with `cache: gradle` or `cache: maven`, an
`actions/cache` step over `~/.gradle` or `~/.m2`, or nothing. `measure.py
cachelog` doesn't read setup-gradle's own log lines; take its outcome from
the job summary setup-gradle writes, or record it as unknown.

Leave a build out of this recipe, for a person, where a restored cache could
change what gets built and tested:

- it resolves dynamic versions (`1.+`, `latest.release`) or changing
  artifacts, SNAPSHOTs included: a restored cache can supply an older
  artifact than a clean run would;
- a job installs the project's own modules into `~/.m2` (`mvn install`): a
  restored cache can then supply a module a later build forgot to build;
- it turns Gradle's build cache on (`org.gradle.caching=true` or
  `--build-cache`): with any cache of the Gradle User Home, the local
  build cache is saved across runs, so a test task can be replayed as `FROM-CACHE` with its old
  reports, and `measure.py tests` sees the same tests as if they ran. That
  is `SKILL.md` step 4's case, and a person decides after its check.

## 2. Gradle: setup-gradle, written from the default branch

- `gradle/actions/setup-gradle` caches by default: the Gradle User Home's
  downloaded dependencies and wrapper distributions among them
  (setup-gradle docs).
- By default it writes the cache only from jobs on the default branch;
  other branches restore it read-only, so pull requests don't fill the
  repository's cache cap with copies of their own. That is the layout
  Acecore settled on: "only main saves the shared cache, and PRs restore it
  in read-only mode". A job that never runs on the default branch never
  saves one, so check `SKILL.md` step 3.1 too.
- With setup-gradle v6.1.0 or later, set `cache-provider: basic`. The
  default provider, Enhanced Caching, is under Gradle's own terms, with
  usage-based pricing planned; choosing it, or changing a job that already
  uses it, is a person's call.
- It replaces a plain `actions/cache` step over the Gradle User Home, or
  `setup-java`'s `cache: gradle` input, which its docs say "may
  interfere". Remove only the overlapping cache step or input; keep
  `setup-java` itself, which installs the JDK. A cache step with
  `fail-on-cache-miss`, or whose `cache-hit` output a later step reads,
  is part of a check: leave it.

## 3. Maven: setup-java's cache

`actions/setup-java` with `cache: maven` caches `~/.m2/repository`, keyed on
the build files (setup-java README). Add only that input, and read the
pinned version's docs for anything else it turns on, keeping the rest as
it was. Check it against `SKILL.md` step 3 like any other cache. Maven's build cache extension also replays
cached modules' tests, so adding it is a person's call, after step 4's
check.

## 4. Measure

As `SKILL.md` step 5 says, and report the build's own counts beside the
times: Gradle's last lines count the tasks it ran, took from the cache and
found up to date.

## What others measured

As their authors reported them; we didn't reproduce them.

- Acecore's DaysChat Android job, one pair of runs on one commit with a
  pull-request cache: "16 minutes 20 seconds on the initial run and 6
  minutes 16 seconds on the rerun", the restore taking 62 seconds; the
  rerun also reused 194 Gradle tasks.
- Picnic, on TeamCity with Maven's build cache extension: "Instead of 10
  minutes 4 seconds, the build that was fully cached took only 1 minute 22
  seconds".

Sources and grades: `references/evidence.md`.
