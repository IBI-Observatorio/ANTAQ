"""
Cluster 1 — Eficiência Operacional

01. Decomposição T1-T4 por porto/ano  — razão T1/T3
02. Índice de aproveitamento do berço — T3/TA
03. Custo Brasil Portuário            — (T1+T2+T4) × ~US$25 k/dia
04. Curva de recuperação pós-COVID    — T2 mensal 2018–2025
05. Clustering de paralisações        — TemposAtracacaoParalisacao
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao, fmt


# ─── 01 — Decomposição T1-T4 por porto/ano ────────────────────────────────────
def a01_decomposicao_t1_t4(top_n: int = 15):
    """
    Decompõe a estadia (TE) em T1+T2+T3+T4 para os top portos por movimentação.
    Razão T1/T3: para cada hora operando, quantas horas se gastou esperando atracar?
    """
    secao(1, "Decomposição T1-T4 por porto/ano")
    db = conectar()

    df_nac = db.sql(
        """
        SELECT Ano,
               AVG(TEsperaAtracacao)     AS T1,
               AVG(TEsperaInicioOp)      AS T2,
               AVG(TOperacao)            AS T3,
               AVG(TEsperaDesatracacao)  AS T4
        FROM atracacao_completa
        WHERE "Tipo de Operação" = 'Movimentação da Carga'
          AND TEstadia BETWEEN 0.5 AND 720
        GROUP BY Ano ORDER BY Ano
        """
    ).df()

    df_top = db.sql(
        f"""
        WITH portos AS (
          SELECT a."Porto Atracação"      AS porto,
                 SUM(c.VLPesoCargaBruta)  AS t
          FROM Carga c JOIN Atracacao a USING(IDAtracacao)
          WHERE c.FlagMCOperacaoCarga = 1 AND c.Ano >= 2015
          GROUP BY 1 ORDER BY t DESC LIMIT {top_n}
        )
        SELECT a."Porto Atracação"        AS porto,
               AVG(a.TEsperaAtracacao)    AS T1,
               AVG(a.TEsperaInicioOp)     AS T2,
               AVG(a.TOperacao)           AS T3,
               AVG(a.TEsperaDesatracacao) AS T4,
               COUNT(*)                   AS atracacoes
        FROM atracacao_completa a
        JOIN portos p ON p.porto = a."Porto Atracação"
        WHERE a.Ano >= 2020 AND a.TEstadia BETWEEN 0.5 AND 720
          AND a."Tipo de Operação" = 'Movimentação da Carga'
        GROUP BY 1
        """
    ).df().set_index("porto")
    df_top["T1_sobre_T3"] = df_top["T1"] / df_top["T3"]
    df_top = df_top.sort_values("T1_sobre_T3", ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    ax = axes[0]
    df_nac.plot(x="Ano", y=["T1", "T2", "T3", "T4"], kind="bar", stacked=True, ax=ax,
                color=["#d94747", "#f0a04b", "#5a9bd4", "#7fb069"], width=0.85)
    ax.set_ylabel("Horas (média por atracação)")
    ax.set_title("Decomposição da estadia média Brasil — Movimentação da Carga")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.tick_params(axis="x", rotation=0)

    ax = axes[1]
    df_top[["T1", "T2", "T3", "T4"]].plot(kind="barh", stacked=True, ax=ax,
        color=["#d94747", "#f0a04b", "#5a9bd4", "#7fb069"])
    ax.set_xlabel("Horas (média 2020–2025)")
    ax.set_title(f"Top {top_n} portos — composição da estadia")
    ax.invert_yaxis()
    ax.legend(loc="lower right", framealpha=0.9)

    salvar(fig, "01_decomposicao_t1_t4")

    razao = df_top["T1_sobre_T3"]
    print(f"  T1/T3 média (top {top_n}): {razao.mean():.2f} h espera por h operada")
    print(f"  Pior:  {razao.idxmax():35s} {razao.max():.2f}")
    print(f"  Melhor:{razao.idxmin():35s} {razao.min():.2f}")
    print(f"  Interpretação: T1 nacional médio ~{df_nac.T1.mean():.1f}h vs T3 ~{df_nac.T3.mean():.1f}h.")
    return df_top


# ─── 02 — Índice de aproveitamento do berço (T3/TA) ───────────────────────────
def a02_aproveitamento_berco():
    """T3/TA — fração do tempo atracado que efetivamente vira operação."""
    secao(2, "Índice de aproveitamento do berço (T3/TA)")
    db = conectar()
    df = db.sql(
        """
        SELECT a.Ano                       AS Ano,
               c."Natureza da Carga"       AS natureza,
               AVG(a.TOperacao/a.TAtracado) AS aproveitamento,
               COUNT(*)                    AS n
        FROM atracacao_completa a JOIN Carga c USING(IDAtracacao)
        WHERE a.TAtracado > 1 AND a.TOperacao > 0 AND a.TOperacao <= a.TAtracado
          AND a."Tipo de Operação" = 'Movimentação da Carga'
          AND c.FlagMCOperacaoCarga = 1
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()

    pivot = df.pivot(index="Ano", columns="natureza", values="aproveitamento")
    fig, ax = plt.subplots()
    pivot.plot(ax=ax, lw=2)
    ax.set_ylim(0, 1)
    ax.axhspan(0.71, 0.77, alpha=0.10, color="grey", label="Faixa estagnada 2010-25")
    ax.set_title("Aproveitamento do berço T3/TA por natureza de carga")
    ax.set_ylabel("T3 / TA  (efetividade da atracação)")
    ax.legend(loc="lower right", framealpha=0.9, fontsize=8)
    salvar(fig, "02_aproveitamento_berco")

    medio_recente = pivot.loc[2020:].mean().mean()
    print(f"  Aproveitamento médio nacional 2020-25: {medio_recente:.1%}")
    print(f"  Granel sólido tipicamente o pior — depende muito de equipamentos terrestres.")
    return pivot


