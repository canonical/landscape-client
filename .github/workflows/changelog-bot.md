---
# Biweekly changelog PR bot (GitHub Agentic Workflow).
#
# This is the gh-aw SOURCE file. After editing, regenerate the compiled
# GitHub Actions workflow with:
#
#     gh aw compile changelog-bot
#
# and commit the generated `.github/workflows/changelog-bot.lock.yml` alongside it.

on:
  # Cron cannot express "every other Saturday", so we fire every Saturday at
  # around 12:00 UTC and the prompt gates on ISO-week parity (see the body below).
  schedule: weekly on saturday around 12:00 UTC
  # Allow maintainers to trigger a run on demand (ignores the biweekly gate).
  workflow_dispatch:

permissions:
  contents: read

# The default checkout is shallow (fetch-depth 1) with no tags, which makes the
# agent see only the latest commit. Fetch full history and tags so it can diff
# against the last release and read the commit log.
checkout:
  - fetch-depth: 0
  # The docs repo is checked out alongside so the agent can draft user-facing
  # release notes in the shared docs PR (see the prompt below).
  - repository: canonical/landscape-documentation
    path: ./landscape-documentation
    fetch: ["*"]
    github-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}

engine:
  id: copilot
  model: sonnet

# Only the shell commands the agent needs to inspect history and format dates.
tools:
  bash:
    - "git"
    - "date"
    - "safeoutputs"
  edit:

# The agent never pushes directly; its file edits are turned into a pull request.
# One token governs both PR handlers (gh-aw requirement when two handlers touch
# the same repo). COPILOT_GITHUB_TOKEN needs contents:write and
# pull-requests:write on canonical/landscape-documentation for the cross-repo
# docs PR.
safe-outputs:
  github-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}
  create-pull-request:
    title-prefix: "build: "
    labels: [changelog, automation]
    team-reviewers: [canonical/landscape]
    draft: false
    if-no-changes: ignore
    max: 2                      # own-repo changelog PR + docs PR
    allowed-repos: ["canonical/landscape-documentation"]
    preserve-branch-name: true
    recreate-ref: true
  push-to-pull-request-branch:
    target: "*"
    target-repo: canonical/landscape-documentation
    required-labels: [changelog, automation]
    max: 1
---

# Biweekly changelog update

You maintain the Debian changelog for Landscape Client. Your job is to draft a new release block summarizing recent user-facing changes and open a pull request with it.

## Biweekly gate

This workflow is scheduled every Saturday but should only act every **other** Saturday. Releases publish on **odd** ISO weeks.

This run was triggered by the `${{ github.event_name }}` event. Use that value literally to decide whether the gate applies:

1. If the triggering event is `workflow_dispatch`, always proceed regardless of the week number (manual runs bypass the biweekly gate entirely).
2. Otherwise (a `schedule` run), run `date +%V` to get the current ISO week number. If that week number is **even**, stop immediately and make no changes — do not open a pull request. Only proceed on **odd** weeks.

## Gather the commits

1. The changelog lives at `debian/changelog`. Read its top block to find the most recent version, which looks like `landscape-client (26.08.1-0landscape0) jammy; urgency=medium`.
2. Determine the last release point with `git describe --tags --abbrev=0 --match '[0-9][0-9].[0-9][0-9]*' --exclude 'import/*' --exclude 'applied/*'`. Release tags look like `26.08.1` or `26.08-beta.4` (note: tags use a hyphen where the changelog uses a tilde). The `--exclude` flags are required because this repo carries gbp import tags under the `import/*` and `applied/*` namespaces that must not be mistaken for releases. If `git describe` fails, fall back to the version parsed from the top changelog block.
3. Collect commit subjects since that point with `git log <last>..HEAD --no-merges --pretty=%s`.

## Select user-facing commits only

Include only conventional commits that a Landscape administrator would notice:

- **Include**: `feat:`, `fix:`, `perf:`, and any breaking change (a `!` before the colon, e.g. `feat!:` / `fix!:`).
- **Maybe Include**: `refactor: ` commits, only if they are user-facing.
- **Exclude**: `chore:`, `ci:`, `test:`, `build:`, `docs:`, and `style:`, commits,
  plus anything that only touches tooling, tests, or CI.

