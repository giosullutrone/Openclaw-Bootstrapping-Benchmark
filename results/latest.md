### Latest results

> Ran on **2026-02-16 14:01 UTC** against a local [Ollama](https://ollama.com/) server (5 runs per model, averaged) · OpenClaw **2026.2.15**.

| Model | Variant | Runs | Avg Score | Perfect | BOOTSTRAP | IDENTITY | USER | SOUL | Avg Duration |
|-------|---------|:----:|:---------:|:-------:|:---------:|:--------:|:----:|:----:|-------------:|
| glm-4.7-flash:bf16 | natural-guided | 5 | 85% | 60% | 80% | 80% | 80% | ✅ | 69.6s |
| glm-4.7-flash:bf16 | natural-unguided | 5 | 80% | 20% | 20% | ✅ | ✅ | ✅ | 76.8s |
| glm-4.7-flash:bf16 | structured-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 69.8s |
| glm-4.7-flash:bf16 | structured-unguided | 5 | 75% | 40% | 40% | 80% | 80% | ✅ | 70.7s |
| glm-4.7-flash:latest | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 65.3s |
| glm-4.7-flash:latest | natural-unguided | 5 | 85% | 80% | 80% | 80% | 80% | ✅ | 64.1s |
| glm-4.7-flash:latest | structured-guided | 5 | 85% | 60% | 60% | ✅ | 80% | ✅ | 58.1s |
| glm-4.7-flash:latest | structured-unguided | 5 | 75% | 40% | 40% | 80% | 80% | ✅ | 57.9s |
| qwen3-coder-next:q8_0 | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 70.5s |
| qwen3-coder-next:q8_0 | natural-unguided | 5 | 70% | 20% | 20% | 80% | 80% | ✅ | 55.4s |
| qwen3-coder-next:q8_0 | structured-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 72.8s |
| qwen3-coder-next:q8_0 | structured-unguided | 5 | 25% | ❌ | ❌ | ❌ | ❌ | ✅ | 35.8s |
| qwen3-coder-next:latest | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 66.0s |
| qwen3-coder-next:latest | natural-unguided | 5 | 60% | 20% | 20% | 60% | 60% | ✅ | 53.3s |
| qwen3-coder-next:latest | structured-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 77.7s |
| qwen3-coder-next:latest | structured-unguided | 5 | 25% | ❌ | ❌ | ❌ | ❌ | ✅ | 33.6s |
| gpt-oss:20b | natural-guided | 5 | 100% | ✅ | ✅ | ✅ | ✅ | ✅ | 42.8s |
| gpt-oss:20b | natural-unguided | 5 | 85% | 40% | 40% | ✅ | ✅ | ✅ | 34.2s |
| gpt-oss:20b | structured-guided | 5 | 95% | 80% | 80% | ✅ | ✅ | ✅ | 53.4s |
| gpt-oss:20b | structured-unguided | 5 | 80% | 20% | 20% | ✅ | ✅ | ✅ | 26.5s |

**7/20** models completed the bootstrap perfectly in every run.

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
