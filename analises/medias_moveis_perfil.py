"""
Médias móveis mensais por perfil de carga (Natureza da Carga).

Constrói série mensal de tonelagem para cada uma das 4 naturezas
(Granel Sólido, Granel Líquido e Gasoso, Carga Geral, Carga Conteinerizada),
sobreposta à média móvel centrada de 12 meses — suaviza sazonalidade e
revela tendência.

Filtro: FlagMCOperacaoCarga = 1 (evita dupla contagem em cabotagem).

Saídas:
    figs/analises/medias_moveis_perfil.png
    figs/analises/medias_moveis_perfil.csv
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from .utils import conectar, salvar, secao, fmt, FIGS


CORES = {
    "Granel Sólido":            "#7fb069",
    "Granel Líquido e Gasoso":  "#d94747",
    "Carga Geral":              "#f0a04b",
    "Carga Conteinerizada":     "#5a9bd4",
}

JANELA = 12  # meses


def serie_mensal_por_natureza(janela: int = JANELA,
                              ano_inicio: int = 2010) -> pd.DataFrame:
    """Retorna DataFrame com colunas: data, natureza, toneladas, ma12, yoy_ma."""
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            c."Natureza da Carga"                          AS natureza,
            SUM(c.VLPesoCargaBruta)                        AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).df()

    df["data"] = pd.to_datetime(df["data"])

    # pivot para alinhar índice temporal e aplicar rolling por coluna
    wide = (df.pivot(index="data", columns="natureza", values="toneladas")
              .sort_index()
              .asfreq("MS"))                      # garante mensal completo

    # remove o último mês se incompleto (heurística: < 50% da média recente)
    media_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * media_recente:
        wide = wide.iloc[:-1]

    ma = wide.rolling(janela, min_periods=janela).mean()
    yoy = ma.pct_change(12) * 100   # crescimento da MA12 vs 12 meses atrás

    long = (wide.stack().rename("toneladas").reset_index()
            .merge(ma.stack().rename("ma12").reset_index(), on=["data", "natureza"])
            .merge(yoy.stack().rename("yoy_ma_pct").reset_index(),
                   on=["data", "natureza"], how="left"))
    return long


def plotar(df: pd.DataFrame, janela: int = JANELA) -> None:
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)

    for ax, nat in zip(axes.flat, naturezas):
        sub = df[df["natureza"] == nat].sort_values("data")
        if sub.empty:
            ax.set_visible(False)
            continue
        cor = CORES.get(nat, "#444")

        # série mensal bruta (linha fina)
        ax.plot(sub["data"], sub["toneladas"] / 1e6,
                color=cor, alpha=0.30, lw=0.9, label="Mensal")
        # MA12 (linha grossa)
        ax.plot(sub["data"], sub["ma12"] / 1e6,
                color=cor, lw=2.2, label=f"MM{janela}m")

        # último ponto da MA + variação a/a da MA
        ultimo = sub.dropna(subset=["ma12"]).iloc[-1]
        ax.scatter([ultimo["data"]], [ultimo["ma12"] / 1e6],
                   color=cor, s=40, zorder=5)
        yoy = ultimo.get("yoy_ma_pct")
        rotulo = (f"{ultimo['ma12']/1e6:,.1f} Mt"
                  + (f"  ({yoy:+.1f}% a/a)" if pd.notna(yoy) else ""))
        ax.annotate(rotulo,
                    xy=(ultimo["data"], ultimo["ma12"] / 1e6),
                    xytext=(-8, 10), textcoords="offset points",
                    fontsize=9, color=cor, fontweight="bold",
                    ha="right")

        ax.set_title(nat, fontsize=12, fontweight="bold", color=cor)
        ax.set_ylabel("Milhões de toneladas / mês")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.legend(loc="upper left", framealpha=0.85, fontsize=9)

    fig.suptitle(
        f"Movimentação portuária mensal por perfil de carga — média móvel {janela}m",
        fontsize=13, fontweight="bold", y=1.00,
    )
    fig.text(0.5, -0.01,
             "Fonte: ANTAQ — Base Estatística Aquaviária (FlagMCOperacaoCarga = 1)",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "medias_moveis_perfil")


def _serie_mensal_por_dim(dimensao_sql: str,
                          dimensao_alias: str,
                          valores: list[str],
                          janela: int = JANELA,
                          ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Constrói série mensal por (natureza, dimensão) e aplica MA12.
    `dimensao_sql` é a expressão SQL que produz a coluna de quebra
    (ex.: 'c.Sentido' ou 'c."Tipo Navegação"').
    """
    db = conectar()
    valores_in = ",".join(f"'{v}'" for v in valores)
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            c."Natureza da Carga"                          AS natureza,
            {dimensao_sql}                                 AS {dimensao_alias},
            SUM(c.VLPesoCargaBruta)                        AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND {dimensao_sql} IN ({valores_in})
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])

    # MA12 por (natureza, dimensão)
    df = df.sort_values(["natureza", dimensao_alias, "data"])
    df["ma12"] = (df.groupby(["natureza", dimensao_alias])["toneladas"]
                    .transform(lambda s: s.rolling(janela, min_periods=janela).mean()))
    df["yoy_ma_pct"] = (df.groupby(["natureza", dimensao_alias])["ma12"]
                         .transform(lambda s: s.pct_change(12) * 100))

    # descartar último mês se parcial (mesmo critério da função principal)
    ult = df["data"].max()
    total_ult = df[df["data"] == ult]["toneladas"].sum()
    media_recente = (df[df["data"] < ult]
                     .groupby("data")["toneladas"].sum().tail(12).mean())
    if total_ult < 0.5 * media_recente:
        df = df[df["data"] < ult]
    return df


def _plotar_por_dim(df: pd.DataFrame,
                    dimensao: str,
                    cores: dict[str, str],
                    titulo: str,
                    nome_arquivo: str,
                    janela: int = JANELA) -> None:
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)

    for ax, nat in zip(axes.flat, naturezas):
        sub_nat = df[df["natureza"] == nat]
        if sub_nat.empty:
            ax.set_visible(False)
            continue

        for valor, cor in cores.items():
            sub = sub_nat[sub_nat[dimensao] == valor].sort_values("data")
            if sub.empty:
                continue
            ax.plot(sub["data"], sub["ma12"] / 1e6,
                    color=cor, lw=2.0, label=valor)
            ult = sub.dropna(subset=["ma12"]).tail(1)
            if not ult.empty:
                u = ult.iloc[0]
                yoy = u["yoy_ma_pct"]
                rotulo = (f"{u['ma12']/1e6:,.1f} Mt"
                          + (f"  ({yoy:+.1f}%)" if pd.notna(yoy) else ""))
                ax.scatter([u["data"]], [u["ma12"] / 1e6],
                           color=cor, s=30, zorder=5)
                ax.annotate(rotulo,
                            xy=(u["data"], u["ma12"] / 1e6),
                            xytext=(-6, 8), textcoords="offset points",
                            fontsize=8.5, color=cor, fontweight="bold",
                            ha="right")

        ax.set_title(nat, fontsize=12, fontweight="bold",
                     color=CORES.get(nat, "#444"))
        ax.set_ylabel("Milhões de toneladas / mês (MM12)")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.legend(loc="upper left", framealpha=0.85, fontsize=9)

    fig.suptitle(titulo, fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "Fonte: ANTAQ — Base Estatística Aquaviária (FlagMCOperacaoCarga = 1)",
             ha="center", fontsize=9, color="#666")
    salvar(fig, nome_arquivo)


