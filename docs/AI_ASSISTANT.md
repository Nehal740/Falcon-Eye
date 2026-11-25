# AI assistant: connect a language model

The assistant works without any setup: it then shows the most relevant parts of these guides and says so. Add a language model and it writes full answers in plain language.

What the assistant can and cannot do:
- It can **explain**: how to connect an agent, why an action was blocked, how to write a rule.
- It **cannot act**: it cannot change policies, approve requests or read passwords or keys.
- Your key stays on the server in `.env`. It is never sent to the browser.
- What is sent to the model: your question, short excerpts of these guides, a summary of your workspace (names of agents and policies) and, if you paste an event id, that event's record. Free plans of some providers may use this to improve their models, so do not paste secrets or real customer data.

## Quick setup (3 steps)
1. Create a key at your provider (examples below).
2. Put these four lines in `.env`, then restart the backend (`docker compose up -d --force-recreate backend`):
   ```
   LLM_PROVIDER=openai
   LLM_BASE_URL=<address from the table>
   LLM_MODEL=<model name>
   LLM_API_KEY=<your key>
   ```
3. Check it: run `python scripts/check_llm.py`, or open **Settings > AI assistant > Test AI connection** in the app (administrators). The check lists the models your key can use and tells you what to change.

`LLM_PROVIDER=openai` means "speaks the OpenAI format", which most providers do. Use `anthropic` for Claude.

## Provider settings
Model names change often. **Do not copy a model name from a guide: run the check and use a name from its list.**

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | Notes |
|---|---|---|---|
| Google Gemini | `openai` | `https://generativelanguage.googleapis.com/v1beta/openai` | Key from Google AI Studio. Free tier available. Pick a "flash" model. |
| Groq | `openai` | `https://api.groq.com/openai/v1` | Key from the Groq console. Fast, with a free tier. |
| OpenRouter | `openai` | `https://openrouter.ai/api/v1` | One key, many models, some marked free. |
| OpenAI | `openai` | leave empty | Paid. |
| Anthropic (Claude) | `anthropic` | leave empty | Paid. |
| Ollama (runs on your own computer, no data leaves it) | `openai` | `http://localhost:11434/v1` (from Docker: `http://host.docker.internal:11434/v1`) | Set `LLM_API_KEY=ollama` (any text). Needs a computer able to run the model. |

## If it does not work
Run `python scripts/check_llm.py`. The "Reason" line says why:

| Message | What to do |
|---|---|
| the API key was rejected (HTTP 401/403) | Create a new key; check there are no spaces or quotes around it in `.env`. |
| the model name or service address is not valid (HTTP 404) | Set `LLM_MODEL` to a name from the printed list; check `LLM_BASE_URL`. |
| the service did not accept the request (HTTP 400) | Usually a wrong model name. Use one from the list. |
| the usage limit was reached (HTTP 429) | Wait a minute, or use another provider. |
| the model ran out of room before answering | Raise `LLM_MAX_TOKENS` (for example 3000) or choose a faster model. |
| could not be reached / took too long | Check the internet connection and `LLM_BASE_URL`. |

Docker note: `.env` is read when the container starts, so after any change run `docker compose up -d --force-recreate backend`. A hidden mistake to check: the same `LLM_*` line twice in `.env`, where the last one wins.
