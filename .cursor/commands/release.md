# Release

Execute the canonical release pipeline for this repo. **One merge to `main`, one CI/Pages cycle, one tag push** — do not tag until remote gates pass, and never delete/recreate a published tag (use a patch bump instead). Stable and pre-release share the same pipeline; only tagging and publish metadata differ.

This monorepo has **two independent version streams**:

| Track | File | Git tag | Workflow | Ships |
|---|---|---|---|---|
| **App** | `VERSION` | `v0.6.x` | `release.yml` | Docker image + bundled `solar_ai_optimizer.zip` at current `INTEGRATION_VERSION` |
| **Integration only** | `INTEGRATION_VERSION` | `integration-v0.1.x` | `release-integration.yml` | `solar_ai_optimizer.zip` only |

Every **stable app release** must include `custom_components/` on the tag (HACS custom-repo validation). App releases always bundle the integration zip even when integration semver did not bump.

Shell and Python execution must follow `.cursor/rules/shell.mdc`, `.cursor/rules/windows-shell.mdc`, and `.cursor/rules/python.mdc` (bash/Git Bash on Windows; Docker-first for Python scripts when host is not 3.14+).

## Version resolution (app)

Determine `{VERSION}` once, then use it in every **app** step below.

| User invocation | `{VERSION}` |
|-----------------|-------------|
| `/release` (no version) | Read `VERSION`. For a **new stable** release, bump semver (default patch) based on changelog significance. |
| `/release 0.6.1` | Explicit stable `0.6.1`. |
| `/release 0.6.1-beta.1` | Explicit pre-release string. |

**Parsing rules** (from user message text after the command):

1. Strip optional leading `v` / `V`.
2. Must match `^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$` (semver core + optional pre-release segment).
3. **Pre-release** = version contains `-` after `major.minor.patch` (e.g. `0.6.1-beta.1`, `0.6.1-rc.2`).
4. If user says “beta” / “prerelease” / “rc” **without** a version → stop and ask.
5. **Never infer a pre-release** from `VERSION` alone — pre-releases are always user-specified.

Convention for successive betas on the same base: increment the numeric suffix (`-beta.1` → `-beta.2`).

All app steps below use `{VERSION}` (no `v` prefix in files; tag is `v{VERSION}`).

## Version resolution (integration-only)

For integration-only releases, determine `{INTEGRATION_VERSION}` from `INTEGRATION_VERSION` (or user request). Tag is `integration-v{INTEGRATION_VERSION}` (no `v` after the prefix).

| User invocation | `{INTEGRATION_VERSION}` |
|-----------------|-------------------------|
| `/release integration 0.1.1` | Explicit integration `0.1.1` |
| `/release integration 0.1.1-beta.1` | Integration pre-release |

Integration releases do **not** build Docker or bump `solar_ai_optimizer/config.yaml`. Use `sync-version.py --integration-only` when only integration files change.

## Release kinds (publish outcomes)

| Kind | `{VERSION}` example | Git tag | Docker tags | GitHub Release |
|------|---------------------|---------|-------------|----------------|
| Stable | `0.6.1` | `v0.6.1` | `:0.6.1`, `:0.6`, `:latest` | normal |
| Pre-release | `0.6.1-beta.1` | `v0.6.1-beta.1` | `:0.6.1-beta.1` only | `prerelease: true` |

Pre-release images are installed by **explicit tag** (`ghcr.io/oraad/solar-ai-optimizer:0.6.1-beta.1`). The **Software updates** UI lists stable releases by default on Docker/compose hosts; admins can enable **Include beta releases** to list and install betas (notifications remain stable-only). **Home Assistant Apps** use the Supervisor channel: the HA manifest (`solar_ai_optimizer/config.yaml` `version`) is bumped on **stable** releases only; pre-releases do not change the store version until GA.

| Integration kind | `{INTEGRATION_VERSION}` | Git tag | GitHub Release |
|---|---|---|---|
| Stable | `0.1.0` | `integration-v0.1.0` | normal |
| Pre-release | `0.1.0-beta.1` | `integration-v0.1.0-beta.1` | `prerelease: true` |

## 1. Prepare version and changelog (single branch)

### App release

