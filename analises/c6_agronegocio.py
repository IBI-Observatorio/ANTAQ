"""
Cluster 6 — Agronegócio

22. Índice de Pressão Portuária na Safra — Granel Sólido / capacidade mensal
23. Lead time porto-a-porto na cabotagem
24. Anomalias de safra — desvios vs tendência (proxy de ENOS)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao


# Anos de El Niño / La Niña fortes (NOAA / CPTEC)
ENOS_ANOS = {
    2010: "La Niña",  2011: "La Niña",  2012: "Neutro/La Niña",
    2014: "Neutro",   2015: "El Niño",  2016: "El Niño",
    2017: "Neutro",   2018: "La Niña",  2019: "Neutro",
    2020: "La Niña",  2021: "La Niña",  2022: "La Niña",
    2023: "El Niño",  2024: "El Niño/La Niña", 2025: "Neutro/La Niña",
}


# ─── 22 — Índice de pressão portuária na safra ────────────────────────────────
def a22_pressao_safra():
    secao(22, "Índice de pressão portuária na safra")
    db = conectar()
    df = db.sql(
        """
        SELECT date_trunc('month', a."Data Atracação")::DATE AS mes,
               a."Região Geográfica" AS regiao,
               SUM(c.VLPesoCargaBruta) AS ton_granel
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1
          AND c."Natureza da Carga"='Granel Sólido'
          AND c.Sentido='Embarcados'
          AND a."Data Atracação" >= '2015-01-01' AND a."Data Atracação" < '2026-01-01'
          AND a."Região Geográfica" IN ('Norte','Nordeste','Sudeste','Sul')
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    pivot = df.pivot(index="mes", columns="regiao", values="ton_granel").fillna(0)
    # capacidade de referência = p90 mensal de cada região (média móvel p/ permitir crescimento)
    cap = pivot.rolling(24, min_periods=6).quantile(0.90)
    pressao = (pivot / cap).clip(upper=1.5)

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
    for ax, regiao in zip(axes.flat, pivot.columns):
        ax.plot(pivot.index, pressao[regiao], color="#3a64a8", lw=1.5)
        ax.axhline(1, color="grey", ls="--", lw=0.8)
        ax.fill_between(pivot.index, 1, pressao[regiao].where(pressao[regiao]>1),
                        color="red", alpha=0.3)
        ax.set_title(f"Pressão portuária — {regiao}")
        ax.set_ylabel("Volume / capacidade ref.")
    salvar(fig, "22_pressao_safra")

    pico = pressao.idxmax()
    pico_val = pressao.max()
    print("  Pico de pressão por região:")
    for r in pressao.columns:
        if pd.notna(pico[r]):
            print(f"    {r:10s}  {pico[r].strftime('%Y-%m')}  índice {pico_val[r]:.2f}")
    return pressao


# ─── 23 — Lead time porto-a-porto na cabotagem ────────────────────────────────
def a23_lead_time_cabotagem():
    """
    Para cada IDCarga em cabotagem que tem registro de origem e destino:
    diferença entre data média de atracação no destino e na origem.
    Aproximação: muitas vezes não temos ambos lados na mesma carga; usamos
    o fluxo agregado por par origem→destino.
    """
    secao(23, "Lead time porto-a-porto na cabotagem")
    db = conectar()

    # Para cabotagem, agregamos por (Origem, Destino) usando o sentido para saber
    # se a atracação é o lado de embarque (origem) ou desembarque (destino).
    df = db.sql(
        """
        SELECT o."Origem Nome"      AS origem,
               d."Nome Destino"     AS destino,
               c.Sentido,
               EXTRACT(epoch FROM a."Data Atracação")  AS t_epoch,
               c.VLPesoCargaBruta
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagCabotagemMovimentacao = 1
          AND a.Ano BETWEEN 2022 AND 2024
          AND c.Sentido IN ('Embarcados','Desembarcados')
          AND o."Origem Nome" IS NOT NULL AND d."Nome Destino" IS NOT NULL
          AND o."Origem Nome" <> d."Nome Destino"
        """
    ).df()

    g = (df.groupby(["origem", "destino", "Sentido"])
           .agg(t_epoch=("t_epoch", "mean"), ton=("VLPesoCargaBruta", "sum"))
           .reset_index())
    pivot_t = g.pivot_table(index=["origem","destino"], columns="Sentido",
                            values="t_epoch")
    pivot_v = g.pivot_table(index=["origem","destino"], columns="Sentido",
                            values="ton", aggfunc="sum")
    out = pd.DataFrame(index=pivot_t.index)
    out["lead_h"] = (pivot_t["Desembarcados"] - pivot_t["Embarcados"]) / 3600
    out["ton"]    = pivot_v.sum(axis=1)
    out = out.dropna(subset=["lead_h"])
    out = out[(out["lead_h"] > 24) & (out["lead_h"] < 720)]
    out["par"] = (out.index.get_level_values(0).str[:18] + " → "
                  + out.index.get_level_values(1).str[:18])
    top = out.sort_values("ton", ascending=False).head(15)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(top["par"], top["lead_h"]/24, color="#3a64a8")
    ax.set_xlabel("Lead time médio (dias)")
    ax.set_title("Lead time típico de pares de cabotagem (top 15 por volume)")
    ax.invert_yaxis()
    salvar(fig, "23_lead_time_cabotagem")

    print(f"  Lead time mediano (top 15 pares): {top['lead_h'].median()/24:.1f} dias")
    print(f"  Mais rápido: {top.loc[top.lead_h.idxmin(),'par']} ({top.lead_h.min()/24:.1f} d)")
    print(f"  Mais lento:  {top.loc[top.lead_h.idxmax(),'par']} ({top.lead_h.max()/24:.1f} d)")
    return top