# ─── 03 — Custo Brasil Portuário ───────────────────────────────────────────────
def a03_custo_brasil(custo_dia_usd: float = 25_000, brl_usd: float = 5.20):
    """
    (T1+T2+T4) × custo de afretamento do navio = perda nacional anual.
    Soma sobre TODAS as atracações, não médias.
    """
    secao(3, "★ Custo Brasil Portuário")
    db = conectar()
    df = db.sql(
        """
        SELECT Ano,
               SUM(TEsperaAtracacao + TEsperaInicioOp + TEsperaDesatracacao) AS horas_perdidas,
               SUM(TEstadia)        AS horas_estadia,
               COUNT(*)             AS atracacoes
        FROM atracacao_completa
        WHERE "Tipo de Operação" = 'Movimentação da Carga'
          AND TEstadia BETWEEN 0.5 AND 720
        GROUP BY 1 ORDER BY 1
        """
    ).df()
    df["custo_usd"] = df["horas_perdidas"] / 24 * custo_dia_usd
    df["custo_brl"] = df["custo_usd"] * brl_usd
    df["pct_estadia"] = df["horas_perdidas"] / df["horas_estadia"]

    fig, ax = plt.subplots()
    ax.bar(df["Ano"], df["custo_brl"]/1e9, color="#c1322f")
    ax.set_ylabel("R$ bilhões (custo de tempo perdido)")
    ax.set_title(f"Custo Brasil Portuário — (T1+T2+T4)×US${custo_dia_usd/1000:.0f}k/dia")
    for _, r in df.iterrows():
        ax.text(r.Ano, r.custo_brl/1e9, f"{r.custo_brl/1e9:.1f}",
                ha="center", va="bottom", fontsize=8)
    salvar(fig, "03_custo_brasil_portuario")

    media_recente = df.query("Ano>=2020")["custo_brl"].mean() / 1e9
    print(f"  Custo médio anual 2020-25:   R$ {media_recente:.1f} bi")
    print(f"  Fração da estadia em espera: {df.pct_estadia.mean():.1%}")
    print(f"  Premissas: US$ {custo_dia_usd:,.0f}/dia × R$ {brl_usd:.2f}/USD; ajustar conforme afretamento real.")
    return df


