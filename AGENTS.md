# AGENTS.md

Guidance for coding agents working in this repository.

Per-module instructions live in `core/<module>/.claude/CLAUDE.md`; each module also has a stub `AGENTS.md` pointing at it. **Before opening a pull request, read "Contribution Bar" at the end of this file.** It sets out what is expected of a change here — reproduce a failure before claiming one, label honestly, make tests exercise the code they cover — and what will be closed rather than reviewed.

## What this repo is

Wren is an open-source semantic engine and GenBI platform for MCP clients and AI agents. SQL is rewritten through a semantic layer (MDL — Modeling Definition Language) and executed against 22+ data sources. The Rust engine is built on upstream Apache DataFusion v53 from crates.io (not the old Canner fork).

The previous WrenAI services (`wren-ui/`, `wren-ai-service/`, `wren-launcher/`, `docker/`, `deployment/`) are **not** on `main`: they live on `legacy/v1` (tag `v1-final`). Do not search `main` for them.

## Repository map

| Path | Contents | Published as |
|---|---|---|
| `core/wren-core/` | Rust semantic engine: MDL analysis, analyzer + optimizer rules, SQL generation. Cargo workspace: `core/`, `sqllogictest/`, `benchmarks/`, `wren-example/` | crates.io `wren-semantic-core` (lib `wren_core`) |
| `core/wren-core-base/` | Shared manifest types (`Model`, `Column`, `Metric`, `Relationship`, `View`, RLAC/CLAC) + fluent `ManifestBuilder` + `manifest-macro` proc macro | crates.io `wren-core-base` |
| `core/wren-core-py/` | PyO3/Maturin bindings exposing wren-core to Python (abi3-py311, one wheel for 3.11+) | PyPI `wren-core` |
| `core/wren-core-wasm/` | Separate Cargo project (outside the wren-core workspace); wasm-pack build + TypeScript SDK; DataFusion runs client-side | npm `wren-core-wasm` |
| `core/wren/` | Python SDK + `wren` CLI: YAML MDL projects, connection profiles, Ibis-backed connectors, optional LanceDB memory, MCP server | PyPI `wrenai` |
| `core/wren-mdl/` | MDL JSON schema definition | — |
| `sdk/wren-langchain/`, `sdk/wren-pydantic/` | Reference agent SDK integrations | PyPI |
| `skills/` | Agent skills served by the CLI (`wren skills get …`); authoring rules in `skills/AUTHORING.md` | — |
| `docs/core/` | Documentation; `docs/core/reference/architecture.md` is the module map, `project-layout-v5.md` the layout rationale | — |

## Commands

### `core/wren-core` (Rust)

```bash
cargo check --all-targets                                  # compile check
RUST_MIN_STACK=8388608 cargo test --lib --tests --bins     # all tests; the stack override matters
RUST_MIN_STACK=8388608 cargo test --lib <filter>           # single test / module, e.g. mdl::
cargo test -p wren-sqllogictest --test sqllogictests -- model   # one .slt file (filename substring); set INCLUDE_TPCH=1 for TPCH
cargo fmt --all                                            # format
cargo clippy --all-targets --all-features -- -D warnings   # lint
taplo fmt                                                  # format Cargo.toml files
cargo insta review                                         # accept/review snapshot changes
```

Unit tests mostly live in `core/src/mdl/mod.rs`. SQL end-to-end tests are sqllogictest `.slt` files under `sqllogictest/test_files/` (`model.slt`, `view.slt`, `type.slt`, `tpch/`).

### `core/wren-core-base` (Rust)

```bash
cargo test                                     # tests
cargo clippy --all-targets -- -D warnings      # lint
taplo fmt                                      # format Cargo.toml
```

Changes here ripple into both wren-core (Rust) and wren-core-py (Python). Keep `python-binding` optional and give new fields serde defaults.

### `core/wren-core-py` (Python bindings)

```bash
just install      # uv sync, deps only (--no-install-project)
just develop      # build a dev wheel with maturin for local testing
just test-rs      # cargo test --no-default-features (extension-module off)
just test-py      # pytest; single test: uv run --no-sync pytest tests/<file>::<test>
just test         # both
just format       # cargo fmt + ruff + taplo
```

### `core/wren-core-wasm`