def total_brasil(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Movimentação portuária total (todas as naturezas somadas), mensal,
    com MM12 e soma móvel de 12 meses (= movimentação anual rolante).
    """
    secao(0, f"Movimentação total Brasil — MM{janela}m + soma 12m rolante")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            SUM(c.VLPesoCargaBruta)                        AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    df = df.set_index("data").asfreq("MS")

    # descarte do último mês se parcial
    media_recente = df["toneladas"].iloc[-13:-1].mean()
    if df["toneladas"].iloc[-1] < 0.5 * media_recente:
        df = df.iloc[:-1]

    df["ma12"]   = df["toneladas"].rolling(janela, min_periods=janela).mean()
    df["sum12"]  = df["toneladas"].rolling(12, min_periods=12).sum()
    df["yoy_sum"] = df["sum12"].pct_change(12) * 100
    df = df.reset_index()

    out_csv = FIGS / "medias_moveis_total.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    # Painel 1 — mensal + MM12
    ax1.plot(df["data"], df["toneladas"] / 1e6,
             color="#5a9bd4", alpha=0.30, lw=0.9, label="Mensal")
    ax1.plot(df["data"], df["ma12"] / 1e6,
             color="#0c4a76", lw=2.4, label=f"MM{janela}m")
    u1 = df.dropna(subset=["ma12"]).iloc[-1]
    ax1.scatter([u1["data"]], [u1["ma12"] / 1e6],
                color="#0c4a76", s=45, zorder=5)
    ax1.annotate(f"{u1['ma12']/1e6:,.1f} Mt/mês",
                 xy=(u1["data"], u1["ma12"] / 1e6),
                 xytext=(-8, 10), textcoords="offset points",
                 fontsize=10, color="#0c4a76", fontweight="bold", ha="right")
    ax1.set_title(f"Movimentação mensal Brasil — MM{janela}m",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Milhões de toneladas / mês")
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.legend(loc="upper left", framealpha=0.9)

    # Painel 2 — soma 12m rolante (= movimentação anual rolante)
    ax2.plot(df["data"], df["sum12"] / 1e6,
             color="#7fb069", lw=2.4, label="Soma 12m rolante")
    u2 = df.dropna(subset=["sum12"]).iloc[-1]
    ax2.scatter([u2["data"]], [u2["sum12"] / 1e6],
                color="#7fb069", s=45, zorder=5)
    yoy = u2["yoy_sum"]
    rotulo = f"{u2['sum12']/1e6:,.0f} Mt"
    if pd.notna(yoy):
        rotulo += f"\n({yoy:+.1f}% a/a)"
    ax2.annotate(rotulo,
                 xy=(u2["data"], u2["sum12"] / 1e6),
                 xytext=(-8, -25), textcoords="offset points",
                 fontsize=10, color="#2a7f3f", fontweight="bold", ha="right")
    ax2.set_title("Movimentação anual rolante (soma 12 meses)",
                  fontsize=12, fontweight="bold")
    ax2.set_ylabel("Milhões de toneladas (12 meses)")
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.legend(loc="upper left", framealpha=0.9)

    fig.suptitle("Movimentação portuária total — Brasil",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — Base Estatística Aquaviária (FlagMCOperacaoCarga = 1, todas as naturezas)",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "medias_moveis_total")
    print(f"  PNG salvo: {FIGS / 'medias_moveis_total.png'}")

    # Resumo: tabela anos-calendário fechados + último rolante
    print(f"\nMovimentação anual (anos-calendário fechados, em Mt):\n")
    anuais = (df.assign(ano=df["data"].dt.year)
                .groupby("ano")["toneladas"].sum() / 1e6)
    # marca anos parciais (último mês na base)
    ult_mes_ano = df["data"].max()
    anos_completos = anuais.index[anuais.index < ult_mes_ano.year]
    serie_completa = anuais.loc[anos_completos]
    crescimento = serie_completa.pct_change() * 100
    ma3 = serie_completa.rolling(3, min_periods=3).mean()
    print(f"  {'Ano':>6} {'Mt':>10}  {'a/a':>8}  {'MM3 anos':>10}")
    print("  " + "-" * 42)
    for ano, v in serie_completa.items():
        g = crescimento.loc[ano]
        m = ma3.loc[ano]
        g_str = f"{g:+.1f}%" if pd.notna(g) else "—"
        m_str = f"{m:,.1f}" if pd.notna(m) else "—"
        print(f"  {ano:>6} {v:>10,.1f}  {g_str:>8}  {m_str:>10}")
    if ult_mes_ano.month < 12:
        parcial = anuais.loc[ult_mes_ano.year]
        print(f"  {ult_mes_ano.year:>6} {parcial:>10,.1f}  (parcial até {ult_mes_ano.strftime('%Y-%m')})")
    print(f"\n  Soma 12m rolante mais recente: {u2['sum12']/1e6:,.0f} Mt  ({yoy:+.1f}% a/a)")
    return df


def total_navegacao(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Movimentação total Brasil dividida em Cabotagem vs Longo Curso,
    com MM12 e soma 12m rolante (movimentação anual rolante por navegação).
    """
    secao(0, f"Total Brasil — Cabotagem vs Longo Curso (MM{janela}m)")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            c."Tipo Navegação"                             AS navegacao,
            SUM(c.VLPesoCargaBruta)                        AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
          AND c."Tipo Navegação" IN ('Cabotagem', 'Longo Curso')
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])

    wide = (df.pivot(index="data", columns="navegacao", values="toneladas")
              .sort_index().asfreq("MS"))

    # descarta último mês se parcial
    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    ma   = wide.rolling(janela, min_periods=janela).mean()
    sum12 = wide.rolling(12, min_periods=12).sum()
    yoy  = sum12.pct_change(12) * 100

    long = (wide.stack().rename("toneladas").reset_index()
            .merge(ma.stack().rename("ma12").reset_index(),
                   on=["data", "navegacao"])
            .merge(sum12.stack().rename("sum12").reset_index(),
                   on=["data", "navegacao"])
            .merge(yoy.stack().rename("yoy_sum_pct").reset_index(),
                   on=["data", "navegacao"], how="left"))

    out_csv = FIGS / "medias_moveis_total_navegacao.csv"
    long.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    cores = {"Longo Curso": "#d97742", "Cabotagem": "#5a9bd4"}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    # Painel 1 — MM12 das duas séries
    for nav, cor in cores.items():
        if nav not in wide.columns:
            continue
        ax1.plot(wide.index, wide[nav] / 1e6,
                 color=cor, alpha=0.25, lw=0.8)
        ax1.plot(ma.index, ma[nav] / 1e6,
                 color=cor, lw=2.4, label=f"{nav} (MM{janela}m)")
        ult_ma = ma[nav].dropna()
        if not ult_ma.empty:
            x_u, y_u = ult_ma.index[-1], ult_ma.iloc[-1]
            ax1.scatter([x_u], [y_u / 1e6], color=cor, s=40, zorder=5)
            ax1.annotate(f"{y_u/1e6:,.1f} Mt/mês",
                         xy=(x_u, y_u / 1e6),
                         xytext=(-8, 10), textcoords="offset points",
                         fontsize=10, color=cor, fontweight="bold", ha="right")

    ax1.set_title(f"Movimentação mensal — MM{janela}m",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Milhões de toneladas / mês")
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.legend(loc="upper left", framealpha=0.9)

    # Painel 2 — soma 12m rolante (movimentação anual)
    for nav, cor in cores.items():
        if nav not in wide.columns:
            continue
        ax2.plot(sum12.index, sum12[nav] / 1e6,
                 color=cor, lw=2.4, label=nav)
        ult_s = sum12[nav].dropna()
        if not ult_s.empty:
            x_u, y_u = ult_s.index[-1], ult_s.iloc[-1]
            yoy_u = yoy[nav].iloc[-1] if nav in yoy.columns else None
            rotulo = f"{y_u/1e6:,.0f} Mt"
            if pd.notna(yoy_u):
                rotulo += f"  ({yoy_u:+.1f}% a/a)"
            ax2.scatter([x_u], [y_u / 1e6], color=cor, s=40, zorder=5)
            ax2.annotate(rotulo,
                         xy=(x_u, y_u / 1e6),
                         xytext=(-8, 10), textcoords="offset points",
                         fontsize=10, color=cor, fontweight="bold", ha="right")

    ax2.set_title("Movimentação anual rolante (soma 12 meses)",
                  fontsize=12, fontweight="bold")
    ax2.set_ylabel("Milhões de toneladas (12 meses)")
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.legend(loc="upper left", framealpha=0.9)

    fig.suptitle("Movimentação portuária total Brasil — Cabotagem vs Longo Curso",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — Base Estatística Aquaviária (FlagMCOperacaoCarga = 1)",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "medias_moveis_total_navegacao")
    print(f"  PNG salvo: {FIGS / 'medias_moveis_total_navegacao.png'}")

    # Resumo anual fechado
    print(f"\nMovimentação anual (anos-calendário fechados, em Mt):\n")
    ult_mes = wide.index.max()
    anos_completos = sorted({d.year for d in wide.index if d.year < ult_mes.year})
    anuais = {nav: wide[nav].groupby(wide.index.year).sum() / 1e6
              for nav in cores if nav in wide.columns}
    print(f"  {'Ano':>6}  {'Cabotagem':>10} {'a/a':>7}  "
          f"{'Longo Curso':>12} {'a/a':>7}  {'Total':>9}")
    print("  " + "-" * 65)
    prev = {}
    for ano in anos_completos:
        cab = anuais.get("Cabotagem", pd.Series()).get(ano, float("nan"))
        lc  = anuais.get("Longo Curso", pd.Series()).get(ano, float("nan"))
        g_cab = (cab / prev.get("Cabotagem") - 1) * 100 if prev.get("Cabotagem") else None
        g_lc  = (lc  / prev.get("Longo Curso") - 1) * 100 if prev.get("Longo Curso") else None
        gcs = f"{g_cab:+.1f}%" if g_cab is not None and pd.notna(g_cab) else "—"
        gls = f"{g_lc:+.1f}%" if g_lc  is not None and pd.notna(g_lc)  else "—"
        print(f"  {ano:>6}  {cab:>10,.1f} {gcs:>7}  "
              f"{lc:>12,.1f} {gls:>7}  {cab+lc:>9,.1f}")
        prev["Cabotagem"], prev["Longo Curso"] = cab, lc

    print(f"\nSoma 12m rolante até {ult_mes.strftime('%Y-%m')}:")
    for nav in cores:
        if nav not in sum12.columns:
            continue
        s = sum12[nav].dropna().iloc[-1] / 1e6
        y = yoy[nav].dropna().iloc[-1]
        print(f"  {nav:<12}  {s:>7,.0f} Mt   ({y:+.1f}% a/a)")

    return long


def cabotagem_domestica(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Cabotagem nominal vs cabotagem doméstica pura (expurgando offshore).
    Offshore = FlagOffshore = 1 (FPSOs/ZEE → litoral).
    """
    secao(0, "Cabotagem nominal vs doméstica (expurga offshore)")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            CASE WHEN c.FlagOffshore = 1 THEN 'Offshore (FPSO/ZEE)'
                 ELSE 'Cabotagem doméstica' END             AS categoria,
            SUM(c.VLPesoCargaBruta)                         AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Cabotagem'
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="categoria", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))

    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    ma    = wide.rolling(janela, min_periods=janela).mean()
    sum12 = wide.rolling(12, min_periods=12).sum()
    yoy   = sum12.pct_change(12) * 100

    out_csv = FIGS / "medias_moveis_cabotagem_domestica.csv"
    wide.assign(cabotagem_total=wide.sum(axis=1)).to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    cores = {"Cabotagem doméstica": "#2a7f3f",
             "Offshore (FPSO/ZEE)": "#b54848"}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    for cat, cor in cores.items():
        if cat not in wide.columns:
            continue
        ax1.plot(ma.index, ma[cat] / 1e6,
                 color=cor, lw=2.4, label=f"{cat} (MM{janela}m)")
        u = ma[cat].dropna()
        if not u.empty:
            ax1.scatter([u.index[-1]], [u.iloc[-1] / 1e6], color=cor, s=40, zorder=5)
            ax1.annotate(f"{u.iloc[-1]/1e6:,.1f} Mt/mês",
                         xy=(u.index[-1], u.iloc[-1] / 1e6),
                         xytext=(-8, 10), textcoords="offset points",
                         fontsize=10, color=cor, fontweight="bold", ha="right")

    ax1.set_title(f"Cabotagem — MM{janela}m mensal",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Milhões de toneladas / mês")
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.legend(loc="upper left", framealpha=0.9)

    for cat, cor in cores.items():
        if cat not in wide.columns:
            continue
        ax2.plot(sum12.index, sum12[cat] / 1e6, color=cor, lw=2.4, label=cat)
        s = sum12[cat].dropna()
        if not s.empty:
            yu = yoy[cat].dropna()
            rotulo = f"{s.iloc[-1]/1e6:,.0f} Mt"
            if not yu.empty:
                rotulo += f"  ({yu.iloc[-1]:+.1f}% a/a)"
            ax2.scatter([s.index[-1]], [s.iloc[-1] / 1e6],
                        color=cor, s=40, zorder=5)
            ax2.annotate(rotulo,
                         xy=(s.index[-1], s.iloc[-1] / 1e6),
                         xytext=(-8, 10), textcoords="offset points",
                         fontsize=10, color=cor, fontweight="bold", ha="right")

    ax2.set_title("Soma 12m rolante (movimentação anual)",
                  fontsize=12, fontweight="bold")
    ax2.set_ylabel("Milhões de toneladas (12 meses)")
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.legend(loc="upper left", framealpha=0.9)

    fig.suptitle(
        "Cabotagem brasileira — doméstica vs offshore (FPSO/ZEE)",
        fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — FlagMCOperacaoCarga = 1, Tipo Navegação = Cabotagem",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "medias_moveis_cabotagem_domestica")
    print(f"  PNG salvo: {FIGS / 'medias_moveis_cabotagem_domestica.png'}")

    print("\nMovimentação anual (Mt) — anos fechados:\n")
    anuais = wide.groupby(wide.index.year).sum() / 1e6
    ult_ano = wide.index.max().year
    anuais = anuais[anuais.index < ult_ano]
    print(f"  {'Ano':>6} {'Doméstica':>11}  {'Offshore':>10}  "
          f"{'Total':>9}  {'% offshore':>11}")
    print("  " + "-" * 56)
    for ano, row in anuais.iterrows():
        dom = row.get("Cabotagem doméstica", 0.0)
        off = row.get("Offshore (FPSO/ZEE)", 0.0)
        tot = dom + off
        pct = off / tot * 100 if tot else 0
        print(f"  {ano:>6} {dom:>11,.1f}  {off:>10,.1f}  "
              f"{tot:>9,.1f}  {pct:>10.1f}%")
    return wide


def cabotagem_por_natureza(janela: int = JANELA, ano_inicio: int = 2010,
                            excluir_offshore: bool = True) -> pd.DataFrame:
    """
    Cabotagem decomposta por natureza (Granel Sólido/Líquido, Carga Geral, Conteineriz.).
    Por padrão expurga offshore (FlagOffshore != 1) → cabotagem doméstica pura.
    """
    rotulo = "doméstica (sem offshore)" if excluir_offshore else "nominal"
    secao(0, f"Cabotagem {rotulo} por natureza — MM{janela}m")

    db = conectar()
    filtro_off = "AND COALESCE(c.FlagOffshore,0) = 0" if excluir_offshore else ""
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            c."Natureza da Carga"                          AS natureza,
            SUM(c.VLPesoCargaBruta)                        AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Cabotagem'
          {filtro_off}
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="natureza", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))

    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    ma    = wide.rolling(janela, min_periods=janela).mean()
    sum12 = wide.rolling(12, min_periods=12).sum()
    yoy   = sum12.pct_change(12) * 100

    out_csv = FIGS / f"medias_moveis_cabotagem_natureza{'_dom' if excluir_offshore else ''}.csv"
    wide.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))
    for nat in naturezas:
        if nat not in ma.columns:
            continue
        cor = CORES[nat]
        ax1.plot(ma.index, ma[nat] / 1e6,
                 color=cor, lw=2.2, label=nat)
        u = ma[nat].dropna()
        if not u.empty:
            ax1.scatter([u.index[-1]], [u.iloc[-1] / 1e6],
                        color=cor, s=35, zorder=5)
            ax1.annotate(f"{u.iloc[-1]/1e6:,.1f} Mt",
                         xy=(u.index[-1], u.iloc[-1] / 1e6),
                         xytext=(-6, 8), textcoords="offset points",
                         fontsize=9, color=cor, fontweight="bold", ha="right")

        ax2.plot(sum12.index, sum12[nat] / 1e6,
                 color=cor, lw=2.2, label=nat)
        s = sum12[nat].dropna()
        if not s.empty:
            yu = yoy[nat].dropna()
            rotulo_y = f"{s.iloc[-1]/1e6:,.0f} Mt"
            if not yu.empty:
                rotulo_y += f"  ({yu.iloc[-1]:+.1f}%)"
            ax2.scatter([s.index[-1]], [s.iloc[-1] / 1e6],
                        color=cor, s=35, zorder=5)
            ax2.annotate(rotulo_y,
                         xy=(s.index[-1], s.iloc[-1] / 1e6),
                         xytext=(-6, 8), textcoords="offset points",
                         fontsize=9, color=cor, fontweight="bold", ha="right")

    ax1.set_title(f"MM{janela}m mensal", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Mt / mês")
    ax2.set_title("Soma 12m rolante", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Mt (12 meses)")
    for ax in (ax1, ax2):
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.legend(loc="upper left", framealpha=0.9, fontsize=9)

    fig.suptitle(f"Cabotagem {rotulo} por natureza da carga",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — FlagMCOperacaoCarga=1, Tipo Navegação=Cabotagem"
             + (", FlagOffshore=0" if excluir_offshore else ""),
             ha="center", fontsize=9, color="#666")
    nome = f"medias_moveis_cabotagem_natureza{'_dom' if excluir_offshore else ''}"
    salvar(fig, nome)
    print(f"  PNG salvo: {FIGS / (nome + '.png')}")

    print("\nÚltima soma 12m rolante por natureza:\n")
    for nat in naturezas:
        if nat not in sum12.columns:
            continue
        s = sum12[nat].dropna()
        if s.empty:
            continue
        y = yoy[nat].dropna()
        y_str = f"{y.iloc[-1]:+.1f}%" if not y.empty else "—"
        print(f"  {nat:<28} {s.iloc[-1]/1e6:>7,.1f} Mt   ({y_str})")
    return wide


def longocurso_por_sentido(janela: int = JANELA,
                            ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Longo Curso decomposto em Embarcados (exportação) vs Desembarcados (importação).
    """
    secao(0, f"Longo Curso por sentido (exportação vs importação) — MM{janela}m")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            c.Sentido                                       AS sentido,
            SUM(c.VLPesoCargaBruta)                         AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Longo Curso'
          AND c.Sentido IN ('Embarcados', 'Desembarcados')
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="sentido", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))

    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    ma    = wide.rolling(janela, min_periods=janela).mean()
    sum12 = wide.rolling(12, min_periods=12).sum()
    yoy   = sum12.pct_change(12) * 100
    saldo_12m = sum12["Embarcados"] - sum12["Desembarcados"]

    out_csv = FIGS / "medias_moveis_longocurso_sentido.csv"
    (wide.assign(saldo_mensal=wide["Embarcados"] - wide["Desembarcados"])
         .to_csv(out_csv, encoding="utf-8"))
    print(f"  CSV salvo: {out_csv}")

    cores = {"Embarcados": "#2a7f3f", "Desembarcados": "#b54848"}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    for sent, cor in cores.items():
        ax1.plot(ma.index, ma[sent] / 1e6, color=cor, lw=2.4,
                 label=f"{sent} (MM{janela}m)")
        u = ma[sent].dropna()
        if not u.empty:
            ax1.scatter([u.index[-1]], [u.iloc[-1] / 1e6],
                        color=cor, s=40, zorder=5)
            ax1.annotate(f"{u.iloc[-1]/1e6:,.1f} Mt/mês",
                         xy=(u.index[-1], u.iloc[-1] / 1e6),
                         xytext=(-8, 10), textcoords="offset points",
                         fontsize=10, color=cor, fontweight="bold", ha="right")
    ax1.set_title(f"Longo Curso — MM{janela}m mensal",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Mt / mês")
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.legend(loc="upper left", framealpha=0.9)

    # Painel 2: soma 12m por sentido + saldo (eixo secundário)
    for sent, cor in cores.items():
        ax2.plot(sum12.index, sum12[sent] / 1e6, color=cor, lw=2.2, label=sent)
        s = sum12[sent].dropna()
        if not s.empty:
            yu = yoy[sent].dropna()
            rotulo_y = f"{s.iloc[-1]/1e6:,.0f} Mt"
            if not yu.empty:
                rotulo_y += f"  ({yu.iloc[-1]:+.1f}%)"
            ax2.scatter([s.index[-1]], [s.iloc[-1] / 1e6], color=cor, s=35, zorder=5)
            ax2.annotate(rotulo_y,
                         xy=(s.index[-1], s.iloc[-1] / 1e6),
                         xytext=(-8, 10), textcoords="offset points",
                         fontsize=9.5, color=cor, fontweight="bold", ha="right")
    ax2.fill_between(saldo_12m.index, 0, saldo_12m / 1e6,
                     color="#999", alpha=0.18, label="Saldo (Exp − Imp)")
    ax2.set_title("Soma 12m rolante + saldo comercial físico",
                  fontsize=12, fontweight="bold")
    ax2.set_ylabel("Mt (12 meses)")
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=9)

    fig.suptitle("Longo Curso — Exportação vs Importação",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — FlagMCOperacaoCarga=1, Tipo Navegação=Longo Curso",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "medias_moveis_longocurso_sentido")
    print(f"  PNG salvo: {FIGS / 'medias_moveis_longocurso_sentido.png'}")

    print("\nLongo Curso anual (Mt) — anos fechados:\n")
    anuais = wide.groupby(wide.index.year).sum() / 1e6
    ult_ano = wide.index.max().year
    anuais = anuais[anuais.index < ult_ano]
    print(f"  {'Ano':>6} {'Exportação':>11} {'Importação':>11} "
          f"{'Saldo':>9} {'Razão E/I':>10}")
    print("  " + "-" * 52)
    for ano, row in anuais.iterrows():
        exp, imp = row["Embarcados"], row["Desembarcados"]
        print(f"  {ano:>6} {exp:>11,.1f} {imp:>11,.1f} "
              f"{exp-imp:>9,.1f} {exp/imp if imp else 0:>10,.2f}x")

    ult = sum12.dropna().iloc[-1]
    print(f"\nSoma 12m rolante até {sum12.dropna().index[-1].strftime('%Y-%m')}:")
    print(f"  Exportação:  {ult['Embarcados']/1e6:>6,.0f} Mt  "
          f"({yoy['Embarcados'].dropna().iloc[-1]:+.1f}% a/a)")
    print(f"  Importação:  {ult['Desembarcados']/1e6:>6,.0f} Mt  "
          f"({yoy['Desembarcados'].dropna().iloc[-1]:+.1f}% a/a)")
    print(f"  Saldo físico:{(ult['Embarcados']-ult['Desembarcados'])/1e6:>6,.0f} Mt  "
          f"(razão E/I = {ult['Embarcados']/ult['Desembarcados']:.2f}x)")
    return wide


def por_sentido(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """MM12 por natureza × sentido (Embarcados vs Desembarcados)."""
    secao(0, f"MM{janela}m por perfil × sentido (embarque/desembarque)")
    cores = {"Embarcados": "#2a7f3f", "Desembarcados": "#b54848"}
    df = _serie_mensal_por_dim(
        dimensao_sql="c.Sentido",
        dimensao_alias="sentido",
        valores=list(cores.keys()),
        janela=janela, ano_inicio=ano_inicio,
    )
    out_csv = FIGS / "medias_moveis_perfil_sentido.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")
    _plotar_por_dim(
        df, dimensao="sentido", cores=cores,
        titulo=f"Movimentação por perfil de carga × sentido — MM{janela}m",
        nome_arquivo="medias_moveis_perfil_sentido", janela=janela,
    )
    print(f"  PNG salvo: {FIGS / 'medias_moveis_perfil_sentido.png'}")
    _imprimir_resumo_dim(df, "sentido", janela)
    return df


def por_navegacao(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """MM12 por natureza × tipo de navegação (Cabotagem vs Longo Curso)."""
    secao(0, f"MM{janela}m por perfil × navegação (cabotagem/longo curso)")
    cores = {"Cabotagem": "#5a9bd4", "Longo Curso": "#d97742"}
    df = _serie_mensal_por_dim(
        dimensao_sql='c."Tipo Navegação"',
        dimensao_alias="navegacao",
        valores=list(cores.keys()),
        janela=janela, ano_inicio=ano_inicio,
    )
    out_csv = FIGS / "medias_moveis_perfil_navegacao.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")
    _plotar_por_dim(
        df, dimensao="navegacao", cores=cores,
        titulo=f"Movimentação por perfil de carga × navegação — MM{janela}m",
        nome_arquivo="medias_moveis_perfil_navegacao", janela=janela,
    )
    print(f"  PNG salvo: {FIGS / 'medias_moveis_perfil_navegacao.png'}")
    _imprimir_resumo_dim(df, "navegacao", janela)
    return df


def _imprimir_resumo_dim(df: pd.DataFrame, dimensao: str, janela: int) -> None:
    print(f"\nÚltima MM{janela}m por perfil × {dimensao}:\n")
    print(f"  {'Perfil':<28} {dimensao.capitalize():<16} "
          f"{'MM último':>14}  {'a/a MA':>10}  {'Mês':>10}")
    print("  " + "-" * 86)
    for (nat, val), sub in df.groupby(["natureza", dimensao]):
        sub = sub.dropna(subset=["ma12"]).sort_values("data")
        if sub.empty:
            continue
        u = sub.iloc[-1]
        yoy = u.get("yoy_ma_pct")
        yoy_str = f"{yoy:+.1f}%" if pd.notna(yoy) else "—"
        print(f"  {nat:<28} {val:<16} {fmt(u['ma12']):>12} t  "
              f"{yoy_str:>10}  {u['data'].strftime('%Y-%m'):>10}")


def _serie_mensal_naturezas(ano_inicio: int = 2010) -> pd.DataFrame:
    """DataFrame wide: index=mês, colunas=naturezas (Mt). Compartilhado por h/i/j."""
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE AS data,
            c."Natureza da Carga"                         AS natureza,
            SUM(c.VLPesoCargaBruta)                       AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="natureza", values="toneladas")
              .sort_index().asfreq("MS"))
    # descartar último mês se parcial
    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]
    return wide


