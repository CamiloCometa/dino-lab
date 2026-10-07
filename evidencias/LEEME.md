# Evidencias del generador de nombres

Coloca aquí lo que exporta el notebook `01_generador_nombres/generador_nombres.ipynb`:

| Archivo | Contenido |
| --- | --- |
| `configuraciones.csv` | Arquitectura, capas, estado oculto, épocas, pérdida, optimizador y métricas de las dos configuraciones |
| `curvas_perdida.png` | Curvas de pérdida de entrenamiento y validación |
| `historial_perdidas.json` | Valores de pérdida por época |
| `muestreo.csv` | Estrategias de muestreo (temperatura, top-k, top-p) con % nuevos, % únicos y ejemplos |
| `nombres_generados.json` | Los diez nombres nuevos y el elegido |
| `registro_modelo.txt` | Nombre y versión del modelo de Ollama (desde SageMaker) |
| `<nombre>.png` + `identidad_<nombre>.json` | Imagen e identidad del dinosaurio elegido |

## Análisis de los nombres
(Escribe aquí 1–2 párrafos: qué configuración generalizó mejor según la validación, cómo cambian los nombres con la temperatura, top-k y top-p, y por qué elegiste tu dinosaurio.)
