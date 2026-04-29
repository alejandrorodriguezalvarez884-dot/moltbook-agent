# Moltbook Agent 🤖

Agente autónomo de IA que vive en **[Moltbook](https://www.moltbook.com)** — la red social construida exclusivamente para agentes de IA.

El agente usa **Claude (Anthropic)** como modelo de razonamiento, se despliega en **Google Cloud Run** y se activa cada 5 minutos mediante **Cloud Scheduler**.

---

## Arquitectura

```
Cloud Scheduler (cada 5 min)
        │
        ▼  POST /heartbeat
  Cloud Run (FastAPI)
        │
        ├── brain.py       → genera respuestas con Claude
        ├── memory.py      → persiste estado en Firestore
        ├── moltbook_client.py → API de Moltbook
        └── register.py    → registro del agente al arrancar
```

**Secrets** (API keys) se guardan en **Secret Manager** — nunca en el código.

---

## Estructura del proyecto

```
moltbook-agent/
├── agent/
│   ├── main.py             # FastAPI app (endpoints /health y /heartbeat)
│   ├── heartbeat.py        # Lógica principal del ciclo del agente
│   ├── brain.py            # Integración con Claude (Anthropic)
│   ├── memory.py           # Persistencia en Firestore
│   ├── moltbook_client.py  # Cliente HTTP de la API de Moltbook
│   ├── register.py         # Auto-registro del agente en Moltbook
│   ├── config.py           # Configuración via variables de entorno
│   ├── Dockerfile
│   └── requirements.txt
├── deploy.sh               # Script de despliegue en GCP (Cloud Run)
├── deploy.env.example      # Plantilla de configuración de despliegue
└── README.md
```

---

## Variables de entorno

### Para desarrollo local — crea `agent/.env`

```dotenv
MOLTBOOK_API_KEY=tu_api_key_de_moltbook
MOLTBOOK_BASE_URL=https://www.moltbook.com/api/v1
ANTHROPIC_API_KEY=tu_api_key_de_anthropic

AGENT_NAME=MiAgente
AGENT_DESCRIPTION="Un agente de IA en Moltbook"
TARGET_SUBMOLTS=general,agents,aitools

GCP_PROJECT_ID=tu-proyecto-gcp   # opcional en local
```

> ⚠️ **Nunca subas `.env` al repositorio.** Está incluido en `.gitignore`.

### Para despliegue — crea `deploy.env` a partir de la plantilla

```bash
cp deploy.env.example deploy.env
# Edita deploy.env con tus valores
```

Las API keys (`MOLTBOOK_API_KEY`, `ANTHROPIC_API_KEY`) **no van en `deploy.env`** — se gestionan en Secret Manager.

---

## Despliegue en GCP

### Pre-requisitos

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) instalado y autenticado
- Proyecto GCP con facturación activa
- Cuenta en [Moltbook](https://www.moltbook.com) con API key

### Paso a paso

```bash
# 1. Configura tu deploy.env
cp deploy.env.example deploy.env
# edita con tu GCP_PROJECT_ID, REGION, AGENT_NAME, etc.

# 2. Despliega (construye imagen, crea Cloud Run, configura Scheduler)
./deploy.sh

# 3. Actualiza los secrets en Secret Manager con tus API keys reales
#    https://console.cloud.google.com/security/secret-manager
```

El script `deploy.sh` se encarga de:
1. Habilitar las APIs necesarias de GCP
2. Crear la Service Account con los permisos mínimos
3. Crear el repositorio en Artifact Registry
4. Crear los secrets vacíos en Secret Manager (tú los rellenas)
5. Construir y publicar la imagen Docker via Cloud Build
6. Desplegar el servicio en Cloud Run
7. Configurar Cloud Scheduler para el heartbeat cada 5 min

---

## Desarrollo local

```bash
cd agent

# Crea y activa el entorno virtual
python -m venv .venv
source .venv/bin/activate

# Instala dependencias
pip install -r requirements.txt

# Crea tu .env (ver sección de variables de entorno)
cp ../.env.example .env   # o créalo manualmente

# Arranca el servidor
uvicorn main:app --reload --port 8080
```

Endpoints disponibles:
- `GET  /health` — estado del servicio
- `POST /heartbeat` — dispara un ciclo completo del agente

---

## Seguridad

| Secreto | Dónde se guarda |
|---|---|
| `MOLTBOOK_API_KEY` | GCP Secret Manager |
| `ANTHROPIC_API_KEY` | GCP Secret Manager |
| `GCP_PROJECT_ID` | `deploy.env` (local, en `.gitignore`) |

El servicio Cloud Run corre con **`--no-allow-unauthenticated`** — solo Cloud Scheduler (con OIDC) puede invocarlo.
