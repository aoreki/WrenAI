# Wren Core Python Binding

Python bindings for [wren-core](../wren-core), the Rust semantic engine behind [Wren Engine](https://github.com/Canner/WrenAI). Built with [PyO3](https://github.com/PyO3/pyo3) and [Maturin](https://github.com/PyO3/maturin).

Wren Engine translates SQL queries through a semantic layer (MDL - Modeling Definition Language) and executes them against 22+ data sources (PostgreSQL, BigQuery, Snowflake, etc.).

## Installation

```bash
pip install wren-core-py
```

Requires Python >= 3.11.

Pre-built wheels are available for:
- Linux x86_64
- macOS x86_64 / ARM64 (Apple Silicon)
- Windows x86_64

Linux ARM64 wheels are not yet available. To use on that platform, build from source (requires Rust toolchain).

## Quick Start

```python
from wren_core import SessionContext

# Create a session context from a base64-encoded MDL JSON string
base64_mdl_json = "<your-base64-encoded-mdl-json>"
ctx = SessionContext(base64_mdl_json)

# Transform a SQL query through the semantic layer
planned_sql = ctx.transform_sql("SELECT * FROM my_model")
```

### Registering local files (Parquet/CSV)

Physical files can back MDL models via two-phase initialization — register the
files, then load the MDL so models resolve to them:

```python
from wren_core import SessionContext

base64_mdl_json = "<your-base64-encoded-mdl-json>"

ctx = SessionContext()
ctx.register_parquet("customer", "/data/customer.parquet")
ctx.register_csv("orders", "/data/orders.csv")
ctx.load_mdl(base64_mdl_json)  # MDL models now resolve to the files

# Query by the MDL's catalog.schema.model name; returns Arrow IPC stream bytes
ipc_bytes = ctx.query("SELECT * FROM my_catalog.my_schema.customer")
```

Visibility contract:

- Tables land in the pre-existing default catalog (`datafusion`.`public`). An
  MDL model resolves to a registered file only if its `tableReference` is
  `{"catalog": "datafusion", "schema": "public", "table": "<registered name>"}`
  and the columns it declares exist in the file.
- Registering after the context was created still works: the internals of
  pre-existing catalogs are live-shared with derived contexts, so the table is
  visible to `query`, `dry_run`, and `list_tables`.
- Brand-new *top-level* catalogs are the exception — they must exist before
  MDL construction, `load_mdl`, or a transform, each of which snapshots the
  top-level catalog list.
- For `load_mdl`'s overlap rule, see the Concurrency section below.

For complete runnable examples (fixture files, matching manifests, decoding
the returned bytes), see `tests/test_physical_tables.py`.

### Concurrency

Calls on one `SessionContext` run in parallel. Each `transform_sql` works
on a private top-level catalog snapshot and analyzer state is
per-invocation, so supported concurrent calls never observe each other's
intermediate state. The contract:

- Concurrent execution is supported for the read-only inputs accepted by
  `transform_sql` and `query`, and for the registration APIs. `dry_run` is
  concurrency-safe for statements that `EXPLAIN` only plans. An
  `ANALYZE`-prefixed input becomes `EXPLAIN ANALYZE` and executes; like a
  state-mutating statement accepted by `query()`, it is outside the
  concurrency contract. Function lookup methods are read-only and
  concurrency-safe.
- `register_parquet` / `register_csv` are safe under distinct table names;
  registering the same name concurrently is unsupported.
- `list_tables` is a best-effort enumeration: registrations that land
  mid-call may or may not appear, but the result is always well-formed.
- `load_mdl` must not overlap other calls on the same context; overlapping
  calls raise `RuntimeError`.

## Developer Guide

### Environment Setup

- Install [Rust](https://www.rust-lang.org/tools/install) and [Cargo](https://doc.rust-lang.org/cargo/getting-started/installation.html)
- Install [Python](https://www.python.org/downloads/)
- Install [uv](https://github.com/astral-sh/uv)
- Install [casey/just](https://github.com/casey/just)

### Test and Build

After installing `casey/just`, you can use the following commands:

- `just install` — Create Python venv and install dependencies.
- `just develop` — Build the Rust package for local development (**required before running Python tests**).
- `just test-rs` — Run Rust tests only.
- `just test-py` — Run Python tests only.
- `just test` — Run both Rust and Python tests.
- `just build` — Build the Python wheel. Output goes to `target/wheels/`.

### Cross-Compilation

The official CI builds wheels on native runners for each platform. When you
need to produce a wheel for a different platform locally (e.g. building a
Linux x86_64 wheel on ARM64 macOS), use one of the approaches below.

#### Option 1: `cargo-zigbuild` + maturin (requires [zig](https://ziglang.org))

```bash
# 1. Install the Rust cross-compilation target
rustup target add x86_64-unknown-linux-gnu

# 2. Install cargo-zigbuild
cargo install cargo-zigbuild

# 3. Build the wheel (large projects may hit macOS's file-descriptor limit;
#    raise it first to avoid "ProcessFdQuotaExceeded")
ulimit -n 4096
cd core/wren-core-py
maturin build --release --target x86_64-unknown-linux-gnu --zig
```

The wheel lands in `target/wheels/` with a `manylinux_2_28_x86_64` tag.

Notes:

- `x86_64-unknown-linux-gnu` (glibc) is the standard target and produces
  wheels that run on virtually all Linux distributions. Only use
  `x86_64-unknown-linux-musl` if you specifically target Alpine Linux —
  its wheels are not compatible with glibc-based systems.
- If linking fails with `ProcessFdQuotaExceeded`, raise the file-descriptor
  limit (`ulimit -n 4096`); if it persists, retry with `CARGO_BUILD_JOBS=1`.

#### Option 2: Docker (no Rust toolchain on host required)

```bash
cd core
docker run --platform linux/amd64 --rm \
  -v "$(pwd):/io" \
  -w /io/wren-core-py \
  quay.io/pypa/manylinux_2_28_x86_64 \
  bash -c "
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source \$HOME/.cargo/env
    pip install maturin
    maturin build --release
  "
```

Mount the parent `core/` directory (not just `wren-core-py/`) because
`Cargo.toml` declares path dependencies on `../wren-core/core` and
`../wren-core-base`.

### Coding Style

Format via `just format`.

### Publishing

See `scripts/publish.sh` for local publishing to PyPI/TestPyPI:

```bash
./scripts/publish.sh --build    # Build wheel only
./scripts/publish.sh --test     # Build + publish to TestPyPI
./scripts/publish.sh            # Build + publish to PyPI
```

## License

Apache-2.0
