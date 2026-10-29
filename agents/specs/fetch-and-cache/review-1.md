# Review: fetch-and-cache 1.2, the gaps step 3 needed settled

**Date:** 2026-10-29
**Spec:** `agents/specs/fetch-and-cache/spec.md` (1.1 to 1.2)
**Task list written against it:** `agents/tasks/fetch-and-cache/tasks-2.md`

## What is being reviewed and how

Writing the task list for step 3 of the implementation order (cache and incremental sync for repos and commits) found places where fetch-and-cache 1.1 was silent or, in one case, would lose data. Version 1.2 settles them so the task list has no "decide with the user" tasks. Two are real decisions and are asked separately; the rest are choices made on the spec's own logic, reported below so they can be flagged. The spec and task list are written on the recommended option of each decision; picking the other option changes the paragraphs named under it.

For each choice: approve it or flag it. For each decision: pick an option.

## Automatic checks

- Whitespace and end-of-file checks (the only pre-commit hooks that apply to Markdown): pass, checked by hand because this session has no Python 3.14 to run `pre-commit`. No code changed.
- Every spec section is mapped to a task or a later step in the task list's coverage table: checked by hand.
- GitHub documentation could not be fetched from this session (`docs.github.com` is outside the session's allowed network), so the API behaviour cited in Decision 1 is from GitHub's documentation as known, not re-read today. Task 4 of the task list records real responses where the network allows, which checks it.

## Choices made (approve or flag)

1. **Merge commits are flagged.** `Commit` gains `is_merge: bool` (more than one parent). The stats spec excludes merge commits from line counts by default (`stats.exclude_merge_commits`), but 1.1's `Commit` had no way to tell one. Reversible.
2. **Only `sync` reaches the network.** `repos()` and `commits()` read the cache. 1.1's docstrings said `commits()` paginated from GitHub while the system spec's data flow said records are yielded from the cache; 1.2 follows the system spec, so a warm-cache report makes no requests.
3. **New types are defined:** `Repo` (name, default branch, head oid, fork and archived flags, `pushedAt`, `updatedAt`, missing), `SyncReport` (repos listed, repos skipped, rows written per resource, repos fully refetched), `RESOURCES` (the resource names `sync` accepts), and `Cache` with `SyncState` and its methods. 1.1 used `Repo`, `SyncReport` and `Cache` without defining them. A resource whose step is not built yet raises `NotImplementedError`.
4. **The skip rule compares GitHub's values with GitHub's values.** 1.1 skipped a repo whose `pushedAt`/`updatedAt` were "not newer than its stored `synced_at`", which compares server time with local time. 1.2 stores the listed `pushedAt` and `updatedAt` in `sync_state` in the same transaction as the rows and skips when they are unchanged, so an interrupted repo is never skipped.
5. **`Fetcher` takes an optional `client`.** Tests inject a `GitHubClient` pointed at the replay server; production passes none.
6. **Missing repos are left out of `repos()`.** Their rows stay in the cache, as 1.1 required, but a deleted or transferred repo no longer contributes to a report. Flag this if you want history from deleted repos kept in reports.
7. **The `--max-age` and `--no-fetch` behaviour stays in step 5** with the CLI flags, as the implementation order already says; step 3 delivers `sync(..., full_refresh=True)`.
8. **Fixtures may be hand-written when GraphQL is unreachable.** The cloud sandbox refuses GraphQL (step 2's Tasks 7 and 8 hit this). Task 4 records real responses when it can, and otherwise writes them from GitHub's documented shapes, notes the deviation, and leaves the re-recording to a session with network access, as step 2 did.
9. **Only the tables step 3 uses are created.** `meta`, `repos`, `commits`, `etags` and `sync_state`; later steps add theirs with a `SCHEMA_VERSION` increase, which the identity check turns into a clear `CacheVersionError`.

## Decisions

### Decision 1: how incremental commit sync finds new commits

**What is being decided:** whether new default-branch commits are found by a time window, as 1.1 says, or by comparing the stored head with the new head.

**Background:** 1.1 reads `history(since: watermark - overlap)` with a one-hour overlap. GraphQL's `since` filters on commit dates, like `git log --since`. A commit can reach the default branch long after its date: a pull request merged with a merge commit brings in branch commits dated days or weeks earlier, and so does pushing work committed offline. Those commits fall before the window and are never fetched, so line counts are silently low. Squash and rebase merges create new commits and are not affected. 1.1 also needed an ancestry check for force-pushes but did not say how to make it.

**What it affects:** `Fetcher` commit sync (task list Tasks 7 to 9), the queries (Task 4), whether `GitHubClient` needs to expose a server timestamp, and request cost.

**Options:**

- **A. Compare from the stored head (recommended).** When the listed head differs from the stored one, REST `compare/{stored}...{new}` returns exactly the commits reachable from the new head and not the old (like `git log stored..new`) and a `status` that is the ancestry check: `ahead` means fast-forward; `diverged`, `behind` or a 404 means rewritten history, which triggers a full refetch. Line counts come from one GraphQL `nodes(ids:)` query per 100 new commits. No time watermark is needed for commits, so no server clock, and commits skip the periodic 30-day full re-read because every rewrite is seen. Cost: one REST call per 100 new commits plus one GraphQL call per 100. This is what 1.2 says.
- **B. Keep the time window from 1.1.** Simpler query path, but commits merged with older dates are missed; the spec would list that as an accepted limit. It also needs `GitHubClient` to expose the server's `Date` header for the watermark, and a compare call anyway for the force-push check.

**Recommendation:** A, because the missed commits are exactly the kind of error that looks right and is not.

### Decision 2: where the `stats/code_frequency` cross-check runs

**What is being decided:** whether the cross-check of line totals against REST `stats/code_frequency` runs at sync time or only in the opt-in live test.

**Background:** 1.1 says the endpoint is "used only as a cheap cross-check on repos under 10,000 commits" without saying when, or what happens on a mismatch. The implementation order's done criterion for step 3 uses it in an opt-in live test. GitHub computes these statistics in the background (the 202 handling from step 2), and how it counts merge commits is not documented, so totals can differ for reasons that are not bugs.

**What it affects:** run time and requests per repo, a new error type if a runtime mismatch must stop the run (the shared versions rule forbids warning and carrying on), and Task 11.

**Options:**

- **A. Live test only (recommended).** The opt-in live test syncs `octocat/Hello-World` and compares summed non-merge additions and deletions with the endpoint. No runtime cost or new error. This is what 1.2 says.
- **B. At sync time.** Every repo under 10,000 commits gets one extra REST call per sync, and a mismatch raises a new `FetchError` subclass. Needs a spec section on the error and what the user does about it.

**Recommendation:** A. A runtime check that can fail for undocumented reasons would stop real reports; the live test proves the method once.

## Answers

- 2026-10-29, Decision 1: A, compare from the stored head (Simon, decision card).
- 2026-10-29, Decision 2: A, opt-in live test only (Simon, decision card).
- 2026-10-29, Choices 1 to 9: none flagged; PR #10, which carried them, was merged.