# ─── 24 — Anomalias de safra × ENOS ───────────────────────────────────────────
def a24_anomalias_safra():
    secao(24, "Anomalias de safra (desvios vs tendência) × ENOS")
    db = conectar()

    df = db.sql(
        """
        SELECT a.Ano,
               m."Mercadoria" AS mercadoria,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        JOIN Mercadoria m ON c.CDMercadoria = m.CDMercadoria
        WHERE c.FlagMCOperacaoCarga=1
          AND c.Sentido='Embarcados'
          AND a.Ano BETWEEN 2010 AND 2025
          AND (UPPER(m."Mercadoria") LIKE '%SOJA%' OR UPPER(m."Mercadoria") LIKE '%MILHO%')
        GROUP BY 1,2
        """
    ).df()
    df["grupo"] = np.where(df["mercadoria"].str.upper().str.contains("SOJA"), "Soja", "Milho")
    g = df.groupby(["Ano", "grupo"])["ton"].sum().unstack("grupo")
    # Tendência polinomial grau 1
    anos = g.index.values
    detrend = pd.DataFrame(index=g.index)
    for col in g.columns:
        b, a = np.polyfit(anos, g[col].values, 1)
        tend = b*anos + a
        detrend[col] = (g[col] - tend) / tend  # desvio relativo

    fig, ax = plt.subplots()
    width = 0.4
    cores_enos = {"El Niño":"#d94747", "La Niña":"#3a64a8", "Neutro":"#999999"}
    for i, col in enumerate(detrend.columns):
        for ano, v in detrend[col].items():
            enos = ENOS_ANOS.get(int(ano), "Neutro")
            cor = "#d94747" if "El Niño" in enos else "#3a64a8" if "La Niña" in enos else "#999999"
            ax.bar(ano + (i-0.5)*width, v*100, width=width, color=cor,
                   alpha=0.85, edgecolor="white")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Desvio relativo da tendência (%)")
    ax.set_title("Anomalias de exportação de soja+milho × fase ENOS")
    handles = [plt.Rectangle((0,0),1,1,color=c) for c in cores_enos.values()]
    ax.legend(handles, cores_enos.keys(), loc="upper left", framealpha=0.9, fontsize=8)
    salvar(fig, "24_anomalias_enos")

    # Estatística simples: média de anomalia por fase ENOS
    df_anom = detrend.stack().rename("anom").reset_index()
    df_anom = df_anom.rename(columns={df_anom.columns[1]: "grupo"})
    df_anom["enos"] = df_anom["Ano"].map(lambda y: ENOS_ANOS.get(int(y), "Neutro"))
    df_anom["fase"] = df_anom["enos"].map(
        lambda s: "El Niño" if "El Niño" in s else "La Niña" if "La Niña" in s else "Neutro")
    media = df_anom.groupby(["grupo", "fase"])["anom"].mean().unstack("fase")*100
    print("  Anomalia média (% sobre tendência) por fase:")
    print(media.round(1).to_string())
    return detrend


def main():
    a22_pressao_safra()
    a23_lead_time_cabotagem()
    a24_anomalias_safra()


if __name__ == "__main__":
    main()
