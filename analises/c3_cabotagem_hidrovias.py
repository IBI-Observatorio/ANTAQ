"""
Cluster 3 — Cabotagem e Hidrovias

10. Revolução silenciosa da cabotagem  — TEUs cabotagem × longo curso
11. Elasticidade cabotagem × PIB       — drivers anuais
12. Tríade hidrográfica                — quais rios cresceram?
13. Corredor Norte (Arco Norte)        — emergência via hidrovia
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao
from .macro import pib_real_anual


# ─── 10 — Revolução silenciosa da cabotagem ───────────────────────────────────
def a10_cabotagem_vs_longo_curso():
    secao(10, "Cabotagem vs Longo Curso — TEUs anuais")
    db = conectar()
    df = db.sql(
        """
        SELECT Ano,
               SUM(CASE WHEN FlagCabotagemMovimentacao=1 THEN TEU ELSE 0 END) AS TEU_cabotagem,
               SUM(CASE WHEN FlagLongoCurso=1            THEN TEU ELSE 0 END) AS TEU_longocurso,
               SUM(CASE WHEN FlagCabotagemMovimentacao=1 THEN VLPesoCargaBruta ELSE 0 END) AS ton_cabotagem,
               SUM(CASE WHEN FlagLongoCurso=1            THEN VLPesoCargaBruta ELSE 0 END) AS ton_longocurso
        FROM Carga
        WHERE "Natureza da Carga"='Carga Conteinerizada'
          AND Ano BETWEEN 2010 AND 2025
        GROUP BY 1 ORDER BY 1
        """
    ).df().set_index("Ano")

    df["razao_cab_lc"] = df["TEU_cabotagem"] / df["TEU_longocurso"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].plot(df.index, df.TEU_cabotagem/1e6, label="Cabotagem", lw=2.2, color="#3a64a8")
    axes[0].plot(df.index, df.TEU_longocurso/1e6, label="Longo Curso", lw=2.2, color="#c1322f")
    axes[0].set_ylabel("Milhões de TEUs")
    axes[0].set_title("TEUs movimentados — cabotagem vs longo curso")
    axes[0].legend(framealpha=0.9)
    axes[1].bar(df.index, df.razao_cab_lc*100, color="#3a64a8")
    axes[1].set_ylabel("Cabotagem / Longo Curso (%)")
    axes[1].set_title("Razão TEUs cabotagem ÷ longo curso")
    salvar(fig, "10_cabotagem_vs_longo_curso")

    cresc = df["TEU_cabotagem"].iloc[-1] / df["TEU_cabotagem"].iloc[0] - 1
    print(f"  TEUs cabotagem  2010→{int(df.index[-1])}: {df.TEU_cabotagem.iloc[0]/1e6:.2f} M → "
          f"{df.TEU_cabotagem.iloc[-1]/1e6:.2f} M  ({cresc:+.0%})")
    print(f"  TEUs longo curso 2010→{int(df.index[-1])}: {df.TEU_longocurso.iloc[0]/1e6:.2f} M → "
          f"{df.TEU_longocurso.iloc[-1]/1e6:.2f} M  ({df.TEU_longocurso.iloc[-1]/df.TEU_longocurso.iloc[0]-1:+.0%})")
    razao_inicio, razao_fim = df.razao_cab_lc.iloc[0], df.razao_cab_lc.iloc[-1]
    if razao_fim < 1:
        # extrapolação simples log-linear sobre últimos 5 pontos
        anos_lin = df.tail(8).index.values
        log_r    = np.log(df.tail(8).razao_cab_lc.values)
        b, a = np.polyfit(anos_lin, log_r, 1)
        if b > 0:
            ano_cross = (-a) / b
            print(f"  Razão cabotagem/longo curso atual = {razao_fim:.2f}; extrapolada cruza 1.0 em ~{ano_cross:.0f}.")
        else:
            print(f"  Razão {razao_fim:.2f} estagnada/decrescente — sem cruzamento previsto.")
    else:
        print(f"  Cabotagem JÁ supera longo curso (razão {razao_fim:.2f}).")
    return df


# ─── 11 — Elasticidade cabotagem × PIB ────────────────────────────────────────
def a11_elasticidade_pib():
    secao(11, "Elasticidade cabotagem × PIB e câmbio")
    db = conectar()
    df = db.sql(
        """
        SELECT Ano,
               SUM(CASE WHEN FlagCabotagemMovimentacao=1 THEN VLPesoCargaBruta ELSE 0 END) AS ton_cab,
               SUM(CASE WHEN FlagLongoCurso=1            THEN VLPesoCargaBruta ELSE 0 END) AS ton_lc
        FROM Carga
        WHERE Ano BETWEEN 2010 AND 2025
        GROUP BY 1 ORDER BY 1
        """
    ).df().set_index("Ano")
    df["d_cab"]  = df["ton_cab"].pct_change()
    df["d_lc"]   = df["ton_lc"].pct_change()
    df["pib"]    = pib_real_anual().reindex(df.index) / 100

    elast_cab = df[["d_cab", "pib"]].dropna().corr().iloc[0, 1]
    elast_lc  = df[["d_lc", "pib"]].dropna().corr().iloc[0, 1]
    # OLS simples: y = α + β*pib
    cab = df.dropna(subset=["d_cab", "pib"])
    bcab = np.polyfit(cab["pib"], cab["d_cab"], 1)
    blc  = np.polyfit(cab["pib"], df.loc[cab.index, "d_lc"], 1)

    fig, ax = plt.subplots()
    ax.scatter(df["pib"]*100, df["d_cab"]*100, color="#3a64a8", s=60, label="Cabotagem")
    ax.scatter(df["pib"]*100, df["d_lc"]*100,  color="#c1322f", s=60, label="Longo Curso")
    xs = np.linspace(df["pib"].min(), df["pib"].max(), 50)*100
    ax.plot(xs, (bcab[0]*xs/100 + bcab[1])*100, color="#3a64a8", lw=1.2, ls="--")
    ax.plot(xs, (blc[0]*xs/100  + blc[1])*100,  color="#c1322f", lw=1.2, ls="--")
    ax.axhline(0, color="grey", lw=0.5); ax.axvline(0, color="grey", lw=0.5)
    ax.set_xlabel("Variação do PIB (%)")
    ax.set_ylabel("Variação anual do volume (%)")
    ax.set_title(f"Cabotagem β={bcab[0]:.2f} (corr {elast_cab:+.2f}) · LC β={blc[0]:.2f} (corr {elast_lc:+.2f})")
    ax.legend(framealpha=0.9)
    salvar(fig, "11_elasticidade_cab_pib")

    print(f"  β cabotagem  vs PIB: {bcab[0]:.2f}    corr {elast_cab:+.2f}")
    print(f"  β longo curso vs PIB: {blc[0]:.2f}    corr {elast_lc:+.2f}")
    if elast_cab > elast_lc:
        print("  → Cabotagem é o modal sensível ao consumo doméstico; longo curso responde a câmbio/commodities.")
    else:
        print("  → Sensibilidades comparáveis ou invertidas.")
    return df


# ─── 12 — Tríade hidrográfica ─────────────────────────────────────────────────
def a12_triade_hidrografica(top_rios: int = 12):
    secao(12, "Tríade hidrográfica — quais rios cresceram?")
    db = conectar()
    df = db.sql(
        """
        SELECT cr.Ano, cr.Rio, SUM(cr.ValorMovimentado) AS ton
        FROM CargaRio cr
        WHERE cr.Ano BETWEEN 2012 AND 2025
        GROUP BY 1,2
        """
    ).df()
    pivot = df.pivot(index="Ano", columns="Rio", values="ton").fillna(0)
    medias = pivot.mean().sort_values(ascending=False).head(top_rios)
    pivot_top = pivot[medias.index]

    inicio = pivot_top.iloc[:3].mean()
    fim    = pivot_top.iloc[-3:].mean()
    growth = (fim / inicio.replace(0, np.nan) - 1).sort_values(ascending=False).dropna()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    pivot_top.plot(ax=axes[0], lw=1.6)
    axes[0].set_title("Volume movimentado por rio (top hidrovias)")
    axes[0].set_ylabel("Toneladas")
    axes[0].legend(loc="upper left", fontsize=7, ncols=2)

    cores = ["#7fb069" if g > 0 else "#d94747" for g in growth]
    axes[1].barh(growth.index[::-1], growth.values[::-1]*100, color=cores[::-1])
    axes[1].axvline(0, color="grey", lw=0.5)
    axes[1].set_xlabel("Crescimento médias 2023-25 vs 2012-14 (%)")
    axes[1].set_title(f"Top {top_rios} rios — variação relativa")
    salvar(fig, "12_triade_hidrografica")

    print(f"  Maior crescimento: {growth.index[0]} ({growth.iloc[0]:+.0%})")
    print(f"  Maior queda:      {growth.index[-1]} ({growth.iloc[-1]:+.0%})")
    print(f"  Top 3 absoluto: {medias.head(3).index.tolist()}")
    return pivot_top


# ─── 13 — Corredor Norte (Arco Norte) ─────────────────────────────────────────
def a13_arco_norte():
    secao(13, "Corredor Norte (Arco Norte) — emergência")
    db = conectar()
    df = db.sql(
        """
        SELECT a.Ano,
               a."Região Geográfica" AS regiao,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Granel Sólido'
          AND a.Ano BETWEEN 2012 AND 2025
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    pivot = df.pivot(index="Ano", columns="regiao", values="ton").fillna(0)
    pct = pivot.div(pivot.sum(axis=1), axis=0)
    arco_norte = ["Norte", "Nordeste"]
    sul_se     = ["Sul", "Sudeste"]
    pct_arco = pct[arco_norte].sum(axis=1)
    pct_sul  = pct[sul_se].sum(axis=1)

    fig, ax = plt.subplots()
    ax.fill_between(pct.index, 0, pct_arco, color="#7fb069", alpha=0.85, label="Arco Norte (N+NE)")
    ax.fill_between(pct.index, pct_arco, pct_arco + pct_sul,
                    color="#3a64a8", alpha=0.85, label="Sul+Sudeste")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Share das exportações de granel sólido (toneladas)")
    ax.set_title("Migração Sul→Norte do escoamento de granéis sólidos")
    ax.legend(loc="lower left", framealpha=0.9)
    salvar(fig, "13_arco_norte")

    a0, an = pct_arco.iloc[0], pct_arco.iloc[-1]
    s0, sn = pct_sul.iloc[0], pct_sul.iloc[-1]
    print(f"  Arco Norte (N+NE) granel sólido: {a0:.0%} (2012) → {an:.0%} ({int(pct.index[-1])})  (Δ {an-a0:+.0%})")
    print(f"  Sul+Sudeste:                    {s0:.0%} → {sn:.0%}  (Δ {sn-s0:+.0%})")

    # Top 5 portos do Arco Norte
    top = db.sql(
        """
        SELECT a."Porto Atracação" AS porto, a."Região Geográfica" AS regiao,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1 AND c."Natureza da Carga"='Granel Sólido'
          AND a.Ano = 2024 AND a."Região Geográfica" IN ('Norte','Nordeste')
        GROUP BY 1,2 ORDER BY 3 DESC LIMIT 5
        """
    ).df()
    print("  Top 5 portos do Arco Norte (2024):")
    for _, r in top.iterrows():
        print(f"    {r.porto[:35]:35s} {r.ton/1e6:6.1f} Mt  ({r.regiao})")
    return pct


def main():
    a10_cabotagem_vs_longo_curso()
    a11_elasticidade_pib()
    a12_triade_hidrografica()
    a13_arco_norte()


if __name__ == "__main__":
    main()
