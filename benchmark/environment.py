"""
Isolated environment management.

Each benchmark run gets its own temporary OPENCLAW_HOME directory so that
parallel or sequential runs never interfere with each other (or with the
user's real ``~/.openclaw``).  This module handles:

* Creating / cleaning the temp directory tree.
* Installing openclaw **locally** inside the temp directory (never touches
  global npm packages).
* Providing the env-vars dict that every subprocess should inherit.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from .config import BenchmarkConfig, ModelConfig, DEFAULT_CONTEXT_WINDOW, MAX_CONTEXT_WINDOW, MIN_CONTEXT_WINDOW

logger = logging.getLogger(__name__)


def _query_ollama_context_window(base_url: str, model_id: str) -> int | None:
    """Ask Ollama for the real context window via ``/api/show``.

    *base_url* is expected to be the OpenAI-compatible endpoint
    (``http://…:11434/v1``).  We strip ``/v1`` to reach the native
    Ollama API.

    Returns the context length in tokens, or ``None`` on failure.
    """
    import urllib.request
    import urllib.error

    # /v1 -> native API root
    api_root = base_url.rstrip("/")
    if api_root.endswith("/v1"):
        api_root = api_root[:-3]

    url = f"{api_root}/api/show"
    payload = json.dumps({"name": model_id}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return None

    # Ollama stores the context length under
    #   model_info.<arch>.context_length  (e.g. model_info.glm4.context_length)
    # or under  parameters  ("num_ctx <value>").
    model_info = data.get("model_info", {})
    for key, val in model_info.items():
        if key.endswith(".context_length") and isinstance(val, (int, float)) and val > 0:
            ctx = int(val)
            logger.info("Ollama reports context_length=%d for %s (via model_info)", ctx, model_id)
            return ctx

    # Fallback: parse parameters string  "num_ctx 131072\nnum_…"
    params_str = data.get("parameters", "")
    for line in params_str.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0] == "num_ctx":
            try:
                ctx = int(parts[1])
                if ctx > 0:
                    logger.info("Ollama reports num_ctx=%d for %s (via parameters)", ctx, model_id)
                    return ctx
            except ValueError:
                pass

    return None


def warm_up_model(model: ModelConfig, timeout: int = 120) -> bool:
    """Send a tiny chat-completion request to force the provider to load the model.

    Ollama (and some other servers) lazy-load models on first request,
    which can add tens of seconds of latency to the first benchmark turn.
    Calling this *before* the timed runs ensures the model is already hot
    in memory and also confirms the API endpoint is actually reachable.

    Returns ``True`` if the model responded successfully, ``False`` otherwise.
    """
    import urllib.request
    import urllib.error

    url = model.base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model.model_id,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 4,
    }).encode()

    headers = {"Content-Type": "application/json"}
    if model.api_key:
        headers["Authorization"] = f"Bearer {model.api_key}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        # Minimal sanity check — any choices array means the model answered
        if data.get("choices"):
            logger.info("Warm-up OK for %s — model is loaded and responding", model.model_id)
            return True
        logger.warning("Warm-up for %s returned unexpected response: %s", model.model_id, data)
        return False
    except urllib.error.HTTPError as exc:
        logger.warning("Warm-up HTTP error for %s: %s %s", model.model_id, exc.code, exc.reason)
        return False
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Warm-up failed for %s: %s", model.model_id, exc)
        return False


class OpenClawEnvironment:
    """Manages an isolated OpenClaw installation for one benchmark run."""

    def __init__(self, cfg: BenchmarkConfig, model: ModelConfig, run_dir: str | None = None):
        self.cfg = cfg
        self.model = model

        # Create isolated home
        if run_dir:
            self.home_dir = Path(run_dir)
            self.home_dir.mkdir(parents=True, exist_ok=True)
            self._is_temp = False
        else:
            # Sanitise the model name for use in filesystem paths.
            # Colons (common in Ollama tags like "llama3:8b") are
            # problematic on macOS (HFS+ uses ':' as its internal
            # separator) and can confuse npm, so replace them.
            safe_name = model.name.replace(":", "_").replace("/", "_")
            self._temp_dir_obj = tempfile.mkdtemp(prefix=f"openclaw_bench_{safe_name}_")
            self.home_dir = Path(self._temp_dir_obj)
            self._is_temp = True

        # Lock down temp dir: owner-only access (no world-readable secrets)
        try:
            self.home_dir.chmod(stat.S_IRWXU)  # 0o700
        except OSError:
            pass

        # Local npm prefix — openclaw binary lands here, never touches global
        self._npm_prefix = self.home_dir / "npm_prefix"
        self._npm_prefix.mkdir(parents=True, exist_ok=True)

        self.workspace_dir = self.home_dir / "workspace"
        self.config_path = self.home_dir / "openclaw.json"

        # Set by write_config()
        self._gateway_token: str | None = None
        self._provider_id: str | None = None

        logger.info("Environment home: %s", self.home_dir)

    # ── Environment variables ────────────────────────────────
    def env(self) -> dict[str, str]:
        """Return a copy of ``os.environ`` with OpenClaw overrides.

        The local npm prefix ``bin/`` directory is prepended to ``PATH``
        so that the locally-installed ``openclaw`` binary is found first.
        """
        e = os.environ.copy()
        e["OPENCLAW_HOME"] = str(self.home_dir)
        e["OPENCLAW_CONFIG_PATH"] = str(self.config_path)
        # Prepend local npm bin so our isolated install is found first
        npm_bin = self._npm_prefix / "bin"
        e["PATH"] = f"{npm_bin}{os.pathsep}{e.get('PATH', '')}"
        # Disable colour / interactive prompts for cleaner parsing
        e["NO_COLOR"] = "1"
        e["CI"] = "1"
        # Set the custom API key if provided
        if self.model.api_key:
            e["CUSTOM_API_KEY"] = self.model.api_key
        # Expose gateway token so CLI commands authenticate
        if self._gateway_token:
            e["OPENCLAW_GATEWAY_TOKEN"] = self._gateway_token
        return e

    # ── Install openclaw ─────────────────────────────────────
    def install_openclaw(self) -> None:
        """Install openclaw into a local prefix (never modifies global npm).

        Uses ``npm install -g --prefix <local_dir>`` which is a standard
        pattern for installing a package "globally" into a custom prefix.
        The binary lands in ``<prefix>/bin/openclaw`` where our ``PATH``
        override picks it up.  The system-wide global npm is untouched.
        """
        logger.info("Installing openclaw@latest into %s …", self._npm_prefix)
        subprocess.run(
            [
                "npm", "install", "-g",
                "--prefix", str(self._npm_prefix),
                "openclaw@latest",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        logger.info("openclaw installed successfully (local prefix)")

    # ── Version detection ────────────────────────────────────
    def detect_openclaw_version(self) -> str:
        """Run ``openclaw --version`` and return the version string.

        Falls back to ``"unknown"`` if the command fails for any reason.
        """
        try:
            result = subprocess.run(
                ["openclaw", "--version"],
                env=self.env(),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info("Detected OpenClaw version: %s", version)
                return version
        except (subprocess.TimeoutExpired, OSError):
            pass
        logger.warning("Could not detect OpenClaw version")
        return "unknown"

    # ── Config management ───────────────────────────────────
    def write_config(self) -> None:
        """Prepare the environment — but do NOT pre-write ``openclaw.json``.

        OpenClaw validates any existing config file *before* the onboard
        command can merge its own changes.  If the pre-written config
        doesn't perfectly match the (frequently evolving) JSON schema,
        onboard will refuse to run.

        Instead, we:
        1. Generate a gateway token for later use.
        2. Ensure the ``OPENCLAW_HOME`` directory exists so that onboard
           can write its own ``openclaw.json`` from scratch using only
           the CLI flags we provide.
        3. After onboard has run (see ``_read_back_config``), we read
           back whatever token/provider onboard persisted so the rest
           of the pipeline (gateway start, agent commands) stays in sync.

        This approach is inherently schema-safe — onboard always writes
        a config that matches its own validation rules.
        """
        import secrets

        # Pre-generate a gateway token that we'll pass to onboard
        self._gateway_token = secrets.token_urlsafe(32)

        # Ensure the home directory exists (onboard still expects it)
        self.home_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Environment prepared (no pre-written config — onboard will create it)")

    def _read_back_config(self) -> None:
        """Read back the config that onboard wrote.

        After ``openclaw onboard --non-interactive`` runs, it writes its
        own ``openclaw.json``.  We read it back to learn the provider ID
        it assigned and to confirm the gateway token.
        """
        if not self.config_path.exists():
            logger.warning("Config not found after onboard — expected at %s", self.config_path)
            return

        try:
            with open(self.config_path) as f:
                cfg = json.load(f)

            # Read provider ID from agents.defaults.model.primary  (format: "provider/model")
            model_primary = (
                cfg.get("agents", {})
                .get("defaults", {})
                .get("model", {})
            )
            if isinstance(model_primary, dict):
                ref = model_primary.get("primary", "")
            elif isinstance(model_primary, str):
                ref = model_primary
            else:
                ref = ""

            if "/" in ref:
                self._provider_id = ref.split("/", 1)[0]
            else:
                self._provider_id = None

            # Confirm gateway token
            written_token = (
                cfg.get("gateway", {})
                .get("auth", {})
                .get("token")
            )
            if written_token and written_token != self._gateway_token:
                # Onboard may have generated its own token; use that instead
                logger.info("Adopting onboard's gateway token")
                self._gateway_token = written_token

            logger.info("Read back config: provider=%s", self._provider_id)

        except Exception:
            logger.warning("Failed to read back config from %s", self.config_path, exc_info=True)

    def _patch_config_context_window(self) -> None:
        """Patch the ``contextWindow`` for our model in the config file.

        ``openclaw onboard --custom-*`` hard-codes ``contextWindow: 4096``
        which is below OpenClaw's 16 000-token minimum and causes a
        ``FailoverError``.  We fix the value *after* onboard has written
        the config so we never fight the schema.

        Resolution order:
        1. User-specified ``context_window`` in config.yaml (if not the
           default 128 000 — i.e. explicitly set).
        2. Live query to Ollama ``/api/show`` (for Ollama endpoints).
        3. Fall back to ``model.context_window`` (which defaults to 128 000).

        The final value is clamped to [MIN_CONTEXT_WINDOW, MAX_CONTEXT_WINDOW]
        (currently 16 000–128 000).
        """
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read config for context-window patch")
            return

        # Determine the best context-window value
        ctx = self.model.context_window

        # If the user didn't explicitly override, try asking Ollama
        if ctx == DEFAULT_CONTEXT_WINDOW and "localhost" in self.model.base_url:
            discovered = _query_ollama_context_window(
                self.model.base_url, self.model.model_id,
            )
            if discovered and discovered >= MIN_CONTEXT_WINDOW:
                ctx = discovered

        # Clamp to [MIN, MAX] to avoid token-budget issues
        ctx = max(ctx, MIN_CONTEXT_WINDOW)
        ctx = min(ctx, MAX_CONTEXT_WINDOW)

        # Walk into the config and patch every model entry that matches
        providers = cfg.get("models", {}).get("providers", {})
        patched = False
        for prov_cfg in providers.values():
            models = prov_cfg.get("models", [])
            if not isinstance(models, list):
                continue
            for mdl in models:
                if mdl.get("id") == self.model.model_id:
                    old = mdl.get("contextWindow", "?")
                    mdl["contextWindow"] = ctx
                    mdl["maxTokens"] = max(mdl.get("maxTokens", 8192), 8192)
                    patched = True
                    logger.info(
                        "Patched contextWindow %s → %d for %s",
                        old, ctx, self.model.model_id,
                    )

        if patched:
            with open(self.config_path, "w") as f:
                json.dump(cfg, f, indent=2)
        else:
            logger.debug("No model entry found to patch (model_id=%s)", self.model.model_id)

    # ── Run onboarding non-interactively ─────────────────────
    def run_onboard(self) -> subprocess.CompletedProcess[str]:
        """Run ``openclaw onboard`` in non-interactive mode.

        The onboard command creates ``openclaw.json`` from scratch
        (no pre-existing config is needed).  All model, gateway, and
        workspace settings are passed via CLI flags.
        """
        cmd = [
            "openclaw", "onboard",
            "--non-interactive",
            "--accept-risk",
            "--mode", "local",
            "--auth-choice", self.model.auth_choice,
            "--custom-base-url", self.model.base_url,
            "--custom-model-id", self.model.model_id,
            "--custom-compatibility", self.model.compatibility,
            "--gateway-port", str(self.cfg.gateway.port),
            "--gateway-bind", self.cfg.gateway.bind,
            "--gateway-auth", "token",
            "--skip-skills",
            "--skip-health",
            "--skip-channels",
            "--workspace", str(self.workspace_dir),
        ]
        if self._gateway_token:
            cmd.extend(["--gateway-token", self._gateway_token])
        if self.model.api_key:
            cmd.extend(["--custom-api-key", self.model.api_key])

        # Log the command with secrets redacted
        safe_cmd = " ".join(cmd)
        if self.model.api_key:
            safe_cmd = safe_cmd.replace(self.model.api_key, "***")
        if self._gateway_token:
            safe_cmd = safe_cmd.replace(self._gateway_token, "***")
        logger.info("Running onboard: %s", safe_cmd)
        result = subprocess.run(
            cmd,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            logger.error("Onboard failed (exit %d):\nstdout: %s\nstderr: %s",
                         result.returncode, result.stdout, result.stderr)
        else:
            logger.info("Onboard completed successfully")
            # Read back the config that onboard wrote so we know the
            # provider ID and can confirm the gateway token.
            self._read_back_config()
            # Fix the context window — onboard defaults to 4096 for
            # custom providers, which is below OpenClaw's 16k minimum.
            self._patch_config_context_window()
        return result

    # ── Start / stop gateway ─────────────────────────────────
    def start_gateway(self) -> subprocess.Popen[str]:
        """Start the gateway as a background process."""
        cmd = [
            "openclaw", "gateway",
            "--port", str(self.cfg.gateway.port),
            "--auth", "token",
        ]
        if self._gateway_token:
            cmd.extend(["--token", self._gateway_token])
        safe_gw_cmd = " ".join(cmd)
        if self._gateway_token:
            safe_gw_cmd = safe_gw_cmd.replace(self._gateway_token, "***")
        logger.info("Starting gateway: %s", safe_gw_cmd)
        proc = subprocess.Popen(
            cmd,
            env=self.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc

    @staticmethod
    def stop_gateway(proc: subprocess.Popen[str]) -> None:
        """Gracefully terminate the gateway process."""
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        logger.info("Gateway stopped")

    # ── Cleanup ──────────────────────────────────────────────
    def cleanup(self) -> None:
        """Remove the temporary home directory."""
        if self._is_temp and self.home_dir.exists():
            shutil.rmtree(self.home_dir, ignore_errors=True)
            logger.info("Cleaned up %s", self.home_dir)