# ─── (h) Decomposição STL ────────────────────────────────────────────────────
def decomposicao_stl(ano_inicio: int = 2010, periodo: int = 12) -> dict:
    """
    Decomposição STL (Seasonal-Trend-Loess) por natureza.
    Devolve dict {natureza: DataFrame(trend, seasonal, resid)}.
    Salva grid 4×3 (natureza × componente).
    """
    from statsmodels.tsa.seasonal import STL
    secao(0, "Decomposição STL — Tendência / Sazonalidade / Resíduo")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    resultados = {}
    fig, axes = plt.subplots(len(naturezas), 3, figsize=(15, 11), sharex=True)

    for i, nat in enumerate(naturezas):
        s = wide[nat].dropna() / 1e6   # Mt
        stl = STL(s, period=periodo, robust=True).fit()
        comp = pd.DataFrame({"observado": s,
                             "trend": stl.trend,
                             "seasonal": stl.seasonal,
                             "resid": stl.resid})
        resultados[nat] = comp
        cor = CORES[nat]

        ax = axes[i, 0]
        ax.plot(s.index, s.values, color=cor, alpha=0.30, lw=0.8, label="Observado")
        ax.plot(stl.trend.index, stl.trend.values, color=cor, lw=2.0, label="Trend")
        ax.set_ylabel(f"{nat}\nMt/mês", fontsize=9, color=cor, fontweight="bold")
        if i == 0:
            ax.set_title("Tendência (STL)", fontsize=11, fontweight="bold")
        # taxa de crescimento da tendência nos últimos 12m
        t = stl.trend.dropna()
        if len(t) > 12:
            taxa = (t.iloc[-1] / t.iloc[-13] - 1) * 100
            ax.annotate(f"trend 12m: {taxa:+.1f}%",
                        xy=(0.98, 0.06), xycoords="axes fraction",
                        ha="right", fontsize=9, color=cor, fontweight="bold")

        ax = axes[i, 1]
        ax.plot(stl.seasonal.index, stl.seasonal.values, color=cor, lw=1.0)
        ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
        if i == 0:
            ax.set_title("Sazonal (STL)", fontsize=11, fontweight="bold")
        # amplitude sazonal (pico-vale do último ciclo de 12 meses)
        ult12 = stl.seasonal.tail(12)
        amp = ult12.max() - ult12.min()
        ax.annotate(f"amp. ±{amp/2:.1f} Mt\npico: {ult12.idxmax().strftime('%b')}",
                    xy=(0.98, 0.06), xycoords="axes fraction",
                    ha="right", fontsize=9, color=cor, fontweight="bold")

        ax = axes[i, 2]
        ax.plot(stl.resid.index, stl.resid.values, color=cor, lw=0.8)
        ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
        if i == 0:
            ax.set_title("Resíduo (STL)", fontsize=11, fontweight="bold")
        # destacar outliers além de ±2σ
        sigma = stl.resid.std()
        outl = stl.resid[abs(stl.resid) > 2 * sigma]
        if not outl.empty:
            ax.scatter(outl.index, outl.values, color=cor,
                       edgecolor="black", s=18, zorder=5, alpha=0.7)
            ax.annotate(f"±2σ = ±{2*sigma:.1f} Mt",
                        xy=(0.98, 0.06), xycoords="axes fraction",
                        ha="right", fontsize=9, color=cor, fontweight="bold")

        for ax in axes[i, :]:
            ax.xaxis.set_major_locator(mdates.YearLocator(2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Decomposição STL — Tendência / Sazonalidade / Resíduo por natureza",
                 fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "Fonte: ANTAQ — FlagMCOperacaoCarga=1 · método STL (loess), período=12m, robusto",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "stl_decomposicao_natureza")
    print(f"  PNG salvo: {FIGS / 'stl_decomposicao_natureza.png'}")

    # exportar tudo num CSV long
    long = pd.concat(
        [d.assign(natureza=nat) for nat, d in resultados.items()]
    ).reset_index().rename(columns={"index": "data"})
    out_csv = FIGS / "stl_decomposicao_natureza.csv"
    long.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    print("\nResumo STL (último ano):\n")
    print(f"  {'Natureza':<28} {'Δ trend 12m':>13} {'Amp.sazonal':>13} "
          f"{'σ resid':>10} {'pico mês':>10}")
    print("  " + "-" * 80)
    for nat, comp in resultados.items():
        t = comp["trend"].dropna()
        delta = (t.iloc[-1] / t.iloc[-13] - 1) * 100 if len(t) > 12 else float("nan")
        ult12 = comp["seasonal"].tail(12)
        amp = (ult12.max() - ult12.min()) / 2
        sigma = comp["resid"].std()
        pico = ult12.idxmax().strftime("%b")
        print(f"  {nat:<28} {delta:>+12.1f}% {amp:>10.2f} Mt {sigma:>7.2f} Mt {pico:>10}")
    return resultados


# ─── (i) Momentum: variação a/a da MA12 ──────────────────────────────────────
def momentum_yoy_ma12(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Variação a/a da MA12 por natureza (= aceleração/desaceleração da tendência).
    Painel único, escala %.
    """
    secao(0, f"Momentum: variação a/a da MA{janela}m por natureza")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    ma = wide.rolling(janela, min_periods=janela).mean()
    yoy = ma.pct_change(12) * 100

    out_csv = FIGS / "momentum_yoy_ma12.csv"
    yoy.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.axhline(0, color="#444", lw=0.8, alpha=0.7)
    # sombrear recessões/eventos (referência)
    eventos = [("2014-12", "2016-12", "Recessão 14-16"),
               ("2020-03", "2020-08", "COVID")]
    for ini, fim, _ in eventos:
        ax.axvspan(pd.Timestamp(ini), pd.Timestamp(fim),
                   color="#888", alpha=0.10)

    for nat in naturezas:
        if nat not in yoy.columns:
            continue
        cor = CORES[nat]
        ax.plot(yoy.index, yoy[nat], color=cor, lw=2.0, label=nat)
        u = yoy[nat].dropna()
        if not u.empty:
            ax.scatter([u.index[-1]], [u.iloc[-1]], color=cor, s=40, zorder=5)
            ax.annotate(f"{u.iloc[-1]:+.1f}%",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=10, color=cor, fontweight="bold",
                        va="center")

    ax.set_title(f"Aceleração da tendência: a/a da MM{janela}m por natureza",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Variação a/a da MA12 (%)")
    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(loc="upper right", framealpha=0.9, ncol=2)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — FlagMCOperacaoCarga=1 · faixas cinza: recessão 14-16 e COVID",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "momentum_yoy_ma12")
    print(f"  PNG salvo: {FIGS / 'momentum_yoy_ma12.png'}")

    print("\nMomentum atual (a/a da MA12):\n")
    for nat in naturezas:
        if nat not in yoy.columns:
            continue
        u = yoy[nat].dropna()
        if u.empty:
            continue
        # tendência do momentum: comparar últimos 6m vs 6m anteriores
        ult6 = u.tail(6).mean()
        ant6 = u.tail(12).head(6).mean()
        flecha = "↑ acelerando" if ult6 > ant6 + 0.5 else (
                 "↓ desacelerando" if ult6 < ant6 - 0.5 else "→ estável")
        print(f"  {nat:<28} {u.iloc[-1]:>+7.2f}%   (média 6m: {ult6:+5.1f}% "
              f"vs ant 6m: {ant6:+5.1f}%  {flecha})")
    return yoy


# ─── (j) Índice base 100 ──────────────────────────────────────────────────────
def indice_base100(janela: int = JANELA, ano_inicio: int = 2010,
                   base: str = "2011-01") -> pd.DataFrame:
    """
    MM12 normalizada para base 100 no mês `base`. Trajetória comparável entre naturezas.
    """
    secao(0, f"Índice base 100 ({base}) — MM{janela}m por natureza")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    ma = wide.rolling(janela, min_periods=janela).mean()

    # primeiro ponto válido = base (ou base informada se já existir)
    base_ts = pd.Timestamp(base)
    if base_ts not in ma.index or ma.loc[base_ts].isna().any():
        # cai para o primeiro mês com todos os naturezas válidos
        base_ts = ma.dropna().index[0]
        print(f"  ⚠ base ajustada para {base_ts.strftime('%Y-%m')} (primeiro mês com MA12 completa)")

    indice = ma.divide(ma.loc[base_ts]) * 100

    out_csv = FIGS / "indice_base100.csv"
    indice.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.8))

    # Painel 1 — linear
    for nat in naturezas:
        if nat not in indice.columns:
            continue
        cor = CORES[nat]
        ax1.plot(indice.index, indice[nat], color=cor, lw=2.2, label=nat)
        u = indice[nat].dropna()
        if not u.empty:
            ax1.scatter([u.index[-1]], [u.iloc[-1]], color=cor, s=40, zorder=5)
            ax1.annotate(f"{u.iloc[-1]:.0f}",
                         xy=(u.index[-1], u.iloc[-1]),
                         xytext=(8, 0), textcoords="offset points",
                         fontsize=10, color=cor, fontweight="bold",
                         va="center")
    ax1.axhline(100, color="#444", lw=0.8, alpha=0.6)
    ax1.set_title(f"Escala linear — base 100 em {base_ts.strftime('%Y-%m')}",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Índice (base 100)")
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.legend(loc="upper left", framealpha=0.9, fontsize=9)

    # Painel 2 — log (mostra CAGR como inclinação constante)
    for nat in naturezas:
        if nat not in indice.columns:
            continue
        cor = CORES[nat]
        ax2.semilogy(indice.index, indice[nat], color=cor, lw=2.2, label=nat)
    ax2.axhline(100, color="#444", lw=0.8, alpha=0.6)
    ax2.set_title("Escala log — inclinação ≈ CAGR",
                  fontsize=12, fontweight="bold")
    ax2.set_ylabel("Índice (log)")
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=9)

    fig.suptitle(f"Trajetória da MM{janela}m por natureza — índice base 100",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             f"Fonte: ANTAQ — FlagMCOperacaoCarga=1 · base = {base_ts.strftime('%Y-%m')}",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "indice_base100")
    print(f"  PNG salvo: {FIGS / 'indice_base100.png'}")

    # CAGR
    print(f"\nCAGR da MM12 ({base_ts.strftime('%Y-%m')} → último mês):\n")
    print(f"  {'Natureza':<28} {'Início':>9} {'Atual':>9} {'Mult.':>7} {'CAGR':>8}")
    print("  " + "-" * 64)
    for nat in naturezas:
        if nat not in ma.columns:
            continue
        s = ma[nat].dropna()
        if s.empty or base_ts not in s.index:
            continue
        v0, v1 = s.loc[base_ts], s.iloc[-1]
        anos = (s.index[-1] - base_ts).days / 365.25
        cagr = (v1 / v0) ** (1 / anos) - 1
        mult = v1 / v0
        print(f"  {nat:<28} {v0/1e6:>7,.1f}Mt {v1/1e6:>7,.1f}Mt "
              f"{mult:>6,.2f}× {cagr*100:>+6.2f}%")
    return indice


# ─── (m) Cabotagem doméstica vs offshore — STL + momentum ────────────────────
def cabotagem_stl_momentum(ano_inicio: int = 2010,
                            periodo: int = 12) -> dict:
    """STL + momentum (a/a da MA12) para cabotagem doméstica vs offshore."""
    from statsmodels.tsa.seasonal import STL
    secao(0, "Cabotagem doméstica vs offshore — STL + Momentum")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            CASE WHEN c.FlagOffshore = 1 THEN 'Offshore (FPSO/ZEE)'
                 ELSE 'Cabotagem doméstica' END             AS categoria,
            SUM(c.VLPesoCargaBruta)                         AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Cabotagem'
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="categoria", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))
    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    cores = {"Cabotagem doméstica": "#2a7f3f",
             "Offshore (FPSO/ZEE)": "#b54848"}
    resultados = {}

    fig, axes = plt.subplots(2, 3, figsize=(15, 7.5))
    for i, (cat, cor) in enumerate(cores.items()):
        s = wide[cat] / 1e6
        # série precisa ter início válido (offshore = 0 antes de 2011)
        s = s.loc[s.gt(0).idxmax():]
        stl = STL(s, period=periodo, robust=True).fit()
        resultados[cat] = pd.DataFrame({"trend": stl.trend,
                                         "seasonal": stl.seasonal,
                                         "resid": stl.resid})

        ax = axes[i, 0]
        ax.plot(s.index, s.values, color=cor, alpha=0.30, lw=0.8)
        ax.plot(stl.trend.index, stl.trend.values, color=cor, lw=2.0)
        ax.set_ylabel(f"{cat}\nMt/mês", fontsize=9, color=cor, fontweight="bold")
        if i == 0:
            ax.set_title("Tendência (STL)", fontsize=11, fontweight="bold")
        t = stl.trend.dropna()
        if len(t) > 12:
            taxa = (t.iloc[-1] / t.iloc[-13] - 1) * 100
            ax.annotate(f"trend 12m: {taxa:+.1f}%",
                        xy=(0.98, 0.06), xycoords="axes fraction",
                        ha="right", fontsize=9, color=cor, fontweight="bold")

        ax = axes[i, 1]
        ax.plot(stl.seasonal.index, stl.seasonal.values, color=cor, lw=1.0)
        ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
        if i == 0:
            ax.set_title("Sazonal (STL)", fontsize=11, fontweight="bold")
        ult12 = stl.seasonal.tail(12)
        amp = (ult12.max() - ult12.min()) / 2
        ax.annotate(f"amp. ±{amp:.2f} Mt\npico: {ult12.idxmax().strftime('%b')}",
                    xy=(0.98, 0.06), xycoords="axes fraction",
                    ha="right", fontsize=9, color=cor, fontweight="bold")

        ax = axes[i, 2]
        # momentum = a/a da MA12
        ma = wide[cat].rolling(12, min_periods=12).mean() / 1e6
        yoy = ma.pct_change(12) * 100
        ax.axhline(0, color="#444", lw=0.8, alpha=0.6)
        ax.plot(yoy.index, yoy.values, color=cor, lw=2.0)
        if i == 0:
            ax.set_title("Momentum: a/a MA12 (%)", fontsize=11, fontweight="bold")
        u = yoy.dropna()
        if not u.empty:
            ax.scatter([u.index[-1]], [u.iloc[-1]], color=cor, s=35, zorder=5)
            ax.annotate(f"{u.iloc[-1]:+.1f}%",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(-6, 8), textcoords="offset points",
                        fontsize=10, color=cor, fontweight="bold", ha="right")

        for ax in axes[i, :]:
            ax.xaxis.set_major_locator(mdates.YearLocator(2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Cabotagem brasileira — STL e momentum (doméstica vs offshore)",
                 fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "Fonte: ANTAQ — FlagMCOperacaoCarga=1, Tipo Navegação=Cabotagem",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "stl_momentum_cabotagem")
    print(f"  PNG salvo: {FIGS / 'stl_momentum_cabotagem.png'}")

    print("\nResumo:\n")
    for cat, comp in resultados.items():
        t = comp["trend"].dropna()
        delta = (t.iloc[-1] / t.iloc[-13] - 1) * 100 if len(t) > 12 else float("nan")
        ult12 = comp["seasonal"].tail(12)
        amp = (ult12.max() - ult12.min()) / 2
        pico = ult12.idxmax().strftime("%b")
        print(f"  {cat:<28} Δtrend 12m: {delta:+6.2f}%   "
              f"amp.sazonal: ±{amp:.2f} Mt   pico: {pico}")
    return resultados


# ─── (n) Momentum do momentum — segunda derivada ─────────────────────────────
def momentum_do_momentum(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Variação 6m do momentum (a/a da MA12).
    Lê: 'em qual ponto da curva de aceleração estamos?'
    """
    secao(0, "Aceleração da aceleração (momentum do momentum, Δ6m)")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]
    ma = wide.rolling(janela, min_periods=janela).mean()
    momentum = ma.pct_change(12) * 100             # % a/a
    accel = momentum - momentum.shift(6)            # pontos percentuais em 6 meses

    out_csv = FIGS / "aceleracao_da_aceleracao.csv"
    accel.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.axhline(0, color="#444", lw=0.8, alpha=0.7)
    for nat in naturezas:
        if nat not in accel.columns:
            continue
        cor = CORES[nat]
        ax.plot(accel.index, accel[nat], color=cor, lw=2.0, label=nat)
        u = accel[nat].dropna()
        if not u.empty:
            ax.scatter([u.index[-1]], [u.iloc[-1]], color=cor, s=40, zorder=5)
            ax.annotate(f"{u.iloc[-1]:+.1f} pp",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=10, color=cor, fontweight="bold", va="center")

    ax.set_title("Aceleração da tendência — Δ6m do momentum (a/a da MA12)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("pp em 6 meses (positivo = acelerando)")
    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(loc="upper right", framealpha=0.9, ncol=2)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — FlagMCOperacaoCarga=1 · positivo = momentum subindo, "
             "negativo = perdendo fôlego",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "aceleracao_da_aceleracao")
    print(f"  PNG salvo: {FIGS / 'aceleracao_da_aceleracao.png'}")

    print("\nEstado atual (Δ6m do momentum):\n")
    for nat in naturezas:
        if nat not in accel.columns:
            continue
        u = accel[nat].dropna()
        m = momentum[nat].dropna()
        if u.empty or m.empty:
            continue
        v = u.iloc[-1]
        if v > 1.0:
            fase = "FASE 1: acelerando ↑↑"
        elif v > 0:
            fase = "FASE 2: ainda subindo ↑"
        elif v > -1.0:
            fase = "FASE 3: empinando topo →"
        else:
            fase = "FASE 4: virando ↓↓"
        print(f"  {nat:<28} Δ6m: {v:+6.2f} pp   momentum atual: {m.iloc[-1]:+5.1f}%   {fase}")
    return accel


# ─── (k') Momentum vs IBC-Br ─────────────────────────────────────────────────
def momentum_vs_ibcbr(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    """
    Sobrepõe o momentum (a/a MA12) de cada natureza com o a/a do IBC-Br.
    Calcula correlação e lead/lag (em meses) que maximiza correlação.
    """
    from .macro import ibc_br
    secao(0, "Momentum portuário vs IBC-Br (lead/lag)")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    ma  = wide.rolling(janela, min_periods=janela).mean()
    mom = ma.pct_change(12) * 100

    # IBC-Br dessazonalizado → a/a (12m vs 12m)
    ibc = ibc_br()
    ibc = ibc.resample("MS").last()
    ibc_yoy = ibc.pct_change(12) * 100
    ibc_yoy = ibc_yoy.loc[ibc_yoy.index >= pd.Timestamp(f"{ano_inicio}-01-01")]

    fig, axes = plt.subplots(2, 2, figsize=(15, 8), sharex=True)

    print("\nCorrelação e lead/lag ótimo (lag positivo = porto adiantado vs IBC-Br):\n")
    print(f"  {'Natureza':<28} {'corr@0':>8} {'lag*':>6} {'corr*':>8}")
    print("  " + "-" * 56)
    resumo_corr = {}
    for ax, nat in zip(axes.flat, naturezas):
        if nat not in mom.columns:
            ax.set_visible(False)
            continue
        cor = CORES[nat]
        m = mom[nat].dropna()

        ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
        ax.plot(m.index, m.values, color=cor, lw=2.2, label=f"{nat}")
        ax.plot(ibc_yoy.index, ibc_yoy.values,
                color="#444", lw=1.6, ls="--", label="IBC-Br a/a")

        # alinhar índices
        df_a = pd.concat([m, ibc_yoy], axis=1, join="inner").dropna()
        df_a.columns = ["porto", "ibc"]
        corr0 = df_a["porto"].corr(df_a["ibc"])
        # best lag em ±18m
        melhor = (0, corr0)
        for lag in range(-18, 19):
            c = df_a["porto"].corr(df_a["ibc"].shift(-lag))
            if pd.notna(c) and abs(c) > abs(melhor[1]):
                melhor = (lag, c)
        resumo_corr[nat] = {"corr0": corr0, "lag": melhor[0], "corr_lag": melhor[1]}
        print(f"  {nat:<28} {corr0:>+7.2f} {melhor[0]:>+5d}m {melhor[1]:>+7.2f}")

        ax.annotate(f"corr@0 = {corr0:+.2f}\nlag* = {melhor[0]:+d}m → {melhor[1]:+.2f}",
                    xy=(0.02, 0.98), xycoords="axes fraction",
                    ha="left", va="top", fontsize=9,
                    bbox=dict(boxstyle="round", fc="white", ec=cor, alpha=0.85))
        ax.set_title(nat, fontsize=11, fontweight="bold", color=cor)
        ax.set_ylabel("% a/a")
        ax.legend(loc="lower left", framealpha=0.9, fontsize=8)
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Momentum portuário (a/a MA12) vs IBC-Br a/a — lead/lag",
                 fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "Fonte: ANTAQ + BCB SGS 24364 (IBC-Br) · lag > 0: porto antecipa IBC-Br",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "momentum_vs_ibcbr")
    print(f"  PNG salvo: {FIGS / 'momentum_vs_ibcbr.png'}")
    return pd.DataFrame(resumo_corr).T


# ─── (o) Análise completa para TEU (contêineres) ─────────────────────────────
def teu_analise_completa(ano_inicio: int = 2010, periodo: int = 12) -> dict:
    """
    STL + momentum + índice 100 para TEU (Carga Conteinerizada),
    decomposto por Tipo Navegação (Cabotagem vs Longo Curso) e cheio vs vazio.
    """
    from statsmodels.tsa.seasonal import STL
    secao(0, "TEU (contêineres) — STL + Momentum + Índice 100")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE  AS data,
            c."Tipo Navegação"                              AS navegacao,
            COALESCE(c.ConteinerEstado, 's/info')           AS estado,
            SUM(c.TEU)                                       AS teu
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c.TEU > 0
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
          AND c."Tipo Navegação" IN ('Cabotagem','Longo Curso')
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])

    # totais por (data, navegacao)
    nav = (df.groupby(["data", "navegacao"])["teu"].sum()
             .unstack().sort_index().asfreq("MS").fillna(0))
    nav["Total"] = nav.sum(axis=1)
    soma_recente = nav["Total"].iloc[-13:-1].mean()
    if nav["Total"].iloc[-1] < 0.5 * soma_recente:
        nav = nav.iloc[:-1]

    out_csv = FIGS / "teu_serie_mensal.csv"
    nav.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    # Painel 1: STL do total TEU + barras cheio/vazio
    s = nav["Total"]
    stl = STL(s.loc[s.gt(0).idxmax():], period=periodo, robust=True).fit()

    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(3, 2)

    # STL
    ax = fig.add_subplot(gs[0, 0])
    ax.plot(s.index, s.values / 1e3, color="#5a9bd4", alpha=0.30, lw=0.8)
    ax.plot(stl.trend.index, stl.trend.values / 1e3, color="#0c4a76", lw=2.4)
    ax.set_ylabel("Mil TEU/mês")
    ax.set_title("TEU total — tendência (STL)", fontsize=11, fontweight="bold")
    t = stl.trend.dropna()
    taxa = (t.iloc[-1] / t.iloc[-13] - 1) * 100
    ax.annotate(f"trend 12m: {taxa:+.1f}%",
                xy=(0.02, 0.96), xycoords="axes fraction",
                ha="left", va="top", fontsize=10, color="#0c4a76", fontweight="bold")

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(stl.seasonal.index, stl.seasonal.values / 1e3, color="#0c4a76", lw=1.0)
    ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
    ax.set_ylabel("Mil TEU")
    ax.set_title("Sazonal (STL)", fontsize=11, fontweight="bold")
    ult12 = stl.seasonal.tail(12)
    amp = (ult12.max() - ult12.min()) / 2 / 1e3
    pico = ult12.idxmax().strftime("%b")
    ax.annotate(f"amp. ±{amp:.0f} mil TEU\npico: {pico}",
                xy=(0.02, 0.96), xycoords="axes fraction",
                ha="left", va="top", fontsize=10, color="#0c4a76", fontweight="bold")

    # Momentum cabotagem vs longo curso
    ax = fig.add_subplot(gs[1, 0])
    ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
    cores_nav = {"Cabotagem": "#5a9bd4", "Longo Curso": "#d97742"}
    for n, cor in cores_nav.items():
        if n not in nav.columns:
            continue
        ma = nav[n].rolling(12, min_periods=12).mean()
        yoy = ma.pct_change(12) * 100
        ax.plot(yoy.index, yoy.values, color=cor, lw=2.0, label=n)
        u = yoy.dropna()
        if not u.empty:
            ax.scatter([u.index[-1]], [u.iloc[-1]], color=cor, s=35, zorder=5)
            ax.annotate(f"{u.iloc[-1]:+.1f}%",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=9.5, color=cor, fontweight="bold", va="center")
    ax.set_title("Momentum TEU — a/a MA12 (cabotagem vs longo curso)",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("% a/a")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)

    # Índice 100 cabotagem vs longo curso
    ax = fig.add_subplot(gs[1, 1])
    ma_nav = nav[["Cabotagem", "Longo Curso"]].rolling(12, min_periods=12).mean()
    base_ts = ma_nav.dropna().index[0]
    indice = ma_nav.divide(ma_nav.loc[base_ts]) * 100
    for n, cor in cores_nav.items():
        if n not in indice.columns:
            continue
        ax.plot(indice.index, indice[n], color=cor, lw=2.2, label=n)
        u = indice[n].dropna()
        if not u.empty:
            ax.scatter([u.index[-1]], [u.iloc[-1]], color=cor, s=35, zorder=5)
            ax.annotate(f"{u.iloc[-1]:.0f}",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=9.5, color=cor, fontweight="bold", va="center")
    ax.axhline(100, color="#444", lw=0.6, alpha=0.6)
    ax.set_title(f"Índice base 100 ({base_ts.strftime('%Y-%m')}) — MM12",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Índice (base 100)")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)

    # Cheio vs Vazio mensal (MA12)
    estado = (df.groupby(["data", "estado"])["teu"].sum()
                .unstack().sort_index().asfreq("MS").fillna(0))
    # mostra só estados com nome conhecido
    estado.columns = [c.strip() for c in estado.columns]

    ax = fig.add_subplot(gs[2, :])
    cores_est = {"Cheio": "#1f6d3a", "Vazio": "#888"}
    for est, cor in cores_est.items():
        if est not in estado.columns:
            continue
        ma = estado[est].rolling(12, min_periods=12).mean() / 1e3
        ax.plot(ma.index, ma.values, color=cor, lw=2.4, label=f"{est} (MA12)")
        u = ma.dropna()
        if not u.empty:
            ax.annotate(f"{u.iloc[-1]:,.0f} mil TEU",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=10, color=cor, fontweight="bold", va="center")
    # razão vazio/cheio (eixo secundário)
    if "Cheio" in estado.columns and "Vazio" in estado.columns:
        ax2 = ax.twinx()
        razao = (estado["Vazio"].rolling(12, min_periods=12).sum()
                 / estado["Cheio"].rolling(12, min_periods=12).sum() * 100)
        ax2.plot(razao.index, razao.values, color="#b54848", lw=1.6, ls="--",
                 label="% vazios sobre cheios")
        ax2.set_ylabel("% vazios / cheios", color="#b54848")
        ax2.spines["right"].set_visible(True)
        ax2.tick_params(axis="y", colors="#b54848")
        u = razao.dropna()
        if not u.empty:
            ax2.annotate(f"{u.iloc[-1]:.0f}%",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(8, 0), textcoords="offset points",
                        fontsize=10, color="#b54848", fontweight="bold", va="center")
    ax.set_title("TEU cheio vs vazio (MA12) — razão vazios/cheios à direita",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Mil TEU / mês")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)

    for ax in fig.axes:
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("TEU (contêineres) — STL, momentum, índice e cheio/vazio",
                 fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "Fonte: ANTAQ — Natureza='Carga Conteinerizada', TEU > 0, FlagMCOperacaoCarga=1",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "teu_analise_completa")
    print(f"  PNG salvo: {FIGS / 'teu_analise_completa.png'}")

    # CAGR por navegação
    print("\nCAGR do TEU (MM12):\n")
    for n in ["Cabotagem", "Longo Curso"]:
        if n not in ma_nav.columns:
            continue
        s = ma_nav[n].dropna()
        v0, v1 = s.iloc[0], s.iloc[-1]
        anos = (s.index[-1] - s.index[0]).days / 365.25
        cagr = (v1 / v0) ** (1 / anos) - 1
        print(f"  {n:<14} {v0/1e3:>6,.0f}k → {v1/1e3:>6,.0f}k TEU/mês   "
              f"{v1/v0:.2f}×   CAGR {cagr*100:+.2f}%")
    return {"nav": nav, "estado": estado, "stl": stl}


# ─── (p) Top-10 resíduos STL — choques identificados ────────────────────────
def choques_residuos_stl(ano_inicio: int = 2010, top_n: int = 10) -> pd.DataFrame:
    """
    Encontra os top-N resíduos absolutos do STL por natureza e mapeia contra
    eventos conhecidos.
    """
    from statsmodels.tsa.seasonal import STL
    secao(0, f"Top {top_n} choques (resíduos STL) por natureza")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]

    eventos_conhecidos = {
        "2018-05": "Greve dos caminhoneiros",
        "2018-06": "Greve dos caminhoneiros (rastro)",
        "2020-03": "COVID — início paralisação",
        "2020-04": "COVID — vale",
        "2020-05": "COVID — recuperação",
        "2015-12": "Recessão 2015-16",
        "2016-01": "Recessão 2015-16",
        "2022-02": "Guerra Ucrânia — choque commodities",
        "2024-05": "Enchente RS",
    }

    todos_choques = []
    for nat in naturezas:
        s = wide[nat].dropna() / 1e6
        stl = STL(s, period=12, robust=True).fit()
        resid = stl.resid
        sigma = resid.std()
        top = resid.reindex(resid.abs().sort_values(ascending=False).index).head(top_n)
        for data, valor in top.items():
            evento = eventos_conhecidos.get(data.strftime("%Y-%m"), "")
            todos_choques.append({
                "natureza": nat, "data": data, "resid_mt": valor,
                "sigmas": valor / sigma, "evento_conhecido": evento,
            })

    df = pd.DataFrame(todos_choques)
    out_csv = FIGS / "choques_residuos_stl.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    for ax, nat in zip(axes.flat, naturezas):
        sub = df[df["natureza"] == nat].sort_values("data")
        cor = CORES[nat]
        # série de resíduos como contexto
        s = wide[nat].dropna() / 1e6
        stl = STL(s, period=12, robust=True).fit()
        ax.plot(stl.resid.index, stl.resid.values, color=cor, lw=0.7, alpha=0.55)
        ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
        # 2σ
        sigma = stl.resid.std()
        ax.axhline(2 * sigma, color="#888", lw=0.6, ls=":", alpha=0.5)
        ax.axhline(-2 * sigma, color="#888", lw=0.6, ls=":", alpha=0.5)
        # destaca top-N
        ax.scatter(sub["data"], sub["resid_mt"], color=cor,
                   edgecolor="black", s=50, zorder=5)
        # rotula choques com evento conhecido
        for _, r in sub.iterrows():
            if r["evento_conhecido"]:
                ax.annotate(r["evento_conhecido"].split(" — ")[0],
                            xy=(r["data"], r["resid_mt"]),
                            xytext=(0, 12 if r["resid_mt"] > 0 else -16),
                            textcoords="offset points",
                            fontsize=7.5, color="#333",
                            ha="center",
                            arrowprops=dict(arrowstyle="-", lw=0.4, color="#888"))
        ax.set_title(nat, fontsize=12, fontweight="bold", color=cor)
        ax.set_ylabel("Resíduo (Mt)")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle(f"Top {top_n} choques (resíduos STL > {top_n}º percentil) por natureza",
                 fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "Pontos pretos = resíduos extremos. Linhas pontilhadas = ±2σ. "
             "Anotações = eventos conhecidos.",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "choques_residuos_stl")
    print(f"  PNG salvo: {FIGS / 'choques_residuos_stl.png'}")

    # imprimir lista
    print(f"\nTop-{top_n} resíduos por natureza:\n")
    for nat in naturezas:
        sub = df[df["natureza"] == nat].sort_values("resid_mt", key=abs, ascending=False)
        print(f"\n  {nat}:")
        for _, r in sub.iterrows():
            tag = f" ← {r['evento_conhecido']}" if r["evento_conhecido"] else ""
            print(f"    {r['data'].strftime('%Y-%m')}  "
                  f"{r['resid_mt']:>+7.2f} Mt  ({r['sigmas']:+.1f}σ){tag}")
    return df


# ─── (q) Decomposição do +11% do granel líquido ─────────────────────────────
def decomposicao_granel_liquido(ano_inicio: int = 2010,
                                 janela: int = JANELA) -> pd.DataFrame:
    """Decompõe granel líquido em 3 buckets: Offshore, LC exportação, LC importação + Cabotagem doméstica."""
    secao(0, "Decomposição do crescimento do Granel Líquido")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            date_trunc('month', a."Data Atracação")::DATE AS data,
            CASE
              WHEN c.FlagOffshore = 1 THEN 'Offshore (FPSO/ZEE)'
              WHEN c."Tipo Navegação" = 'Longo Curso' AND c.Sentido = 'Embarcados'
                   THEN 'LC Exportação'
              WHEN c."Tipo Navegação" = 'Longo Curso' AND c.Sentido = 'Desembarcados'
                   THEN 'LC Importação'
              WHEN c."Tipo Navegação" = 'Cabotagem'
                   THEN 'Cabotagem doméstica'
              ELSE 'Outros'
            END AS bucket,
            SUM(c.VLPesoCargaBruta) AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Granel Líquido e Gasoso'
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="bucket", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))

    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    ma = wide.rolling(janela, min_periods=janela).mean()
    yoy_ma = ma.pct_change(12) * 100

    out_csv = FIGS / "granel_liquido_decomposicao.csv"
    wide.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    cores = {
        "Offshore (FPSO/ZEE)": "#b54848",
        "LC Exportação":       "#2a7f3f",
        "LC Importação":       "#5a9bd4",
        "Cabotagem doméstica": "#f0a04b",
        "Outros":              "#888",
    }
    ordem = [c for c in cores if c in wide.columns]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Painel 1: empilhado MA12
    ma_ordem = ma[ordem] / 1e6
    ax1.stackplot(ma_ordem.index,
                  [ma_ordem[c].values for c in ordem],
                  labels=ordem, colors=[cores[c] for c in ordem], alpha=0.85)
    ax1.set_title(f"MM{janela}m mensal — composição (empilhado)",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Milhões de toneladas / mês")
    ax1.legend(loc="upper left", framealpha=0.9, fontsize=9)
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Painel 2: contribuição em pp para o crescimento total
    # contribuição_bucket(t) = (Δbucket / total_t-12) * 100
    # = peso × momento do bucket
    total_t_12 = ma[ordem].sum(axis=1).shift(12)
    contrib = ma[ordem].diff(12).divide(total_t_12, axis=0) * 100
    for c in ordem:
        if c not in contrib.columns:
            continue
        ax2.plot(contrib.index, contrib[c], color=cores[c], lw=2.0, label=c)
        u = contrib[c].dropna()
        if not u.empty:
            ax2.annotate(f"{u.iloc[-1]:+.1f}pp",
                         xy=(u.index[-1], u.iloc[-1]),
                         xytext=(8, 0), textcoords="offset points",
                         fontsize=9.5, color=cores[c], fontweight="bold",
                         va="center")
    total_yoy = (ma[ordem].sum(axis=1).pct_change(12) * 100)
    ax2.plot(total_yoy.index, total_yoy.values, color="black",
             lw=2.2, ls="--", label="Total (a/a)")
    u = total_yoy.dropna()
    if not u.empty:
        ax2.annotate(f"{u.iloc[-1]:+.1f}%",
                     xy=(u.index[-1], u.iloc[-1]),
                     xytext=(8, 0), textcoords="offset points",
                     fontsize=10, color="black", fontweight="bold", va="center")
    ax2.axhline(0, color="#444", lw=0.6, alpha=0.5)
    ax2.set_title("Contribuição em pp para o crescimento total",
                  fontsize=12, fontweight="bold")
    ax2.set_ylabel("pp do crescimento a/a")
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=9)
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Granel Líquido e Gasoso — quem está puxando os +11%?",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — Natureza='Granel Líquido e Gasoso', FlagMCOperacaoCarga=1",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "granel_liquido_decomposicao")
    print(f"  PNG salvo: {FIGS / 'granel_liquido_decomposicao.png'}")

    print("\nContribuição atual (em pp) para o crescimento a/a do Granel Líquido:\n")
    ult = contrib.dropna(how="all").iloc[-1]
    total_atual = total_yoy.dropna().iloc[-1]
    print(f"  Total a/a:  {total_atual:+.2f}%\n")
    for c in ordem:
        if c not in ult.index:
            continue
        print(f"  {c:<24} {ult[c]:>+7.2f} pp  "
              f"(MA12 atual: {ma[c].dropna().iloc[-1]/1e6:>5.1f} Mt/mês, "
              f"a/a: {yoy_ma[c].dropna().iloc[-1]:>+6.1f}%)")
    return contrib


