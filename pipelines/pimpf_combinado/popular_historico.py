"""
Pré-popula data/previsoes/historico.csv com as 12 últimas previsões
da janela de validação (origens jan/2024 a out/2025, h=2), a partir
do CSV do walk-forward GR rolling (gr_rolling_pesos.csv).

São registradas com tipo=validacao_historica, com realizado já
preenchido (são previsões walk-forward sobre meses já observados).

Rodar uma única vez na inicialização do pipeline.

Uso:
    python -m pipelines.pimpf_combinado.popular_historico
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

OUT     = ROOT / "data" / "previsoes" / "historico.csv"
GR_CSV  = ROOT / "validacao" / "portgdp_v2" / "gr_rolling_pesos.csv"
CONF_CSV = ROOT / "validacao" / "portgdp_v2" / "conformal_intervalos_teste.csv"

COLUNAS_HIST = [
    "data_emissao", "mes_alvo", "horizonte", "previsao_pontual",
    "intervalo_inferior_80", "intervalo_superior_80",
    "peso_dfm", "tipo", "realizado", "erro", "dentro_intervalo",
    "modelo_dfm", "ultima_obs_pim_pf",
]


def main() -> int:
    print("\n  ── popular_historico — 12 últimas validações (h=2) ──")
    if not GR_CSV.exists():
        raise FileNotFoundError(f"falta {GR_CSV}")

    gr = pd.read_csv(GR_CSV, parse_dates=["origem", "alvo"])
    h2 = (gr[(gr["h"] == 2) & gr["y_comb"].notna()]
            .sort_values("alvo").reset_index(drop=True))
    print(f"  Total OOS-legítimas h=2: {len(h2)} · pegando últimas 12.")

    ultimas = h2.tail(12).copy()

    # Para o intervalo: usa o quantil conformal padrão da janela h=2
    # (mesmo método que o produto público).
    if not CONF_CSV.exists():
        raise FileNotFoundError(f"falta {CONF_CSV}")
    inter = pd.read_csv(CONF_CSV, parse_dates=["alvo"])
    # Pega o intervalo do método "conformal_padrao" e h=2 quando disponível
    inter_h2 = (inter[(inter["h"] == 2) &
                       (inter["metodo"] == "conformal_padrao")]
                  .set_index("alvo"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        # Lê histórico atual e remove pré-populações antigas para
        # idempotência
        hist = pd.read_csv(OUT)
        hist = hist[hist["tipo"] != "validacao_historica"]
        hist.to_csv(OUT, index=False)
    else:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUNAS_HIST).writeheader()

    n_escritas = 0
    for _, r in ultimas.iterrows():
        alvo = r["alvo"]
        # Intervalo conformal: tenta extrair do conjunto de teste; se não
        # tiver, deixa em branco (linha ainda válida).
        if alvo in inter_h2.index:
            row_int = inter_h2.loc[alvo]
            if isinstance(row_int, pd.DataFrame):
                row_int = row_int.iloc[0]
            inf = float(row_int["intervalo_inf"])
            sup = float(row_int["intervalo_sup"])
        else:
            # Estima largura média da banda h=2 para preencher histórico
            # (cobertura empírica reportada como conservadora — q ≈ 5.35 pp)
            q_padrao = 0.0535
            inf = float(r["y_comb"]) - q_padrao
            sup = float(r["y_comb"]) + q_padrao

        erro = abs(r["y_true"] - r["y_comb"])
        dentro = (r["y_true"] >= inf) and (r["y_true"] <= sup)

        linha = {
            "data_emissao":          r["origem"].strftime("%Y-%m-%d"),
            "mes_alvo":              alvo.strftime("%Y-%m-%d"),
            "horizonte":             2,
            "previsao_pontual":      round(float(r["y_comb"]), 6),
            "intervalo_inferior_80": round(inf, 6),
            "intervalo_superior_80": round(sup, 6),
            "peso_dfm":              round(float(r["w_dfm"]), 4)
                                       if pd.notna(r["w_dfm"]) else "",
            "tipo":                  "validacao_historica",
            "realizado":             round(float(r["y_true"]), 6),
            "erro":                  round(float(erro), 6),
            "dentro_intervalo":      bool(dentro),
            "modelo_dfm":            "dfm_2026",   # modelo na janela validada
            "ultima_obs_pim_pf":     r["origem"].strftime("%Y-%m-%d"),
        }
        with open(OUT, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUNAS_HIST).writerow(linha)
        n_escritas += 1

    print(f"  ✓ {n_escritas} validações registradas em "
          f"{OUT.relative_to(ROOT)} (tipo=validacao_historica).")

    # Sanity
    df = pd.read_csv(OUT)
    print(f"  Total no histórico: {len(df)} linhas "
          f"({(df['tipo']=='validacao_historica').sum()} validação, "
          f"{(df['tipo']=='producao').sum()} produção).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
