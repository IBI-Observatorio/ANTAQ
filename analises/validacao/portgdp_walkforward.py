"""
Item 1 do plano metodológico — validação rolling-origin do PortGDP.

Walk-forward com janela expansiva. Para cada origem τ (a partir de 36 meses
de treino mínimo), treina cada modelo em todo o histórico ≤ τ e prevê:
    - h = 1 (próximo mês)
    - h = 2 (dois meses à frente)

Modelos comparados: portgdp_ols (alvo), rw, sazonal_naive, ar1.
Cada modelo emite distribuição preditiva via 9 quantis (0.1 a 0.9).

Outputs em validacao/portgdp/:
    walkforward_previsoes.csv  — long format (origem, alvo, h, modelo, q*, y_true)
    sumario.md                  — tabela de métricas
    dm_tests.md                 — DM-HLN: portgdp_ols vs cada baseline
    .png                        — gráficos exploratórios

Uso:
    python -m analises.validacao.portgdp_walkforward
    python -m analises.validacao.portgdp_walkforward --min-train 24
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import antaq                                            # noqa: E402
from analises.macro import pim_pf as carregar_pim_pf    # noqa: E402
from analises.validacao.modelos import MODELOS, QUANTIS_DEFAULT  # noqa: E402
from analises.validacao.metricas import resumir, dm_pareado      # noqa: E402

OUT_DIR = ROOT / "validacao" / "portgdp"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Carregamento de dados ────────────────────────────────────────────────────
def carregar_series() -> tuple[pd.Series, pd.Series]:
    """
    Constrói:
        port_imp  — índice mensal dessazonalizado de PortGDP-Importações (base 2014=100)
        pim       — índice mensal dessazonalizado de PIM-PF Indústria Geral (BCB SGS 28503)
    """
    db = antaq.conectar()
    df = db.sql(
        """
        SELECT date_trunc('month', a."Data Atracação")::DATE AS mes,
               SUM(CASE WHEN c.FlagLongoCurso=1
                         AND c.Sentido='Desembarcados'
                         AND c."Natureza da Carga" IN
                              ('Carga Conteinerizada','Carga Geral','Granel Líquido e Gasoso')
                        THEN c.VLPesoCargaBruta ELSE 0 END) AS ton_imp
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE a."Data Atracação" >= '2014-01-01' AND a."Data Atracação" < '2026-01-01'
        GROUP BY 1 ORDER BY 1
        """
    ).df().set_index("mes")
    df.index = pd.to_datetime(df.index)
    s = df["ton_imp"].astype(float)

    # Dessaz por razão sobre média móvel 12m / média mensal
    sazonal = s / s.rolling(12, center=True).mean()
    ds = s / sazonal.groupby(sazonal.index.month).transform("mean")
    port_imp = ds / ds.loc["2014-01":"2014-12"].mean() * 100

    pim = carregar_pim_pf()
    pim = pim / pim.loc["2014-01":"2014-12"].mean() * 100
    pim.name = "pim"

    return port_imp.rename("port_imp"), pim


# ─── Walk-forward principal ───────────────────────────────────────────────────
def walkforward(port_imp: pd.Series, pim: pd.Series,
                min_train: int = 36,
                horizontes: tuple[int, ...] = (1, 2),
                quantiles: list[float] = QUANTIS_DEFAULT) -> pd.DataFrame:
    """
    Loop rolling-origin com janela expansiva.

    Trabalha sobre variações interanuais (pct_change(12)) — escala estacionária
    e diretamente comparável entre modelos.

    Args:
        min_train  — número mínimo de observações no treino antes de gerar
                     previsões. 36 = 3 anos.
        horizontes — quais h validar (separadamente).
    """
    v_port = port_imp.pct_change(12)
    v_pim  = pim.pct_change(12)

    # Alinha índice comum (ambos não-NaN)
    idx = v_port.dropna().index.intersection(v_pim.dropna().index)
    v_port = v_port.loc[idx].sort_index()
    v_pim  = v_pim.loc[idx].sort_index()
    n = len(v_pim)

    print(f"  Janela total alinhada: {idx[0].date()} → {idx[-1].date()}  "
          f"({n} meses)")
    print(f"  Min. treino: {min_train} meses · Origens válidas: "
          f"{n - min_train - max(horizontes)} → {n - min_train}")

    registros = []
    inicio = time.time()
    for i in range(min_train, n - 1):              # origem τ no índice i
        origem = v_pim.index[i]
        train_y = v_pim.iloc[: i + 1]              # ≤ τ
        train_x = v_port.iloc[: i + 1]
        for h in horizontes:
            j = i + h
            if j >= n:
                continue
            alvo = v_pim.index[j]
            y_true = float(v_pim.iloc[j])

            for nome, fn in MODELOS.items():
                pred = fn(train_y, train_x, h, quantiles=quantiles)
                registros.append({
                    "origem": origem,
                    "alvo":   alvo,
                    "h":      h,
                    "modelo": nome,
                    "y_true": y_true,
                    **pred,
                })

    df = pd.DataFrame(registros)
    df["q50"] = df.get("q50", df.get("media"))
    print(f"  Walk-forward concluído em {time.time() - inicio:.1f}s · "
          f"{len(df)} previsões.")
    return df


# ─── Outputs ──────────────────────────────────────────────────────────────────
def salvar_csv(df: pd.DataFrame) -> Path:
    arq = OUT_DIR / "walkforward_previsoes.csv"
    df.to_csv(arq, index=False, float_format="%.6f")
    return arq


def salvar_sumario_md(resumo: pd.DataFrame, dm: pd.DataFrame,
                       n_total: int, periodo: tuple[pd.Timestamp, pd.Timestamp]) -> Path:
    arq = OUT_DIR / "sumario.md"
    linhas = []
    linhas.append("# Validação rolling-origin — PortGDP")
    linhas.append("")
    linhas.append(f"- **Janela validada**: {periodo[0].date()} → {periodo[1].date()}")
    linhas.append(f"- **Total de previsões geradas**: {n_total}")
    linhas.append(f"- **Modelos comparados**: portgdp_ols (alvo), rw, sazonal_naive, ar1")
    linhas.append(f"- **Quantis preditos**: {', '.join(f'{int(q*100)}%' for q in QUANTIS_DEFAULT)}")
    linhas.append(f"- **Métricas em pp** (variação interanual × 100)")
    linhas.append("")
    linhas.append("## Métricas por modelo × horizonte")
    linhas.append("")
    for h in sorted(resumo["h"].unique()):
        linhas.append(f"### h = {h}")
        linhas.append("")
        sub = resumo[resumo["h"] == h].copy()
        sub = sub[["modelo", "n", "mae_pp", "rmse_pp", "pinball_avg", "crps_pp"]]
        sub.columns = ["modelo", "n", "MAE (pp)", "RMSE (pp)", "Pinball médio (pp)", "CRPS (pp)"]
        linhas.append(_md_table(sub))
        linhas.append("")
    linhas.append("## Diebold-Mariano com correção HLN — portgdp_ols vs baselines")
    linhas.append("")
    linhas.append("Convenção: `dm_stat < 0` indica que portgdp_ols tem erro quadrático")
    linhas.append("**menor** que o baseline. p-valor bilateral.")
    linhas.append("")
    dm_disp = dm.copy()
    dm_disp["dm_stat"] = dm_disp["dm_stat"].round(3)
    dm_disp["p_value"] = dm_disp["p_value"].round(4)
    dm_disp["sig"] = dm_disp["p_value"].apply(_estrelas)
    dm_disp = dm_disp[["h", "baseline", "n", "dm_stat", "p_value", "sig"]]
    dm_disp.columns = ["h", "baseline", "n", "DM stat", "p-valor", "sig."]
    linhas.append(_md_table(dm_disp))
    linhas.append("")
    linhas.append("> sig.: `***` p<0,01 · `**` p<0,05 · `*` p<0,10 · `ns` não signif.")
    linhas.append("")
    arq.write_text("\n".join(linhas), encoding="utf-8")
    return arq


def _md_table(df: pd.DataFrame) -> str:
    """Tabela markdown a partir de DataFrame, com floats formatados."""
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep  = "|" + "|".join("---" for _ in cols) + "|"
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *rows])


def _estrelas(p: float) -> str:
    if not np.isfinite(p):
        return "—"
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.10:
        return "*"
    return "ns"


def gerar_grafico_diagnostico(df: pd.DataFrame) -> Path:
    """Gráfico exploratório: erro absoluto ao longo do tempo, por modelo × h."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    cores = {"portgdp_ols": "#c1322f", "rw": "#999999",
             "sazonal_naive": "#7fb069", "ar1": "#3a64a8"}
    for ax, h in zip(axes, sorted(df["h"].unique())):
        sub_h = df[df["h"] == h]
        for modelo, cor in cores.items():
            d = sub_h[sub_h["modelo"] == modelo].sort_values("alvo")
            erro = (d["y_true"] - d["q50"]).abs() * 100
            ax.plot(d["alvo"], erro.rolling(6, min_periods=1).mean(),
                    label=modelo, color=cor, lw=1.6)
        ax.set_title(f"Erro absoluto (var. 12m, pp) — h = {h}, média móvel 6m")
        ax.legend(fontsize=9, framealpha=0.9)
        ax.set_ylabel("|y_true - ŷ| (pp)")
        ax.grid(alpha=0.25, ls="--")
    fig.tight_layout()
    arq = OUT_DIR / "erro_ao_longo_do_tempo.png"
    fig.savefig(arq, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return arq


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-train", type=int, default=36,
                        help="número mínimo de observações no treino (default: 36)")
    parser.add_argument("--horizontes", type=int, nargs="+", default=[1, 2])
    args = parser.parse_args()

    print("\n  ── Item 1: walk-forward rolling-origin (PortGDP) ──")
    print("  Carregando séries…")
    port_imp, pim = carregar_series()

    df = walkforward(port_imp, pim,
                     min_train=args.min_train,
                     horizontes=tuple(args.horizontes))

    print("  Computando métricas…")
    resumo = resumir(df)

    print("  Computando DM-HLN (portgdp_ols vs baselines)…")
    baselines = ["rw", "sazonal_naive", "ar1"]
    dm = dm_pareado(df, modelo_alvo="portgdp_ols", baselines=baselines)

    print("\n  Resumo:")
    print(resumo.to_string(index=False))
    print("\n  DM-HLN:")
    print(dm.to_string(index=False))

    csv_path = salvar_csv(df)
    md_path  = salvar_sumario_md(
        resumo, dm,
        n_total=len(df),
        periodo=(df["alvo"].min(), df["alvo"].max()),
    )
    fig_path = gerar_grafico_diagnostico(df)

    print(f"\n  ✓ {csv_path.relative_to(ROOT)}")
    print(f"  ✓ {md_path.relative_to(ROOT)}")
    print(f"  ✓ {fig_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
