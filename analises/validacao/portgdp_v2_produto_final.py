"""
Gera artefatos do produto final PIM-PF Combinado IBI (h=2):
  - Diagnósticos de resíduo da combinação OOS-legítima (Ljung-Box, JB, ARCH-LM)
  - Plot comparativo: combinação vs AR(1) vs realizado nas últimas 36 origens
  - Métricas finais arredondadas, prontas para inclusão no produto

Outputs:
    validacao/portgdp_v2/produto_final/diagnosticos_residuos_h2.csv
    validacao/portgdp_v2/produto_final/comparacao_36_origens_h2.png
    validacao/portgdp_v2/produto_final/metricas_finais_h2.csv

Uso:
    python -m analises.validacao.portgdp_v2_produto_final
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "validacao" / "portgdp_v2"
PROD = OUT / "produto_final"
PROD.mkdir(parents=True, exist_ok=True)


def diagnosticos_residuos(residuos: np.ndarray, h: int) -> pd.DataFrame:
    """Ljung-Box (12 e 24), Jarque-Bera, ARCH-LM (12) sobre resíduos."""
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
    from statsmodels.stats.stattools import jarque_bera

    rows = []
    s = pd.Series(residuos).dropna()
    if len(s) < 24:
        return pd.DataFrame([{"teste": "—",
                              "obs": f"n={len(s)} insuficiente"}])

    lb = acorr_ljungbox(s, lags=[12, 24], return_df=True)
    rows.append({"teste": "Ljung-Box (lag 12)",
                 "stat": float(lb.iloc[0, 0]), "p_value": float(lb.iloc[0, 1])})
    rows.append({"teste": "Ljung-Box (lag 24)",
                 "stat": float(lb.iloc[1, 0]), "p_value": float(lb.iloc[1, 1])})

    jb_stat, jb_p, *_ = jarque_bera(s)
    rows.append({"teste": "Jarque-Bera (normalidade)",
                 "stat": float(jb_stat), "p_value": float(jb_p)})

    arch_lm, arch_p, _, _ = het_arch(s, nlags=12)
    rows.append({"teste": "ARCH-LM (lag 12)",
                 "stat": float(arch_lm), "p_value": float(arch_p)})
    return pd.DataFrame(rows)


def main() -> int:
    print("\n  ── Produto final PIM-PF Combinado IBI (h=2) ──")
    df_gr = pd.read_csv(OUT / "gr_rolling_pesos.csv", parse_dates=["origem", "alvo"])
    sub = (df_gr[(df_gr["h"] == 2) & df_gr["y_comb"].notna()]
              .sort_values("alvo").reset_index(drop=True))
    print(f"    {len(sub)} origens OOS-legítimas em h=2")

    # Métricas finais por modelo (na janela OOS-legítima)
    metricas = []
    y    = sub["y_true"].values
    comb = sub["y_comb"].values
    ar1  = sub["y_ar1"].values
    dfm  = sub["y_dfm"].values
    for nome, yhat in [("comb_oos_h2", comb),
                        ("ar1_h2", ar1),
                        ("dfm_1f_h2", dfm)]:
        err = y - yhat
        metricas.append({
            "modelo": nome,
            "n":      len(sub),
            "mae_pp": float(np.mean(np.abs(err))) * 100,
            "rmse_pp": float(np.sqrt(np.mean(err**2))) * 100,
        })
    pd.DataFrame(metricas).to_csv(PROD / "metricas_finais_h2.csv",
                                    index=False, float_format="%.4f")
    print("\n  Métricas finais (h=2):")
    for m in metricas:
        print(f"    {m['modelo']:18s}  MAE = {m['mae_pp']:.2f} pp  "
              f"RMSE = {m['rmse_pp']:.2f} pp")

    # Diagnósticos de resíduo da combinação
    print("\n  Diagnósticos de resíduo da combinação OOS (h=2)…")
    diag = diagnosticos_residuos(y - comb, h=2)
    diag.to_csv(PROD / "diagnosticos_residuos_h2.csv",
                 index=False, float_format="%.6f")
    print(diag.to_string(index=False))

    # Plot comparativo das últimas 36 origens
    print("\n  Plot comparativo (últimas 36 origens)…")
    n_plot = min(36, len(sub))
    last = sub.tail(n_plot).copy()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8),
                                      sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1]})

    # Painel superior: nível
    ax1.plot(last["alvo"], last["y_true"]*100, color="#111827", lw=2.4,
             marker="o", ms=4, label="Realizado (var12m PIM-PF, pp)")
    ax1.plot(last["alvo"], last["y_comb"]*100, color="#c1322f", lw=2,
             ls="--", label="PIM-PF Combinado IBI (h=2)")
    ax1.plot(last["alvo"], last["y_ar1"]*100, color="#3a64a8", lw=1.5,
             ls=":", label="AR(1) baseline")
    ax1.axhline(0, color="grey", lw=0.6)
    ax1.set_ylabel("Variação 12m do PIM-PF (pp)")
    ax1.set_title(f"PIM-PF Combinado IBI vs AR(1) baseline — "
                   f"últimas {n_plot} origens (h=2)")
    ax1.legend(framealpha=0.9, loc="upper left")
    ax1.grid(alpha=0.25, ls="--")

    # Painel inferior: erro absoluto
    err_comb = np.abs(last["y_true"] - last["y_comb"]) * 100
    err_ar1  = np.abs(last["y_true"] - last["y_ar1"])  * 100
    ax2.bar(last["alvo"], err_comb, width=20, color="#c1322f", alpha=0.85,
             label="|erro| Combinado")
    ax2.bar(last["alvo"], err_ar1, width=20, color="#3a64a8", alpha=0.4,
             label="|erro| AR(1)")
    ax2.set_ylabel("|erro| (pp)")
    ax2.set_xlabel("Mês alvo")
    ax2.legend(framealpha=0.9, fontsize=9, loc="upper left")
    ax2.grid(alpha=0.25, ls="--")

    fig.tight_layout()
    arq_plot = PROD / "comparacao_36_origens_h2.png"
    fig.savefig(arq_plot, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"    ✓ {arq_plot.relative_to(ROOT)}")

    print("\n  Outputs gerados:")
    print(f"    {(PROD / 'metricas_finais_h2.csv').relative_to(ROOT)}")
    print(f"    {(PROD / 'diagnosticos_residuos_h2.csv').relative_to(ROOT)}")
    print(f"    {(PROD / 'comparacao_36_origens_h2.png').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
