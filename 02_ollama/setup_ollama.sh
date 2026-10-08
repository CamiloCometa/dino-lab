#!/bin/bash
# =============================================================================
# Primera instalación (se ejecuta UNA vez desde la terminal de Jupyter):
#   bash 02_ollama/setup_ollama.sh
# Aplica la misma configuración del on-start, descarga el modelo y registra versiones.
# =============================================================================
set -e
MODELO=${OLLAMA_MODEL:-llama3.2:3b}
PERSIST=/home/ec2-user/SageMaker
DIR=$(cd "$(dirname "$0")" && pwd)

echo ">> Aplicando on-start (data-root persistente + contenedor)"
sudo bash "$DIR/on-start.sh"

echo ">> Esperando a que Ollama responda (la primera vez descarga la imagen, hasta 10 min)..."
for i in $(seq 1 120); do
  curl -s http://localhost:11434/api/version && break
  sleep 5
done
echo

echo ">> Registro del arranque:"; tail -n 5 "$PERSIST/on-start.log"
echo ">> Docker data-root:"; sudo docker info --format '{{.DockerRootDir}}'

echo ">> Descargando $MODELO (puede tardar unos minutos)"
sudo docker exec ollama ollama pull "$MODELO"

echo ">> Registro de versiones"
{
  echo "fecha: $(date -Iseconds)"
  echo "instancia: m5.xlarge (4 vCPU, 16 GiB, sin GPU)"
  echo "docker: $(sudo docker --version)"
  echo "ollama: $(sudo docker exec ollama ollama --version)"
  echo "modelo: $MODELO"
  sudo docker exec ollama ollama list
  sudo docker exec ollama ollama show "$MODELO"
} | tee "$PERSIST/registro_modelo.txt"

echo ">> Prueba rápida"
curl -s http://localhost:11434/api/generate \
  -d "{\"model\":\"$MODELO\",\"prompt\":\"Di hola en una frase.\",\"stream\":false}" | python3 -m json.tool | head -20
