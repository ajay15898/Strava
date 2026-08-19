# Coach layer (M5 — not built)

The coach is provider-agnostic by construction: any OpenAI-compatible
chat-completions endpoint, selected by three environment variables.

```
COACH_BASE_URL   e.g. https://api.groq.com/openai/v1
COACH_MODEL      e.g. openai/gpt-oss-120b
COACH_API_KEY
```

Switching provider is a config change, never a code change.

## Why a free tier is adequate here

The coach never computes anything. It receives a `CoachContext` that has already
been computed and validated, and `verify.py` rejects any numeric token in the
output that isn't in that context. So the model's job is fluent summarisation of
supplied facts, not reasoning — a bar that free 70B-class models clear.

Two consequences worth designing around:

**The templated fallback is a normal code path, not an edge case.** Weaker
models trip the verifier more often. Build the deterministic summary first and
treat a rejection as routine.

**Budget two API calls per user message.** The verifier retries once with the
violation named before falling back, which halves the effective rate limit.

## Choosing a provider

Reference list: https://github.com/mnfst/awesome-free-llm-apis — community
maintained, so confirm limits at signup rather than trusting the table.

Model names churn. `llama-3.3-70b-versatile` was Groq's headline model when
this was written and had been retired by the time the key was first used, so
the call failed with a 404 naming the missing model. Query `GET /v1/models`
against the provider before trusting any model id, including this one.

The differentiator for this project is **privacy, not quota**. This is personal
health data. Google Gemini and Mistral both state prompts may be used to improve
their models; OpenRouter notes free providers may log prompts for training.
Groq, Cloudflare and SambaNova state no training policy in that list — which is
not the same as a commitment not to.

| Provider | Free tier | Note |
|---|---|---|
| **Groq** (default) | 30 RPM / 1,000 RPD | No card, fast SSE streaming |
| Google Gemini | 1,500 RPD | Largest quota; trains on prompts |
| Cloudflare Workers AI | 10k neurons/day | Good if deploying on Cloudflare |
| SambaNova | 20 RPD | Too low for interactive use |
| Cerebras | — | Requires a credit card |
| Ollama Cloud | — | Not OpenAI-compatible; breaks the abstraction |

One person chatting will not approach even the smallest of these limits; a
runaway retry loop would. Rate-limit at the application layer regardless.

## Still to build

- `context.py` — build `CoachContext` from the analytics layer
- `prompt.py` — system prompt stating the numeric-grounding contract
- `verify.py` — extract every numeric token, assert membership, retry once,
  then fall back to a deterministic template
- `service.py` — streaming client, persist the context snapshot with every
  message so past answers stay re-verifiable
