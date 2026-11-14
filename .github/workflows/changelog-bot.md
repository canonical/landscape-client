---
# Weekly changelog PR bot (GitHub Agentic Workflow).
#
# This is the gh-aw SOURCE file. After editing, regenerate the compiled
# GitHub Actions workflow with:
#
#     gh aw compile changelog-bot
#
# and commit the generated `.github/workflows/changelog-bot.lock.yml` alongside it.

on:
  schedule: weekly on saturday around 12:00 UTC
  # Allow maintainers to trigger a run on demand.
  workflow_dispatch:

# Run on the Canonical self-hosted fleet. The agent and threat-detection jobs
# need Docker/AWF and target the noble amd64 runners; the framework and
# safe_outputs jobs only need the self-hosted label.
runs-on: [self-hosted, noble, amd64]
runs-on-slim: self-hosted

permissions:
  contents: read

jobs:
  activation:
    pre-steps:
      - name: Setup modern Node for gh-aw runtime
        uses: actions/setup-node@v4
        with:
          node-version: "24"
  detection:
    pre-steps:
      - name: Install modern gh CLI
        run: |
          GH_VERSION="2.83.1"
          GH_SHA256="1c5252d4ce3db07b51c01ff0b909583da6364ff3fdc06d0c2e75e62dc0380a34"
          tmp="$(mktemp -d)"
          curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" -o "$tmp/gh.tgz"
          echo "${GH_SHA256}  $tmp/gh.tgz" | sha256sum -c -
          tar -xzf "$tmp/gh.tgz" -C "$tmp"
          install -m 0755 "$tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh
          rm -rf "$tmp"
          gh version
        env:
          GH_TOKEN: ${{ github.token }}
      - name: Install GitHub Copilot CLI
        run: |
          export NPM_CONFIG_PREFIX="$HOME/.npm-global"
          mkdir -p "$NPM_CONFIG_PREFIX"
          npm install -g @github/copilot@1.0.103
          echo "$NPM_CONFIG_PREFIX/bin" >> "$GITHUB_PATH"
          "$NPM_CONFIG_PREFIX/bin/copilot" --version

pre-steps:
  - name: Install modern gh CLI
    run: |
      GH_VERSION="2.83.1"
      GH_SHA256="1c5252d4ce3db07b51c01ff0b909583da6364ff3fdc06d0c2e75e62dc0380a34"
      tmp="$(mktemp -d)"
      curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" -o "$tmp/gh.tgz"
      echo "${GH_SHA256}  $tmp/gh.tgz" | sha256sum -c -
      tar -xzf "$tmp/gh.tgz" -C "$tmp"
      install -m 0755 "$tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh
      rm -rf "$tmp"
      gh version
    env:
      GH_TOKEN: ${{ github.token }}

# The self-hosted runner image lacks the Docker Compose plugin, so AWF's
# `docker compose up -d` fails ("unknown shorthand flag: 'd' in -d"). Install
# it before the AWF bring-up (same fix as the DISA STIG evaluator's
# test-airgap.md).
steps:
  - name: Install Docker Compose plugin
    run: |
      if docker compose version >/dev/null 2>&1; then
        echo "Docker Compose plugin already present, skipping install."
        docker compose version
        exit 0
      fi
      COMPOSE_VERSION="v5.5.0"
      mkdir -p ~/.docker/cli-plugins
      curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
        -o ~/.docker/cli-plugins/docker-compose
      chmod +x ~/.docker/cli-plugins/docker-compose
      docker compose version

# The default checkout is shallow (fetch-depth 1) with no tags, which makes the
# agent see only the latest commit. Fetch full history and tags so it can diff
# against the last release and read the commit log. A second checkout fetches
# the documentation repo (all branches) for the shared release-notes PR.
checkout:
  - fetch-depth: 0
  # canonical/landscape-documentation is a public repo, so the checkout needs
  # no token.
  - repository: canonical/landscape-documentation
    path: ./landscape-documentation
    fetch: ["*"]

engine:
  id: gemini
  # The native Gemini engine uses GEMINI_API_KEY directly and takes an exact
  # model id, avoiding the pi engine's model-grammar rejection of vendored
  # OpenRouter ids (github/gh-aw#77514). Gemini does not resolve gh-aw model
  # aliases, so this must be an exact id.
  model: gemini-3.5-flash
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}

network:
  allowed: [defaults]

# Shell access for inspecting history and formatting dates. The pi engine
# cannot allowlist individual commands, so bash is open; the AWF sandbox,
# network allowlist, and safe-output handlers still confine the run.
tools:
  bash: ["*"]
  edit:

