"""
Cluster 5 — Infraestrutura

18. Saturação de berço como alerta — TaxaOcupacao > 70% × T1
19. Porto público vs privado          — comparação T2/T3/T4
20. Efeito de novos terminais          — diff-in-diff natural
21. PMO por natureza de carga ao longo do tempo
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao


# Mapeamento mês pt-br abreviado → número
MESES_PT = {"jan":1, "fev":2, "mar":3, "abr":4, "mai":5, "jun":6,
            "jul":7, "ago":8, "set":9, "out":10, "nov":11, "dez":12}


# ─── 18 — Saturação de berço como alerta ──────────────────────────────────────
def a18_saturacao_berco():
    secao(18, "Saturação de berço (TaxaOcupação) × T1 (espera de fundeio)")
    db = conectar()

    # Trabalhar a nível de IDBerco-ano-mes (evita explosão do join)
    df = db.sql(
        """
        WITH ocup AS (
          SELECT IDBerco,
                 AnoTaxaOcupacao  AS ano,
                 "MêsTaxaOcupacao" AS mes,
                 SUM(TempoEmMinutosdias) / (30.0 * 24 * 60) * 100 AS ocup_pct
          FROM TaxaOcupacao
          GROUP BY 1,2,3
        ),
        atr AS (
          SELECT IDBerco,
                 EXTRACT(year  FROM "Data Atracação")::INT AS ano,
                 LOWER(CASE EXTRACT(month FROM "Data Atracação")
                   WHEN 1 THEN 'jan' WHEN 2 THEN 'fev' WHEN 3 THEN 'mar'
                   WHEN 4 THEN 'abr' WHEN 5 THEN 'mai' WHEN 6 THEN 'jun'
                   WHEN 7 THEN 'jul' WHEN 8 THEN 'ago' WHEN 9 THEN 'set'
                   WHEN 10 THEN 'out' WHEN 11 THEN 'nov' WHEN 12 THEN 'dez' END) AS mes,
                 AVG(TEsperaAtracacao) AS T1_h,
                 COUNT(*)              AS atracacoes
          FROM atracacao_completa
          WHERE "Tipo de Operação" = 'Movimentação da Carga'
            AND TEstadia BETWEEN 0.5 AND 720
            AND "Data Atracação" >= '2020-01-01'
            AND IDBerco IS NOT NULL
          GROUP BY 1,2,3
        )
        SELECT o.IDBerco, o.ano, o.mes, o.ocup_pct, a.T1_h, a.atracacoes
        FROM ocup o JOIN atr a USING(IDBerco, ano, mes)
        WHERE o.ocup_pct > 0 AND a.atracacoes >= 3
        """
    ).df()

    df["bucket"] = pd.cut(df["ocup_pct"],
                          bins=[0, 30, 50, 70, 85, 100],
                          labels=["<30%", "30-50%", "50-70%", "70-85%", ">85%"])
    bucket = df.groupby("bucket", observed=True)["T1_h"].agg(["mean", "median", "count"])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].scatter(df["ocup_pct"], df["T1_h"], alpha=0.05, s=8, color="#3a64a8")
    # Bin médio
    bins = np.arange(0, 105, 5)
    df["b5"] = pd.cut(df["ocup_pct"], bins=bins)
    med = df.groupby("b5", observed=True)["T1_h"].median()
    axes[0].plot([(b.left+b.right)/2 for b in med.index], med.values,
                 color="#c1322f", lw=2.2, marker="o", label="mediana T1 por bucket")
    axes[0].axvspan(70, 100, alpha=0.10, color="red")
    axes[0].set_xlabel("Taxa de ocupação do berço (%)")
    axes[0].set_ylabel("T1 médio mensal (h)")
    axes[0].set_xlim(0, 100); axes[0].set_ylim(0, df["T1_h"].quantile(0.99))
    axes[0].set_title("T1 vs ocupação — alerta a partir de 70%")
    axes[0].legend(framealpha=0.9)

    bucket["mean"].plot(kind="bar", ax=axes[1], color="#3a64a8")
    axes[1].set_ylabel("T1 médio (h)")
    axes[1].set_title("T1 médio por faixa de ocupação")
    axes[1].tick_params(axis="x", rotation=0)
    salvar(fig, "18_saturacao_berco")

    print("  T1 médio por faixa de ocupação:")
    print(bucket.round(1).to_string())
    if (bucket["mean"].iloc[-1] > bucket["mean"].iloc[0] * 1.5):
        print(f"  → Berços > 70% ocupados têm T1 ~{bucket['mean'].iloc[-1]/bucket['mean'].iloc[0]:.1f}× maior que <30%.")
    return df


# ─── 19 — Porto público vs privado ────────────────────────────────────────────
def a19_publico_vs_privado():
    secao(19, "Porto público (Porto Organizado) vs privado (Terminal Autorizado)")
    db = conectar()
    df = db.sql(
        """
        SELECT a."Tipo da Autoridade Portuária" AS tipo,
               c."Natureza da Carga"           AS natureza,
               AVG(a.TEsperaAtracacao)          AS T1,
               AVG(a.TEsperaInicioOp)           AS T2,
               AVG(a.TOperacao)                 AS T3,
               AVG(a.TEsperaDesatracacao)       AS T4,
               AVG(a.TOperacao/NULLIF(a.TAtracado,0)) AS aproveitamento,
               COUNT(*) AS n
        FROM atracacao_completa a JOIN Carga c USING(IDAtracacao)
        WHERE a.Ano BETWEEN 2020 AND 2025
          AND a."Tipo de Operação"='Movimentação da Carga'
          AND a.TEstadia BETWEEN 0.5 AND 720
          AND a."Tipo da Autoridade Portuária" IS NOT NULL
          AND c.FlagMCOperacaoCarga=1
        GROUP BY 1,2
        """
    ).df()

    nats = sorted(df["natureza"].dropna().unique())
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(nats))
    width = 0.35
    pub = df[df["tipo"]=="Porto Organizado"].set_index("natureza")
    pri = df[df["tipo"]=="Terminal Autorizado"].set_index("natureza")

    for i, comp in enumerate(["T1", "T2", "T3", "T4"]):
        offset = (i-1.5)*0.06
        # nada — vamos plotar empilhado
    bottom_pub = np.zeros(len(nats)); bottom_pri = np.zeros(len(nats))
    cores = {"T1":"#d94747", "T2":"#f0a04b", "T3":"#5a9bd4", "T4":"#7fb069"}
    for comp in ["T1", "T2", "T3", "T4"]:
        v_pub = pub.reindex(nats)[comp].values
        v_pri = pri.reindex(nats)[comp].values
        ax.bar(x - width/2, v_pub, width, bottom=bottom_pub, label=f"Público — {comp}" if comp=="T1" else None,
               color=cores[comp], edgecolor="white", linewidth=0.5, alpha=0.9, hatch="//")
        ax.bar(x + width/2, v_pri, width, bottom=bottom_pri, label=f"Privado — {comp}" if comp=="T1" else None,
               color=cores[comp], edgecolor="white", linewidth=0.5, alpha=0.9)
        bottom_pub += np.nan_to_num(v_pub); bottom_pri += np.nan_to_num(v_pri)

    ax.set_xticks(x); ax.set_xticklabels(nats, rotation=15, fontsize=8)
    ax.set_ylabel("Horas (média 2020-25)")
    ax.set_title("Decomposição da estadia: Porto Organizado (//) vs Terminal Autorizado")
    handles = [plt.Rectangle((0,0), 1, 1, color=c, edgecolor="white") for c in cores.values()]
    ax.legend(handles, list(cores.keys()), loc="upper right", framealpha=0.9)
    salvar(fig, "19_publico_vs_privado")

    pub_mean = pub[["T1","T2","T3","T4"]].mean()
    pri_mean = pri[["T1","T2","T3","T4"]].mean()
    print("  Médias (h) por componente:")
    print(f"  {'':<6}  Público  Privado  Δ%")
    for c in ["T1", "T2", "T3", "T4"]:
        delta = (pri_mean[c]/pub_mean[c]-1)*100
        print(f"  {c:<6}  {pub_mean[c]:>7.1f}  {pri_mean[c]:>7.1f}  {delta:+5.0f}%")
    print("  Δ negativo significa privado mais rápido.")
    return df


# ─── 20 — Efeito de novos terminais (diff-in-diff natural) ────────────────────
def a20_novos_terminais():
    secao(20, "Novos terminais — diff-in-diff natural via primeira aparição de IDBerco")
    db = conectar()

    # Para cada IDBerco, primeiro ano. Define "novo" = berço apareceu >= 2018.
    novos = db.sql(
        """
        WITH primeiro AS (
          SELECT IDBerco, MIN(Ano) AS ano_inicio,
                 ANY_VALUE("Porto Atracação") AS porto
          FROM Atracacao
          WHERE IDBerco IS NOT NULL
          GROUP BY IDBerco
        )
        SELECT * FROM primeiro WHERE ano_inicio >= 2018
        """
    ).df()
    if novos.empty:
        print("  Nenhum berço novo identificado.")
        return novos

    # Toneladas por porto-ano para portos com berço novo vs outros
    df = db.sql(
        """
        SELECT a."Porto Atracação" AS porto, a.Ano,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1 AND a.Ano BETWEEN 2014 AND 2025
        GROUP BY 1,2
        """
    ).df()

    portos_novos = set(novos["porto"].unique())
    df["grupo"] = df["porto"].apply(lambda p: "Com berço novo" if p in portos_novos else "Demais")
    serie = (df.groupby(["Ano", "grupo"])["ton"].sum()
              .unstack("grupo").fillna(0))
    pct = serie.div(serie.iloc[0]).fillna(1.0)  # base = ano inicial

    fig, ax = plt.subplots()
    pct.plot(ax=ax, lw=2.2)
    ax.axvline(2018, color="grey", ls="--", lw=1, label="Primeiros berços novos (2018)")
    ax.set_ylabel("Volume (índice base 2014 = 1.0)")
    ax.set_title("Crescimento relativo: portos com berço novo (≥2018) vs demais")
    ax.legend(framealpha=0.9)
    salvar(fig, "20_novos_terminais")

    cresc_novo = pct.iloc[-1].get("Com berço novo", np.nan)
    cresc_outros = pct.iloc[-1].get("Demais", np.nan)
    print(f"  N portos com berço novo (≥2018): {len(portos_novos)}")
    print(f"  Crescimento 2014→{int(pct.index[-1])} portos novos: {cresc_novo:.2f}×  vs demais {cresc_outros:.2f}×")
    if cresc_novo > cresc_outros * 1.15:
        print("  → Berços novos têm efeito de capacidade visível: portos crescem acima da média.")
    return pct


# ─── 21 — PMO por natureza de carga ───────────────────────────────────────────
def a21_pmo_natureza():
    secao(21, "PMO (Prancha Média Operacional) por natureza de carga")
    db = conectar()
    df = db.sql(
        """
        SELECT a.Ano, c."Natureza da Carga" AS natureza,
               -- PMO ponderada: total tons / total horas operação
               SUM(c.VLPesoCargaBruta)::DOUBLE / NULLIF(SUM(a.TOperacao), 0) AS PMO_tph,
               SUM(c.VLPesoCargaBruta) AS ton,
               SUM(a.TOperacao)        AS horas
        FROM atracacao_completa a JOIN Carga c USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1 AND a.TOperacao > 0
          AND a."Tipo de Operação"='Movimentação da Carga'
          AND a.Ano BETWEEN 2010 AND 2025
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    pivot = df.pivot(index="Ano", columns="natureza", values="PMO_tph")

    fig, ax = plt.subplots()
    pivot.plot(ax=ax, lw=2)
    ax.set_ylabel("PMO — toneladas por hora de operação")
    ax.set_title("PMO ponderada por natureza de carga (tons/h)")
    ax.legend(framealpha=0.9, fontsize=8)
    salvar(fig, "21_pmo_natureza")

    print("  PMO médio últimos 3 anos × primeiros 3 anos:")
    n0 = pivot.head(3).mean()
    n1 = pivot.tail(3).mean()
    var = (n1/n0 - 1) * 100
    for c in pivot.columns:
        print(f"    {c[:22]:22s}  {n0[c]:>7.1f} → {n1[c]:>7.1f} t/h  ({var[c]:+5.0f}%)")
    if var.mean() > 5:
        print("  → Brasil ficou mais eficiente em média.")
    elif var.mean() < -5:
        print("  → Brasil ficou MENOS eficiente — sinal de saturação.")
    else:
        print("  → Eficiência relativamente estável.")
    return pivot


def main():
    a18_saturacao_berco()
    a19_publico_vs_privado()
    a20_novos_terminais()
    a21_pmo_natureza()


if __name__ == "__main__":
    main()