# ─── (r) Mapa contêiner cabotagem por par OD ─────────────────────────────────
def mapa_conteiner_rotas(ano_inicio: int = 2010, top_n: int = 10) -> pd.DataFrame:
    """Top-N pares (Origem, Destino) por TEU em cabotagem conteinerizada, com CAGR."""
    secao(0, f"Top {top_n} rotas cabotagem conteinerizada por TEU")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            EXTRACT(year FROM a."Data Atracação")::INT  AS ano,
            o."Origem Nome"                              AS origem,
            o."UF.Origem"                                AS uf_origem,
            d."Nome Destino"                             AS destino,
            d."UF.Destino"                               AS uf_destino,
            SUM(c.TEU)                                   AS teu
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        LEFT JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c."Tipo Navegação"    = 'Cabotagem'
          AND c.TEU > 0
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2,3,4,5
        """
    ).df()

    # totais por par OD
    pares = (df.groupby(["origem", "uf_origem", "destino", "uf_destino"])
                ["teu"].sum().reset_index()
                .sort_values("teu", ascending=False))
    top = pares.head(top_n).copy()

    # CAGR de cada top par (primeiro ao último ano)
    cagrs = []
    for _, r in top.iterrows():
        sub = df[(df["origem"] == r["origem"]) & (df["destino"] == r["destino"])]
        s = sub.groupby("ano")["teu"].sum().sort_index()
        # exclui ano corrente (parcial)
        s = s[s.index < df["ano"].max()]
        if len(s) >= 2 and s.iloc[0] > 0:
            anos = s.index[-1] - s.index[0]
            cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / anos) - 1
            ult = s.iloc[-1]
        else:
            cagr, ult = float("nan"), float("nan")
        cagrs.append({"ultimo_ano_teu": ult, "cagr": cagr})
    top = pd.concat([top.reset_index(drop=True),
                     pd.DataFrame(cagrs)], axis=1)
    top["rota"] = (top["origem"] + " (" + top["uf_origem"] + ")"
                   + " → "
                   + top["destino"] + " (" + top["uf_destino"] + ")")

    out_csv = FIGS / "conteiner_top_rotas.csv"
    top.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    # bar chart horizontal: TEU acumulado + CAGR como cor
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))
    top_sorted = top.sort_values("teu")
    cores_b = ["#2a7f3f" if c > 0.08 else ("#5a9bd4" if c > 0 else "#b54848")
               for c in top_sorted["cagr"].fillna(0)]
    ax1.barh(top_sorted["rota"], top_sorted["teu"] / 1e6, color=cores_b, alpha=0.85)
    for i, (_, r) in enumerate(top_sorted.iterrows()):
        cagr_str = f"{r['cagr']*100:+.1f}%" if pd.notna(r["cagr"]) else "—"
        ax1.text(r["teu"] / 1e6, i, f"  {cagr_str}",
                 va="center", fontsize=9, color="#333")
    ax1.set_xlabel("Milhões de TEU (acumulado)")
    ax1.set_title(f"Top {top_n} rotas — TEU cabotagem (acumulado) + CAGR",
                  fontsize=12, fontweight="bold")

    # série anual de cada top rota
    df_top = df.merge(top[["origem", "destino"]], on=["origem", "destino"])
    pivot_top = (df_top.groupby(["ano", "origem", "destino"])["teu"].sum()
                       .unstack(["origem", "destino"]) / 1e3)
    pivot_top = pivot_top[pivot_top.index < df["ano"].max()]
    for col in pivot_top.columns:
        ax2.plot(pivot_top.index, pivot_top[col], lw=1.5, alpha=0.85,
                 label=f"{col[0][:18]}→{col[1][:18]}")
    ax2.set_xlabel("Ano")
    ax2.set_ylabel("Mil TEU / ano")
    ax2.set_title(f"Trajetória anual das top {top_n} rotas",
                  fontsize=12, fontweight="bold")
    ax2.legend(loc="upper left", fontsize=7, framealpha=0.85, ncol=1)
    ax2.grid(alpha=0.3)

    fig.suptitle("Cabotagem conteinerizada — top rotas (pares Origem-Destino)",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — Natureza='Carga Conteinerizada', Tipo Navegação=Cabotagem, TEU>0",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "conteiner_top_rotas")
    print(f"  PNG salvo: {FIGS / 'conteiner_top_rotas.png'}")

    print(f"\nTop {top_n} rotas (TEU acumulado, CAGR):\n")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        cagr_str = f"{r['cagr']*100:+.1f}%" if pd.notna(r["cagr"]) else "—"
        print(f"  {i:>2}. {r['origem'][:22]:<22} ({r['uf_origem']}) → "
              f"{r['destino'][:22]:<22} ({r['uf_destino']})  "
              f"{r['teu']/1e6:>5,.2f}M TEU acum.  CAGR {cagr_str:>7}")

    # Concentração: top-N como % do total
    total = pares["teu"].sum()
    pct_top = top["teu"].sum() / total * 100
    print(f"\n  Top {top_n} = {pct_top:.1f}% do TEU acumulado da cabotagem conteinerizada")
    return top


# ─── (s) Carga Geral cabotagem vs LC — mercadorias migrando ─────────────────
def carga_geral_migracao(ano_inicio: int = 2015, top_n: int = 10) -> pd.DataFrame:
    """
    Decompõe Carga Geral por mercadoria (Grupo de Mercadoria) em cabotagem vs LC.
    Identifica mercadorias com sinal divergente.
    """
    secao(0, "Carga Geral — mercadorias migrando entre LC e Cabotagem")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            EXTRACT(year FROM a."Data Atracação")::INT  AS ano,
            c."Tipo Navegação"                           AS navegacao,
            COALESCE(m."Grupo de Mercadoria", 's/info')  AS grupo,
            SUM(c.VLPesoCargaBruta)                       AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        LEFT JOIN Mercadoria m ON c.CDMercadoria = m.CDMercadoria
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Carga Geral'
          AND c."Tipo Navegação" IN ('Cabotagem','Longo Curso')
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2,3
        """
    ).df()

    ult_ano = df["ano"].max()
    df = df[df["ano"] < ult_ano]   # remove ano corrente (parcial)
    ult_ano = df["ano"].max()
    anos_base = sorted(df["ano"].unique())
    if len(anos_base) < 3:
        print("  ⚠ poucos anos para análise"); return pd.DataFrame()
    ano_ini = anos_base[0]

    pivot = (df.groupby(["grupo", "navegacao", "ano"])["toneladas"].sum()
                .unstack("ano").fillna(0))

    # CAGR por (grupo, navegação) entre ano_ini e ult_ano
    n_anos = ult_ano - ano_ini
    pivot["cagr"] = ((pivot[ult_ano] / pivot[ano_ini].replace(0, float("nan"))) ** (1 / n_anos) - 1) * 100
    pivot["ult_ano_mt"] = pivot[ult_ano] / 1e6

    # foca em grupos com volume relevante (top-N por total)
    totais = (df[df["ano"] >= ult_ano - 2]
              .groupby("grupo")["toneladas"].sum()
              .sort_values(ascending=False).head(top_n).index.tolist())
    sub = pivot.reset_index()
    sub = sub[sub["grupo"].isin(totais)]

    # tabela: grupo × (cabotagem CAGR, LC CAGR, cabotagem volume, LC volume)
    out = (sub.pivot(index="grupo", columns="navegacao",
                     values=["cagr", "ult_ano_mt"])
              .reindex(totais))
    out_csv = FIGS / "carga_geral_migracao.csv"
    out.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    fig, ax = plt.subplots(figsize=(12, 7))
    grupos = out.index.tolist()
    y = list(range(len(grupos)))
    width = 0.4
    cab_cagr = out[("cagr", "Cabotagem")].fillna(0).values
    lc_cagr  = out[("cagr", "Longo Curso")].fillna(0).values
    cab_vol  = out[("ult_ano_mt", "Cabotagem")].fillna(0).values
    lc_vol   = out[("ult_ano_mt", "Longo Curso")].fillna(0).values

    bars_cab = ax.barh([yi + width/2 for yi in y], cab_cagr,
                       height=width, color="#5a9bd4", label="Cabotagem CAGR")
    bars_lc  = ax.barh([yi - width/2 for yi in y], lc_cagr,
                       height=width, color="#d97742", label="Longo Curso CAGR")
    for yi, c, vol in zip(y, cab_cagr, cab_vol):
        ax.text(c, yi + width/2, f"  {vol:,.1f}Mt",
                va="center", fontsize=8, color="#222")
    for yi, c, vol in zip(y, lc_cagr, lc_vol):
        ax.text(c, yi - width/2, f"  {vol:,.1f}Mt",
                va="center", fontsize=8, color="#222")
    ax.axvline(0, color="#444", lw=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(grupos, fontsize=9)
    ax.set_xlabel(f"CAGR {ano_ini}–{ult_ano} (%)")
    ax.set_title(f"Carga Geral — CAGR por Grupo de Mercadoria (top {top_n} por volume recente)",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="lower right", framealpha=0.9, fontsize=9)
    ax.grid(alpha=0.3, axis="x")
    fig.text(0.5, -0.02,
             "Fonte: ANTAQ — Natureza='Carga Geral', FlagMCOperacaoCarga=1 · "
             "valores = volume Mt no último ano fechado",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "carga_geral_migracao")
    print(f"  PNG salvo: {FIGS / 'carga_geral_migracao.png'}")

    print(f"\nCAGR {ano_ini}–{ult_ano} por grupo de mercadoria (Carga Geral):\n")
    print(f"  {'Grupo':<35} {'Cab CAGR':>10} {'LC CAGR':>10} {'Sinal':>15}")
    print("  " + "-" * 76)
    for g in grupos:
        cc = out.loc[g, ("cagr", "Cabotagem")]   if ("cagr", "Cabotagem") in out.columns   else float("nan")
        lc = out.loc[g, ("cagr", "Longo Curso")] if ("cagr", "Longo Curso") in out.columns else float("nan")
        sinal = ""
        if pd.notna(cc) and pd.notna(lc):
            if cc > 3 and lc < -3:
                sinal = "← NACIONALIZAÇÃO"
            elif lc > 3 and cc < -3:
                sinal = "→ EXPORTAÇÃO"
            elif cc < -3 and lc < -3:
                sinal = "↓ DECLÍNIO ambos"
            elif cc > 3 and lc > 3:
                sinal = "↑ CRESCIMENTO ambos"
        cc_s = f"{cc:+.1f}%" if pd.notna(cc) else "—"
        lc_s = f"{lc:+.1f}%" if pd.notna(lc) else "—"
        print(f"  {g[:35]:<35} {cc_s:>10} {lc_s:>10} {sinal:>15}")
    return out


# ─── (t) Modelo simples de previsão Conteinerizada ───────────────────────────
def previsao_conteiner_simples(ano_inicio: int = 2010) -> dict:
    """
    Regressão OLS: momentum_conteiner(t) = a + b·IBC-Br_yoy(t-5) + c·momentum_cargageral(t-k)
    Encontra k ótimo e calcula in-sample R², MAE, RMSE.
    """
    from .macro import ibc_br
    import numpy as np
    try:
        from sklearn.linear_model import LinearRegression
    except ImportError:
        print("  ⚠ sklearn não disponível — pulando")
        return {}

    secao(0, "Modelo simples de previsão do momentum Conteinerizado")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    ma = wide.rolling(12, min_periods=12).mean()
    mom = ma.pct_change(12) * 100

    ibc = ibc_br().resample("MS").last()
    ibc_yoy = ibc.pct_change(12) * 100

    y_cont = mom["Carga Conteinerizada"]
    x_ibc  = ibc_yoy.shift(5)                # IBC defasada 5m (lead positivo p/ porto)

    # busca lag ótimo de Carga Geral como leading indicator
    melhor = None
    for k in range(0, 13):
        x_cg = mom["Carga Geral"].shift(k)
        d = pd.concat([y_cont, x_ibc, x_cg], axis=1).dropna()
        d.columns = ["y", "x_ibc", "x_cg"]
        if len(d) < 24:
            continue
        X = d[["x_ibc", "x_cg"]].values
        y = d["y"].values
        r = LinearRegression().fit(X, y)
        r2 = r.score(X, y)
        if melhor is None or r2 > melhor["r2"]:
            melhor = {"k": k, "r2": r2, "coef": r.coef_,
                      "intercept": r.intercept_, "n": len(d),
                      "X": X, "y": y, "pred": r.predict(X),
                      "idx": d.index}

    if melhor is None:
        print("  ⚠ dados insuficientes"); return {}

    pred = pd.Series(melhor["pred"], index=melhor["idx"])
    obs  = pd.Series(melhor["y"],    index=melhor["idx"])
    err  = obs - pred
    rmse = float(np.sqrt((err**2).mean()))
    mae  = float(err.abs().mean())

    print(f"\nMelhor combinação:")
    print(f"  k (lag Carga Geral) = {melhor['k']} meses")
    print(f"  n = {melhor['n']} observações")
    print(f"  R² in-sample = {melhor['r2']:.3f}")
    print(f"  RMSE = {rmse:.2f} pp   MAE = {mae:.2f} pp")
    print(f"\nCoeficientes:")
    print(f"  intercept           {melhor['intercept']:+.3f}")
    print(f"  IBC-Br a/a (t-5)    {melhor['coef'][0]:+.3f}")
    print(f"  Carga Geral mom (t-{melhor['k']}) {melhor['coef'][1]:+.3f}")

    # gráfico in-sample
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.axhline(0, color="#444", lw=0.6, alpha=0.6)
    ax.plot(obs.index, obs.values, color="#5a9bd4", lw=2.0, label="Conteinerizada — observado")
    ax.plot(pred.index, pred.values, color="#0c4a76", lw=1.6, ls="--", label="Modelo (in-sample)")
    ax.fill_between(pred.index, pred - rmse, pred + rmse,
                    color="#0c4a76", alpha=0.10, label=f"±RMSE ({rmse:.1f} pp)")
    ax.set_title(f"Modelo: momentum Conteinerizada = f(IBC-Br t-5, Carga Geral t-{melhor['k']})  ·  "
                 f"R²={melhor['r2']:.2f}",
                 fontsize=12, fontweight="bold")
    ax.set_ylabel("a/a MA12 (%)")
    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(loc="upper right", framealpha=0.9)
    fig.text(0.5, -0.02,
             "Modelo simples OLS; R² é in-sample (não validação cruzada)",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "previsao_conteiner_simples")
    print(f"  PNG salvo: {FIGS / 'previsao_conteiner_simples.png'}")

    return melhor


# ─── (u) Validação out-of-sample + forecast 12m do modelo Conteinerizada ────
def modelo_conteiner_validacao_e_forecast(ano_inicio: int = 2010,
                                            corte_treino: str = "2022-12",
                                            horizonte: int = 12) -> dict:
    """
    Walk-forward: treina até `corte_treino`, valida nos meses seguintes.
    Depois projeta `horizonte` meses à frente onde os regressores existem.
    Lag IBC-Br = 5m, lag Carga Geral = 12m (do modelo anterior).
    """
    from .macro import ibc_br
    from sklearn.linear_model import LinearRegression
    import numpy as np

    secao(0, f"Modelo Conteinerizada — validação OOS + forecast {horizonte}m")
    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    ma = wide.rolling(12, min_periods=12).mean()
    mom = ma.pct_change(12) * 100

    ibc = ibc_br().resample("MS").last()
    ibc_yoy = ibc.pct_change(12) * 100

    # construir dataset com lags
    df_full = pd.concat({
        "y": mom["Carga Conteinerizada"],
        "x_ibc": ibc_yoy.shift(5),
        "x_cg": mom["Carga Geral"].shift(12),
    }, axis=1).dropna()

    corte = pd.Timestamp(corte_treino)
    treino = df_full[df_full.index <= corte]
    teste  = df_full[df_full.index > corte]

    model = LinearRegression().fit(treino[["x_ibc", "x_cg"]].values,
                                    treino["y"].values)
    pred_treino = model.predict(treino[["x_ibc", "x_cg"]].values)
    pred_teste  = model.predict(teste[["x_ibc", "x_cg"]].values) if len(teste) else np.array([])

    r2_in  = model.score(treino[["x_ibc","x_cg"]].values, treino["y"].values)
    r2_oos = (model.score(teste[["x_ibc","x_cg"]].values, teste["y"].values)
              if len(teste) > 2 else float("nan"))
    rmse_in  = float(np.sqrt(((treino["y"].values - pred_treino) ** 2).mean()))
    rmse_oos = (float(np.sqrt(((teste["y"].values - pred_teste) ** 2).mean()))
                if len(teste) else float("nan"))
    mae_oos = (float(np.abs(teste["y"].values - pred_teste).mean())
               if len(teste) else float("nan"))
    corr_oos = (float(np.corrcoef(teste["y"].values, pred_teste)[0, 1])
                if len(teste) > 2 else float("nan"))

    print(f"\nCorte treino/teste: {corte.strftime('%Y-%m')}")
    print(f"  Treino: {len(treino)} obs ({treino.index.min().strftime('%Y-%m')} → {treino.index.max().strftime('%Y-%m')})")
    print(f"  Teste:  {len(teste)} obs ({teste.index.min().strftime('%Y-%m')} → {teste.index.max().strftime('%Y-%m')})")
    print(f"\nIn-sample:    R²={r2_in:.3f}   RMSE={rmse_in:.2f} pp")
    print(f"Out-of-sample: R²={r2_oos:.3f}  RMSE={rmse_oos:.2f} pp  "
          f"MAE={mae_oos:.2f} pp  corr={corr_oos:+.2f}")
    print(f"Coeficientes: ibc(t-5)={model.coef_[0]:+.3f}  "
          f"cg(t-12)={model.coef_[1]:+.3f}  intercept={model.intercept_:+.3f}")

    # ─── Forecast à frente ───────────────────────────────────────────────
    # construir índice futuro até onde temos regressores
    # x_ibc(t) = ibc_yoy(t-5) → precisa de ibc_yoy até t-5
    # x_cg(t)  = mom_cg(t-12) → precisa de mom_cg até t-12
    # último mês com x_ibc disponível: ibc_yoy.last + 5
    # último mês com x_cg disponível:  mom_cg.last + 12
    ult_ibc_yoy = ibc_yoy.dropna().index.max()
    ult_mom_cg = mom["Carga Geral"].dropna().index.max()
    ult_y      = mom["Carga Conteinerizada"].dropna().index.max()
    def _months_between(a, b):
        return (a.year - b.year) * 12 + (a.month - b.month)
    horizonte_real = min(
        _months_between(ult_ibc_yoy + pd.DateOffset(months=5), ult_y),
        _months_between(ult_mom_cg  + pd.DateOffset(months=12), ult_y),
        horizonte,
    )

    if horizonte_real < 1:
        print("  ⚠ sem horizonte de forecast disponível")
        return {"model": model, "treino": treino, "teste": teste}

    futuro_idx = pd.date_range(ult_y + pd.DateOffset(months=1),
                                periods=horizonte_real, freq="MS")
    x_ibc_fut = pd.Series(
        [ibc_yoy.get(d - pd.DateOffset(months=5)) for d in futuro_idx],
        index=futuro_idx)
    x_cg_fut = pd.Series(
        [mom["Carga Geral"].get(d - pd.DateOffset(months=12)) for d in futuro_idx],
        index=futuro_idx)
    X_fut = np.column_stack([x_ibc_fut.values, x_cg_fut.values])
    y_fut = model.predict(X_fut)
    # banda de incerteza ≈ ±RMSE OOS (assume mesma distribuição de erro)
    pred_futuro = pd.DataFrame({
        "central": y_fut,
        "low": y_fut - (rmse_oos if pd.notna(rmse_oos) else rmse_in),
        "high": y_fut + (rmse_oos if pd.notna(rmse_oos) else rmse_in),
    }, index=futuro_idx)

    print(f"\nForecast {horizonte_real}m à frente:\n")
    print(f"  {'Mês':>10} {'Central':>9} {'Low':>9} {'High':>9}")
    for d, row in pred_futuro.iterrows():
        print(f"  {d.strftime('%Y-%m'):>10} {row['central']:>+8.2f}% "
              f"{row['low']:>+8.2f}% {row['high']:>+8.2f}%")

    # ─── Plot ────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 6.5))
    ax.axhline(0, color="#444", lw=0.6, alpha=0.5)
    # treino
    ax.plot(treino.index, treino["y"].values, color="#5a9bd4",
            lw=1.6, alpha=0.5, label="Conteinerizada — observado (treino)")
    ax.plot(treino.index, pred_treino, color="#0c4a76",
            lw=1.4, ls=":", label=f"Modelo treino (R²={r2_in:.2f})")
    # teste
    ax.plot(teste.index, teste["y"].values, color="#1f6d3a",
            lw=2.0, label="Conteinerizada — observado (teste)")
    ax.plot(teste.index, pred_teste, color="#0c4a76",
            lw=2.0, ls="--", label=f"Modelo OOS (R²={r2_oos:.2f})")
    ax.axvspan(treino.index.min(), corte, color="#5a9bd4", alpha=0.05)
    ax.axvspan(corte, futuro_idx[-1] if len(futuro_idx) else teste.index.max(),
                color="#1f6d3a", alpha=0.05)
    # forecast
    if len(futuro_idx):
        ax.plot(pred_futuro.index, pred_futuro["central"], color="#b54848",
                lw=2.4, label=f"Forecast {horizonte_real}m")
        ax.fill_between(pred_futuro.index, pred_futuro["low"],
                        pred_futuro["high"], color="#b54848", alpha=0.15,
                        label="±RMSE OOS")
    ax.axvline(corte, color="#444", lw=0.8, ls="--", alpha=0.6)
    if len(futuro_idx):
        ax.axvline(ult_y, color="#444", lw=0.8, ls="--", alpha=0.6)
    ax.set_title(f"Modelo Conteinerizada — validação OOS + forecast {horizonte_real}m",
                  fontsize=12, fontweight="bold")
    ax.set_ylabel("Momentum: a/a MA12 (%)")
    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=9)
    fig.text(0.5, -0.02,
             f"OOS: R²={r2_oos:.2f}, RMSE={rmse_oos:.2f}pp, MAE={mae_oos:.2f}pp · "
             f"corte={corte.strftime('%Y-%m')}",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "conteiner_modelo_oos_forecast")
    print(f"\n  PNG salvo: {FIGS / 'conteiner_modelo_oos_forecast.png'}")

    out_csv = FIGS / "conteiner_modelo_oos_forecast.csv"
    pred_futuro.to_csv(out_csv, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    return {
        "model": model, "treino": treino, "teste": teste,
        "pred_treino": pred_treino, "pred_teste": pred_teste,
        "r2_in": r2_in, "r2_oos": r2_oos,
        "rmse_in": rmse_in, "rmse_oos": rmse_oos,
        "mae_oos": mae_oos, "corr_oos": corr_oos,
        "forecast": pred_futuro,
    }


# ─── (v) Diagnóstico porto-a-porto — quem diverge da sua natureza? ──────────
def diagnostico_portos(ano_inicio: int = 2018, top_n: int = 8) -> pd.DataFrame:
    """
    Para cada natureza × porto (com volume relevante), compara CAGR do porto
    com CAGR da natureza no mesmo período. Destaca outperformers/underperformers.
    """
    secao(0, f"Diagnóstico por porto — divergência vs natureza (top {top_n})")
    db = conectar()
    df = db.sql(
        f"""
        SELECT
            EXTRACT(year FROM a."Data Atracação")::INT  AS ano,
            a."Porto Atracação"                          AS porto,
            a.SGUF                                       AS uf,
            c."Natureza da Carga"                        AS natureza,
            SUM(c.VLPesoCargaBruta)                      AS toneladas
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2,3,4
        """
    ).df()

    ult_ano = df["ano"].max()
    df = df[df["ano"] < ult_ano]
    ult_ano = df["ano"].max()
    ano_base = df["ano"].min()
    n_anos = ult_ano - ano_base

    # CAGR por porto×natureza
    pivot = df.pivot_table(index=["porto", "uf", "natureza"], columns="ano",
                           values="toneladas", aggfunc="sum").fillna(0)
    pivot["cagr"] = ((pivot[ult_ano] / pivot[ano_base].replace(0, float("nan")))
                       ** (1 / n_anos) - 1) * 100
    pivot["ult_mt"] = pivot[ult_ano] / 1e6
    pivot = pivot.reset_index()

    # CAGR de cada natureza no agregado nacional
    nat_total = df.groupby(["natureza", "ano"])["toneladas"].sum().unstack("ano")
    nat_cagr = ((nat_total[ult_ano] / nat_total[ano_base])
                  ** (1 / n_anos) - 1) * 100
    pivot["cagr_natureza"] = pivot["natureza"].map(nat_cagr)
    pivot["divergencia"] = pivot["cagr"] - pivot["cagr_natureza"]

    # filtrar portos com volume mínimo (≥ 0,5 Mt no último ano fechado)
    relevantes = pivot[(pivot["ult_mt"] >= 0.5) & pivot["cagr"].notna()]

    out_csv = FIGS / "diagnostico_portos.csv"
    relevantes.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]
    fig, axes = plt.subplots(2, 2, figsize=(15, 11))

    for ax, nat in zip(axes.flat, naturezas):
        sub = relevantes[relevantes["natureza"] == nat].copy()
        if sub.empty:
            ax.set_visible(False); continue
        sub = sub.sort_values("divergencia")
        cor_base = CORES[nat]
        nat_cagr_val = nat_cagr.get(nat, 0)

        # top N positivos + top N negativos
        cabeca = sub.head(top_n)
        cauda = sub.tail(top_n)
        candidatos = pd.concat([cabeca, cauda]).drop_duplicates(["porto", "natureza"])
        candidatos = candidatos.sort_values("divergencia")

        rótulos = candidatos.apply(
            lambda r: f"{r['porto'][:24]} ({r['uf']})", axis=1).tolist()
        cores_b = ["#b54848" if d < 0 else "#2a7f3f" for d in candidatos["divergencia"]]
        ax.barh(rótulos, candidatos["divergencia"], color=cores_b, alpha=0.85)
        for i, (_, r) in enumerate(candidatos.iterrows()):
            ax.text(r["divergencia"], i,
                    f"  {r['cagr']:+.1f}% ({r['ult_mt']:.1f}Mt)",
                    va="center", fontsize=8.5, color="#222")
        ax.axvline(0, color="#444", lw=0.8)
        ax.set_xlabel(f"pp de divergência vs natureza")
        ax.set_title(f"{nat}  ·  Brasil: {nat_cagr_val:+.1f}% CAGR {ano_base}-{ult_ano}",
                     fontsize=11, fontweight="bold", color=cor_base)

    fig.suptitle(
        f"Quais portos divergem da tendência da sua natureza? "
        f"({ano_base}-{ult_ano}, volume ≥ 0,5 Mt/ano)",
        fontsize=13, fontweight="bold", y=1.00)
    fig.text(0.5, -0.01,
             "verde = porto outperforming sua natureza (ganhou share); "
             "vermelho = underperforming (perdeu share)",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "diagnostico_portos")
    print(f"  PNG salvo: {FIGS / 'diagnostico_portos.png'}")

    print(f"\nPortos mais ganhadores e perdedores de share por natureza ({ano_base}-{ult_ano}):\n")
    for nat in naturezas:
        sub = relevantes[relevantes["natureza"] == nat].sort_values("divergencia")
        if sub.empty:
            continue
        nat_c = nat_cagr.get(nat, 0)
        print(f"\n  {nat}  (Brasil: {nat_c:+.1f}% CAGR)")
        print(f"    GANHADORES:")
        for _, r in sub.tail(5).iloc[::-1].iterrows():
            print(f"      {r['porto'][:30]:<30} ({r['uf']})  "
                  f"CAGR {r['cagr']:>+6.1f}%  vol {r['ult_mt']:>5.1f}Mt  "
                  f"div {r['divergencia']:>+6.1f}pp")
        print(f"    PERDEDORES:")
        for _, r in sub.head(5).iterrows():
            print(f"      {r['porto'][:30]:<30} ({r['uf']})  "
                  f"CAGR {r['cagr']:>+6.1f}%  vol {r['ult_mt']:>5.1f}Mt  "
                  f"div {r['divergencia']:>+6.1f}pp")
    return relevantes


