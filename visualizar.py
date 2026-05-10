"""
Visualizações do Harvest Oracle e da migração de soja Sul → Norte.

Gera (em figs/):
  migracao_soja.png     — share regional 2012-2025 + evolução dos top portos
  forecast_t1.png       — previsão de congestionamento p25/p50/p75 por porto
  rota_e_importancia.png — crescimento de share + importância de features
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import antaq
from harvest_oracle import HarvestOracle

FIGS = Path("figs")
FIGS.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family":        "DejaVu Sans",
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.grid":          True,
    "grid.alpha":         0.35,
    "grid.linewidth":     0.6,
    "figure.facecolor":   "white",
    "axes.facecolor":     "white",
})

COR_NORTE = "#E07B39"
COR_SUL   = "#3874B8"
COR_OUTRO = "#AAAAAA"
ALERTA_COR = {
    "CRITICO":  "#D32F2F",
    "ELEVADO":  "#F57C00",
    "MODERADO": "#F9A825",
    "NORMAL":   "#388E3C",
}

NORTE = {
    "Itaqui", "Santarém", "Santana", "Belém",
    "Terminal Graneleiro Hermasa", "Terminal Ponta da Montanha",
    "Terminal Portuário Novo Remanso", "Terminal Portuário Graneleiro de Barcarena",
    "Vila do Conde", "Terminal Vila do Conde",
}
SUL_SE = {"Santos", "Paranaguá", "Rio Grande", "São Francisco do Sul", "Imbituba"}

TOP_PORTOS_COR = {
    "Santos":                      "#1565C0",
    "Paranaguá":                   "#42A5F5",
    "Itaqui":                      "#E65100",
    "São Francisco do Sul":        "#81D4FA",
    "Rio Grande":                  "#0288D1",
    "Terminal Graneleiro Hermasa": "#FF7043",
    "Terminal Vila do Conde":      "#FFAB40",
    "Terminal Ponta da Montanha":  "#F57F17",
}


# ── Dados ───────────────────────────────────────────────────────────────────────

def carregar_migracao() -> pd.DataFrame:
    db = antaq.conectar()
    df = db.sql("""
        SELECT
            a."Porto Atracação"             AS porto,
            c.Ano,
            SUM(c."VLPesoCargaBruta") / 1e6 AS vol_Mt
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE LEFT(CAST(c.CDMercadoria AS VARCHAR), 4) = '1201'
          AND c.Sentido = 'Embarcados'
          AND c."FlagLongoCurso" = 1
          AND c."FlagMCOperacaoCarga" = 1
          AND c.Ano BETWEEN 2012 AND 2025
        GROUP BY porto, c.Ano
        ORDER BY c.Ano, vol_Mt DESC
    """).df()
    db.close()
    return df


# ── Figura 1: Migração Sul → Norte ──────────────────────────────────────────────

def fig_migracao(df_raw: pd.DataFrame) -> None:
    total = df_raw.groupby("Ano")["vol_Mt"].sum().rename("total_Mt")
    df = df_raw.join(total, on="Ano")
    df["share_pct"] = df["vol_Mt"] / df["total_Mt"] * 100
    df["regiao"] = df["porto"].apply(
        lambda p: "Norte/NE" if p in NORTE else ("Sul/SE" if p in SUL_SE else "Outros")
    )

    reg = df.groupby(["Ano", "regiao"])["share_pct"].sum().unstack(fill_value=0)
    anos = reg.index.values

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        "Soja brasileira: migração de rota de exportação  (2012–2025)",
        fontsize=14, fontweight="bold", y=1.01,
    )

    # — Stacked area: share regional
    norte = reg.get("Norte/NE", pd.Series(0, index=reg.index)).values
    sul   = reg.get("Sul/SE",   pd.Series(0, index=reg.index)).values
    outro = reg.get("Outros",   pd.Series(0, index=reg.index)).values

    ax1.stackplot(
        anos, norte, outro, sul,
        labels=["Norte / NE  (Arco Norte)", "Outros", "Sul / Sudeste"],
        colors=[COR_NORTE, COR_OUTRO, COR_SUL], alpha=0.88,
    )

    # Marcos temporais
    for x_ann, txt in [(2015, "Hidrovia\nMadeira\n(Redenção)"), (2022, "MATOPIBA\npeak")]:
        ax1.axvline(x_ann, color="gray", lw=0.9, ls="--", alpha=0.55)
        ax1.text(x_ann + 0.15, 8, txt, fontsize=7.5, color="#555555", va="bottom")

    # Rótulos de share Norte nas extremidades
    for ano_label, y_offset in [(2012, 0), (2017, 0), (2022, 0), (2025, 0)]:
        idx = list(anos).index(ano_label)
        ax1.text(ano_label, norte[idx] / 2, f"{norte[idx]:.0f}%",
                 ha="center", va="center", fontsize=9,
                 color="white", fontweight="bold")

    ax1.set_xlabel("Ano", fontsize=11)
    ax1.set_ylabel("Share das exportações de soja (%)", fontsize=11)
    ax1.set_ylim(0, 100)
    ax1.set_xlim(2012, 2025)
    ax1.legend(loc="upper right", fontsize=9, framealpha=0.9)
    ax1.set_title("Share por região", fontsize=11)

    # — Multi-linha: evolução em volume dos top portos
    for porto, cor in TOP_PORTOS_COR.items():
        sub = df[df["porto"] == porto].sort_values("Ano")
        if sub.empty:
            continue
        label = (
            porto.replace("Terminal Graneleiro", "T. Gran.")
                 .replace("Terminal Portuário", "T. Port.")
                 .replace("Terminal ", "T. ")
                 .replace("  ", " ")
        )
        ax2.plot(sub["Ano"], sub["vol_Mt"],
                 marker="o", markersize=3.5, linewidth=1.8,
                 color=cor, label=label)

    ax2.set_xlabel("Ano", fontsize=11)
    ax2.set_ylabel("Volume exportado (Mt — soja)", fontsize=11)
    ax2.set_xlim(2012, 2025)
    ax2.legend(fontsize=8.5, loc="upper left", framealpha=0.9)
    ax2.set_title("Evolução dos principais portos", fontsize=11)

    fig.tight_layout()
    out = FIGS / "migracao_soja.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {out}")


# ── Figura 2: Forecast T1 ───────────────────────────────────────────────────────

def fig_forecast(prev: pd.DataFrame, min_vol_kt: float = 3000) -> None:
    prev = prev[prev["vol_est_kt"] >= min_vol_kt].copy()
    lags = sorted(prev["lag_meses"].unique())

    fig, axes = plt.subplots(1, len(lags), figsize=(8 * len(lags), 9))
    if len(lags) == 1:
        axes = [axes]
    fig.suptitle(
        "Previsão de congestionamento portuário — Harvest Oracle v3\n"
        "T1 = tempo de espera para atracação (horas)  |  Referência: Abr/2026",
        fontsize=13, fontweight="bold", y=1.01,
    )

    for ax, lag in zip(axes, lags):
        bloco = prev[prev["lag_meses"] == lag].copy()
        bloco["label"] = (
            bloco["porto"]
                .str.replace("Terminal Integrador Portuário Luiz Antonio Mesquita - TIPLAM", "TIPLAM")
                .str.replace("Terminal Marítimo Luiz Fogliatto - Termasa", "T. Termasa")
                .str.replace("Terminal Portuário ", "T.P. ")
                .str.replace("Terminal Vila do Conde", "T. Vila do Conde")
                .str.replace("Terminal Graneleiro Hermasa", "T. Hermasa")
                .str.replace("Terminal Ponta da Montanha", "T. Ponta da Montanha")
                .str[:34]
            + " / " + bloco["produto"]
        )
        bloco = bloco.sort_values("t1_p50", ascending=True).reset_index(drop=True)
        y = np.arange(len(bloco))

        cores = [ALERTA_COR[a] for a in bloco["alerta"]]

        # Intervalo p25–p75
        ax.barh(
            y, bloco["t1_p75"] - bloco["t1_p25"], left=bloco["t1_p25"],
            height=0.55, color=cores, alpha=0.30, zorder=2,
        )
        # Intervalo p10–p90 (mais fino)
        ax.barh(
            y, bloco["t1_p90"] - bloco["t1_p10"], left=bloco["t1_p10"],
            height=0.18, color=cores, alpha=0.20, zorder=2,
        )
        # p50 (ponto principal)
        ax.scatter(bloco["t1_p50"], y, color=cores, s=55, zorder=5)
        # Mediana histórica (linha vertical preta)
        ax.scatter(bloco["t1_historico"], y,
                   color="black", marker="|", s=160, linewidths=2, zorder=6, alpha=0.55)

        mes_str = bloco["mes_alvo"].iloc[0].upper() if len(bloco) > 0 else ""
        ano_str = bloco["ano_alvo"].iloc[0] if len(bloco) > 0 else ""
        ax.set_title(f"{mes_str}/{ano_str}  (t+{lag})", fontsize=11, fontweight="bold")
        ax.set_yticks(y)
        ax.set_yticklabels(bloco["label"], fontsize=8)
        ax.set_xlabel("T1 — horas de espera para atracação", fontsize=10)
        ax.set_xlim(left=0)

    # Legenda global
    patches = [mpatches.Patch(color=c, alpha=0.75, label=a) for a, c in ALERTA_COR.items()]
    patches += [
        plt.Line2D([0], [0], marker="o",  color="#555", markersize=7, linestyle="None", label="p50 previsto"),
        plt.Line2D([0], [0], marker="|",  color="black", markersize=12, linewidth=2, linestyle="None", label="mediana histórica"),
        mpatches.Patch(color="#999", alpha=0.30, label="intervalo p25–p75"),
    ]
    fig.legend(handles=patches, loc="lower center", ncol=7, fontsize=9,
               bbox_to_anchor=(0.5, -0.04), framealpha=0.9)

    fig.tight_layout()
    out = FIGS / "forecast_t1.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {out}")


# ── Figura 3: Crescimento de rota + Importância de features ─────────────────────

def fig_rota_e_importancia(prev: pd.DataFrame, imp: pd.DataFrame) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(17, 8))
    fig.suptitle(
        "Harvest Oracle v3 — Estrutura da migração de rotas e modelo",
        fontsize=13, fontweight="bold", y=1.01,
    )

    # — Crescimento de rota (t+1, maio)
    bloco = (
        prev[prev["lag_meses"] == 1][["porto", "produto", "crescimento_rota_pct", "alerta"]]
        .dropna(subset=["crescimento_rota_pct"])
        .drop_duplicates(["porto", "produto"])
        .sort_values("crescimento_rota_pct")
        .reset_index(drop=True)
    )
    bloco["label"] = (
        bloco["porto"]
            .str.replace("Terminal Integrador Portuário Luiz Antonio Mesquita - TIPLAM", "TIPLAM")
            .str.replace("Terminal Marítimo Luiz Fogliatto - Termasa", "T. Termasa")
            .str.replace("Terminal Portuário ", "T.P. ")
            .str.replace("Terminal Vila do Conde", "T. Vila do Conde")
            .str.replace("Terminal Graneleiro Hermasa", "T. Hermasa")
            .str.replace("Terminal Ponta da Montanha", "T. Ponta da Montanha")
            .str[:34]
        + " / " + bloco["produto"]
    )

    y = np.arange(len(bloco))
    cores = ["#C62828" if v > 0 else "#1565C0" for v in bloco["crescimento_rota_pct"]]
    ax1.barh(y, bloco["crescimento_rota_pct"], color=cores, alpha=0.82, height=0.65)
    ax1.set_yticks(y)
    ax1.set_yticklabels(bloco["label"], fontsize=8)
    ax1.axvline(0, color="black", lw=1.0)
    ax1.set_xlabel("Crescimento anual de share de mercado  (% a.a., janela 3 anos)", fontsize=10)
    ax1.set_title(
        "Crescimento de rota por porto × produto\n"
        "Vermelho = ganhando share  |  Azul = perdendo share",
        fontsize=10,
    )

    # Rótulos com valor
    for i, (val, alerta) in enumerate(zip(bloco["crescimento_rota_pct"], bloco["alerta"])):
        offset = 1.0 if val >= 0 else -1.0
        ha = "left" if val >= 0 else "right"
        icone = {"CRITICO": "🔴", "ELEVADO": "🟠", "MODERADO": "🟡", "NORMAL": "🟢"}[alerta]
        ax1.text(val + offset, i, f"{val:+.0f}%  {icone}", va="center", ha=ha, fontsize=7.5)

    # — Feature importance
    imp_sorted = imp.sort_values("importancia").reset_index(drop=True)
    nova_cor = "#E07B39"
    cores_imp = [nova_cor if f == "crescimento_rota" else "#455A64" for f in imp_sorted["feature"]]
    bars = ax2.barh(imp_sorted["feature"], imp_sorted["importancia"],
                    color=cores_imp, alpha=0.85, height=0.65)
    ax2.set_xlabel("Importância média (LightGBM gain — modelos p50)", fontsize=10)
    ax2.set_title(
        "Importância das features\n"
        "Laranja = feature de migração estrutural de rota",
        fontsize=10,
    )
    for bar, val in zip(bars, imp_sorted["importancia"]):
        ax2.text(val + 15, bar.get_y() + bar.get_height() / 2,
                 f"{val:.0f}", va="center", fontsize=8.5, color="#333333")

    fig.tight_layout()
    out = FIGS / "rota_e_importancia.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {out}")


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[ 1/4 ] Carregando dados de migração (ANTAQ)...")
    df_mig = carregar_migracao()
    print(f"        {len(df_mig):,} registros porto×ano")

    print("[ 2/4 ] Treinando Harvest Oracle v3...")
    oracle = HarvestOracle()
    oracle.fit(verbose=True)

    print("[ 3/4 ] Gerando previsões...")
    prev = oracle.prever(meses=3)
    imp  = oracle.importancia_features()

    print("[ 4/4 ] Renderizando figuras...")
    fig_migracao(df_mig)
    fig_forecast(prev, min_vol_kt=3000)
    fig_rota_e_importancia(prev, imp)

    print(f"\nPronto. Figuras em: {FIGS.resolve()}/")