```bash
just build        # WASM (release) + TS SDK → dist/
just build-wasm-dev   # debug WASM, much faster
just test         # node --test sdk/tests/index.test.mjs (requires dist/)
just typecheck    # tsc --noEmit
just serve        # localhost:8787 browser examples
```

macOS builds need LLVM (`brew install llvm`); the justfile sets `CC_wasm32_unknown_unknown`/`AR_wasm32_unknown_unknown` itself. Output is ~68 MB raw / ~14 MB gzip (target < 15 MB gzip).

### `core/wren` (Python SDK & CLI)

```bash
just install          # uv sync against the locked prebuilt wren-core wheel — no Rust needed
just install-all      # all extras, including memory
just install-extra postgres   # one datasource extra
just install-local    # uv sync + build local engine wheel + overlay (needs Rust)
just use-local-core   # rebuild + re-overlay after a Rust change
just dev              # run the `wren` CLI
just test             # pytest tests/ -v; single test: uv run --no-sync pytest tests/unit/test_x.py::test_y -v
just test-unit        # fast unit tests (-m "unit and not slow")
just test-connector postgres   # connector tests by marker: uv run --no-sync pytest tests/connectors/ -m <marker>
just test-memory      # memory tests; slow variants: just test-memory-slow
just lint / just format        # ruff (line-length 88, py3.11)
just build            # uv build → wheel
```

Uses `uv` (not Poetry), `hatchling` backend. Extras: `postgres`, `mysql`, `bigquery`, `snowflake`, `clickhouse`, `trino`, `mssql`, `databricks`, `redshift`, `spark`, `athena`, `oracle`, `memory`, `mcp`, `interactive`, `ui`, `main` (`interactive`+`ui`), `all`, `dev`. On macOS the `mysql` extra needs `PKG_CONFIG_PATH="$(brew --prefix mysql-client)/lib/pkgconfig"`. Run recipes use `uv run --no-sync` so a locally overlaid engine wheel is not reverted.

## Architecture

### Query flow

```text
MDL project YAML (models/ views/ relationships/)  ──wren context build──▶ target/mdl.json
business question ─▶ agent / `wren ask`
  ─▶ wren CLI / WrenEngine (core/wren)
  ─▶ wren-core-py  (PyO3: manifest deserialize, SessionContext.transform_sql)
  ─▶ wren-core (Rust): MDL analyze → logical plan → optimizer
  ─▶ DataFusion (planning/execution primitives, crates.io v53)
  ─▶ transpile to the target dialect with sqlglot
  ─▶ connector (Ibis backend, or native driver) executes on the data source
```

`wren-core-wasm` is the same semantic layer without the Python middle: `loadMDL()` produces `AnalyzedWrenMDL`, `query()` applies the analyzer rules and executes directly in DataFusion (no SQL unparse/transpile), over Parquet/JSON tables registered in memory or fetched over HTTP.

### Layer boundaries that matter