# ─── (w) Dashboard executivo ─────────────────────────────────────────────────
def dashboard_executivo(ano_inicio: int = 2010) -> None:
    """Painel consolidado com as 6 leituras mais importantes da sessão."""
    from statsmodels.tsa.seasonal import STL
    secao(0, "Dashboard executivo")

    wide = _serie_mensal_naturezas(ano_inicio=ano_inicio)
    naturezas = ["Granel Sólido", "Granel Líquido e Gasoso",
                 "Carga Geral", "Carga Conteinerizada"]
    ma = wide.rolling(12, min_periods=12).mean()
    mom = ma.pct_change(12) * 100

    fig = plt.figure(figsize=(17, 11))
    gs = fig.add_gridspec(3, 3, hspace=0.42, wspace=0.30)

    # 1. Total Brasil — MM12 e soma 12m
    ax = fig.add_subplot(gs[0, 0])
    total = wide.sum(axis=1)
    s12 = total.rolling(12, min_periods=12).sum() / 1e6
    ax.plot(s12.index, s12.values, color="#0c4a76", lw=2.4)
    u = s12.dropna().iloc[-1]
    ax.annotate(f"{u:.0f} Mt", xy=(s12.dropna().index[-1], u),
                xytext=(-6, 8), textcoords="offset points",
                fontsize=11, color="#0c4a76", fontweight="bold", ha="right")
    ax.set_title("1. Movimentação total Brasil (soma 12m)",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Mt (12m)")

    # 2. Índice 100 (base 2011-01)
    ax = fig.add_subplot(gs[0, 1])
    base_ts = ma.dropna().index[0]
    indice = ma.divide(ma.loc[base_ts]) * 100
    for nat in naturezas:
        ax.plot(indice.index, indice[nat], color=CORES[nat], lw=1.8, label=nat)
    ax.axhline(100, color="#444", lw=0.6, alpha=0.6)
    ax.set_title(f"2. Trajetória — índice base 100 ({base_ts.strftime('%Y-%m')})",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Índice")
    ax.legend(loc="upper left", fontsize=7.5, framealpha=0.9)

    # 3. Momentum atual
    ax = fig.add_subplot(gs[0, 2])
    ax.axhline(0, color="#444", lw=0.6)
    for nat in naturezas:
        ax.plot(mom.index, mom[nat], color=CORES[nat], lw=1.8, label=nat)
        u = mom[nat].dropna()
        if not u.empty:
            ax.scatter([u.index[-1]], [u.iloc[-1]], color=CORES[nat], s=35, zorder=5)
            ax.annotate(f"{u.iloc[-1]:+.1f}%",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(6, 0), textcoords="offset points",
                        fontsize=8.5, color=CORES[nat], fontweight="bold",
                        va="center")
    ax.set_title("3. Momentum (a/a MA12) por natureza",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("% a/a")
    ax.legend(loc="upper left", fontsize=7.5, framealpha=0.9)

    # 4. Cabotagem doméstica vs offshore
    ax = fig.add_subplot(gs[1, 0])
    db = conectar()
    cab = db.sql(f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               CASE WHEN c.FlagOffshore=1 THEN 'Offshore' ELSE 'Doméstica' END AS k,
               SUM(c.VLPesoCargaBruta) AS t
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1 AND c."Tipo Navegação"='Cabotagem'
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2
    """).df()
    cab["data"] = pd.to_datetime(cab["data"])
    cab_wide = cab.pivot(index="data", columns="k", values="t").sort_index().asfreq("MS").fillna(0)
    cab_s12 = cab_wide.rolling(12, min_periods=12).sum() / 1e6
    ax.plot(cab_s12.index, cab_s12["Doméstica"], color="#2a7f3f", lw=2.2, label="Doméstica")
    ax.plot(cab_s12.index, cab_s12["Offshore"], color="#b54848", lw=2.2, label="Offshore (FPSO/ZEE)")
    for col, cor in [("Doméstica", "#2a7f3f"), ("Offshore", "#b54848")]:
        u = cab_s12[col].dropna()
        if not u.empty:
            ax.annotate(f"{u.iloc[-1]:.0f} Mt",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(-6, 6), textcoords="offset points",
                        fontsize=9, color=cor, fontweight="bold", ha="right")
    ax.set_title("4. Cabotagem: doméstica vs offshore (soma 12m)",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Mt (12m)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # 5. Granel Líquido — contribuição por bucket (último ponto)
    ax = fig.add_subplot(gs[1, 1])
    liq = db.sql(f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               CASE
                 WHEN c.FlagOffshore=1 THEN 'Offshore'
                 WHEN c."Tipo Navegação"='Longo Curso' AND c.Sentido='Embarcados' THEN 'LC Export'
                 WHEN c."Tipo Navegação"='Longo Curso' AND c.Sentido='Desembarcados' THEN 'LC Import'
                 WHEN c."Tipo Navegação"='Cabotagem' THEN 'Cabotagem'
                 ELSE 'Outros' END AS bucket,
               SUM(c.VLPesoCargaBruta) AS t
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1
          AND c."Natureza da Carga"='Granel Líquido e Gasoso'
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2
    """).df()
    liq["data"] = pd.to_datetime(liq["data"])
    liq_wide = liq.pivot(index="data", columns="bucket", values="t").sort_index().asfreq("MS").fillna(0)
    liq_ma = liq_wide.rolling(12, min_periods=12).mean()
    total_t_12 = liq_ma.sum(axis=1).shift(12)
    contrib = liq_ma.diff(12).divide(total_t_12, axis=0) * 100
    ult = contrib.dropna(how="all").iloc[-1]
    cores_b = {"Offshore": "#b54848", "LC Export": "#2a7f3f",
               "LC Import": "#5a9bd4", "Cabotagem": "#f0a04b", "Outros": "#888"}
    ult_o = ult.sort_values()
    bars = ax.barh(ult_o.index, ult_o.values,
                   color=[cores_b.get(c, "#888") for c in ult_o.index], alpha=0.85)
    for i, v in enumerate(ult_o.values):
        ax.text(v, i, f"  {v:+.1f}pp", va="center", fontsize=9, color="#222")
    ax.axvline(0, color="#444", lw=0.7)
    total = ult.sum()
    ax.set_title(f"5. Granel Líquido +{total:.1f}% — quem puxa?",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("pp do crescimento a/a")

    # 6. TEU cabotagem vs LC (índice 100)
    ax = fig.add_subplot(gs[1, 2])
    teu = db.sql(f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               c."Tipo Navegação" AS nav, SUM(c.TEU) AS teu
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1
          AND c."Natureza da Carga"='Carga Conteinerizada'
          AND c.TEU>0 AND c."Tipo Navegação" IN ('Cabotagem','Longo Curso')
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2
    """).df()
    teu["data"] = pd.to_datetime(teu["data"])
    teu_wide = teu.pivot(index="data", columns="nav", values="teu").sort_index().asfreq("MS").fillna(0)
    teu_ma = teu_wide.rolling(12, min_periods=12).mean()
    base = teu_ma.dropna().index[0]
    teu_idx = teu_ma.divide(teu_ma.loc[base]) * 100
    cores_nav = {"Cabotagem": "#5a9bd4", "Longo Curso": "#d97742"}
    for n, cor in cores_nav.items():
        if n not in teu_idx.columns:
            continue
        ax.plot(teu_idx.index, teu_idx[n], color=cor, lw=2.2, label=n)
        u = teu_idx[n].dropna()
        if not u.empty:
            ax.annotate(f"{u.iloc[-1]:.0f}",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(6, 0), textcoords="offset points",
                        fontsize=10, color=cor, fontweight="bold", va="center")
    ax.axhline(100, color="#444", lw=0.6, alpha=0.6)
    ax.set_title(f"6. TEU contêiner — índice 100 ({base.strftime('%Y-%m')})",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # 7. Top 5 rotas TEU cabotagem
    ax = fig.add_subplot(gs[2, 0])
    rotas = db.sql(f"""
        SELECT o."Origem Nome" || ' (' || o."UF.Origem" || ') → ' ||
               d."Nome Destino" || ' (' || d."UF.Destino" || ')' AS rota,
               SUM(c.TEU) AS teu
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        LEFT JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagMCOperacaoCarga=1
          AND c."Natureza da Carga"='Carga Conteinerizada'
          AND c."Tipo Navegação"='Cabotagem' AND c.TEU>0
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1 ORDER BY teu DESC LIMIT 5
    """).df()
    rotas["rota_short"] = rotas["rota"].str.slice(0, 36)
    ax.barh(rotas["rota_short"][::-1], rotas["teu"][::-1] / 1e6,
            color="#5a9bd4", alpha=0.85)
    for i, v in enumerate(rotas["teu"][::-1] / 1e6):
        ax.text(v, i, f"  {v:.2f}M", va="center", fontsize=9, color="#222")
    ax.set_title("7. Top 5 rotas — TEU cabotagem", fontsize=11, fontweight="bold")
    ax.set_xlabel("M TEU acumulado")

    # 8. Fase do ciclo (Δ6m do momentum) — bullet
    ax = fig.add_subplot(gs[2, 1])
    accel = mom - mom.shift(6)
    ax.axvline(0, color="#444", lw=0.8)
    valores = []
    for nat in naturezas:
        u = accel[nat].dropna()
        if not u.empty:
            valores.append((nat, u.iloc[-1], mom[nat].dropna().iloc[-1]))
    valores.sort(key=lambda x: x[1])
    nomes = [v[0] for v in valores]
    deltas = [v[1] for v in valores]
    ax.barh(nomes, deltas,
            color=["#b54848" if d < 0 else "#2a7f3f" for d in deltas], alpha=0.85)
    for i, (nat, d, m) in enumerate(valores):
        ax.text(d, i, f"  Δ6m {d:+.1f}pp · mom {m:+.1f}%",
                va="center", fontsize=8.5, color="#222")
    ax.set_title("8. Fase do ciclo (Δ6m do momentum)",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("pp em 6 meses")

    # 9. Saldo Longo Curso (Export − Import)
    ax = fig.add_subplot(gs[2, 2])
    lc = db.sql(f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               c.Sentido AS sentido, SUM(c.VLPesoCargaBruta) AS t
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagMCOperacaoCarga=1 AND c."Tipo Navegação"='Longo Curso'
          AND c.Sentido IN ('Embarcados','Desembarcados')
          AND a.Ano >= {ano_inicio}
          AND EXTRACT(year FROM a."Data Atracação") >= {ano_inicio}
        GROUP BY 1,2
    """).df()
    lc["data"] = pd.to_datetime(lc["data"])
    lc_w = lc.pivot(index="data", columns="sentido", values="t").sort_index().asfreq("MS").fillna(0)
    lc_s12 = lc_w.rolling(12, min_periods=12).sum() / 1e6
    ax.plot(lc_s12.index, lc_s12["Embarcados"], color="#2a7f3f", lw=2.2, label="Exportação")
    ax.plot(lc_s12.index, lc_s12["Desembarcados"], color="#b54848", lw=2.2, label="Importação")
    ax.fill_between(lc_s12.index, 0, lc_s12["Embarcados"] - lc_s12["Desembarcados"],
                    color="#999", alpha=0.18, label="Saldo")
    for col, cor in [("Embarcados", "#2a7f3f"), ("Desembarcados", "#b54848")]:
        u = lc_s12[col].dropna()
        if not u.empty:
            ax.annotate(f"{u.iloc[-1]:.0f}",
                        xy=(u.index[-1], u.iloc[-1]),
                        xytext=(-6, 6), textcoords="offset points",
                        fontsize=9, color=cor, fontweight="bold", ha="right")
    ax.set_title("9. Longo Curso — saldo comercial físico",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Mt (12m)")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    for ax in fig.axes:
        if ax.get_xlabel() == "":
            ax.xaxis.set_major_locator(mdates.YearLocator(3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle(
        "Dashboard executivo — Movimentação portuária Brasil (até fev/2026)",
        fontsize=14, fontweight="bold", y=1.005)
    fig.text(0.5, -0.005,
             "Fonte: ANTAQ Base Estatística Aquaviária · FlagMCOperacaoCarga=1 · "
             "Análises geradas em medias_moveis_perfil.py",
             ha="center", fontsize=9, color="#666")
    salvar(fig, "dashboard_executivo")
    print(f"  PNG salvo: {FIGS / 'dashboard_executivo.png'}")


def imprimir_resumo(df: pd.DataFrame, janela: int = JANELA) -> None:
    print(f"\nÚltima MM{janela}m por perfil de carga (variação a/a da MA):\n")
    print(f"  {'Perfil':<28} {'MM último':>14}  {'a/a MA':>10}  {'Mês':>10}")
    print("  " + "-" * 70)
    for nat, sub in df.groupby("natureza"):
        sub = sub.dropna(subset=["ma12"]).sort_values("data")
        if sub.empty:
            continue
        u = sub.iloc[-1]
        yoy = u.get("yoy_ma_pct")
        yoy_str = f"{yoy:+.1f}%" if pd.notna(yoy) else "—"
        print(f"  {nat:<28} {fmt(u['ma12']):>12} t  "
              f"{yoy_str:>10}  {u['data'].strftime('%Y-%m'):>10}")


def main(janela: int = JANELA, ano_inicio: int = 2010) -> pd.DataFrame:
    secao(0, f"Médias móveis ({janela}m) por perfil de carga")
    df = serie_mensal_por_natureza(janela=janela, ano_inicio=ano_inicio)

    out_csv = FIGS / "medias_moveis_perfil.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV salvo: {out_csv}")

    plotar(df, janela=janela)
    print(f"  PNG salvo: {FIGS / 'medias_moveis_perfil.png'}")

    imprimir_resumo(df, janela=janela)
    return df


if __name__ == "__main__":
    main()
    por_sentido()
    por_navegacao()
