"""
Configuration loader for the benchmark suite.

Reads config.yaml and provides typed access
to all settings.

Environment variable interpolation
-----------------------------------
Any string value in config.yaml can reference environment variables:

  ``$VAR``  or  ``${VAR}``  or  ``${VAR:-default}``

The variable is expanded at load time.  If the variable is not set and
no ``:-default`` is given, the literal string is left unchanged, so
harmless placeholders like ``"ollama"`` work as-is.  This lets users
keep real API keys out of the checked-in config file::

    api_key: "${MY_SECRET_KEY}"
    api_key: "${OLLAMA_API_KEY:-ollama}"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Matches  $VAR  ,  ${VAR}  ,  and  ${VAR:-default}
_ENV_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}"
    r"|\$([A-Za-z_][A-Za-z0-9_]*)"
)


def _expand_env(value: str) -> str:
    """Replace ``$VAR`` / ``${VAR}`` / ``${VAR:-default}`` with env values.

    If the variable is not set **and** no default is provided, the original
    reference is left unchanged (safe for dummy keys like ``"ollama"``).
    """
    def _replace(m: re.Match[str]) -> str:
        # ${VAR} or ${VAR:-default}
        if m.group(1) is not None:
            var = m.group(1)
            default = m.group(2)  # None when no :- was used
            env_val = os.environ.get(var)
            if env_val is not None:
                return env_val
            return default if default is not None else m.group(0)
        # $VAR  (bare)
        var = m.group(3)
        return os.environ.get(var, m.group(0))
    return _ENV_RE.sub(_replace, value)


# Minimum context window accepted by OpenClaw's agent runtime
MIN_CONTEXT_WINDOW = 16_000

# Hard ceiling – clamp any value above this to avoid token-budget issues
MAX_CONTEXT_WINDOW = 128_000

# Sensible default when the model/server doesn't report a value
DEFAULT_CONTEXT_WINDOW = 128_000


@dataclass
class ModelConfig:
    """A single model to benchmark."""

    name: str
    provider: str
    auth_choice: str
    base_url: str
    model_id: str
    api_key: str = ""
    compatibility: str = "openai"
    context_window: int = DEFAULT_CONTEXT_WINDOW

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelConfig:
        return cls(
            name=d["name"],
            provider=d.get("provider", "custom"),
            auth_choice=d.get("auth_choice", "custom-api-key"),
            base_url=d["base_url"],
            model_id=d["model_id"],
            api_key=_expand_env(d.get("api_key", "")),
            compatibility=d.get("compatibility", "openai"),
            context_window=int(d.get("context_window", DEFAULT_CONTEXT_WINDOW)),
        )


@dataclass
class GatewayConfig:
    port: int = 18789
    bind: str = "loopback"


@dataclass
class BootstrapFields:
    """Expected field values injected into prompt templates and verified
    in the post-bootstrap checks.

    Prompt templates reference these as ``{user_name}``, ``{agent_emoji}``, etc.
    """

    # User fields (checked in USER.md)
    user_name: str = "Alex"
    user_timezone: str = "Europe/Rome"
    user_preferences: str = "concise answers, no filler, direct and helpful"

    # Agent fields (checked in IDENTITY.md)
    agent_name: str = "Coral"
    agent_creature: str = "space lobster"
    agent_vibe: str = "warm and casual"
    agent_emoji: str = "\U0001f99e"  # 🦞

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BootstrapFields:
        return cls(
            user_name=str(d.get("user_name", cls.user_name)),
            user_timezone=str(d.get("user_timezone", cls.user_timezone)),
            user_preferences=str(d.get("user_preferences", cls.user_preferences)),
            agent_name=str(d.get("agent_name", cls.agent_name)),
            agent_creature=str(d.get("agent_creature", cls.agent_creature)),
            agent_vibe=str(d.get("agent_vibe", cls.agent_vibe)),
            agent_emoji=str(d.get("agent_emoji", cls.agent_emoji)),
        )

    def as_template_vars(self) -> dict[str, str]:
        """Return a dict suitable for ``str.format_map()``."""
        return {
            "user_name": self.user_name,
            "user_timezone": self.user_timezone,
            "user_preferences": self.user_preferences,
            "agent_name": self.agent_name,
            "agent_creature": self.agent_creature,
            "agent_vibe": self.agent_vibe,
            "agent_emoji": self.agent_emoji,
        }

    # Convenience accessors for verify.py
    @property
    def identity_expected(self) -> dict[str, str]:
        """Field-name → expected value for IDENTITY.md checks."""
        return {
            "name": self.agent_name,
            "creature": self.agent_creature,
            "vibe": self.agent_vibe,
            "emoji": self.agent_emoji,
        }

    @property
    def user_expected(self) -> dict[str, str]:
        """Field-name → expected value for USER.md checks."""
        return {
            "name": self.user_name,
            "timezone": self.user_timezone,
        }


@dataclass
class PromptVariant:
    """A named prompt variant (e.g. 'guided' or 'unguided')."""

    name: str
    prompts: list[str] = field(default_factory=list)


@dataclass
class BenchmarkConfig:
    """Top-level benchmark configuration."""

    prompt_variants: list[PromptVariant] = field(default_factory=list)
    agent_turn_timeout: int = 120
    bootstrap_timeout: int = 600
    retries: int = 1
    runs_per_model: int = 5
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    openclaw_home: str = ""
    models: list[ModelConfig] = field(default_factory=list)
    bootstrap_fields: BootstrapFields = field(default_factory=BootstrapFields)

    # Legacy accessor — returns the first variant's prompts (or empty list)
    @property
    def bootstrap_prompts(self) -> list[str]:
        if self.prompt_variants:
            return self.prompt_variants[0].prompts
        return []

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BenchmarkConfig:
        gw = d.get("gateway", {})

        # Parse prompt_variants — supports two config styles:
        #
        # Style 1 (new — named variants):
        #   prompt_variants:
        #     guided:
        #       - "prompt text ..."
        #     unguided:
        #       - "prompt text ..."
        #
        # Style 2 (legacy — flat prompt list):
        #   bootstrap_prompts:
        #     - "prompt text ..."
        raw_variants = d.get("prompt_variants", {})
        variants: list[PromptVariant] = []

        # Parse bootstrap_fields first so we can interpolate prompts
        bf = BootstrapFields.from_dict(d.get("bootstrap_fields", {}))
        tpl_vars = bf.as_template_vars()

        def _interpolate_prompts(prompts: list[str]) -> list[str]:
            """Replace {field} placeholders in prompt templates."""
            result = []
            for p in prompts:
                try:
                    result.append(p.format_map(tpl_vars))
                except KeyError:
                    result.append(p)  # leave unresolvable templates as-is
            return result

        if raw_variants and isinstance(raw_variants, dict):
            for name, prompts in raw_variants.items():
                if isinstance(prompts, list):
                    variants.append(PromptVariant(name=name, prompts=_interpolate_prompts(prompts)))
                elif isinstance(prompts, str):
                    variants.append(PromptVariant(name=name, prompts=_interpolate_prompts([prompts])))
        elif "bootstrap_prompts" in d:
            # Legacy format: treat as a single unnamed variant
            bp = d["bootstrap_prompts"]
            if isinstance(bp, list):
                variants.append(PromptVariant(name="default", prompts=_interpolate_prompts(bp)))

        return cls(
            prompt_variants=variants,
            agent_turn_timeout=d.get("agent_turn_timeout", 120),
            bootstrap_timeout=d.get("bootstrap_timeout", 600),
            retries=d.get("retries", 1),
            runs_per_model=int(d.get("runs_per_model", 5)),
            gateway=GatewayConfig(
                port=gw.get("port", 18789),
                bind=gw.get("bind", "loopback"),
            ),
            openclaw_home=d.get("openclaw_home", ""),
            models=[ModelConfig.from_dict(m) for m in d.get("models", [])],
            bootstrap_fields=bf,
        )


def load_config(path: str | Path | None = None) -> BenchmarkConfig:
    """Load configuration from YAML file.

    When *path* is ``None``, loads ``config.yaml`` from the project root.
    """
    if path is None:
        root = Path(__file__).resolve().parent.parent
        path = root / "config.yaml"
        if not path.exists():
            raise FileNotFoundError(
                "No config file found.  Expected config.yaml in the project root."
            )
    else:
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    return BenchmarkConfig.from_dict(raw)
