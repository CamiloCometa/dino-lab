"""
char_model.py
Modelo de lenguaje a nivel de caracteres (RNN / LSTM / GRU) + muestreo.
Lo usan el notebook de entrenamiento (01_generador_nombres) y la app web (04_app).
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

PAD, SOS, EOS = "<PAD>", "<SOS>", "<EOS>"


class CharRNN(nn.Module):
    """Embedding -> celda recurrente (rnn | lstm | gru) -> capa lineal sobre el vocabulario."""

    def __init__(self, vocab_size, emb_dim=32, hidden_size=128, num_layers=1,
                 cell="gru", dropout=0.0, pad_idx=0):
        super().__init__()
        celdas = {"rnn": nn.RNN, "lstm": nn.LSTM, "gru": nn.GRU}
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=pad_idx)
        self.rnn = celdas[cell.lower()](
            emb_dim, hidden_size, num_layers=num_layers, batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_size, vocab_size)

    def forward(self, x, h=None):
        # x: (batch, T) indices -> logits: (batch, T, vocab)
        salida, h = self.rnn(self.emb(x), h)
        return self.fc(salida), h


def filtrar_logits(logits, temperatura=1.0, top_k=0, top_p=1.0):
    """Aplica temperatura, top-k y top-p a un vector de logits (1D)."""
    logits = logits / max(float(temperatura), 1e-6)

    if top_k and top_k > 0:
        k = min(int(top_k), logits.size(-1))
        umbral = torch.topk(logits, k).values[-1]
        logits = logits.masked_fill(logits < umbral, float("-inf"))

    if top_p is not None and top_p < 1.0:
        ordenados, idx = torch.sort(logits, descending=True)
        probs = F.softmax(ordenados, dim=-1)
        acumulada_previa = probs.cumsum(-1) - probs
        # se quitan los caracteres que aparecen DESPUÉS de alcanzar p
        ordenados = ordenados.masked_fill(acumulada_previa >= top_p, float("-inf"))
        logits = torch.full_like(logits, float("-inf")).scatter(0, idx, ordenados)

    return logits


@torch.no_grad()
def generar_nombre(modelo, stoi, itos, max_len=30, temperatura=1.0, top_k=0,
                   top_p=1.0, device="cpu"):
    """Generación autoregresiva: cada carácter muestreado es la entrada del siguiente paso."""
    modelo.eval()
    x = torch.tensor([[stoi[SOS]]], device=device)
    h, chars = None, []
    for _ in range(max_len):
        logits, h = modelo(x, h)
        logits = logits[0, -1].clone()
        logits[stoi[PAD]] = float("-inf")   # nunca generar PAD ni SOS
        logits[stoi[SOS]] = float("-inf")
        logits = filtrar_logits(logits, temperatura, top_k, top_p)
        idx = torch.multinomial(F.softmax(logits, dim=-1), 1).item()
        if idx == stoi[EOS]:
            break
        chars.append(itos[idx])
        x = torch.tensor([[idx]], device=device)
    return "".join(chars)


def cargar_checkpoint(ruta, device="cpu"):
    """Carga el archivo dino_rnn.pt exportado por el notebook."""
    ck = torch.load(ruta, map_location=device, weights_only=False)
    cfg = ck["config"]
    modelo = CharRNN(
        vocab_size=len(ck["itos"]), emb_dim=cfg["emb"], hidden_size=cfg["oculto"],
        num_layers=cfg["capas"], cell=cfg["celda"], dropout=cfg.get("dropout", 0.0),
    ).to(device)
    modelo.load_state_dict(ck["state_dict"])
    modelo.eval()
    return modelo, ck
