# Dependency Audit - 2026-05-19

## Scope

Audited dependency declarations and lockfiles in:

- `pyproject.toml`
- `dashboard/package.json` and `dashboard/package-lock.json`
- `deploy/dashboard/package.json` and `deploy/dashboard/package-lock.json`

No code was modified. `deploy/dashboard/` is the canonical hosted dashboard per
repo docs; root `dashboard/` is a legacy/local prototype.

## Method And Limits

- Local manifests and lockfiles were inspected.
- Installed Python versions in `.venv` were sampled for current resolved state.
- `npm audit --json` was attempted in both dashboard directories, but registry
  access failed with `getaddrinfo ENOTFOUND registry.npmjs.org`.
- `osv-scanner` and `pip-audit` are not installed in this environment.
- A targeted web check found a current Snyk advisory page for `vite@5.4.21`:
  <https://security.snyk.io/package/npm/vite/5.4.21>
- PyPI metadata was checked for `google-auth-oauthlib` provenance:
  <https://pypi.org/project/google-auth-oauthlib/>
- This report is therefore a dependency risk audit, not a complete CVE verdict.
  Run live advisory tooling before release.

## Executive Summary

| Area | Risk | Finding | Recommended Action |
| --- | --- | --- | --- |
| Python app | High | Runtime dependencies are range-only in `pyproject.toml`; no committed Python lockfile was found. | Commit a lockfile for app/runtime installs, or document the exact `uv lock` workflow used by CI/release. |
| Legacy `dashboard/` | High | `@insforge/sdk` is declared as `latest`, creating non-reproducible installs despite the current lockfile resolving to `1.2.5`. | Replace `latest` with an explicit compatible range or exact version. |
| Legacy `dashboard/` | Medium | `vite` is locked at `5.4.21`. Snyk reports a dev-server directory traversal issue affecting this version when the dev server is exposed with `--host`; fixes begin at `6.4.2`, `7.3.2`, or `8.0.5`. | If the legacy dashboard remains runnable, upgrade Vite or restrict dev-server exposure. |
| Production `deploy/dashboard/` | Medium | Locked dependency surface is larger than the legacy dashboard: 262 node packages. | Keep `npm ci`, lockfile review, and live audit in CI; treat Vite/React/build-tool updates as regular maintenance. |
| Insforge boundary | Medium | `@insforge/sdk` is runtime code that talks to the hosted public plane. | Keep typed public projections at the boundary; do not pass private context into SDK callers. |
| Google/Gmail path | Medium | OAuth and Google API dependencies handle tokens and private mailbox metadata/content locally. | Keep tokens local, review scopes, and pin/lock transitive auth libraries. |
| Anthropic/http clients | Medium | LLM and HTTP clients are outbound private-plane dependencies. | Ensure redaction/projection discipline before network calls; lock versions. |

## Python Dependencies

Declared in `pyproject.toml`; current `.venv` versions are shown only as a local
sample because the repo does not commit a Python lockfile.

| Package | Declared | Local Version | Use In Repo | Risk | Notes |
| --- | --- | ---: | --- | --- | --- |
| `redis` | `>=5.0` | `7.4.0` | Private/public Redis stores and Redis-backed tests. | Medium | Handles private-plane data and keyspace boundaries. Range-only dependency can silently change client behavior. |
| `anthropic` | `>=0.40` | `0.102.0` | Optional live LLM drafting path in `actions/draft.py`. | Medium | Outbound private-context dependency. Main risk is privacy boundary misuse and SDK behavior drift without a lockfile. |
| `httpx` | `>=0.27` | `0.28.1` | Human review, Insforge publish, scripts, and fallback LLM HTTP calls. | Medium | General outbound HTTP layer. Keep timeouts, target URLs, and payload minimization reviewed. |
| `pydantic` | `>=2.0` | `2.13.4` | Boundary and public/private view models. | Medium | Type-boundary dependency. Version drift can alter validation/serialization semantics. |
| `click` | `>=8.0` | `8.3.3` | CLI dependency; also required by some auth tooling extras. | Low | Small runtime surface. Primary concern is unpinned resolution. |
| `google-api-python-client` | `>=2.100` | `2.196.0` | Gmail source adapter. | Medium | Pulls a broad Google API/auth stack and touches restricted Gmail flows. Needs lockfile and scope discipline. |
| `google-auth-oauthlib` | `>=1.2` | `1.4.0` | OAuth onboarding flow. | Medium | Handles local OAuth tokens. PyPI metadata for `1.4.0` shows trusted publishing/provenance, but local token handling remains sensitive. |
| `pytest` | `>=8.0` | `9.0.3` | Dev/test only. | Low | Test-only, but still range-only. |
| `ruff` | unbounded | `0.15.12` | Dev/lint only. | Low | Unbounded dev tool; can change lint output without source changes. Pin for reproducible CI. |

