### Latest results

> Ran on **2026-02-17 01:58 UTC** against a local [Ollama](https://ollama.com/) server (5 runs per model, averaged) · OpenClaw **2026.2.15**.

| Model | Variant | Runs | Avg Score | Perfect | BOOTSTRAP | IDENTITY | USER | SOUL | Avg Duration |
|-------|---------|:----:|:---------:|:-------:|:---------:|:--------:|:----:|:----:|-------------:|
| glm-4.7-flash:bf16 | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 97.5s |
| glm-4.7-flash:bf16 | natural-unguided | 5 | 75% | 40% | 40% | 80% | 80% | ✅ | 57.1s |
| glm-4.7-flash:bf16 | structured-guided | 5 | 85% | 80% | 80% | 80% | 80% | ✅ | 74.2s |
| glm-4.7-flash:bf16 | structured-unguided | 5 | 90% | 60% | 60% | ✅ | ✅ | ✅ | 96.4s |
| glm-4.7-flash:latest | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 56.7s |
| glm-4.7-flash:latest | natural-unguided | 5 | 80% | 60% | 60% | 80% | 80% | ✅ | 66.5s |
| glm-4.7-flash:latest | structured-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 65.3s |
| glm-4.7-flash:latest | structured-unguided | 5 | 85% | 40% | 40% | ✅ | ✅ | ✅ | 60.4s |
| qwen3-coder-next:q8_0 | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 71.0s |
| qwen3-coder-next:q8_0 | natural-unguided | 5 | 85% | 40% | 40% | ✅ | ✅ | ✅ | 74.6s |
| qwen3-coder-next:q8_0 | structured-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 67.5s |
| qwen3-coder-next:q8_0 | structured-unguided | 5 | 25% | ❌ | ❌ | ❌ | ❌ | ✅ | 35.0s |
| qwen3-coder-next:latest | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 68.0s |
| qwen3-coder-next:latest | natural-unguided | 5 | 75% | 40% | 40% | 80% | 80% | ✅ | 80.0s |
| qwen3-coder-next:latest | structured-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 68.6s |
| qwen3-coder-next:latest | structured-unguided | 5 | 35% | ❌ | ❌ | 20% | 20% | ✅ | 44.4s |
| gpt-oss:20b | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 57.4s |
| gpt-oss:20b | natural-unguided | 5 | 65% | 40% | 40% | 60% | 60% | ✅ | 21.0s |
| gpt-oss:20b | structured-guided | 5 | 90% | 60% | 60% | ✅ | ✅ | ✅ | 42.5s |
| gpt-oss:20b | structured-unguided | 5 | 75% | 40% | 40% | 80% | 80% | ✅ | 20.7s |
| ministral-3:14b-instruct-2512-fp16 | natural-guided | 5 | 50% | ❌ | 20% | 20% | 60% | ✅ | 107.4s |
| ministral-3:14b-instruct-2512-fp16 | natural-unguided | 5 | 45% | ❌ | ❌ | 40% | 40% | ✅ | 80.4s |
| ministral-3:14b-instruct-2512-fp16 | structured-guided | 5 | 70% | 20% | 20% | 60% | ✅ | ✅ | 173.7s |
| ministral-3:14b-instruct-2512-fp16 | structured-unguided | 5 | 45% | ❌ | ❌ | 40% | 40% | ✅ | 75.0s |
| ministral-3:14b | natural-guided | 5 | 55% | 20% | 40% | 40% | 40% | ✅ | 58.2s |
| ministral-3:14b | natural-unguided | 5 | 45% | ❌ | ❌ | 40% | 40% | ✅ | 82.8s |
| ministral-3:14b | structured-guided | 5 | 70% | 20% | 20% | 80% | 80% | ✅ | 65.0s |
| ministral-3:14b | structured-unguided | 5 | 45% | ❌ | ❌ | 40% | 40% | ✅ | 52.9s |

**8/28** models completed the bootstrap perfectly in every run.

<details><summary>Column legend</summary>

| Column | Meaning |
|--------|---------|
| **Variant** | Prompt variant: *natural-guided*, *natural-unguided*, *structured-guided*, or *structured-unguided* |
| **Runs** | Number of independent runs (each from a fresh environment) |
| **Avg Score** | Average percentage of checks passed across all runs |
| **Perfect** | Fraction of runs where all 4 checks passed (✅ = 100%) |
| **BOOTSTRAP** | Rate at which `BOOTSTRAP.md` was deleted |
| **IDENTITY** | Rate at which `IDENTITY.md` has real Name, Creature, Vibe, Emoji |
| **USER** | Rate at which `USER.md` has real Name, Timezone |
| **SOUL** | Rate at which `SOUL.md` was personalised beyond the template |
| **Avg Duration** | Average wall-clock time for the bootstrap conversation |

</details>
