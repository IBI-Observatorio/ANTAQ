"""
Itens 1 e 2 do pré-registro de lançamento (REGRA_LANCAMENTO.md):

  Item 1 — Pesos Granger-Ramanathan em rolling OOS (expanding window)
  Item 2 — Calibração conformal dos intervalos da combinação

Ambos são pré-requisito para publicação pública do PIM-PF Combinado IBI.

Uso:
    python -m analises.validacao.portgdp_v2_lancamento
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.validacao.metricas import (resumir, dm_test_hln, pinball_loss)

OUT = ROOT / "validacao" / "portgdp_v2"
ALPHA = 0.20            # cobertura nominal 80%
JANELA_AQUECIMENTO = 36 # origens mínimas para estimar GR
BLOCK_SIZE = 12         # tamanho do bloco para bootstrap conformal
N_BOOT = 5000           # n. de reamostragens do block-bootstrap


# ═════════════════════════════════════════════════════════════════════════════
# Carregamento das previsões walk-forward
# ═════════════════════════════════════════════════════════════════════════════
def carregar_previsoes() -> pd.DataFrame:
    """
    Junta DFM-1f (v2) com AR(1) (v1) numa tabela longa, ordenada por (h, alvo).
    """
    arq_dfm = OUT / "walkforward_dfm_previsoes.csv"
    arq_ar1 = ROOT / "validacao" / "portgdp" / "walkforward_ardl_previsoes.csv"
    if not arq_dfm.exists() or not arq_ar1.exists():
        raise FileNotFoundError("CSVs de walk-forward ausentes.")
    dfm = pd.read_csv(arq_dfm, parse_dates=["origem", "alvo"])
    ar1 = (pd.read_csv(arq_ar1, parse_dates=["origem", "alvo"])
              .query("modelo == 'ar1'"))
    df = pd.concat([dfm, ar1], ignore_index=True)
    if "q50" not in df.columns:
        df["q50"] = df.get("media")
    df["q50"] = df["q50"].fillna(df.get("media"))
    return df


# ═════════════════════════════════════════════════════════════════════════════
# ITEM 1 — Granger-Ramanathan rolling OOS
# ═════════════════════════════════════════════════════════════════════════════
def gr_rolling(df_pred: pd.DataFrame,
               modelo_dfm: str = "dfm_1f",
               janela_aq: int = JANELA_AQUECIMENTO) -> pd.DataFrame:
    """
    Para cada origem τ (ordenada cronologicamente, separadamente por h):
      1. Coleta pares (y_t, ŷ_DFM_t, ŷ_AR1_t) das origens anteriores a τ.
      2. OLS sem intercepto: (y - ar1) ~ (dfm - ar1).
      3. Trunca w_DFM em [0, 1].
      4. Aplica peso na previsão da origem τ.

    Retorna DataFrame longo com colunas:
        h, origem, alvo, y_true, y_dfm, y_ar1, y_comb, w_dfm,
        truncado (bool), n_treino_gr
    """
    registros = []
    for h in [1, 2]:
        sub = df_pred[df_pred["h"] == h]
        dfm = sub[sub["modelo"] == modelo_dfm].set_index("alvo")
        ar1 = sub[sub["modelo"] == "ar1"      ].set_index("alvo")
        comum = dfm.index.intersection(ar1.index).sort_values()
        if len(comum) < janela_aq + 5:
            continue

        # Tabela alinhada cronologicamente
        tab = pd.DataFrame({
            "origem": dfm.loc[comum, "origem"].values,
            "alvo":   comum,
            "y_true": dfm.loc[comum, "y_true"].values,
            "y_dfm":  dfm.loc[comum, "q50"].values,
            "y_ar1":  ar1.loc[comum, "q50"].values,
        }).sort_values("alvo").reset_index(drop=True)

        # Para cada τ ≥ janela_aq+1: estima w_DFM com pares 1..τ-1
        for i in range(len(tab)):
            if i < janela_aq:
                registros.append({
                    "h": h, "origem": tab.loc[i, "origem"],
                    "alvo":   tab.loc[i, "alvo"],
                    "y_true": tab.loc[i, "y_true"],
                    "y_dfm":  tab.loc[i, "y_dfm"],
                    "y_ar1":  tab.loc[i, "y_ar1"],
                    "y_comb": np.nan,
                    "w_dfm":  np.nan,
                    "truncado": False,
                    "n_treino_gr": i,
                })
                continue

            treino = tab.iloc[:i]                  # origens estritamente anteriores
            X = (treino["y_dfm"] - treino["y_ar1"]).values
            Y = (treino["y_true"] - treino["y_ar1"]).values
            # OLS sem intercepto: w = sum(X*Y) / sum(X*X)
            denom = float(np.sum(X * X))
            if denom <= 0 or not np.isfinite(denom):
                w = 0.0
            else:
                w = float(np.sum(X * Y)) / denom
            truncado = (w < 0.0) or (w > 1.0)
            w = float(np.clip(w, 0.0, 1.0))

            y_dfm_τ = float(tab.loc[i, "y_dfm"])
            y_ar1_τ = float(tab.loc[i, "y_ar1"])
            y_comb  = w * y_dfm_τ + (1 - w) * y_ar1_τ

            registros.append({
                "h": h, "origem": tab.loc[i, "origem"],
                "alvo":   tab.loc[i, "alvo"],
                "y_true": tab.loc[i, "y_true"],
                "y_dfm":  y_dfm_τ,
                "y_ar1":  y_ar1_τ,
                "y_comb": y_comb,
                "w_dfm":  w,
                "truncado": truncado,
                "n_treino_gr": i,
            })

    return pd.DataFrame(registros)


def metricas_combinacao_oos(df_gr: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Métricas pontuais e DM-HLN da combinação OOS-legítima (origens com w
    estimado) vs AR(1) puro vs DFM-1f puro, na MESMA janela.
    """
    metricas = []
    dm_rows = []
    for h in sorted(df_gr["h"].unique()):
        sub = df_gr[(df_gr["h"] == h) & df_gr["y_comb"].notna()].copy()
        if sub.empty:
            continue
        y    = sub["y_true"].values
        comb = sub["y_comb"].values
        ar1  = sub["y_ar1"].values
        dfm  = sub["y_dfm"].values
        for nome, yhat in [("comb_oos", comb), ("ar1", ar1), ("dfm_1f", dfm)]:
            err = y - yhat
            metricas.append({
                "h": h, "modelo": nome, "n": len(sub),
                "mae_pp":  float(np.mean(np.abs(err))) * 100,
                "rmse_pp": float(np.sqrt(np.mean(err**2))) * 100,
            })
        # DM combinação vs AR(1)
        dm, p, n = dm_test_hln(y - comb, y - ar1, h=h)
        dm_rows.append({"h": h, "comparacao": "comb_oos vs ar1",
                          "dm_stat": dm, "p_value": p, "n": n})
        # DM combinação vs DFM-1f puro
        dm2, p2, n2 = dm_test_hln(y - comb, y - dfm, h=h)
        dm_rows.append({"h": h, "comparacao": "comb_oos vs dfm_1f",
                          "dm_stat": dm2, "p_value": p2, "n": n2})

    return pd.DataFrame(metricas), pd.DataFrame(dm_rows)


