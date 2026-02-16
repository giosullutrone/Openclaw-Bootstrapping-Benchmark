# Security Policy

## Scope

This project is a **local benchmarking tool** — it runs on your machine,
talks to your own model server, and never sends data to external services.
There is no hosted service or cloud component.

## Supported Versions

Only the latest release on the `main` branch is supported with security
updates.

## Reporting a Vulnerability

If you discover a security issue, please **do not** open a public GitHub
issue.  Instead:

1. Email the maintainers at **security@example.com** (replace with your
   actual contact) with:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact
2. You will receive an acknowledgement within **72 hours**.
3. A fix will be developed privately and released as soon as practical.

## Security Design

| Area | Approach |
|---|---|
| **API keys** | `config.yaml` supports env-var interpolation (`${VAR:-default}`) so real keys can live in environment variables instead of the committed file |
| **npm isolation** | `openclaw` is installed to a local prefix inside each temp dir — global npm is never modified |
| **File permissions** | Temp dirs are `0700`; `openclaw.json` (contains API key) is `0600` |
| **Subprocess execution** | All commands use list-form `subprocess.run` / `Popen` — no shell expansion, no injection risk |
| **Secret redaction** | API keys are masked in log output; JSON reports scrub Bearer tokens and apiKey patterns |
| **Cleanup** | `SIGINT` / `SIGTERM` / `atexit` handlers ensure gateway processes are killed and temp directories removed |
| **Network** | The OpenClaw gateway binds to loopback (`127.0.0.1`) only, with auth mode `off` — it is not reachable from other machines |

## Dependencies

This project depends on a small set of well-known Python packages
(`pyyaml`, `rich`, `pexpect`, `dataclasses-json`).  We recommend pinning
versions in production via `pip freeze > requirements-lock.txt`.

## Best Practices for Users

- **Always use a virtual environment** (`python3 -m venv .venv`)
- **Use env-var interpolation** for any non-trivial API keys (`${MY_KEY}`)
- **Never hard-code real secrets** in `config.yaml` — use `${VAR:-default}` syntax
- The shipped defaults are safe for local Ollama use