- **MDL is the contract.** It is defined once as Rust types in `core/wren-core-base/src/mdl/manifest.rs`, with `ManifestBuilder` for programmatic construction; the `python-binding` feature makes `manifest-macro` generate Pydantic-compatible Python classes. Adding or renaming a manifest field touches Rust, Python bindings, the JSON schema in `core/wren-mdl/`, and usually tests in both `wren-core-py` and `wren`.
- **wren-core internals** (`core/wren-core/core/src/`): `mdl/` (`WrenMDL` = manifest + symbol table, `AnalyzedWrenMDL` with lineage, per-dialect scalar/aggregate/window functions, type planning); `logical_plan/analyze/` (DataFusion analyzer rules — `ModelAnalyzeRule` rewrites `TableScan` into `ModelPlanNode`, plus scope tracking, RLAC/CLAC access control, view expansion, relationship-chain resolution); `logical_plan/optimize/` (type coercion, timestamp simplification); `sql/`.
- **`WrenEngine` is the Python entry point** (`core/wren/src/wren/`). It receives the manifest as a base64 JSON string plus a datasource and connection dict. `_plan()` first extracts a minimal sub-manifest scoped to the query's referenced tables, then calls wren-core, then transpiles. `get_session_context` is `@lru_cache(maxsize=32)`: mutating session state silently disappears when an entry is evicted, so never mutate it.
- **Connectors** are selected in `connector/factory.py`; each wraps an Ibis backend exposing `.query(sql, limit)` and `.dry_run(sql)`. `ibis.py` holds the shared implementation (trino, clickhouse, snowflake, athena), file sources all map to duckdb, `canner`→postgres, `doris`→mysql, and `oracle` uses native `oracledb` rather than Ibis. Write dialect mapping: `canner`→`trino`, file sources→`duckdb`.
- **CLI surface** (`core/wren`): `wren query|dry-plan|validate`, `wren context init|build|validate|show`, `wren profile add|list|show|remove|activate`, `wren memory index|fetch|store|recall`, `wren serve mcp`, `wren skills get <name>`, `wren ask "<q>" --guided|--direct`. Profiles auto-discover from `~/.wren/profiles.yml`; `~/.wren/config.json` carries `strict_mode` and `denied_functions`. All workflow guides are served by the CLI, so docs and behavior stay in sync with the installed version.
- **Optional memory** (`core/wren/src/wren/memory/`): `WrenMemory` over LanceDB with sentence-transformers embeddings for schema items and NL↔SQL pairs; `seed_queries.py` bootstraps canonical pairs at index time.
- **Validation boundary — validate once, at the edge.** The manifest schema is enforced in exactly one place: serde deserialization in wren-core, reached via `ManifestExtractor`/`SessionContext`. Downstream of a successful deserialization the schema holds, so `isinstance` guards over `manifest["models"]`/`["views"]`/`["columns"]` on those paths are dead code and are not accepted. Upstream of it (user-supplied `--from-mdl` JSON, hand-edited project YAML, external API responses) is a genuine input boundary and must validate rather than crash. Say which side of that line a change sits on.
- **Access control**: row/column-level security code paths exist in wren-core (`RowLevelAccessControl`, `ColumnLevelAccessControl`), but RLAC/CLAC in the product are Cloud/Enterprise features; OSS scope is published in `docs/core/concepts/oss_vs_commercial.md`.

### Known wren-core limitation

`ModelAnalyzeRule` cannot resolve outer column references inside correlated subqueries — it only sees the subquery's own table scope. Affects TPCH Q2, Q4, Q15, Q17, Q20, Q21, Q22.

## Conventions

- **Commits**: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `perf:`, `deps:`). Releases are automated by release-please with independent release lines per module, so `fix:`/`feat:` prefixes drive changelogs and versions.
- **Rust**: `cargo fmt`, `clippy -D warnings`, `taplo fmt` for manifests; `insta` for snapshots.
- **Python**: `ruff` (line length 88, target 3.11); `uv` in both `core/wren` and `core/wren-core-py`.
- **CI is path-filtered per module** (`core/wren-core/**`, `core/wren-core-py/**` also triggers on wren-core changes, etc.). A test placed in a file gated behind an optional extra or a container will not run in the default job.
- **Docs**: `docs/**` contributions are CC BY 4.0; everything else Apache-2.0 (see `LICENSE` for the path map). `scripts/sync-docs.sh` mirrors `docs/core` into the docs website repo via PR — it is a dry run unless given `--apply`, and needs `DOCS_REPO` set.

## Contribution Bar

Read before opening a pull request; a PR that violates these is closed rather than iterated on.

- **Prove the problem before fixing it.** Do not assert the behavior of an external engine/driver/library you have not observed — reproduce it and paste the real error. Do not add a guard for a state you have not shown to be reachable: trace the call path and explain how the bad value arrives (see "Validation boundaries" above; re-validating downstream is dead code). If you cannot reproduce a failure, open an issue with the reproduction attempt, not a PR.
- **Label honestly.** `fix:` requires a reproducible failure the change repairs; a change with no observable behavior difference is `refactor:` or `chore:`. The description must say what changes for a user — "improves robustness" / "hardens X" is not an answer.
- **Tests must exercise the changed code.** A test that reads a source file as text and asserts substrings tests nothing; call the function and assert on what it returns or passes downstream. Every assertion must be capable of failing, and the test must actually run in CI.
- **One change, once.** Search open PRs first (duplicates are closed without review); a mechanical change repeated across connectors/files goes in one PR, not one PR per file.
- **Respect recorded decisions.** If a comment or test documents a deliberate choice, quote it and argue why it should change instead of silently reversing it.
- **Keep the branch current.** Rebase before requesting review; a textually clean merge is not a semantically correct one.