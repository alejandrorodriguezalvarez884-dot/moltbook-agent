#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Carga configuración desde deploy.env si existe
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/deploy.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Configuración (override con variables de entorno)
# ─────────────────────────────────────────────────────────────────────────────
GCP_PROJECT_ID="${GCP_PROJECT_ID:?Pon GCP_PROJECT_ID en deploy.env}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="moltbook-agent"
AR_REPO="moltbook"
IMAGE="$REGION-docker.pkg.dev/$GCP_PROJECT_ID/$AR_REPO/$SERVICE_NAME"
SA_NAME="moltbook-agent-sa"
SA_EMAIL="$SA_NAME@$GCP_PROJECT_ID.iam.gserviceaccount.com"
SCHEDULER_JOB="moltbook-heartbeat"

AGENT_NAME="${AGENT_NAME:-MoltAgent}"
AGENT_DESCRIPTION="${AGENT_DESCRIPTION:-An AI agent exploring ideas on Moltbook}"
TARGET_SUBMOLTS="${TARGET_SUBMOLTS:-general,agents,aitools}"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
info()    { echo "▶ $*"; }
success() { echo "  ✓ $*"; }
warn()    { echo "  ⚠️  $*"; }

gcloud_quiet() { gcloud "$@" --project "$GCP_PROJECT_ID" --quiet; }

# ─────────────────────────────────────────────────────────────────────────────
# 1. APIs
# ─────────────────────────────────────────────────────────────────────────────
info "Habilitando APIs de GCP..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project "$GCP_PROJECT_ID"
success "APIs habilitadas"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Service Account
# ─────────────────────────────────────────────────────────────────────────────
info "Configurando service account..."
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project "$GCP_PROJECT_ID" &>/dev/null; then
  gcloud_quiet iam service-accounts create "$SA_NAME" \
    --display-name="Moltbook Agent SA"
fi

for role in \
  roles/datastore.user \
  roles/secretmanager.secretAccessor \
  roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$role" \
    --quiet 2>/dev/null
done
success "Service account: $SA_EMAIL"

# ─────────────────────────────────────────────────────────────────────────────
# 3. Artifact Registry
# ─────────────────────────────────────────────────────────────────────────────
info "Configurando Artifact Registry..."
if ! gcloud artifacts repositories describe "$AR_REPO" \
  --location="$REGION" --project "$GCP_PROJECT_ID" &>/dev/null; then
  gcloud_quiet artifacts repositories create "$AR_REPO" \
    --repository-format=docker \
    --location="$REGION"
fi
gcloud_quiet auth configure-docker "$REGION-docker.pkg.dev"
success "Repositorio: $AR_REPO"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Secrets (crea vacíos si no existen — el usuario los rellena después)
# ─────────────────────────────────────────────────────────────────────────────
info "Verificando secrets en Secret Manager..."
for secret in MOLTBOOK_API_KEY ANTHROPIC_API_KEY; do
  if ! gcloud secrets describe "$secret" --project "$GCP_PROJECT_ID" &>/dev/null; then
    echo -n "placeholder" | gcloud secrets create "$secret" \
      --data-file=- \
      --project "$GCP_PROJECT_ID" \
      --quiet
    warn "Secret '$secret' creado con valor placeholder. Actualízalo en:"
    warn "  https://console.cloud.google.com/security/secret-manager?project=$GCP_PROJECT_ID"
  else
    success "Secret '$secret' ya existe"
  fi
done

# ─────────────────────────────────────────────────────────────────────────────
# 5. Build y Push de la imagen
# ─────────────────────────────────────────────────────────────────────────────
info "Construyendo imagen con Cloud Build..."
gcloud_quiet builds submit "$SCRIPT_DIR/agent" --tag "$IMAGE"
success "Imagen: $IMAGE"

# ─────────────────────────────────────────────────────────────────────────────
# 6. Deploy en Cloud Run
# ─────────────────────────────────────────────────────────────────────────────
info "Desplegando en Cloud Run..."

# Escribimos un YAML temporal para las env vars porque TARGET_SUBMOLTS
# contiene comas que gcloud --set-env-vars interpreta como separadores.
ENV_VARS_FILE=$(mktemp /tmp/cloudrun-env-XXXXXX.yaml)
trap 'rm -f "$ENV_VARS_FILE"' EXIT
cat > "$ENV_VARS_FILE" <<YAML
AGENT_NAME: "${AGENT_NAME}"
AGENT_DESCRIPTION: "${AGENT_DESCRIPTION}"
TARGET_SUBMOLTS: "${TARGET_SUBMOLTS}"
GCP_PROJECT_ID: "${GCP_PROJECT_ID}"
YAML

gcloud_quiet run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 120s \
  --set-secrets "MOLTBOOK_API_KEY=MOLTBOOK_API_KEY:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --env-vars-file "$ENV_VARS_FILE"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$GCP_PROJECT_ID" \
  --format "value(status.url)")
success "Cloud Run URL: $SERVICE_URL"

# ─────────────────────────────────────────────────────────────────────────────
# 7. Permiso para que el SA invoque el servicio
# ─────────────────────────────────────────────────────────────────────────────
info "Configurando permisos de invocación..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region "$REGION" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/run.invoker" \
  --project "$GCP_PROJECT_ID" \
  --quiet
success "SA puede invocar el servicio"

# ─────────────────────────────────────────────────────────────────────────────
# 8. Cloud Scheduler (heartbeat cada 5 minutos)
# ─────────────────────────────────────────────────────────────────────────────
info "Configurando Cloud Scheduler (cada 5 min)..."
HEARTBEAT_URL="$SERVICE_URL/heartbeat"
SCHEDULER_ARGS=(
  http "$SCHEDULER_JOB"
  --location "$REGION"
  --schedule "*/5 * * * *"
  --uri "$HEARTBEAT_URL"
  --http-method POST
  --oidc-service-account-email "$SA_EMAIL"
  --oidc-token-audience "$SERVICE_URL"
  --project "$GCP_PROJECT_ID"
  --quiet
)

if gcloud scheduler jobs describe "$SCHEDULER_JOB" \
  --location "$REGION" --project "$GCP_PROJECT_ID" &>/dev/null; then
  gcloud scheduler jobs update "${SCHEDULER_ARGS[@]}"
  success "Scheduler actualizado"
else
  gcloud scheduler jobs create "${SCHEDULER_ARGS[@]}"
  success "Scheduler creado"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Resumen
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅  Deploy completado"
echo "    Service URL : $SERVICE_URL"
echo "    Health check: curl -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' $SERVICE_URL/health"
echo "    Heartbeat   : cada 5 min via Cloud Scheduler"
echo ""
echo "⚠️  Pasos pendientes antes de que el agente funcione:"
echo "   1. Actualiza MOLTBOOK_API_KEY en Secret Manager:"
echo "      https://console.cloud.google.com/security/secret-manager?project=$GCP_PROJECT_ID"
echo "   2. Actualiza ANTHROPIC_API_KEY en Secret Manager"
echo "   3. Asegúrate de que Firestore está en modo NATIVE (no Datastore):"
echo "      https://console.cloud.google.com/firestore?project=$GCP_PROJECT_ID"
echo "   4. Redespliega si acabas de actualizar los secrets:"
echo "      gcloud run deploy $SERVICE_NAME --image $IMAGE --region $REGION --project $GCP_PROJECT_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
