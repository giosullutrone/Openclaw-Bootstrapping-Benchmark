# 🦞 OpenClaw Bootstrapping Benchmark

Automated benchmark suite that tests whether **local LLM models** can
successfully complete the [OpenClaw](https://github.com/openclaw/openclaw)
bootstrapping (first-run identity ritual) process — in a **single prompt**.

## Benchmark results

<!-- BENCHMARK RESULTS -->
### Latest results

> Ran on **2026-02-16 10:13 UTC** against a local [Ollama](https://ollama.com/) server.

| Model | Score | Bootstrap | IDENTITY | USER | SOUL | Duration |
|-------|:-----:|:---------:|:--------:|:----:|:----:|----------:|
| glm-4.7-flash:bf16 | 100% | ✅ | ✅ | ✅ | ✅ | 88.5s |
| gpt-oss:120b | 100% | ✅ | ✅ | ✅ | ✅ | 65.2s |
| qwen3-coder-next:q8_0 | 100% | ✅ | ✅ | ✅ | ✅ | 90.7s |
| qwen3-next:80b-a3b-thinking-q4_K_M | 25% | ❌ | ❌ | ❌ | ✅ | 184.4s |
| qwen3-vl:30b-a3b-instruct-q8_0 | 100% | ✅ | ✅ | ✅ | ✅ | 53.8s |

**4/5** models completed the bootstrap perfectly.

<details><summary>Column legend</summary>

| Column | Meaning |
|--------|---------|
| **Score** | Percentage of checks passed (4 total) |
| **Bootstrap** | `BOOTSTRAP.md` was deleted (ritual completed) |
| **IDENTITY** | `IDENTITY.md` has real Name, Creature, Vibe, Emoji |
| **USER** | `USER.md` has real Name, Timezone |
| **SOUL** | `SOUL.md` was personalised beyond the template |
| **Duration** | Wall-clock time for the bootstrap conversation |

</details>

<!-- /BENCHMARK RESULTS -->

> **⚠️ Note on variability:** Although each model is run multiple times and
> results are averaged, LLM outputs are inherently non-deterministic due to
> sampling (temperature, top-p, etc.). The scores above represent the model's
> performance *during this benchmark* — your own results may be better or worse
> on any given run.

### Ollama configuration

The results above were produced with the following Ollama server settings:

| Setting | Value |
|---|---|
| **Flash Attention** | Enabled (`OLLAMA_FLASH_ATTENTION=1`) |
| **KV Cache type** | FP16 (`OLLAMA_KV_CACHE_TYPE=f16`) |

These settings affect inference speed and memory usage.  Flash attention
generally improves throughput and reduces VRAM usage.  FP16 KV cache uses
more memory than the default Q8 quantised cache but preserves precision,
which can matter for instruction-following tasks like the bootstrap ritual.

To reproduce:

```bash
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=f16 ollama serve
```

## What is bootstrapping?

When OpenClaw starts for the first time, it runs a **bootstrap ritual** — a
short conversation between the agent and the user to establish:

1. **Agent identity** — name, creature type, vibe, emoji → written to `IDENTITY.md`
2. **User profile** — name, timezone, preferences → written to `USER.md`
3. **Soul / persona** — tone, boundaries, behaviour → written to `SOUL.md`
4. **Completion signal** — `BOOTSTRAP.md` is **deleted** when finished

## How the benchmark works

The benchmark sends **one single prompt** containing all required
information (user name, timezone, agent name, creature, vibe, emoji, etc.)
and expects the model to complete the entire ritual autonomously — writing
the files and deleting `BOOTSTRAP.md` — without any follow-up.

Each model is tested with **four prompt variants** that combine two
independent dimensions:

|  | **Guided** (explicit file instructions) | **Unguided** (data only) |
|---|---|---|
| **Natural** (conversational prose) | `natural-guided` | `natural-unguided` |
| **Structured** (bullet-point lists) | `structured-guided` | `structured-unguided` |

- **Guided** prompts explicitly name the target files (`IDENTITY.md`,
  `USER.md`, `SOUL.md`) and tell the model to delete `BOOTSTRAP.md`.
  This tests raw instruction-following ability.
- **Unguided** prompts provide only the identity data — the model must
  read `BOOTSTRAP.md` on its own and figure out what to do.
  This tests autonomous reasoning and context awareness.
- **Natural** prompts use flowing, conversational prose.
- **Structured** prompts use labelled bullet-point fields.

Each model × variant combination is run **multiple times from scratch**
(default: 5, configurable via `runs_per_model` in config or `--runs` on
the CLI).  Every run creates a brand-new isolated environment so results
are independent.  The final reported score is the **average** across all
runs.

The **OpenClaw version** used for the benchmark is auto-detected at
runtime and included in every report (terminal, JSON, markdown, README).

For each configured model the suite:

1. **Isolated install** — installs `openclaw@latest` into a **local** npm
   prefix (never touches your global npm packages)
2. **Isolated environment** — creates a temporary `OPENCLAW_HOME` with
   restricted permissions (`0700`) so nothing touches your real config
3. **Non-interactive onboarding** — runs `openclaw onboard --non-interactive`
   with the model pointed at your local inference server
4. **Single-prompt bootstrap** — sends one comprehensive message via
   `openclaw agent --message` per prompt variant (4 variants by default)
5. **Verification** — inspects the workspace files:

   | Check | Pass condition |
   |---|---|
   | `BOOTSTRAP.md` | Must be **deleted** |
   | `IDENTITY.md` | Must have non-placeholder Name, Creature, Vibe, Emoji |
   | `USER.md` | Must have non-placeholder Name, Timezone |
   | `SOUL.md` | Must differ from the default template |

6. **Reporting** — prints a rich terminal table, saves a JSON report,
   and **auto-updates this README** with the latest results table
7. **Cleanup** — temp directories and gateway processes are torn down,
   even on `Ctrl-C` / `SIGTERM`

## ⚠️ Important warnings

> **Read this before running the benchmark.**

### Will this affect my existing OpenClaw installation?

The benchmark is designed to be **fully isolated**:
- OpenClaw is installed into a **local npm prefix** inside each temp directory
  (your global `npm` packages are **never** modified)
- Each run uses its own **temporary `OPENCLAW_HOME`** (your real
  `~/.openclaw/` config and workspace are **never** touched)
- Everything is cleaned up automatically after each run

**However**, there are edge cases you should be aware of:

| Risk | Likelihood | Mitigation |
|---|---|---|
| If you have a **globally installed** `openclaw` that conflicts with the version the benchmark installs locally | Low | The local prefix is prepended to `PATH`, so the local copy takes priority. Your global install is unchanged. |
| If the benchmark crashes hard (e.g. `kill -9`) before cleanup runs | Low | Orphaned temp dirs in `/tmp/openclaw_bench_*` may remain. Delete them manually: `rm -rf /tmp/openclaw_bench_*` |
| If port `18789` is already in use by another OpenClaw gateway | Low | Pre-flight checks detect this and abort. You can change the port in `config.yaml`. |
| If you run the benchmark **while** using OpenClaw in another terminal | Low | They use separate `OPENCLAW_HOME` dirs, but if both try to bind the same gateway port there will be a conflict. Use `--skip-preflight` only if you know what you're doing. |

**TL;DR:** Your existing OpenClaw installation **will not** be modified.
The worst that can happen is orphaned temp files in `/tmp/` if the process
is force-killed. This is safe to run.

## Prerequisites

| Prerequisite | Required | Auto-checked | Install |
|---|---|---|---|
| **Node.js ≥ 22** | ✅ | ✅ | [nodejs.org](https://nodejs.org/) or `brew install node@22` |
| **npm** | ✅ | ✅ | Ships with Node.js |
| **Python ≥ 3.10** | ✅ | — | [python.org](https://python.org/) |
| **pip dependencies** | ✅ | — | `pip install -r requirements.txt` |
| **Local model server** | ✅ | ✅ | [Ollama](https://ollama.com/), [LM Studio](https://lmstudio.ai/), [vLLM](https://github.com/vllm-project/vllm) |
| **Model pulled/loaded** | ✅ | ✅ | e.g. `ollama pull llama3.1:8b` |
| **Gateway port free** | ✅ | ✅ | `lsof -ti:18789 \| xargs kill` |

## Quick start

There are two ways to run the benchmark: the **one-liner** (recommended)
or a **manual setup** if you want more control.

### Option A — One-command launch (`run.sh`)

The included `run.sh` script creates the virtual environment, installs
all dependencies, and launches the benchmark in one step:

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/openclaw_bootstrapping_benchmark.git
cd openclaw_bootstrapping_benchmark

# 2. Edit config.yaml to add your models / adjust settings
$EDITOR config.yaml

# 3. Start your local model server (example: Ollama)
ollama serve &
ollama pull llama3.1:8b

# 4. Run the benchmark (creates .venv, installs deps, launches)
./run.sh
```

All `run_benchmark.py` flags work with `run.sh` too:

```bash
./run.sh --verbose --runs 3
./run.sh --models "glm-4.7-flash:bf16" --keep-env
./run.sh --preflight-only
```

### Option B — Manual setup

If you prefer to manage the virtual environment yourself:

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/openclaw_bootstrapping_benchmark.git
cd openclaw_bootstrapping_benchmark

# 2. Create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Edit config.yaml to add your models / adjust settings
$EDITOR config.yaml

# 5. Start your local model server (example: Ollama)
ollama serve &
ollama pull llama3.1:8b

# 6. Run the benchmark
python run_benchmark.py
```

> **Tip:** API keys in `config.yaml` support `${ENV_VAR}` interpolation
> so you can keep secrets in environment variables instead of the file.

After the benchmark finishes, the **results table above** is automatically
updated. Commit the updated `README.md` to share your results.

## Security

This tool is designed to run **locally** against your own model server.
Several measures keep your environment safe:

| Concern | Mitigation |
|---|---|
| **API keys in config** | Supports `${ENV_VAR}` and `${VAR:-default}` interpolation so real keys can live in environment variables instead of the committed file |
| **npm packages** | Installed to a local prefix inside each temp dir — **never modifies global npm** |
| **Temp directories** | Created with `0700` permissions (owner-only); cleaned up automatically |
| **Config files** | `openclaw.json` written with `0600` permissions |
| **Logs** | API keys are redacted from all log messages |
| **Reports** | JSON reports scrub secret-looking patterns (Bearer tokens, apiKey values) |
| **Interrupts** | `SIGINT` / `SIGTERM` handlers ensure gateway processes are killed and temp dirs removed |
| **Subprocesses** | All commands use list-form `subprocess` (no shell injection) |
| **Gateway auth** | Bound to loopback only (`127.0.0.1`) with auth mode `off` — not reachable from the network |

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Pre-flight checks

Before running any model, the benchmark validates all prerequisites.
If anything fails you get a clear table with fix instructions, and
the benchmark **aborts** (no wasted time).

```bash
# Run only the pre-flight checks (no benchmark)
python run_benchmark.py --preflight-only
```

To bypass (not recommended): `--skip-preflight`.

## Usage

All examples below work with both `./run.sh` and `python run_benchmark.py`.
Use `./run.sh` if you haven't set up the venv manually.

```bash
# Run all models in config.yaml
./run.sh                          # or: python run_benchmark.py

# Run only specific models
./run.sh --models "glm-4.7-flash:bf16" "qwen3-coder-next:q8_0"

# Override runs per model (default: 5)
./run.sh --runs 10

# Quick single run for testing
./run.sh --runs 1

# Skip npm install (openclaw already installed locally)
./run.sh --skip-install

# Keep temp environments for debugging
./run.sh --keep-env --verbose

# Skip models already in the latest report (same version + prompts)
./run.sh --skip-completed

# Use a custom config file
./run.sh --config my_config.yaml

# Run only pre-flight checks (no benchmark)
./run.sh --preflight-only
```

## Configuration

Edit `config.yaml` in the project root to add models, change prompt
variants, or adjust settings.

### Prompt variants

The benchmark ships with **four** prompt variants that cover two
independent dimensions — prompt *style* (natural vs structured) and
bootstrap *guidance* (guided vs unguided):

```yaml
prompt_variants:
  natural-guided:
    - |
      Hey there! I'd like to get everything configured right away …
      Please take all of this and write it into the right places:
      put your identity details in IDENTITY.md, my info in USER.md,
      and update SOUL.md. Delete BOOTSTRAP.md when you're done.

  natural-unguided:
    - |
      Hi! I'd love to get started. My name is Alex, Europe/Rome …
      That should be everything you need to get going. Take it from here!

  structured-guided:
    - |
      **About me (the user):**
      - Name: Alex
      - Timezone: Europe/Rome
      …
      Please write all of this to IDENTITY.md, USER.md, SOUL.md
      and delete BOOTSTRAP.md when you're done.

  structured-unguided:
    - |
      **User:**
      - Name: Alex
      - Timezone: Europe/Rome
      …
      **Agent:**
      - Name: Coral
      - Creature: space lobster
```

- **Guided** variants explicitly name the target files and the deletion
  step.
- **Unguided** variants provide only the data and trust the model to read
  `BOOTSTRAP.md` and follow its instructions autonomously.
- **Natural** variants use flowing conversational prose.
- **Structured** variants use labelled bullet-point fields.

Comparing scores across the four variants reveals how prompt format and
explicitness affect a model's ability to complete the ritual.  You can
add, remove, or edit variants freely.  The old `bootstrap_prompts` key
is still supported for backward compatibility (treated as a single
"default" variant).

### API key interpolation

```yaml
api_key: "${MY_SECRET_KEY}"          # expanded from env at runtime
api_key: "${OLLAMA_API_KEY:-ollama}" # with a fallback default
api_key: "ollama"                    # literal strings work too
```

See [config.yaml](config.yaml) for the full annotated template.

## Adding models

Add entries under `models:` in your `config.yaml`. Any server that exposes an
OpenAI-compatible `/v1/chat/completions` endpoint works:

| Server | `base_url` | Notes |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | `api_key: "ollama"` |
| LM Studio | `http://localhost:1234/v1` | `api_key: "lm-studio"` |
| vLLM | `http://localhost:8000/v1` | `api_key: "vllm"` |
| text-generation-inference | `http://localhost:8080/v1` | — |

## Output

### Auto-updated README

After each run, the results table at the top of this README is
automatically replaced with the latest data. Commit the change
to keep your results visible on GitHub.

### JSON report

Full reports are saved to `results/benchmark_YYYYMMDD_HHMMSS.json` (git-ignored)
with per-model details including prompts, full responses, timings, file
contents, and check results.

A copy is also written to `results/benchmark_latest.json` which **is**
committed to the repo, so the most recent results are always available
without re-running.

A `results/latest.md` file is also generated with just the markdown table,
useful for embedding elsewhere.

## Project structure

```
├── LICENSE                    # MIT license
├── README.md                  # This file (auto-updated results table)
├── SECURITY.md                # Vulnerability reporting policy
├── config.yaml                # Benchmark configuration
├── requirements.txt           # Python dependencies
├── .gitignore
├── run.sh                     # One-command launcher (venv + deps + benchmark)
├── run_benchmark.py           # CLI entry-point (use directly or via run.sh)
├── benchmark/
│   ├── __init__.py
│   ├── config.py              # YAML config loader + env-var interpolation
│   ├── preflight.py           # Pre-flight prerequisite checks
│   ├── environment.py         # Isolated openclaw home management
│   ├── bootstrap.py           # Bootstrap conversation driver
│   ├── verify.py              # Post-bootstrap file verification
│   ├── report.py              # Rich terminal + JSON + markdown reporting
│   └── runner.py              # Top-level orchestrator + signal handlers
└── results/                   # Generated reports
    ├── benchmark_latest.json  # Latest full JSON report (committed)
    ├── latest.md              # Markdown results table (committed)
    └── benchmark_*.json       # Timestamped JSON reports (git-ignored)
```

## How OpenClaw bootstrapping works (reference)

The OpenClaw agent workspace (default `~/.openclaw/workspace/`) contains these
key files, seeded on first run:

| File | Purpose | Loaded when |
|---|---|---|
| `AGENTS.md` | Operating instructions for the agent | Every session |
| `SOUL.md` | Persona, tone, boundaries | Every session |
| `IDENTITY.md` | Agent name, creature, vibe, emoji | Every session |
| `USER.md` | User name, timezone, preferences | Every session |
| `TOOLS.md` | Tool notes and conventions | Every session |
| `HEARTBEAT.md` | Heartbeat checklist | Heartbeat runs |
| `BOOTSTRAP.md` | **First-run ritual** — deleted when done | First run only |

During the bootstrap ritual the agent:
1. Reads `BOOTSTRAP.md` which says "figure out who you are"
2. Asks the user identity questions (name, creature, vibe, emoji)
3. Writes answers to `IDENTITY.md` and `USER.md`
4. Customises `SOUL.md`
5. **Deletes `BOOTSTRAP.md`** to signal completion

This benchmark automates step 2 with a single deterministic prompt (in
four variants — natural/structured × guided/unguided) and verifies
steps 3–5 programmatically.

## Contributing

Contributions are welcome! There are two main ways to contribute:

### Request a new model

If you'd like to see a model added to the official results table but can't
run it yourself, **open an issue** with:

- The model name and where to get it (Ollama tag, HuggingFace ID, etc.)
- Any special settings it needs (quantisation, context window, etc.)

Models will be added depending on hardware resource availability.

### Submit your own benchmark results

If you have access to hardware we don't, you can run the benchmark yourself
and submit the results.  We especially welcome **more extensive** benchmarks
(more models, higher `runs_per_model`, different quantisations, etc.):

1. Fork the repo and create a branch
2. Edit `config.yaml` to configure your models
3. Run `./run.sh` (or `python run_benchmark.py`) — the README is auto-updated
4. Open a **pull request** with:
   - The updated `README.md` (auto-generated results table)
   - The JSON report from `results/` (for reproducibility)
   - A note about your hardware and Ollama settings in the PR description

> **Tip:** Use `--runs 10` or higher for more statistically significant
> results.  The default is 5 runs per model.

### Other contributions

Bug fixes, new features, and documentation improvements are also welcome.
Please ensure `./run.sh --preflight-only` (or `python run_benchmark.py --preflight-only`)
passes before opening a PR.

## License

[MIT](LICENSE)
