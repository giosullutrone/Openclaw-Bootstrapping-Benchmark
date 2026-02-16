"""
OpenClaw Bootstrapping Benchmark
=================================
Automated benchmark suite that tests whether local LLM models can
successfully complete the OpenClaw bootstrapping (first-run identity
ritual) process.

Modules
-------
- config       – YAML configuration loader
- environment  – Isolated OpenClaw home / install management
- onboard      – Non-interactive onboarding automation
- bootstrap    – Bootstrap conversation driver (TUI automation)
- verify       – Post-bootstrap file verification
- report       – Rich terminal + JSON results reporting
- runner       – Top-level orchestrator
"""