# The agent never pushes directly; its file edits are turned into pull
# requests. gh-aw binds the whole safe_outputs job to a single credential for
# its git checkouts and pushes (github/gh-aw#77580), and the default
# GITHUB_TOKEN cannot write to canonical/landscape-documentation. Both
# handlers therefore run under LANDSCAPE_CHANGELOG_TOKEN, a fine-grained PAT
# with contents/pull-requests read+write on this repo and
# canonical/landscape-documentation (canonical/landscape-internal-docs#385).
safe-outputs:
  github-token: ${{ secrets.LANDSCAPE_CHANGELOG_TOKEN }}
  runs-on: self-hosted
  threat-detection:
    runs-on: [self-hosted, noble, amd64]
    # The detection job inherits the agent's engine by default; the external
    # threat-detect binary only supports the Copilot CLI, so pin it here.
    # Runs with COPILOT_GITHUB_TOKEN.
    engine: copilot
  create-pull-request:
    title-prefix: "build: "
    labels: [changelog, automation]
    team-reviewers: [canonical/landscape]
    draft: false
    if-no-changes: ignore
    max: 1                      # only ever the own-repo changelog PR
    preserve-branch-name: true
    recreate-ref: true
    # The bot only ever prepends to debian/changelog or bumps the version
    # constants in landscape/__init__.py; the handler rejects any other path
    # outright.
    allowed-files: ["debian/changelog", "landscape/__init__.py"]
    # gh-aw allowed-files filters by path only, not diff status, so "prepend a
    # new block, never rewrite existing changelog content" for debian/changelog
    # is enforced by the prompt, not the handler.
  push-to-pull-request-branch:
    github-token: ${{ secrets.LANDSCAPE_CHANGELOG_TOKEN }}
    target: "*"
    target-repo: canonical/landscape-documentation
    required-labels: [changelog, automation]
    # Docs PR updates may only touch release-notes pages (including index.md).
    allowed-files: ["docs/reference/release-notes/*.md"]
    max: 1
---

# Weekly changelog update

You maintain the Debian changelog for Landscape Client. Your job is to draft a new release block summarizing recent user-facing changes and open a pull request with it. You also maintain the Landscape Client island in the shared docs release-notes pull request (see "Docs release notes (shared PR)" below).

## Hard prohibitions

- NEVER edit, reformat, or delete any existing `debian/changelog` block; release blocks are historical records. You only ever PREPEND one new block at the top of the file.
- In this repository, only ever touch `debian/changelog` and `landscape/__init__.py`. In the `./landscape-documentation` checkout, only ever touch release-notes pages, and only inside your own island markers.
- These limits are mechanically enforced by the pull-request handlers: any other path is rejected from the delivered patch outright.

## Gather the commits

1. The changelog lives at `debian/changelog`. Read its top block to find the most recent version, which looks like `landscape-client (26.08.1-0landscape0) jammy; urgency=medium`.
2. Determine the last release point with `git describe --tags --abbrev=0 --match '[0-9][0-9].[0-9][0-9]*' --exclude 'import/*' --exclude 'applied/*'`. Release tags look like `26.08.1` or `26.08-beta.4` (note: tags use a hyphen where the changelog uses a tilde). The `--exclude` flags are required because this repo carries gbp import tags under the `import/*` and `applied/*` namespaces that must not be mistaken for releases. If `git describe` fails, fall back to the version parsed from the top changelog block.
3. Collect commit subjects since that point with `git log <last>..HEAD --no-merges --pretty=%s`.
4. Deduplicate against the top changelog block. A release pull request can be merged before its tag is pushed, so the tag from step 2 sometimes lags `debian/changelog` by one release and step 3 then re-collects commits that are already released per the changelog. For each collected commit, compare its subject with every bullet in the TOP block of `debian/changelog`: normalize both sides first (drop the conventional-commit type prefix and any `(scope)`, `(#1234)`, Jira, and `(LP: #NNNN)` references, then compare case-insensitively). Drop the commits that already have a matching bullet. If nothing remains, stop and make no changes.

## Select user-facing commits only

Include only commits that a Landscape administrator would notice. Commit subjects in this repo are conventional commits; match type prefixes case-insensitively and use your judgment for non-conforming subjects.

- **Include**: `feat:`, `fix:`, `perf:`, and any breaking change (a `!` before the colon, e.g. `feat!:` / `fix!:`).
- **Maybe Include**: `refactor: ` commits, only if they are user-facing.
- **Exclude**: `chore:`, `ci:`, `test:`, `build:`, `docs:`, and `style:`, commits,
  plus anything that only touches tooling, tests, or CI, and any dependency bumps.

Breaking changes are not always flagged in the subject. For every selected commit, also inspect the full commit message with `git show -s --format=%B <sha>` and look for `BREAKING CHANGE:` or `BREAKING-CHANGE:` footers. A commit carrying such a footer is a breaking change even when its subject has no `!` — classify it as breaking and note the breaking nature in the docs island bullet.

Add each selected commit's subject line, including its type prefix and any `(LP: #NNNN)` Launchpad references, but excluding any `(scope)` after the type prefix. Proofread and correct any obvious spelling or grammar errors. Remove Jira issue references such as `LNDENG-5678` wherever they occur in the subject, and strip any trailing GitHub pull request reference such as ` (#1234)`. Do **not** strip `(LP: #NNNN)` references. If there are no user-facing commits, stop and make no changes.

