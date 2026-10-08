#!/bin/bash
# =============================================================================
# Lifecycle configuration (on-start) para el notebook de SageMaker.
# SageMaker cancela la instancia si este script tarda más de 5 minutos, así que
# solo escribe un script auxiliar y lo lanza en SEGUNDO PLANO; termina al instante.
# El trabajo real (cada vez que la instancia arranca):
#   1) apunta el data-root de Docker al disco persistente (/home/ec2-user/SageMaker)
#   2) arranca el contenedor de Ollama (imagen y modelos sobreviven a los reinicios)
# Registro: /home/ec2-user/SageMaker/on-start.log
# Pégalo en: SageMaker > Configuraciones de ciclo de vida > Instancia de cuaderno > Iniciar cuaderno
# =============================================================================
PERSIST=/home/ec2-user/SageMaker
mkdir -p "$PERSIST"

cat > /usr/local/bin/dino-onstart.sh <<'SCRIPT'
#!/bin/bash
PERSIST=/home/ec2-user/SageMaker
DOCKER_ROOT=$PERSIST/docker-data      # imágenes y contenedores de Docker
OLLAMA_DIR=$PERSIST/ollama            # modelos descargados por Ollama
mkdir -p "$DOCKER_ROOT" "$OLLAMA_DIR"
echo "== $(date) inicio"

# 0. Docker instalado
if ! command -v docker >/dev/null 2>&1; then
  echo "Instalando Docker..."
  dnf install -y docker || yum install -y docker
fi

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
systemctl enable docker
systemctl restart docker
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

# Lanzar desacoplado: sin heredar la salida del lifecycle, para que AWS no lo espere
setsid nohup /usr/local/bin/dino-onstart.sh >> "$PERSIST/on-start.log" 2>&1 < /dev/null &
disown
exit 0
