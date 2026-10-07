#!/bin/bash
# =============================================================================
# Lifecycle configuration (on-start) para el notebook de SageMaker.
# Se ejecuta como root CADA vez que la instancia arranca:
#   1) apunta el data-root de Docker al disco persistente (/home/ec2-user/SageMaker)
#   2) arranca el contenedor de Ollama (imagen y modelos sobreviven a los reinicios)
# Pégalo en: SageMaker > Lifecycle configurations > Notebook instance > Start notebook
# =============================================================================
set -e

PERSIST=/home/ec2-user/SageMaker
DOCKER_ROOT=$PERSIST/docker-data      # imágenes y contenedores de Docker
OLLAMA_DIR=$PERSIST/ollama            # modelos descargados por Ollama
mkdir -p "$DOCKER_ROOT" "$OLLAMA_DIR"

# --- 1. data-root persistente (se fusiona con la config existente, no se pisa) ---
python3 - <<PY
import json, os
p = "/etc/docker/daemon.json"
cfg = {}
if os.path.exists(p) and os.path.getsize(p) > 0:
    cfg = json.load(open(p))
cfg["data-root"] = "$DOCKER_ROOT"
json.dump(cfg, open(p, "w"), indent=2)
PY
systemctl restart docker

# --- 2. Contenedor de Ollama (en segundo plano: el on-start tiene límite de 5 min) ---
nohup bash -c "
  if docker ps -a --format '{{.Names}}' | grep -q '^ollama$'; then
      docker start ollama
  else
      docker run -d --name ollama --restart unless-stopped \
        -p 127.0.0.1:11434:11434 \
        -v $OLLAMA_DIR:/root/.ollama \
        -e OLLAMA_KEEP_ALIVE=30m \
        ollama/ollama:latest
  fi
" > $PERSIST/ollama-start.log 2>&1 &

echo "on-start terminado: data-root=$DOCKER_ROOT"