## Review the commits

Flag-only: never edit or delete existing changelog content, and never silently drop an ambiguous commit. List every flag under a `Changelog entries to review` heading in the pull request body, one bullet per commit with the reason and evidence (commit SHA, PR links). If no pull request is opened, report the flags in your run summary instead — never open a pull request just to report flags.

- **Fix for an unreleased regression**: for a `fix:` commit F, take the hunks F modified (`git show -U0 F`) and run `git blame --porcelain -L <start>,<end> F^ -- <file>` to find the commits that introduced those lines. If they ALL fall inside your scan window (i.e. after the last release point), the bug never shipped: drop the commit from the changelog block and the docs island, and flag it. A PR title or body that references another PR merged in the same window is supporting evidence. If the blame results are mixed, keep the commit in the block and mark the flag "possible", not certain.
- **No pull request reference**: the subject has no trailing ` (#1234)`, so its coverage cannot be cross-checked against a merged PR. Still include the commit if it is user-facing, but flag it so a human can confirm.

## Sort the commits

Group the commits by their type. Adhere to the following order.

- Breaking changes (a `!` in the subject or a `BREAKING CHANGE:`/`BREAKING-CHANGE:` footer)
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

Open a pull request with the change. Use a title like `release 26.08~beta.<N+1> for jammy` (the `build: ` prefix is added automatically, matching this repo's release-PR titles such as `build: release 26.08~beta.4 for jammy`) and a body that lists the included commits, explains the chosen next version, notes that only user-facing changes were selected, and includes the `Changelog entries to review` heading when any commits were flagged. If no commits survived selection and review, do nothing — do not open an empty pull request.

## Docs release notes (shared PR)

In addition to the Debian changelog, you maintain one island in ONE SHARED pull request against `canonical/landscape-documentation` that drafts the user-facing release notes for the in-development Landscape release. That shared PR is created centrally: a scheduled `release-notes-draft` workflow in canonical/landscape-documentation opens it weekly (based on `develop`, pre-seeded with all eight islands, labeled `changelog` + `automation`, titled `build: draft release notes for Landscape YY.MM`). You NEVER create a docs PR yourself — find the shared PR and push your island to it, or skip the docs work if none is open.

The docs work happens in the separate `./landscape-documentation` checkout. The hard prohibitions above apply to this repository (landscape-client) only; editing the release-notes page inside your own island in the docs checkout is expected and allowed.

Your island content derives from ALL user-facing commits selected above, excluding only the commits dropped in "Review the commits" as certain fixes for unreleased regressions.

1. Determine the in-development Landscape release `YY.MM`: Landscape releases are `YY.04` and `YY.10`. From today's date, the in-development release is the next boundary strictly in the future (before April -> `YY.04`; before October -> `YY.10`; otherwise `(YY+1).04`). As of November 2026 this is **27.04** (betas are underway), so the target page is `docs/reference/release-notes/27.04-release-notes.md`.
2. Find the shared docs PR: use the GitHub tools to list open PRs in `canonical/landscape-documentation` with labels `changelog` and `automation` (titled `build: draft release notes for Landscape YY.MM`). If one exists, this is THE docs PR — use it regardless of which `YY.MM` page it targets.
3. If a docs PR exists:
   - In the `./landscape-documentation` checkout, check out that PR's head branch (branches were fetched via the wildcard fetch at setup: `git checkout <branch>`). If the branch is not among the fetched refs, skip the docs work for this run — the agent has no credentials to fetch it.
   - Other Landscape bots push to this same shared branch, so the checkout (fetched at setup time) may be stale and another bot may push while you work. The agent environment has NO git credentials — `git fetch` fails here, so NEVER attempt to fetch or rebase. Work from the PR branch ref as fetched at setup; keep every edit strictly inside your own island markers so it applies cleanly over the other bots' island updates. `push_to_pull_request_branch` applies your patch to the branch's live tip in a credentialed job; if a concurrent push made it conflict, the delivery fails safely — do not retry, the next run redoes the work. NEVER force-push over another bot's commits.
   - Update ONLY your own island (see below). If the release-notes page for the in-development version does not exist on that branch, create it from the template below and add it to the toctree in `docs/reference/release-notes/index.md` (newest non-LTS page goes directly under the LTS entries, matching existing ordering).
   - Commit in the docs checkout and deliver via `push_to_pull_request_branch` with `pull_request_number` set to the docs PR number.
4. If no docs PR exists, skip the docs release-notes work for this run entirely — make no changes in the `./landscape-documentation` checkout. The shared PR is created weekly by the `release-notes-draft` workflow in canonical/landscape-documentation; if none is open when you run (for example before that workflow's next weekly firing), the next run picks the work up. NEVER create the shared docs PR yourself — no changelog bot does. (Your in-repo changelog work above is unaffected.)
5. If you have no user-facing changes this cycle, leave your island untouched; do not update the docs PR. (Your own-repo changelog PR logic is unaffected.)

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