Add each selected commit's subject line, including its type prefix and any `(LP: #NNNN)` Launchpad references, but excluding any `(scope)` after the type prefix. Proofread and correct any obvious spelling or grammar errors. Remove Jira issue references such as `LNDENG-5678` wherever they occur in the subject, and strip any trailing GitHub pull request reference such as ` (#1234)`. Do **not** strip `(LP: #NNNN)` references. If there are no user-facing commits, stop and make no changes.

## Sort the commits

Group the commits by their type. Adhere to the following order.

- Breaking changes (!)
- `feat`
- `fix`
- `perf`
- `refactor`

Within each group, maintain the relative ordering of the commits.

## Compose the new block

1. Parse the current top version from the changelog.
2. Produce the next version:
   - If the top version contains `~beta.N` (e.g. `26.08~beta.4-0landscape0`), increment the beta number to `26.08~beta.<N+1>`.
   - Otherwise (a final `YY.MM` or a patch `YY.MM.P`, e.g. `26.08.1-0landscape0`), start the next release cycle: pick the next `YY.MM` from the cycle cadence visible in the changelog (recent cycles: 25.10, 26.02, 26.08) relative to the run date, and use `YY.MM~beta.1`. Explain your choice of the new cycle version in the pull request body.
   - Use `-0landscape0` for the new debian revision even if the previous debian revision was something different. Use the same distribution and urgency (e.g. `jammy; urgency=medium`).
