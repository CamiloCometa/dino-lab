# Isla de los Dinosaurios — Laboratorio II (PLN, 2026 S02)

Aplicación que crea un dinosaurio ficticio en cuatro etapas encadenadas:

```
Modelo de caracteres (RNN) → Nombre → Ollama → Identidad → Imagen (aMUSEd) → Chat
```

**Sitio web:** http://<IP-o-dominio-de-EC2>  ← reemplazar
**Repositorio:** https://github.com/CamiloCometa/dino-lab
**Integrantes:** Camilo Cometa, …

## Componentes

| Carpeta | Qué es | Dónde corre |
| --- | --- | --- |
| `01_generador_nombres/` | Notebook: preprocesamiento, 2 configuraciones RNN, curvas, muestreo, 10 nombres, exporta `dino_rnn.pt` | Google Colab |
| `02_ollama/` | Lifecycle script, instalación de Ollama en Docker, túnel ngrok y notebook de identidad | SageMaker `ml.m5.xlarge` |
| `03_imagen/` | Notebook: imagen con `amused/amused-512` + servicio HTTP `/generar` expuesto con Cloudflare | Google Colab (GPU T4) |
| `04_app/` | Backend FastAPI + interfaz web (carga el modelo RNN entrenado y el dinosaurio inicial de `04_app/inicial/`) | AWS EC2 (Docker) |
| `evidencias/` | Curvas, configuraciones, muestreo, nombres, registro del modelo de Ollama, imagen e identidad | — |

## Qué recibe y devuelve cada componente

**Modelo de caracteres** (dentro de `04_app`, archivo `char_model.py`)
- Recibe: token `<SOS>` y parámetros de muestreo (temperatura, top-k, top-p).
- Devuelve: un nombre (string) generado carácter a carácter; se descartan los que existen en `dinos.csv`.

**Ollama** (SageMaker, `POST {OLLAMA_URL}/api/chat`)
- Identidad — recibe: `{model, messages:[system, user:"Crea la identidad de <nombre>"], format:<esquema JSON>}`.
  Devuelve: JSON `{nombre, significado_nombre, apariencia, habitat, alimentacion, comportamiento, rasgo_distintivo, prompt_imagen}`.
- Chat — recibe: `{model, messages:[system:<identidad>, …historial, user:<mensaje>]}`. Devuelve: `{message:{content}}`.

**Servicio de imagen** (Colab)
- `GET /salud` → `{ok, modelo}`
- `POST /generar` recibe `{prompt, semilla, pasos}` → devuelve `{image_base64, mime, modelo, prompt}`.

**Backend de la app** (`04_app/app.py`)

| Endpoint | Recibe | Devuelve |
| --- | --- | --- |
| `GET /api/dinosaurios/inicial` | — | `{id, nombre, identidad, imagen, prompt}` del dinosaurio elegido en los pasos 1–3 |
| `POST /api/dinosaurios` | — | `{id, nombre}` (genera con la RNN, sin reentrenar) |
| `POST /api/dinosaurios/{id}/identidad` | — | `{identidad}` (llama a Ollama) |
| `POST /api/dinosaurios/{id}/imagen` | — | `{imagen (data URL), prompt}` (se genera una sola vez y se guarda) |
| `POST /api/dinosaurios/{id}/chat` | `{mensaje}` o `{presentar:true}` | `{respuesta, incluir_imagen}` |
| `GET /api/info` | — | arquitectura y métricas del modelo de nombres, modelo de Ollama |
| `GET /api/estado` | — | si Ollama y el servicio de imagen están accesibles |

Al abrir la página se muestra el dinosaurio elegido (**Sinornithomerus**): su nombre salió de la RNN, su identidad de Ollama y su imagen de aMUSEd, y están guardados en `04_app/inicial/` (copias de `evidencias/`). El botón **Nuevo dinosaurio** recorre el flujo completo en vivo para otro nombre.

La identidad se envía como mensaje `system` en **cada** petición de chat. `incluir_imagen` es `true` cuando el dinosaurio se presenta o el usuario pide su descripción/aspecto; la interfaz reutiliza la imagen ya guardada.

## Cómo ejecutar

1. **Nombres:** abrir `01_generador_nombres/generador_nombres.ipynb` en Colab, subir `dinos.csv`, ejecutar todo. Copiar `dino_rnn.pt` a `04_app/model/` y las evidencias a `evidencias/`.
2. **Ollama:** crear la instancia `ml.m5.xlarge` (volumen 30 GB, rol `LabRole`, acceso raíz habilitado) y la lifecycle configuration `dino-ollama-onstart`. **El script se carga desde CloudShell, no pegándolo en la consola web**: desde Windows el pegado mete saltos de línea `\r\n` y el script falla con `cannot execute: required file not found`.
   ```bash
   # En AWS CloudShell
   curl -sL https://raw.githubusercontent.com/CamiloCometa/dino-lab/main/02_ollama/on-start.sh | tr -d '\r' > on-start.sh
   aws sagemaker update-notebook-instance-lifecycle-config \
     --notebook-instance-lifecycle-config-name dino-ollama-onstart \
     --on-start Content=$(base64 -w0 on-start.sh)
   ```
   Primera vez, en la terminal de Jupyter: `bash 02_ollama/setup_ollama.sh` (descarga `llama3.2:3b`). Luego `identidad_ollama.ipynb`. Exponer Ollama: `NGROK_AUTHTOKEN=… NGROK_DOMAIN=… bash 02_ollama/tunel_ollama.sh`.
3. **Imagen:** abrir `03_imagen/imagen_colab.ipynb` en Colab con GPU y ejecutarlo. La celda del túnel imprime `IMAGEN_URL = https://….trycloudflare.com` (cambia en cada sesión de Colab).
4. **App local:**
   ```bash
   cd 04_app
   cp ../.env.example .env      # llenar OLLAMA_URL e IMAGEN_URL
   docker build -t dino-app .
   docker run --rm -p 8000:8000 --env-file .env dino-app
   # abrir http://localhost:8000  y revisar http://localhost:8000/api/estado
   ```
5. **Despliegue en AWS (EC2):** ver la sección siguiente.

## Despliegue en AWS (EC2)

```bash
# En una EC2 Amazon Linux 2023, t3.small, puerto 80 abierto en el security group
sudo dnf install -y docker git && sudo systemctl enable --now docker
git clone https://github.com/CamiloCometa/dino-lab.git && cd dino-lab/04_app
nano .env                       # OLLAMA_URL, OLLAMA_MODEL, IMAGEN_URL
sudo docker build -t dino-app .
sudo docker run -d --name dino-app --restart unless-stopped -p 80:8000 --env-file .env dino-app
```

## Seguridad

- Ningún token ni clave está en el repositorio. `.env` está en `.gitignore`; las credenciales de ngrok se pasan por variables de entorno (SageMaker) o Secretos de Colab.
- Las URLs de los túneles no se publican en el repositorio.
