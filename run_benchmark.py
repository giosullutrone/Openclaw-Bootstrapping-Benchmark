#!/usr/bin/env python3
"""
CLI entry-point for the OpenClaw Bootstrapping Benchmark.

Usage
-----
  # Run all models
  python run_benchmark.py

  # Run specific models
  python run_benchmark.py --models llama3.1-8b qwen2.5-coder-32b

  # Skip npm install (if openclaw is already installed)
  python run_benchmark.py --skip-install

  # Keep temp environments for debugging
  python run_benchmark.py --keep-env --verbose

  # Use a custom config file
  python run_benchmark.py --config my_config.yaml
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="🦞 OpenClaw Bootstrapping Benchmark — test local models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                  Run all models in config.yaml
  %(prog)s --models llama3.1-8b             Run only one model
  %(prog)s --skip-install --verbose         Skip npm install, verbose logging
  %(prog)s --keep-env                       Keep temp dirs for debugging
        """,
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--models", "-m",
        nargs="+",
        default=None,
        help="Run only these models (by name from config.yaml)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip 'npm install openclaw@latest' (use existing install)",
    )
    parser.add_argument(
        "--keep-env",
        action="store_true",
        help="Keep temporary environments after runs (for debugging)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip pre-flight prerequisite checks (not recommended)",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run pre-flight checks only, don't start the benchmark",
    )
    parser.add_argument(
        "--runs", "-r",
        type=int,
        default=None,
        help="Number of independent runs per model (overrides config.yaml runs_per_model)",
    )
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help=(
            "Skip model/variant pairs already present in benchmark_latest.json "
            "(re-runs if openclaw version or prompts changed)"
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()

    # Pre-flight only mode
    if args.preflight_only:
        from benchmark.config import load_config
        from benchmark.preflight import print_preflight, run_preflight
        from rich.console import Console

        cfg = load_config(args.config)
        if args.models:
            model_set = set(args.models)
            cfg.models = [m for m in cfg.models if m.name in model_set]
        report = run_preflight(cfg, skip_install=args.skip_install)
        print_preflight(report, Console())
        sys.exit(0 if report.all_passed else 2)

    from benchmark.runner import run_benchmark

    results = run_benchmark(
        config_path=args.config,
        models=args.models,
        skip_install=args.skip_install,
        skip_preflight=args.skip_preflight,
        keep_env=args.keep_env,
        verbose=args.verbose,
        runs_per_model=args.runs,
        skip_completed=args.skip_completed,
    )

    # Exit with non-zero if any model failed completely
    any_failed = any(ag.perfect_rate < 1.0 for ag in results)
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