def estatisticas_pesos(df_gr: pd.DataFrame) -> pd.DataFrame:
    """Média/mediana/mín/máx/dp de w_DFM e contagem de truncamentos por h."""
    rows = []
    for h in sorted(df_gr["h"].unique()):
        sub = df_gr[(df_gr["h"] == h) & df_gr["w_dfm"].notna()]
        if sub.empty:
            continue
        rows.append({
            "h": h,
            "n_origens_oos":  len(sub),
            "w_dfm_media":    float(sub["w_dfm"].mean()),
            "w_dfm_mediana":  float(sub["w_dfm"].median()),
            "w_dfm_min":      float(sub["w_dfm"].min()),
            "w_dfm_max":      float(sub["w_dfm"].max()),
            "w_dfm_dp":       float(sub["w_dfm"].std(ddof=0)),
            "n_truncamentos": int(sub["truncado"].sum()),
        })
    return pd.DataFrame(rows)


def plot_pesos_rolling(df_gr: pd.DataFrame, arq_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    cores = {1: "#3a64a8", 2: "#c1322f"}
    for h in sorted(df_gr["h"].unique()):
        sub = df_gr[(df_gr["h"] == h) & df_gr["w_dfm"].notna()]
        if sub.empty:
            continue
        ax.plot(sub["alvo"], sub["w_dfm"], color=cores[h],
                lw=1.8, label=f"h = {h}")
        ax.axhline(sub["w_dfm"].mean(), color=cores[h], lw=0.8, ls=":",
                    alpha=0.7)
    ax.axhline(0.25, color="grey", lw=0.6, ls="--",
                label="Limiar decisão (25%)")
    ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("w_DFM (peso de DFM-1f na combinação)")
    ax.set_title("Pesos Granger-Ramanathan rolling OOS — origens 37+")
    ax.legend(framealpha=0.9, fontsize=9)
    ax.grid(alpha=0.25, ls="--")
    fig.tight_layout()
    fig.savefig(arq_png, dpi=120, bbox_inches="tight")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════════════════════
# ITEM 2 — Calibração conformal
# ═════════════════════════════════════════════════════════════════════════════
def quantil_conformal(erros_abs_calib: np.ndarray, alfa: float) -> float:
    """
    Split conformal (Lei et al. 2018):
        q̂ = ⌈(n+1)(1-α)⌉-ésimo menor erro absoluto do conjunto de calibração.
    Garante cobertura marginal ≥ 1 − α sob exchangeability.
    """
    n = len(erros_abs_calib)
    if n == 0:
        return float("nan")
    k = int(np.ceil((n + 1) * (1 - alfa)))   # 1-indexed
    k = min(k, n)                             # se k > n, retorna o máximo
    return float(np.sort(erros_abs_calib)[k - 1])


def block_bootstrap_conformal(erros_calib_em_ordem: np.ndarray,
                                alfa: float, block_size: int = BLOCK_SIZE,
                                n_boot: int = N_BOOT,
                                seed: int = 42) -> float:
    """
    Bootstrap circular em blocos sobre os erros (em ORDEM TEMPORAL):
      1. Repete `n_boot` vezes:
         a. Reamostra blocos contíguos de `block_size` com reposição até
            preencher n erros.
         b. Calcula q̂ = quantil conformal nessa amostra.
      2. Retorna a média dos q̂.

    Justificativa: preserva autocorrelação local dos erros que o split
    conformal padrão ignora.
    """
    rng = np.random.default_rng(seed)
    erros = np.asarray(erros_calib_em_ordem, dtype=float)
    n = len(erros)
    if n < block_size:
        return quantil_conformal(np.abs(erros), alfa)
    n_blocos = int(np.ceil(n / block_size))
    qs = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, size=n_blocos)
        amostra = np.concatenate([
            erros[(s + np.arange(block_size)) % n]    # circular
            for s in starts
        ])[:n]
        qs[b] = quantil_conformal(np.abs(amostra), alfa)
    return float(np.mean(qs))