### Python Findings

- No `uv.lock`, `requirements*.txt`, `poetry.lock`, or `Pipfile.lock` is
  committed for Python dependencies.
- `ruff` is declared with no lower or upper bound.
- Because dependency versions are not locked, a fresh environment can resolve
  different auth, HTTP, validation, and Redis clients than the versions sampled
  above.

## Production Dashboard Dependencies (`deploy/dashboard/`)

Lockfile: `deploy/dashboard/package-lock.json`

- Lockfile version: 3
- Locked package count: 263 package entries, including root
- Direct runtime deps: 3
- Direct dev deps: 15
- Duplicate package names in lockfile: none found
- Packages with install scripts: `fsevents@2.3.3` only, optional macOS watcher

| Package | Declared | Locked | Kind | Risk | Notes |
| --- | --- | ---: | --- | --- | --- |
| `@insforge/sdk` | `^1.2.5` | `1.2.5` | runtime | Medium | Talks to hosted public-plane services. Boundary risk depends on callers only sending public projections. Pulls `@supabase/postgrest-js` and `socket.io-client`. |
| `react` | `^19.2.5` | `19.2.5` | runtime | Low | UI runtime. Main risk is framework churn and compatibility with ecosystem packages. |
| `react-dom` | `^19.2.5` | `19.2.5` | runtime | Low | Browser rendering runtime. Keep paired with `react`. |
| `@eslint/js` | `^10.0.1` | `10.0.1` | dev | Low | Lint-only. Supply-chain risk is install-time only. |
| `@types/node` | `^24.12.2` | `24.12.2` | dev | Low | Types-only. |
| `@types/react` | `^19.2.14` | `19.2.14` | dev | Low | Types-only. |
| `@types/react-dom` | `^19.2.3` | `19.2.3` | dev | Low | Types-only. |
| `@vitejs/plugin-react` | `^6.0.1` | `6.0.1` | dev/build | Medium | Build pipeline package. Dev-server and transform-chain packages deserve regular audit. |
| `autoprefixer` | `^10.5.0` | `10.5.0` | dev/build | Low | CSS build tooling. |
| `eslint` | `^10.2.1` | `10.2.1` | dev | Low | Lint-only but broad transitive tree. |
| `eslint-plugin-react-hooks` | `^7.1.1` | `7.1.1` | dev | Low | Lint-only. |
| `eslint-plugin-react-refresh` | `^0.5.2` | `0.5.2` | dev | Low | Lint/dev-only. |
| `globals` | `^17.5.0` | `17.5.0` | dev | Low | Lint config data. |
| `postcss` | `^8.5.10` | `8.5.10` | dev/build | Low | CSS parser/build dependency. Historically important to audit, but current local evidence found no direct issue. |
| `tailwindcss` | `3.4` | `3.4.19` | dev/build | Low | CSS generation dependency with many transitive packages. Exact major/minor declaration limits movement. |
| `typescript` | `~6.0.2` | `6.0.3` | dev/build | Low | Compiler only. Patch-range pin is good. |
| `typescript-eslint` | `^8.58.2` | `8.59.0` | dev | Low | Lint-only, broad TypeScript parser stack. |
| `vite` | `^8.0.10` | `8.0.10` | dev/build | Medium | Dev server/build system. Snyk's cited Vite advisory says affected `8.0.x` versions are fixed from `8.0.5`, so `8.0.10` is above that specific fixed floor. Full audit still unverified due registry access failure. |

## Legacy Dashboard Dependencies (`dashboard/`)

Lockfile: `dashboard/package-lock.json`