3. Prepend a new block to the top of `debian/changelog`, matching the exact existing format (See https://manpages.debian.org/testing/dpkg-dev/deb-changelog.5.en.html):

   ```
   landscape-client (26.08~beta.<N+1>-0landscape0) jammy; urgency=medium

     * <user-facing commit subject>
     * <user-facing commit subject>

    -- Landscape Bot <landscape-server-bot@canonical.com>  <date>
   ```

   - Each bullet is indented with two spaces and begins with `* `.
   - The signature line is indented with one space and begins with `-- `.
   - Use `date -R` for `<date>` (RFC 2822, e.g. `Sat, 18 Jul 2026 12:00:00 +0000`), with two spaces between the email and the date.

## Additional Changes

Bump the version in `landscape/__init__.py`:

- `UPSTREAM_VERSION`: set to the new changelog version exactly, tilde included (e.g. `26.08~beta.4` to `26.08~beta.5`).
- `PYTHON_VERSION`: set to the PEP 440 equivalent of `UPSTREAM_VERSION` (e.g. `26.08~beta.4` becomes `26.8b4`, `26.08.1` becomes `26.8.1`). `UPSTREAM_VERSION` and `PYTHON_VERSION` always move together.
- Leave `DEBIAN_REVISION` unchanged; it stays `"-0landscape0"`.

If for some reason the existing version is older than anticipated, still update it to the latest version. (e.g. `26.08~beta.3` to `26.08~beta.5`)

## Open the pull request

Open a pull request with the change. Use a title like `release for 26.08~beta.<N+1> for jammy` (the `build: ` prefix is added automatically) and a body that lists the included commits, explains the chosen next version, and notes that only user-facing changes were selected.

## Docs release notes (shared PR)

In addition to the Debian changelog, you maintain one island in ONE SHARED pull request against `canonical/landscape-documentation` that drafts the user-facing release notes for the in-development Landscape release. NEVER open a separate per-repo docs PR.

1. Determine the in-development Landscape release `YY.MM`: Landscape releases are `YY.04` and `YY.10`. From today's date, the in-development release is the next boundary strictly in the future (before April -> `YY.04`; before October -> `YY.10`; otherwise `(YY+1).04`). As of November 2026 this is **27.04** (betas are underway), so the target page is `docs/reference/release-notes/27.04-release-notes.md`.
2. Find the shared docs PR: use the GitHub tools to list open PRs in `canonical/landscape-documentation` with labels `changelog` and `automation` (title starts with `build: `). If one exists, this is THE docs PR — use it regardless of which `YY.MM` page it targets.
3. If a docs PR exists:
   - In the `./landscape-documentation` checkout, check out that PR's head branch (PR refs were fetched via the wildcard fetch; e.g. `git checkout <branch>` after identifying it, or `git fetch origin pull/<N>/head:<branch>`).
   - Update ONLY your own island (see below). If the release-notes page for the in-development version does not exist on that branch, create it from the template below and add it to the toctree in `docs/reference/release-notes/index.md` (newest non-LTS page goes directly under the LTS entries, matching existing ordering).
   - Before committing, re-sync onto the branch's latest tip: `git fetch origin pull/<N>/head` (or `git fetch origin <branch>`), then rebase/reset your work onto the fetched tip so the push is a fast-forward. Several changelog bots update this same shared branch.
   - Commit in the docs checkout and deliver via `push_to_pull_request_branch` with `pull_request_number` set to the docs PR number.
4. If no docs PR exists: skip the docs release-notes work for this run entirely. You NEVER create the shared docs PR — only landscape-server's changelog bot creates it, which avoids several bots racing to create the same PR. (Your in-repo changelog work above is unaffected.)
5. If you have no user-facing changes this cycle, leave your island untouched; do not create or update the docs PR. (Your own-repo changelog PR logic is unaffected.)

### Your island

Island markers (HTML comments, invisible in rendered docs). Your slug is `landscape-client`. The full island set, in this fixed order:

1. `landscape-server` — Landscape Server
2. `landscape-client` — Landscape Client
3. `landscape-ui` — Web portal
4. `landscape-go` — Snaps (debarchive, outbox, task-handler services)
5. `landscape-server-operator` — Landscape Server charm
6. `landscape-client-charm` — Landscape Client charm
7. `landscape-debarchive-operator` — Debarchive charm
8. `landscape-task-handler-operator` — Task handler charm

Island format inside `## Additional updates`:

```markdown
<!-- changelog-bot:landscape-client:start -->
### Landscape Client

#### Features
- <docs-appropriate bullet>

#### Fixes
- <docs-appropriate bullet>
<!-- changelog-bot:landscape-client:end -->
```

Rules:
- BEFORE writing, read `.github/instructions/release-notes.instructions.md` and `.github/instructions/documentation.instructions.md` in the docs checkout and follow them (applicability: state self-hosted vs SaaS and the component; factual, non-promotional; do not invent benefits, migration steps, or breaking-change claims).
- Rewrite your selected commits into user-facing docs bullets: no conventional-commit prefixes, no `(scope)`, no `(#1234)`, no Jira keys. Keep Launchpad references but format them as `[LP: #NNNN](https://bugs.launchpad.net/landscape/+bug/NNNN)`. Write in the style of existing release notes (see any `docs/reference/release-notes/*.md` page): complete sentences, no trailing period inconsistency, admin-focused.
- Omit `#### Features` / `#### Fixes` when empty. If your island has no entries yet, put `(pending)` as the island body.
- NEVER edit outside your own island markers. Other sections belong to other bots.
- When creating the page, include ALL eight islands in the fixed order above (yours filled, the rest with `(pending)`), so later bot runs find their markers.

### New-page template

File `docs/reference/release-notes/YY.MM-release-notes.md` (dots in the filename, matching `26.10-release-notes.md`; anchor uses dashes):

```markdown
---
myst:
  html_meta:
    description: "Release notes for Landscape YY.MM. Draft; updated automatically until release."
---

(reference-release-notes-YY-MM)=
# YY.MM release notes

> Landscape Server YY.MM runs on Ubuntu 26.04 LTS Resolute Raccoon, 24.04 LTS Noble Numbat, or 22.04 LTS Jammy Jellyfish.

```{note}
This page is a draft maintained automatically until release.
```

## Highlights

(pending - written at release time)

## Additional updates

(eight islands here)

## Upgrade

(pending - written at release time)

## Bug fixes

(pending - written at release time)
```
