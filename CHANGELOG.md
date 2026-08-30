# Changelog

All notable changes to DevMind CLI are documented here. Dates reflect when
work landed on this branch; versions follow `pyproject.toml`.

## Unreleased

Fixes and features from a 100-scenario developer-simulation audit (first-time
students, CI/CD runners, monorepos, offline developers, Docker/WSL users).

### Added
- `devmind doctor` — self-healing environment diagnostics (Python version,
  git, AI provider connectivity/latency, Ollama model listing, local memory
  integrity, FastEmbed readiness, PyPI/update status).
- `devmind config` is now a real inspector: shows active provider/model/
  embedding config, and offers a menu to switch provider, update just the
  API key, change just the model, or diff global vs local config — instead
  of duplicating `devmind init`'s full wizard.
- `--version`/`-v` flag; `--debug` flag for verbose logging.
- Commands are now grouped by category (`Memory & Ingestion`, `Offline
  Analysis`, `Interfaces`, `Configuration`) in `--help`, and running
  `devmind` with no subcommand shows a quick-start banner instead of a raw
  help dump.
- `devmind impact` now flags ambiguous targets (multiple symbols sharing a
  name) and lists the other locations instead of silently picking the first.

### Fixed
- **Project-scoped memory isolation**: `.cognee_system`/`.cognee_data` now
  resolve from the developer's working directory instead of the installed
  package directory, so `devmind forget --all` only wipes the current
  project's memory.
- **Safe query guard**: `devmind ask`/`chat` show a friendly "run `devmind
  remember` first" message instead of a raw database exception on
  un-indexed projects.
- Python < 3.10 now fails fast with a clear upgrade message instead of
  crashing deep inside an import on `str | list[str]` union-type syntax.
- `devmind remember --incremental` outside a git repo now tells you to run
  `git init` instead of silently doing nothing; the root-commit case (no
  parent to diff against) now correctly treats every file it introduced as
  changed.
- `devmind dashboard`/`graph` validate the target directory exists before
  changing into it; `graph` no longer opens the browser before the server
  is actually ready (was a fixed race, now polls the port).
- `devmind blame` checks for a git repository up front instead of crashing
  with an unhandled exception outside one.
- Security scanner (`devmind secure`) no longer flags test/fixture/mock
  files with its regex secret patterns, and skips `.env.example`/
  `.env.sample`/`*.example` files outright instead of relying on
  placeholder-substring matching that missed values like `your_key1`.
- `devmind chat`'s `clear` command now clears the screen instead of quitting
  the session; only `exit`/`quit`/`q` terminate; the whole session now runs
  on one persistent event loop instead of a new loop per query.
- `health`/`onboard`/`impact`/`drift`/`secure` now create nested `--output`
  directories instead of raising `FileNotFoundError`.
- ADR logging (`devmind log`, the MCP server, and the web dashboard) now
  writes into one unified `devmind_adr_records` dataset per project instead
  of a new timestamped dataset per call, enabling cross-decision search.
- `remember_content()` now correctly returns `False` on an unexpected
  ingestion failure instead of always reporting success.
- Unicode/emoji project folder names are sanitized into a stable dataset
  name instead of being passed through as-is.
- Setup wizard: provider API key prompts re-prompt until non-empty; the
  global/local save-scope prompt now explains what each option means.
- Polyglot ingestion: added Rust/Go/Java/C/C++/Ruby/PHP/Swift/Kotlin/C#/
  Scala/SQL/GraphQL extensions; minimum ingestible file size dropped from
  15 to 3 characters so short config scripts aren't silently dropped.
- Version-cache writes are now atomic (temp file + rename) to avoid
  corruption from concurrent `devmind` invocations; the update check itself
  is skipped for `--help`/`--version`/completion invocations.
- Default CLI log level dropped to `WARNING` (was `INFO`) for clean stdout.
- Added missing `__init__.py` to `devmind/ingestion`, `devmind/integrations`,
  and `devmind/web` for reliable packaging.

### Documentation
- README now documents every offline analysis command (`doctor`, `health`,
  `onboard`, `impact`, `drift`, `blame`, `secure`), links `GETTING_STARTED.md`
  and this changelog, documents `DEVMIND_NO_UPDATE_CHECK`/
  `DEVMIND_RECALL_TOP_K`, fixes the MCP tool name (`log_architectural_decision`,
  not `log_decision_record`), and clarifies that Ollama.app already runs
  the server on macOS/Windows.

---

## Prior work (see git history for full detail)

- `devmind secure` — offline security & penetration scanner.
- `devmind drift` — architecture drift/churn detector; `devmind blame` —
  semantic git blame.
- `devmind impact` — blast-radius dependency impact analysis.
- `devmind onboard` — auto-generated codebase onboarding guide.
- `devmind health` — codebase technical-debt and quality scoring.
- `devmind init` — interactive multi-provider setup wizard.
- `devmind graph`/`digest` — visual architecture graph and Markdown digest.
- Native Ollama support, git-diff-aware incremental ingestion, and a
  deterministic local AST/multi-language symbol parser for zero-token
  ingestion.