- Lockfile version: 3
- Locked package count: 197 package entries, including root
- Direct runtime deps: 3
- Direct dev deps: 8
- Duplicate package names in lockfile: none found
- Packages with install scripts: `esbuild@0.21.5`, `fsevents@2.3.3`

| Package | Declared | Locked | Kind | Risk | Notes |
| --- | --- | ---: | --- | --- | --- |
| `@insforge/sdk` | `latest` | `1.2.5` | runtime | High | `latest` is non-reproducible and can silently install a new public-plane SDK on fresh install if the lockfile is bypassed or regenerated. |
| `react` | `^18.3.1` | `18.3.1` | runtime | Low | UI runtime; stable if the lockfile is honored. |
| `react-dom` | `^18.3.1` | `18.3.1` | runtime | Low | Browser rendering runtime; keep paired with `react`. |
| `@types/react` | `^18.3.3` | `18.3.28` | dev | Low | Types-only. |
| `@types/react-dom` | `^18.3.0` | `18.3.7` | dev | Low | Types-only. |
| `@vitejs/plugin-react` | `^4.3.1` | `4.7.0` | dev/build | Medium | Build transform package. Legacy line should be updated if this dashboard remains active. |
| `autoprefixer` | `^10.4.19` | `10.5.0` | dev/build | Low | CSS build tooling. |
| `postcss` | `^8.4.38` | `8.5.10` | dev/build | Low | CSS parser/build dependency. |
| `tailwindcss` | `^3.4.4` | `3.4.19` | dev/build | Low | CSS generation dependency. |
| `typescript` | `^5.5.3` | `5.9.3` | dev/build | Low | Compiler only; broad minor movement is acceptable for local prototype but less reproducible than `~`. |
| `vite` | `^5.3.4` | `5.4.21` | dev/build | Medium | Snyk reports a directory traversal issue for `5.4.21` when Vite dev server is exposed with `--host`; recommended fixed lines include `6.4.2`, `7.3.2`, or `8.0.5+`. |

## Boundary-Specific Risk Notes

- The highest-value dependency risk is not package count; it is accidental
  private-plane disclosure through outbound dependencies.
- Packages that can cross process/network boundaries deserve stricter treatment:
  `anthropic`, `httpx`, Google auth/API packages, `redis`, and `@insforge/sdk`.
- Public-plane dashboard dependencies are acceptable only if callers continue to
  consume typed public views rather than private context or draft bodies.
- Build/dev tools such as Vite, TypeScript, ESLint, Tailwind, PostCSS, Rollup,
  Rolldown, and esbuild are mostly install/build-time risks, but Vite also has a
  dev-server attack surface if exposed on the network.

## Recommended Remediation Order

1. Add or commit reproducible Python dependency locking for runtime and dev
   dependencies.
2. Replace `dashboard/package.json`'s `@insforge/sdk: "latest"` with an explicit
   version range or exact pin.
3. Decide whether `dashboard/` should be kept. If yes, upgrade its Vite line; if
   no, document that it is non-production and exclude it from release dependency
   gates.
4. Add live advisory checks to CI once network is available:
   - `npm audit --audit-level=moderate` in `deploy/dashboard/`
   - `pip-audit` or `uv pip audit` for Python, depending on the chosen workflow
   - optionally `osv-scanner scan .` for lockfile and manifest coverage
5. Treat any dependency touching Gmail tokens, private Redis state, LLM prompts,
   or Insforge publication as a privacy-boundary dependency and review payloads
   alongside version bumps.

## Verification Commands Run

```bash
git status --short
rg --files -g 'pyproject.toml' -g 'requirements*.txt' -g 'uv.lock' -g 'package.json' -g 'package-lock.json' -g 'pnpm-lock.yaml' -g 'yarn.lock' -g 'bun.lockb' -g 'Cargo.toml' -g 'go.mod' -g 'Pipfile' -g 'poetry.lock' -g 'README.md' -g 'AGENTS.md'
npm audit --json
node -e '...' # lockfile root dependency/version summary
.venv/bin/python - <<'PY' # installed Python version sample
```

`npm audit --json` failed in both dashboard directories because this sandbox
could not resolve `registry.npmjs.org`.