def quantil_empirico_simples(erros_calib: np.ndarray, alfa: float) -> float:
    """Referência ingênua usada no v1: quantil empírico de |err|."""
    return float(np.quantile(np.abs(erros_calib), 1 - alfa))


def avaliar_intervalos(y_test: np.ndarray, ŷ_test: np.ndarray,
                        q: float) -> dict:
    """
    Retorna cobertura empírica + IC binomial 95% (Wilson), largura média e
    pinball nos quantis 10% e 90% implícitos.
    """
    inf = ŷ_test - q
    sup = ŷ_test + q
    dentro = (y_test >= inf) & (y_test <= sup)
    n = len(y_test)
    cob = float(np.mean(dentro))
    # IC Wilson 95% para a proporção (mais robusto que normal aprox. com n pequeno)
    z = 1.959963984540054
    if n > 0:
        denom = 1 + z**2 / n
        centro = (cob + z**2 / (2 * n)) / denom
        margem = z * np.sqrt(cob*(1-cob)/n + z**2/(4*n**2)) / denom
        ic_lo, ic_hi = float(centro - margem), float(centro + margem)
    else:
        ic_lo, ic_hi = float("nan"), float("nan")
    lar = float(np.mean(sup - inf))
    pin10 = pinball_loss(y_test, inf, 0.10)
    pin90 = pinball_loss(y_test, sup, 0.90)
    return {"cobertura": cob,
             "ic_lo_95": ic_lo, "ic_hi_95": ic_hi,
             "largura_pp": lar * 100,
             "pinball_10pp": pin10 * 100, "pinball_90pp": pin90 * 100}


