# Kachieng AI Agent

> Climate-smart advisories. Extension officers decide.

MajiShamba Extension Agent is a human-in-the-loop Django + LangGraph platform that helps agricultural extension officers create evidence-based, climate-smart advisories for farmers in Kachieng Ward, Nyatike Sub-County, Migori County, Kenya. It combines weather, pest, market, crop-calendar, and farm data through MCP tools, while ensuring every advisory is reviewed and approved by a qualified officer before follow-up actions are created.

## Prerequisites

- **Python 3.11+** — must be on PATH as `python` (Windows) or `python3` (Linux/macOS)
- **Git** — to clone the repository
- **`make`** — required on Linux/macOS/WSL/Git Bash. On Windows PowerShell, use `.\scripts\run_demo.ps1` instead (no `make` needed)

No database, API key, or external service is required for the demo. The application uses SQLite by default and falls back to a deterministic template generator when no LLM provider is configured.

## Quick start

### Linux / macOS / WSL / Git Bash

```bash
git clone https://github.com/Onunga123/majishamba-extension-agent.git
cd majishamba-extension-agent
make demo
```

### Windows PowerShell

```powershell
git clone https://github.com/Onunga123/majishamba-extension-agent.git
cd majishamba-extension-agent
.\scripts\run_demo.ps1
```

Both commands will:

1. Create a Python virtualenv at `.venv/` and install all dependencies
2. Apply database migrations (SQLite — no PostgreSQL or PostGIS needed)
3. Load synthetic Kachieng Ward fixtures (clusters, plots, weather, pest, and market data)
4. Seed 14 locality-based farmer clusters
5. Optionally start Ollama if installed (falls back to a deterministic template if not)
6. Start the Django development server on http://127.0.0.1:8000

## Create an account and log in

The setup scripts do not seed any user accounts. After the server is running, open a new terminal in the project directory and create an account:

```bash
# Activate the virtualenv first:
# Linux/macOS:  source .venv/bin/activate
# Windows:       .venv\Scripts\activate

python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
python manage.py changepassword jdoe
```

The account is created with an unusable password — login will fail until you run `changepassword`. The account is immediately approved (no admin review needed for accounts created via this command). Available roles: `extension_officer`, `supervisor`, `viewer`.

Then open http://127.0.0.1:8000/accounts/login/ and sign in.

## LLM provider (optional)

The demo works without any API key using a deterministic fallback. To enable AI-generated advisories, copy `.env.example` to `.env` and configure one of the following:

| Provider | Setting | Requirement |
|----------|---------|-------------|
| OpenRouter (cloud) | `LLM_PROVIDER=openrouter` | API key from [openrouter.ai](https://openrouter.ai/keys) |
| Ollama (local) | `LLM_PROVIDER=ollama` | [Ollama](https://ollama.com) installed, `ollama pull qwen2.5:7b-instruct` |
| None (fallback) | `LLM_PROVIDER=none` | No external service needed |

See `.env.example` for all configuration options. Provider failures never silently switch models — the advisory records the generation mode used (`llm_openrouter`, `llm_ollama`, or `fallback_template`).

## Key capabilities

- Evidence-based advisory generation from weather, pest, market, and crop-calendar data
- Human approval gate — no advisory reaches farmers without officer review
- Role-based access control (Extension Officer, Supervisor, Viewer, System Administrator)
- Audit trail for every tool call, approval decision, and task creation
- 14 Kachieng Ward farmer clusters with synthetic demo data
- Custom MCP server with 8 tools (6 read-only, 2 action — all audit-logged)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python: command not found` | Install Python 3.11+ and ensure it is on PATH |
| `pip install failed` | Run `python -m pip install --upgrade pip`, then retry |
| `make: command not found` | Use `.\scripts\run_demo.ps1` on Windows, or install `make` on macOS/Linux |
| Port 8000 already in use | Run `python manage.py runserver 8001` after setup |
| Migration warning about model changes | Run `python manage.py makemigrations --dry-run` to inspect what changed; if the warning is about a `help_text` or `max_length` field change, run `makemigrations` then `migrate` to apply the schema update. Do not ignore the warning — the model and migration must stay in sync. |

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system architecture overview
- [EVALS.md](EVALS.md) — evaluation plan with 14 evaluation tasks
- [docs/governance/human_approval_policy.md](docs/governance/human_approval_policy.md) — human approval gate policy
- [docs/governance/synthetic_data_notice.md](docs/governance/synthetic_data_notice.md) — synthetic data statement
- [docs/operations/developer_setup.md](docs/operations/developer_setup.md) — detailed developer setup guide

## Contributing

Issues and pull requests welcome. All contributions must keep the human-in-the-loop invariant: no automated outbound messages, no auto-approval, no auto-task creation.

## Licence

MIT — see [LICENSE](LICENSE).
