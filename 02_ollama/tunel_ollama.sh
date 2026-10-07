#!/bin/bash
# =============================================================================
# Expone Ollama (localhost:11434) con ngrok para que la app web lo alcance.
# Uso (terminal de Jupyter en SageMaker):
#   export NGROK_AUTHTOKEN=xxxx            # NUNCA lo subas al repositorio
#   export NGROK_DOMAIN=tu-dominio.ngrok-free.app   # dominio estático gratis (dashboard de ngrok)
#   bash 02_ollama/tunel_ollama.sh
# =============================================================================
set -e
BIN=/home/ec2-user/SageMaker/bin
mkdir -p "$BIN"
if [ ! -x "$BIN/ngrok" ]; then
  curl -sSLo /tmp/ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
  tar -xzf /tmp/ngrok.tgz -C "$BIN"
fi
"$BIN/ngrok" config add-authtoken "$NGROK_AUTHTOKEN"

# --host-header es necesario: Ollama solo acepta peticiones dirigidas a localhost
ARGS="http 11434 --host-header=localhost:11434 --log=stdout"
[ -n "$NGROK_DOMAIN" ] && ARGS="$ARGS --url=$NGROK_DOMAIN"
nohup "$BIN/ngrok" $ARGS > /home/ec2-user/SageMaker/ngrok.log 2>&1 &
sleep 4
grep -o 'url=https://[^ ]*' /home/ec2-user/SageMaker/ngrok.log | head -1
echo "Prueba desde tu PC:  curl https://<url>/api/version"