1. Read canonical version from `VERSION` (or use resolved `{VERSION}` from above).
2. If releasing a **new** version, write `VERSION` with **LF only**, then sync derived files:

   ```bash
   printf '%s\n' '{VERSION}' > VERSION
   python scripts/sync-version.py
   ```

   Docker equivalent (Windows or Python < 3.14):

   ```bash
   printf '%s\n' '{VERSION}' > VERSION
   docker run --rm -v "/c/Projects/solar:/repo" -w /repo python:3.14-slim-trixie \
     python scripts/sync-version.py
   ```

   `sync-version.py` normalizes `VERSION` to `<version>\n` (LF), updates `frontend/package.json`, and updates `solar_ai_optimizer/config.yaml` **only on stable releases** (pre-releases preserve the last stable HA store version). Integration `manifest.json` is synced from `INTEGRATION_VERSION` (not `VERSION`). Repo `.gitattributes` enforces LF on checkout/commit.

3. Update `CHANGELOG.md`: move `## [Unreleased]` items into `## [{VERSION}] - YYYY-MM-DD` (optional `### App` / `### Integration (bundled X.Y.Z)` subsections); leave `## [Unreleased]` empty. Brackets must match `VERSION` exactly.

### Integration-only release

1. Write `INTEGRATION_VERSION` with **LF only**, then:

   ```bash
   printf '%s\n' '{INTEGRATION_VERSION}' > INTEGRATION_VERSION
   python scripts/sync-version.py --integration-only
   ```

2. Add `## [integration {INTEGRATION_VERSION}] - YYYY-MM-DD` with `### Integration` bullets to `CHANGELOG.md`.

### Both tracks

4. Update `docs/` when UI or setup changed (see `.github/PULL_REQUEST_TEMPLATE.md`).
5. **Do not commit** unless the user explicitly asks; stage changes and report `git status`.

After a pre-release, `main` carries the beta `VERSION` and image tags until the next stable release PR (e.g. `0.6.1-beta.2` → `0.6.1`). The HA app store manifest stays on the last stable until that stable sync runs.

## 2. Local checks (once, before opening the PR)

Run and fix failures before proceeding:

```bash
docker compose run --rm test
docker compose run --rm frontend-test
python scripts/sync-version.py --check
python scripts/changelog-excerpt.py --kind app --version {VERSION}
# integration-only:
python scripts/changelog-excerpt.py --kind integration --version {INTEGRATION_VERSION}
```

`sync-version.py --check` verifies **both** `VERSION` and `INTEGRATION_VERSION` derived fields **and** LF-only bytes (matches Linux release CI). Use Docker for the Python scripts if host Python is not 3.14+.

Do **not** re-run the full Docker test suite after merge if CI will run the same jobs — local checks are the pre-push gate only.

## 3. One PR → merge to `main`

- Create **one** release branch with version bump, changelog, and code changes together.
- Open a PR and merge to `main` (use `gh` for GitHub tasks).
- **Pages does not run on tags** — doc changes must land on `main` before tagging (`.github/workflows/pages.yml` triggers on push to `main` only).

## 4. Gate: CI, Validate HA, and Pages green on the merge commit

After merge, wait for workflows triggered by that push (they run in parallel — watch once, then confirm Pages):

```bash
git fetch origin main
MERGE_SHA="$(git rev-parse origin/main)"
gh run list --commit "$MERGE_SHA" --limit 8
gh run watch --exit-status $(gh run list --workflow=ci.yml --commit "$MERGE_SHA" --json databaseId --jq '.[0].databaseId')
gh run watch --exit-status $(gh run list --workflow=validate-ha.yml --commit "$MERGE_SHA" --json databaseId --jq '.[0].databaseId')
gh run list --workflow=pages.yml --commit "$MERGE_SHA" --limit 1
```

**Stop here** until **CI**, **Validate HA** (`validate-ha.yml`), and **Pages** all succeed. Do not tag.

Site: https://oraad.github.io/solar-ai-optimizer/

Manual Pages redeploy if needed: `gh workflow run pages.yml --ref main`

## 5. Tag and push (triggers release only)

### App (`v{VERSION}`)

On latest `main` after gates pass:

```bash
git checkout main && git pull origin main
python scripts/sync-version.py --check
git tag v{VERSION}
git push origin v{VERSION}
```

Replace `{VERSION}` with the value in `VERSION` (tag has `v` prefix; `VERSION` does not). The pre-tag `--check` catches CRLF drift before a failed release workflow.

`.github/workflows/release.yml` then:

- Verifies tag (without `v`) matches `VERSION` and `manifest.json` matches `INTEGRATION_VERSION`
- Builds `dist/solar_ai_optimizer.zip` via `scripts/package-ha-integration.sh` (flat domain root; excludes `tests/`)
- Pushes multi-arch image to `ghcr.io/oraad/solar-ai-optimizer` (see **Release kinds** table for stable vs pre-release tags)
- Extracts `## [{VERSION}]` from `CHANGELOG.md` via `scripts/changelog-excerpt.py --kind app`
- Creates **one** GitHub Release with CHANGELOG body + auto-generated notes, attaching **`solar_ai_optimizer.zip`** (`prerelease: true` when `{VERSION}` contains a `-` suffix; zip attached on betas too)

### Integration-only (`integration-v{INTEGRATION_VERSION}`)

```bash
git checkout main && git pull origin main
python scripts/sync-version.py --check
git tag integration-v{INTEGRATION_VERSION}
git push origin integration-v{INTEGRATION_VERSION}
```

`.github/workflows/release-integration.yml` then:

- Verifies tag (without `integration-v` prefix) matches `INTEGRATION_VERSION`
- Packages and attaches **`solar_ai_optimizer.zip`** only (no Docker)
- Notes from `scripts/changelog-excerpt.py --kind integration`

## 6. Gate: Release workflow green

App:

```bash
gh run watch --exit-status $(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')
gh release view v{VERSION}
gh release view v{VERSION} --json assets --jq '.assets[].name'
# must include: solar_ai_optimizer.zip
```

Integration-only:

```bash
gh run watch --exit-status $(gh run list --workflow=release-integration.yml --limit=1 --json databaseId --jq '.[0].databaseId')
gh release view integration-v{INTEGRATION_VERSION}
```

For pre-releases, confirm `prerelease: true` in the release view. Report the release URL, image tags (app only), and zip asset when complete.

`hacs.json` uses `zip_release: true` with `"filename": "solar_ai_optimizer.zip"` and `hide_default_branch: true`. Do not attach extra unnamed `.zip` assets on GitHub Releases.

## Pitfalls

| Pitfall | Consequence |
|---------|-------------|
| Tag before merge / wrong commit | Release builds stale code |
| `VERSION` saved with CRLF on Windows | Release verify fails on Linux (`0.5.12\r` ≠ `0.5.12`); use `printf` + `sync-version.py` |
| Delete/recreate tag after failed release | Extra release workflow, duplicate GH Release noise; fix on `main` and bump patch instead |
| Hotfix PR after tagging | Second CI/Pages cycle; include CRLF/version fixes in the release PR |
| `v{VERSION}` ≠ `VERSION` | App release job fails at verify step |
| `integration-v{X}` ≠ `INTEGRATION_VERSION` | Integration release job fails at verify step |
| Tag integration with `v0.1.x` (app prefix) | Wrong workflow; use `integration-v0.1.x` |
| Stable app tag without `custom_components/` | HACS custom-repo add fails (“add-on repository”) |
| Missing `## [{VERSION}]` in CHANGELOG | Release succeeds but notes are auto-generated only |
| Tag before CI / Validate HA / Pages green | Broken release or outdated docs live |
| Expecting Pages on tag push | Pages never runs; only `main` push deploys docs |
| Set `hacs.json` `zip_release: true` before any zip-bearing release | HACS install/update fails (missing named asset) |
| Extra unnamed `.zip` assets on the GitHub Release | HACS zip_release can pick the wrong file |
| Release missing `solar_ai_optimizer.zip` | `fail_on_unmatched_files: true` fails the release job (correct) |
| Re-running local Docker tests after merge | Wasted time; CI already runs the same suites |
| `type=raw,value=latest` left unconditional in workflow | Beta becomes `:latest`; `:latest` self-update hosts get unintended build |
| Non-semver suffix (`0.6.1beta`) | `docker/metadata-action` semver parsing fails; use `0.6.1-beta.1` |
| `VERSION` on `main` stays at beta until stable PR | Expected; stable release must set final `X.Y.Z` |

## Reporting

At each step, summarize: track (app / integration), kind (stable / pre-release), version(s), what changed, gate status (CI / Pages / Release), image tags (app), and release URL. Pre-releases: note explicit-tag install only. If the tree is already release-ready on `main`, skip to step 4.
