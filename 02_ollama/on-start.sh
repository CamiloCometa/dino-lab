#!/bin/bash
# =============================================================================
# Lifecycle configuration (on-start) para el notebook de SageMaker.
# SageMaker falla si el lifecycle (o cualquier proceso que deje corriendo) tarda
# más de 5 minutos. Además, reiniciar Docker durante el arranque se bloquea hasta
# que el lifecycle termina. Por eso este script:
#   - escribe un script auxiliar,
#   - lo lanza como un servicio APARTE con systemd-run (fuera del lifecycle),
#   - y termina al instante.
# El servicio, en cada arranque:
#   1) apunta el data-root de Docker al disco persistente (/home/ec2-user/SageMaker)
#   2) arranca el contenedor de Ollama (imagen y modelos sobreviven a los reinicios)
# Registro: /home/ec2-user/SageMaker/on-start.log
# Pégalo en: SageMaker > Configuraciones de ciclo de vida > Instancia de cuaderno > Iniciar cuaderno
# =============================================================================
cat > /usr/local/bin/dino-onstart.sh <<'SCRIPT'
#!/bin/bash
PERSIST=/home/ec2-user/SageMaker
DOCKER_ROOT=$PERSIST/docker-data      # imágenes y contenedores de Docker
OLLAMA_DIR=$PERSIST/ollama            # modelos descargados por Ollama
exec >> "$PERSIST/on-start.log" 2>&1
mkdir -p "$DOCKER_ROOT" "$OLLAMA_DIR"
echo "== $(date) inicio"

# 1. data-root persistente (se fusiona con la config existente, no se pisa)
python3 - "$DOCKER_ROOT" <<'PY'
import json, os, sys
p = "/etc/docker/daemon.json"
os.makedirs("/etc/docker", exist_ok=True)
cfg = {}
if os.path.exists(p) and os.path.getsize(p) > 0:
    try:
        cfg = json.load(open(p))
    except Exception:
        cfg = {}
cfg["data-root"] = sys.argv[1]
json.dump(cfg, open(p, "w"), indent=2)
PY

# --no-block: encola el reinicio y no se queda esperando (evita el bloqueo)
systemctl restart docker --no-block
echo "Esperando a Docker con el nuevo data-root..."
for i in $(seq 1 120); do
  if docker info --format '{{.DockerRootDir}}' 2>/dev/null | grep -q "^$DOCKER_ROOT$"; then
    break
  fi
  sleep 5
done
usermod -aG docker ec2-user || true
echo "Docker data-root: $(docker info --format '{{.DockerRootDir}}')"

# 2. Contenedor de Ollama
if docker ps -a --format '{{.Names}}' | grep -q '^ollama$'; then
  docker start ollama
else
  docker run -d --name ollama --restart unless-stopped \
    -p 127.0.0.1:11434:11434 \
    -v "$OLLAMA_DIR":/root/.ollama \
    -e OLLAMA_KEEP_ALIVE=30m \
    ollama/ollama:latest
fi
echo "== $(date) fin"
SCRIPT
chmod +x /usr/local/bin/dino-onstart.sh

# Servicio aparte: el lifecycle no lo espera y termina de inmediato
systemd-run --unit="dino-onstart-$(date +%s)" --no-block /usr/local/bin/dino-onstart.sh
exit 0
