# Moltbook Agent 🤖

An autonomous AI agent that lives on **[Moltbook](https://www.moltbook.com)** — the social network built exclusively for AI agents.

The agent uses **Claude (Anthropic)** as its reasoning model, deploys on **Google Cloud Run**, and is triggered every 5 minutes via **Cloud Scheduler**.

---

## Architecture

```
Cloud Scheduler (every 5 min)
        │
        ▼  POST /heartbeat
  Cloud Run (FastAPI)
        │
        ├── brain.py           → generates responses with Claude
        ├── memory.py          → persists state in Firestore
        ├── moltbook_client.py → Moltbook API client
        └── register.py        → registers the agent on startup
```

**Secrets** (API keys) are stored in **Secret Manager** — never in the code.

---

## Project structure

```
moltbook-agent/
├── agent/
│   ├── main.py             # FastAPI app (/health and /heartbeat endpoints)
│   ├── heartbeat.py        # Main logic of the agent cycle
│   ├── brain.py            # Claude (Anthropic) integration
│   ├── memory.py           # Firestore persistence
│   ├── moltbook_client.py  # Moltbook HTTP API client
│   ├── register.py         # Auto-registration on Moltbook at startup
│   ├── config.py           # Configuration via environment variables
│   ├── Dockerfile
│   └── requirements.txt
├── deploy.sh               # GCP deployment script (Cloud Run)
├── deploy.env.example      # Deployment configuration template
└── README.md
```

---

## Environment variables

### For local development — create `agent/.env`

```dotenv
MOLTBOOK_API_KEY=your_moltbook_api_key
MOLTBOOK_BASE_URL=https://www.moltbook.com/api/v1
ANTHROPIC_API_KEY=your_anthropic_api_key

AGENT_NAME=MyAgent
AGENT_DESCRIPTION="An AI agent on Moltbook"
TARGET_SUBMOLTS=general,agents,aitools

GCP_PROJECT_ID=your-gcp-project   # optional for local development
```

> ⚠️ **Never commit `.env` to the repository.** It is included in `.gitignore`.

### For deployment — create `deploy.env` from the template

```bash
cp deploy.env.example deploy.env
# Edit deploy.env with your values
```

API keys (`MOLTBOOK_API_KEY`, `ANTHROPIC_API_KEY`) **do not go in `deploy.env`** — they are managed via Secret Manager.

---

## Deploying to GCP

### Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and authenticated
- GCP project with billing enabled
- [Moltbook](https://www.moltbook.com) account with an API key

### Step by step

```bash
# 1. Set up your deploy.env
cp deploy.env.example deploy.env
# edit with your GCP_PROJECT_ID, REGION, AGENT_NAME, etc.

# 2. Deploy (builds image, creates Cloud Run service, sets up Scheduler)
./deploy.sh

# 3. Update the secrets in Secret Manager with your real API keys
#    https://console.cloud.google.com/security/secret-manager
```

The `deploy.sh` script takes care of:
1. Enabling the required GCP APIs
2. Creating the Service Account with least-privilege permissions
3. Creating the Artifact Registry repository
4. Creating empty secrets in Secret Manager (you fill them in)
5. Building and pushing the Docker image via Cloud Build
6. Deploying the service to Cloud Run
7. Setting up Cloud Scheduler for the heartbeat every 5 minutes

---

## Local development

```bash
cd agent

# Create and activate the virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create your .env (see environment variables section above)
cp ../.env.example .env   # or create it manually

# Start the server
uvicorn main:app --reload --port 8080
```

Available endpoints:
- `GET  /health` — service health check
- `POST /heartbeat` — triggers a full agent cycle

---

## Security

| Secret | Where it's stored |
|---|---|
| `MOLTBOOK_API_KEY` | GCP Secret Manager |
| `ANTHROPIC_API_KEY` | GCP Secret Manager |
| `GCP_PROJECT_ID` | `deploy.env` (local only, in `.gitignore`) |

The Cloud Run service runs with **`--no-allow-unauthenticated`** — only Cloud Scheduler (via OIDC) can invoke it.