def calibracao_conformal(df_gr: pd.DataFrame,
                          alfa: float = ALPHA) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Para cada h:
      - usa metade da janela OOS-legítima como calibração, metade como teste
      - aplica os 3 métodos sobre os erros |y - y_comb|
      - reporta cobertura empírica e largura no conjunto de teste
    Retorna (cobertura_df, intervalos_df).
    """
    cob_rows = []
    int_rows = []
    for h in sorted(df_gr["h"].unique()):
        sub = (df_gr[(df_gr["h"] == h) & df_gr["y_comb"].notna()]
                  .sort_values("alvo")
                  .reset_index(drop=True))
        if len(sub) < 10:
            continue
        meio = len(sub) // 2
        cal, tst = sub.iloc[:meio], sub.iloc[meio:]

        err_cal = (cal["y_true"] - cal["y_comb"]).values
        y_test = tst["y_true"].values
        ŷ_test = tst["y_comb"].values

        # 1. Conformal padrão
        q_padrao  = quantil_conformal(np.abs(err_cal), alfa)
        # 2. Block-bootstrap
        q_boot    = block_bootstrap_conformal(err_cal, alfa)
        # 3. Quantil empírico simples
        q_simples = quantil_empirico_simples(err_cal, alfa)

        for nome, q in [("conformal_padrao", q_padrao),
                         ("conformal_block_bootstrap", q_boot),
                         ("quantil_empirico_simples", q_simples)]:
            ev = avaliar_intervalos(y_test, ŷ_test, q)
            cob_rows.append({
                "metodo": nome, "h": h,
                "n_calibracao": len(cal), "n_teste": len(tst),
                "q_calibracao_pp": q * 100,
                "nominal": 1 - alfa,
                **ev,
                "desvio_cobertura_pp": (ev["cobertura"] - (1 - alfa)) * 100,
            })
            for i, (alvo, y, yhat) in enumerate(zip(tst["alvo"], y_test, ŷ_test)):
                int_rows.append({
                    "metodo": nome, "h": h, "alvo": alvo,
                    "y_true": y, "y_comb": yhat,
                    "intervalo_inf": yhat - q,
                    "intervalo_sup": yhat + q,
                    "dentro": bool((y >= yhat - q) and (y <= yhat + q)),
                })

    return pd.DataFrame(cob_rows), pd.DataFrame(int_rows)


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════
def _md_table(df: pd.DataFrame, casas: int = 4) -> str:
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep  = "|" + "|".join("---" for _ in cols) + "|"
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f"{v:.{casas}f}")
            elif isinstance(v, (pd.Timestamp,)):
                cells.append(v.strftime("%Y-%m"))
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *rows])


def main() -> int:
    print("\n  ── Itens 1+2 (lançamento) — PortGDP v2 ──")
    t0 = time.time()
    df_pred = carregar_previsoes()

    # ─── ITEM 1 ──────────────────────────────────────────────────────────────
    print("\n  [Item 1.1] Rolling Granger-Ramanathan (expanding window, "
          f"aquecimento {JANELA_AQUECIMENTO})…")
    df_gr = gr_rolling(df_pred, modelo_dfm="dfm_1f",
                        janela_aq=JANELA_AQUECIMENTO)
    df_gr.to_csv(OUT / "gr_rolling_pesos.csv",
                  index=False, float_format="%.6f")
    print(f"    {len(df_gr)} linhas (origens × h).")

    print("\n  [Item 1.2] Estatísticas dos pesos…")
    stats = estatisticas_pesos(df_gr)
    print(stats.to_string(index=False))

    print("\n  [Item 1.3] Métricas da combinação OOS-legítima vs componentes…")
    metricas, dm_rolling = metricas_combinacao_oos(df_gr)
    metricas.to_csv(OUT / "gr_rolling_metricas.csv",
                     index=False, float_format="%.6f")
    dm_rolling.to_csv(OUT / "gr_rolling_dm.csv",
                       index=False, float_format="%.6f")
    print(metricas.to_string(index=False))
    print("\n  DM-HLN (combinação OOS):")
    print(dm_rolling.to_string(index=False))

    print("\n  [Item 1.4] Plot série de pesos…")
    plot_pesos_rolling(df_gr, OUT / "gr_rolling_pesos.png")
    print(f"    ✓ {(OUT / 'gr_rolling_pesos.png').relative_to(ROOT)}")

    # ─── ITEM 2 ──────────────────────────────────────────────────────────────
    print("\n  [Item 2] Calibração conformal (3 métodos × 2 h)…")
    cob, intervalos = calibracao_conformal(df_gr, alfa=ALPHA)
    cob.to_csv(OUT / "conformal_cobertura.csv",
                index=False, float_format="%.6f")
    intervalos.to_csv(OUT / "conformal_intervalos_teste.csv",
                       index=False, float_format="%.6f")

    # CSV de calibração (erros usados)
    cal_rows = []
    for h in sorted(df_gr["h"].unique()):
        sub = (df_gr[(df_gr["h"] == h) & df_gr["y_comb"].notna()]
                  .sort_values("alvo").reset_index(drop=True))
        meio = len(sub) // 2
        for _, r in sub.iloc[:meio].iterrows():
            cal_rows.append({"h": h, "alvo": r["alvo"],
                              "y_true": r["y_true"], "y_comb": r["y_comb"],
                              "erro_abs": abs(r["y_true"] - r["y_comb"])})
    pd.DataFrame(cal_rows).to_csv(OUT / "conformal_calibracao.csv",
                                    index=False, float_format="%.6f")

    print(cob[["metodo", "h", "n_calibracao", "n_teste", "q_calibracao_pp",
                "nominal", "cobertura", "ic_lo_95", "ic_hi_95",
                "largura_pp", "desvio_cobertura_pp"]].to_string(index=False))

    # ─── Decisão pós-resultado ──────────────────────────────────────────────
    decisao_item1 = {}
    for h in sorted(df_gr["h"].unique()):
        s = stats[stats["h"] == h].iloc[0]
        m = metricas[(metricas["h"] == h) & (metricas["modelo"] == "comb_oos")].iloc[0]
        m_ar1 = metricas[(metricas["h"] == h) & (metricas["modelo"] == "ar1")].iloc[0]
        w = s["w_dfm_media"]
        comb_melhor = m["mae_pp"] < m_ar1["mae_pp"]
        if w >= 0.25 and comb_melhor:
            status = "Linha D MANTIDA (w_DFM ≥ 25% e MAE_comb < MAE_AR1)"
        elif w < 0.15 or not comb_melhor:
            status = "Linha D FRÁGIL — escalar (w_DFM < 15% OU MAE_comb ≥ MAE_AR1)"
        else:
            status = "Zona cinza (15% ≤ w_DFM < 25% e MAE_comb < MAE_AR1)"
        decisao_item1[h] = {
            "w_dfm_medio": w,
            "mae_combinado": m["mae_pp"],
            "mae_ar1": m_ar1["mae_pp"],
            "status": status,
        }

    decisao_item2 = {}
    for h in sorted(cob["h"].unique()):
        sub_h = cob[cob["h"] == h].copy()
        sub_h["desv_abs"] = sub_h["desvio_cobertura_pp"].abs()
        padrao_row = sub_h[sub_h["metodo"] == "conformal_padrao"].iloc[0]
        bb_row = sub_h[sub_h["metodo"] == "conformal_block_bootstrap"].iloc[0]
        cob_padrao = padrao_row["cobertura"]

        # Aplicação literal do pré-registro:
        if 0.75 <= cob_padrao <= 0.85:
            metodo_recomendado = "conformal_padrao"
            alerta = ""
        else:
            # padrão fora da faixa → tenta block-bootstrap;
            # se ele também está fora, escolhe o de menor desvio + alerta.
            if 0.75 <= bb_row["cobertura"] <= 0.85:
                metodo_recomendado = "conformal_block_bootstrap"
                alerta = ""
            else:
                metodo_recomendado = sub_h.sort_values("desv_abs").iloc[0]["metodo"]
                alerta = ("AMBOS desviam > 5pp da nominal — registrar na "
                            "nota técnica e considerar correção empírica.")

        sel = sub_h[sub_h["metodo"] == metodo_recomendado].iloc[0]
        decisao_item2[h] = {
            "metodo_recomendado":   metodo_recomendado,
            "cobertura_recomendado": float(sel["cobertura"]),
            "ic95_lo":              float(sel.get("ic_lo_95", float("nan"))),
            "ic95_hi":              float(sel.get("ic_hi_95", float("nan"))),
            "largura_recomendado_pp": float(sel["largura_pp"]),
            "alerta": alerta,
        }

    # ─── Sumário executivo ──────────────────────────────────────────────────
    md = []
    md.append("# Itens finais antes do lançamento — sumário executivo")
    md.append("")
    md.append(f"Tempo total de execução: {time.time() - t0:.1f}s")
    md.append("")
    md.append("## Item 1 — Granger-Ramanathan rolling OOS")
    md.append("")
    md.append("### Estatísticas dos pesos")
    md.append("")
    md.append(_md_table(stats, casas=3))
    md.append("")
    md.append("### Métricas da combinação OOS-legítima")
    md.append("")
    md.append(_md_table(metricas, casas=3))
    md.append("")
    md.append("### DM-HLN")
    md.append("")
    md.append(_md_table(dm_rolling, casas=4))
    md.append("")
    md.append("### Decisão Item 1")
    md.append("")
    for h, info in decisao_item1.items():
        md.append(f"- **h = {h}**: w_DFM médio = {info['w_dfm_medio']:.3f}, "
                   f"MAE_comb = {info['mae_combinado']:.2f} pp, "
                   f"MAE_AR1 = {info['mae_ar1']:.2f} pp → "
                   f"**{info['status']}**")
    md.append("")
    md.append("## Item 2 — Calibração conformal")
    md.append("")
    md.append(_md_table(
        cob[["metodo", "h", "n_calibracao", "n_teste", "nominal",
              "cobertura", "largura_pp", "desvio_cobertura_pp"]],
        casas=3))
    md.append("")
    md.append("### Decisão Item 2")
    md.append("")
    for h, info in decisao_item2.items():
        md.append(f"- **h = {h}**: método recomendado = "
                   f"`{info['metodo_recomendado']}` "
                   f"(cobertura empírica {info['cobertura_recomendado']:.1%}, "
                   f"largura {info['largura_recomendado_pp']:.2f} pp)")
    md.append("")
    md.append("## Status final do lançamento")
    md.append("")
    md.append("| h | Status Item 1 | Método conformal | Cobertura empírica | Largura |")
    md.append("|---|---|---|---|---|")
    for h in sorted(decisao_item1):
        i1 = decisao_item1[h]
        i2 = decisao_item2.get(h, {})
        md.append(f"| {h} | {i1['status']} | "
                   f"`{i2.get('metodo_recomendado', '—')}` | "
                   f"{i2.get('cobertura_recomendado', float('nan')):.1%} | "
                   f"{i2.get('largura_recomendado_pp', float('nan')):.2f} pp |")
    md.append("")
    (OUT / "sumario_itens_1_2.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n  ✓ {(OUT / 'sumario_itens_1_2.md').relative_to(ROOT)}")
    print(f"\n  Decisão Item 1 por h:")
    for h, info in decisao_item1.items():
        print(f"    h={h}: {info['status']}")
    print(f"\n  Decisão Item 2 por h:")
    for h, info in decisao_item2.items():
        print(f"    h={h}: método={info['metodo_recomendado']}, "
              f"cobertura={info['cobertura_recomendado']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
