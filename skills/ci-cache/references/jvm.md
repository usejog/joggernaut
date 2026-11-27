# Gradle, Maven and Android: the cache each build tool expects

For a Java, Kotlin or Android job that spends minutes downloading
dependencies or rebuilding what an earlier run built. Android builds are
Gradle builds, so the Gradle part covers them. The four rules in `SKILL.md`
apply to every step here, and each fix is its own pull request.

## 1. What the build costs now

From `measure.py split`, take the build step's median seconds, apart for
runs whose cache restored and runs whose cache didn't (`measure.py
cachelog`). Note how the workflow caches today: `gradle/actions/setup-gradle`,
`actions/setup-java` with `cache: gradle` or `cache: maven`, an
`actions/cache` step over `~/.gradle` or `~/.m2`, or nothing.

## 2. Gradle: setup-gradle, written from the default branch

- `gradle/actions/setup-gradle` caches by default. It saves the Gradle
  User Home's `caches` (downloaded dependencies in `caches/modules-2`, the
  local build cache in `caches/build-cache-1`) and `notifications`, and the
  wrapper's distributions (setup-gradle docs).
- By default it writes the cache only from jobs on the default branch;
  other branches restore it read-only. That keeps pull requests from
  filling the repository's cache cap with copies of their own. It is the
  layout Acecore settled on: "only main saves the shared cache, and PRs
  restore it in read-only mode". A job that never runs on the default
  branch never saves one, so check `SKILL.md` step 3.1 too.
- Use it in place of, never beside, an `actions/cache` step over the
  Gradle User Home or `setup-java`'s `cache: gradle`: its docs say either
  "may interfere with the caching provided by this action". Moving to it
  is one pull request; removing the old step is part of it.
- Its docs call its default cache provider "currently available as a Free
  Preview for private repositories". Read its current terms; a provider
  that would cost money is a person's call.

**Replayed test tasks.** With Gradle's build cache turned on
(`org.gradle.caching=true` or `--build-cache`), a restored cache can replay
a test task as `FROM-CACHE` instead of running it, with the old task's
outputs, its test reports among them, so `measure.py tests` sees the same
tests as if they ran. Gradle keys that on the task's declared inputs, so a
test that reads an undeclared file, an environment variable, a service or
the clock can be replayed when it would now fail. That is `SKILL.md`
step 4's case: check those tests as it says for Go, and make such a test
task run on the merge gate (declare the input it reads, or mark the task
not cacheable with `outputs.cacheIf { false }`). Turning the build cache on
is a change of its own, and the same check comes first.

## 3. Maven: setup-java's cache, and the build cache extension

- `actions/setup-java` with `cache: maven` caches `~/.m2/repository`, keyed
  on `**/pom.xml`, `**/.mvn/wrapper/maven-wrapper.properties` and
  `**/.mvn/extensions.xml` (setup-java README). That is the dependency
  cache; check it against `SKILL.md` step 3 like any other.
- Maven's build cache extension (Maven 3.9 or later) "calculates a key
  from module inputs, stores outputs in the cache, and transparently
  restores them later", so a cached module's tests don't run again. It is
  an input-keyed task cache, so `SKILL.md` step 4 applies to every module
  whose tests it would replay. Its docs recommend clean builds for
  production artifacts, and Picnic turns it off on its default branch and
  release builds. Adding it is a change of its own, it needs a place to
  keep the cache between runs, and where a module's tests read anything
  outside its inputs, the merge gate builds that module without it.

## 4. Measure cold and warm runs apart

Compare like with like, as `references/measuring.md` says (`--cache-state`):
the build step and the job, cold and warm. Gradle's last lines count the
tasks it ran, took from the cache and found up to date; report those beside
the times, before and after.

## Why this works: reasoning

This is reasoning from how CI works, not a measurement.

- An ephemeral runner starts with an empty Gradle User Home or `~/.m2`, so
  without a cache every run downloads every dependency and rebuilds every
  task.
- A pull request's cache can be restored only by later runs of the same
  pull request (GitHub docs), so letting only the default branch write
  keeps one copy that every pull request can read.
- A cache keyed on a task's declared inputs replays the task when those
  inputs match. What it doesn't declare, it can't see.

## What others measured

As their authors reported them; we didn't reproduce them.

- Acecore, an Android job on one commit: "16 minutes 20 seconds on the
  initial run and 6 minutes 16 seconds on the rerun" with the Gradle cache
  restored, which took 62 seconds. One pair of runs; it didn't measure its
  final layout.
- Picnic, on TeamCity with the Maven build cache extension: "Instead of 10
  minutes 4 seconds, the build that was fully cached took only 1 minute 22
  seconds"; "Build times dropped from 12 minutes to 8 minutes in general."

Sources and grades: `references/evidence.md`.