# ─── 04 — Curva de recuperação pós-COVID (T2 mensal) ──────────────────────────
def a04_recuperacao_covid():
    secao(4, "Curva de recuperação pós-COVID (T2 mensal)")
    db = conectar()
    df = db.sql(
        """
        SELECT date_trunc('month', "Data Atracação")::DATE AS mes,
               AVG(TEsperaInicioOp) AS T2_h,
               AVG(TOperacao)       AS T3_h,
               COUNT(*)             AS n
        FROM atracacao_completa
        WHERE "Data Atracação" >= '2018-01-01' AND "Data Atracação" < '2026-01-01'
          AND "Tipo de Operação" = 'Movimentação da Carga'
          AND TEstadia BETWEEN 0.5 AND 720
        GROUP BY 1 ORDER BY 1
        """
    ).df()
    df["T2_roll"] = df["T2_h"].rolling(3, center=True).mean()

    fig, ax = plt.subplots()
    ax.plot(df["mes"], df["T2_h"], color="lightgrey", lw=0.8, label="T2 mensal")
    ax.plot(df["mes"], df["T2_roll"], color="#c1322f", lw=2, label="média móvel 3m")
    ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2021-06-01"),
               alpha=0.12, color="grey", label="Período COVID")
    ax.set_ylabel("T2 (espera atracação→início op) — horas")
    ax.set_title("T2 mensal 2018–2025 — efeito COVID e recuperação")
    ax.legend(framealpha=0.9)
    salvar(fig, "04_curva_covid_t2")

    pre   = df.query("'2018-01-01' <= mes < '2020-03-01'")["T2_h"].mean()
    covid = df.query("'2020-03-01' <= mes < '2021-06-01'")["T2_h"].mean()
    pos   = df.query("'2022-01-01' <= mes < '2026-01-01'")["T2_h"].mean()
    print(f"  T2 pré-COVID  (2018-19) : {pre:5.2f} h")
    print(f"  T2 COVID      (mar/20-mai/21): {covid:5.2f} h  ({covid/pre-1:+.0%})")
    print(f"  T2 pós-COVID  (2022-25): {pos:5.2f} h  ({pos/pre-1:+.0%})")
    if pos > pre * 1.05:
        print("  → Nova normalidade: T2 NÃO retornou ao patamar pré-COVID.")
    elif pos < pre * 0.95:
        print("  → Recuperação completa e além: T2 abaixo do pré-COVID.")
    else:
        print("  → Recuperação plena.")
    return df


# ─── 05 — Clustering de paralisações ──────────────────────────────────────────
def a05_paralisacoes():
    secao(5, "Clustering de paralisações")
    db = conectar()

    df = db.sql(
        """
        WITH base AS (
          SELECT DescricaoTempoDesconto AS motivo,
                 date_diff('minute',
                   TRY_CAST(DTInicio  AS TIMESTAMP),
                   TRY_CAST(DTTermino AS TIMESTAMP))/60.0 AS horas
          FROM TemposAtracacaoParalisacao
          WHERE Ano >= 2015 AND DTInicio IS NOT NULL AND DTTermino IS NOT NULL
        )
        SELECT motivo,
               COUNT(*) AS ocorrencias,
               SUM(horas) AS horas
        FROM base
        WHERE horas BETWEEN 0 AND 720
        GROUP BY 1
        """
    ).df()

    def classificar(s: str | None) -> str:
        if not s:
            return "Outro"
        s = s.lower()
        if re.search(r"chuv|vento|mar[é \-]|tempo|nevoeiro|maré|clim", s):  return "Climático"
        if re.search(r"quebr|defeit|aguard.*equip|manut|falha|conserto", s): return "Equipamento"
        if re.search(r"oper|paus|refeic|turno|troca de turma|jorna|greve", s): return "Mão-de-obra"
        if re.search(r"document|despach|liber|aduan|aut|alfan|fiscal", s):    return "Burocrático"
        if re.search(r"carga|descarga|porão|grão|cereal", s):                 return "Operacional"
        if re.search(r"acid|ocorr|incid", s):                                 return "Acidente"
        return "Outro"

    df["categoria"] = df["motivo"].map(classificar)
    cat = (df.groupby("categoria")
             .agg(ocorrencias=("ocorrencias", "sum"),
                  horas=("horas", "sum"))
             .sort_values("horas", ascending=False))
    cat["pct_horas"] = cat["horas"] / cat["horas"].sum()

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    cores = plt.cm.Set2(np.linspace(0, 1, len(cat)))
    axes[0].pie(cat["horas"], labels=cat.index, autopct="%1.0f%%", colors=cores)
    axes[0].set_title("Horas de paralisação por categoria (2015+)")
    cat["horas"].sort_values().plot(kind="barh", ax=axes[1], color=cores[::-1])
    axes[1].set_xlabel("Horas acumuladas")
    axes[1].set_title("Total de horas perdidas")
    salvar(fig, "05_paralisacoes")

    print(f"  Top 3 categorias (horas): {cat.head(3).index.tolist()}")
    evit = cat.loc[cat.index.isin(["Equipamento", "Burocrático", "Mão-de-obra"]), "pct_horas"].sum()
    print(f"  Categorias evitáveis (equip+burocra+mão-obra): {evit:.0%} do tempo perdido.")
    print(f"  Climático ~{cat.loc['Climático','pct_horas']:.0%} é o ‘piso natural’.")
    return cat


def main():
    a01_decomposicao_t1_t4()
    a02_aproveitamento_berco()
    a03_custo_brasil()
    a04_recuperacao_covid()
    a05_paralisacoes()


if __name__ == "__main__":
    main()
