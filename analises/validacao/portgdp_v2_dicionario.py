"""
Dia 1 — Construção mecânica do dicionário de séries do DFM PortGDP v2.

Pré-registrado em validacao/portgdp_v2/REGRA_DECISAO.md.

Critério (sem inspeção visual prévia das séries):
    Portos    : top 10 por movimentação total 2014-2024 (toneladas)
    Naturezas : Carga Conteinerizada, Carga Geral, Granel Sólido, Granel Líquido e Gasoso
    Sentidos  : Desembarcados, Embarcados
    Filtro    : FlagLongoCurso = 1
    Universo  : 10 × 4 × 2 = 80 séries candidatas

Filtro de cobertura: descartar séries com > 24 meses de zeros/NA em 2014-2025.

Outputs:
    validacao/portgdp_v2/dicionario_series.csv
    validacao/portgdp_v2/series_brutas.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import antaq                                       # noqa: E402

OUT = ROOT / "validacao" / "portgdp_v2"
OUT.mkdir(parents=True, exist_ok=True)

NATUREZAS = (
    "Carga Conteinerizada",
    "Carga Geral",
    "Granel Sólido",
    "Granel Líquido e Gasoso",
)
SENTIDOS = ("Desembarcados", "Embarcados")
PERIODO_INI = "2014-01-01"
PERIODO_FIM = "2026-01-01"
LIMITE_FALTANTES = 24  # meses


def top10_portos() -> list[str]:
    db = antaq.conectar()
    df = db.sql(
        """
        SELECT a."Porto Atracação"        AS porto,
               SUM(c.VLPesoCargaBruta)    AS ton
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.Ano BETWEEN 2014 AND 2024
        GROUP BY 1
        ORDER BY ton DESC
        LIMIT 10
        """
    ).df()
    return df["porto"].tolist()


def construir_universo(portos: list[str]) -> pd.DataFrame:
    """Retorna DataFrame mensal long: (mes, porto, natureza, sentido, ton)."""
    db = antaq.conectar()
    placeholders = ", ".join(f"'{p.replace(chr(39), chr(39)+chr(39))}'" for p in portos)
    df = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS mes,
               a."Porto Atracação"      AS porto,
               c."Natureza da Carga"    AS natureza,
               c.Sentido                AS sentido,
               SUM(c.VLPesoCargaBruta)  AS ton
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c.FlagLongoCurso = 1
          AND a."Porto Atracação" IN ({placeholders})
          AND c."Natureza da Carga" IN ('Carga Conteinerizada','Carga Geral',
                                         'Granel Sólido','Granel Líquido e Gasoso')
          AND c.Sentido IN ('Desembarcados','Embarcados')
          AND a."Data Atracação" >= '{PERIODO_INI}'
          AND a."Data Atracação"  < '{PERIODO_FIM}'
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4
        """
    ).df()
    df["mes"] = pd.to_datetime(df["mes"])
    return df


def montar_painel(df_long: pd.DataFrame, portos: list[str]) -> pd.DataFrame:
    """
    Pivota para painel wide com 80 colunas (chave = porto|natureza|sentido)
    e índice mensal completo. Faltantes preenchidos com NaN (não com zero —
    distinção é importante para o filtro de cobertura).
    """
    df_long["chave"] = (
        df_long["porto"].str.replace("|", "_", regex=False) + "|" +
        df_long["natureza"] + "|" +
        df_long["sentido"]
    )
    pivot = (df_long.pivot_table(index="mes", columns="chave",
                                  values="ton", aggfunc="sum")
                    .sort_index())
    # Garante grade mensal completa
    idx = pd.date_range(PERIODO_INI, "2025-12-01", freq="MS")
    pivot = pivot.reindex(idx)
    pivot.index.name = "mes"

    # Garante presença de todas as 80 chaves esperadas
    chaves_esperadas = [f"{p}|{n}|{s}" for p in portos
                                          for n in NATUREZAS
                                          for s in SENTIDOS]
    for chave in chaves_esperadas:
        if chave not in pivot.columns:
            pivot[chave] = pd.NA
    pivot = pivot[chaves_esperadas]
    return pivot


def avaliar_cobertura(painel: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada série: conta meses com NaN ou zero; aplica regra de exclusão
    (>24 meses → drop). Reporta também quantidade de stretches longos de
    NaN (>2 consecutivos) — exclui imediatamente se houver.
    """
    rows = []
    for chave in painel.columns:
        s = painel[chave]
        n_nan = int(s.isna().sum())
        n_zero = int((s == 0).sum())
        n_zero_ou_nan = int((s.isna() | (s == 0)).sum())

        # Maior streak de NaN consecutivos
        nan_mask = s.isna().astype(int)
        # Conta streaks via groupby
        if nan_mask.any():
            streaks = (nan_mask.groupby((nan_mask != nan_mask.shift()).cumsum())
                                .sum())
            streak_max = int(streaks.max())
        else:
            streak_max = 0

        excluida = False
        motivo = ""
        if n_zero_ou_nan > LIMITE_FALTANTES:
            excluida = True
            motivo = f"{n_zero_ou_nan} meses zero/NA > {LIMITE_FALTANTES}"
        elif streak_max > 2:
            excluida = True
            motivo = f"streak NaN consecutivo {streak_max} > 2"

        porto, natureza, sentido = chave.split("|")
        rows.append({
            "chave": chave,
            "porto": porto,
            "natureza": natureza,
            "sentido": sentido,
            "n_obs":   int(s.notna().sum()),
            "n_nan":   n_nan,
            "n_zero":  n_zero,
            "streak_nan_max": streak_max,
            "excluida": excluida,
            "motivo":  motivo,
        })
    return pd.DataFrame(rows)


def main() -> int:
    print("\n  ── Dia 1 — Dicionário PortGDP v2 ──")
    print("\n  [1.1] Top 10 portos por movimentação total 2014-2024…")
    portos = top10_portos()
    for i, p in enumerate(portos, 1):
        print(f"    {i:>2}. {p}")

    print(f"\n  [1.2] Construindo universo de séries (80 candidatas)…")
    df_long = construir_universo(portos)
    print(f"    {len(df_long):,} linhas brutas (porto-natureza-sentido-mês).")

    print("\n  [1.3] Pivotando para painel wide…")
    painel = montar_painel(df_long, portos)
    print(f"    Painel: {painel.shape[0]} meses × {painel.shape[1]} séries")

    print(f"\n  [1.4] Avaliando cobertura (limite: {LIMITE_FALTANTES} meses zero/NA)…")
    dic = avaliar_cobertura(painel)
    n_excl = int(dic["excluida"].sum())
    n_ok   = len(dic) - n_excl
    print(f"    {n_ok} séries passam · {n_excl} excluídas")

    # Salvar
    arq_dic = OUT / "dicionario_series.csv"
    dic.to_csv(arq_dic, index=False, encoding="utf-8")
    print(f"\n  ✓ {arq_dic.relative_to(ROOT)}")

    arq_painel = OUT / "series_brutas.parquet"
    painel.reset_index().to_parquet(arq_painel)
    print(f"  ✓ {arq_painel.relative_to(ROOT)}  (painel completo)")

    # Sumário por motivo de exclusão
    if n_excl > 0:
        print("\n  Motivos de exclusão (top):")
        for motivo, n in dic[dic["excluida"]]["motivo"].value_counts().head(5).items():
            print(f"    {n:>3}  {motivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
