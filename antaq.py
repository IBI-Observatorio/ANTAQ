"""
Módulo de acesso à Base Estatística Aquaviária da ANTAQ.

Uso rápido:
    import antaq

    # Conexão DuckDB com todas as views registradas (recomendado)
    db = antaq.conectar()
    df = db.sql("SELECT * FROM Atracacao WHERE Ano = 2023 LIMIT 100").df()

    # Ou carregue diretamente em pandas
    atracacao = antaq.carregar("Atracacao", anos=[2022, 2023])
    mercadoria = antaq.carregar("Mercadoria")

    # Resumo de todas as tabelas disponíveis
    antaq.resumo()
"""

import pandas as pd
import duckdb
from pathlib import Path

PARQUET_DIR = Path(__file__).parent / "parquet"

# Tabelas com particionamento anual (2010-2026)
TABELAS_ANUAIS = [
    "Atracacao",
    "Carga",
    "CargaConteinerizada",
    "CargaHidrovia",
    "CargaRegiao",
    "CargaRio",
    "TemposAtracacao",
    "TemposAtracacaoParalisacao",
    "TaxaOcupacao",
    "TaxaOcupacaoComCarga",
    "TaxaOcupacaoTOAtracacao",
]

# Tabelas de cadastro — estáticas (sem ano)
TABELAS_CADASTRO = [
    "InstalacaoOrigem",
    "InstalacaoDestino",
    "Mercadoria",
    "MercadoriaConteinerizada",
]

TODAS_TABELAS = TABELAS_ANUAIS + TABELAS_CADASTRO


def conectar(parquet_dir: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """
    Retorna uma conexão DuckDB com views para todas as tabelas ANTAQ.

    Views disponíveis após conectar():
        Anuais (2010-2026): Atracacao, Carga, CargaConteinerizada,
            CargaHidrovia, CargaRegiao, CargaRio, TemposAtracacao,
            TemposAtracacaoParalisacao, TaxaOcupacao, TaxaOcupacaoComCarga,
            TaxaOcupacaoTOAtracacao
        Cadastro: InstalacaoOrigem, InstalacaoDestino, Mercadoria,
            MercadoriaConteinerizada

    Exemplo:
        db = antaq.conectar()
        df = db.sql("SELECT Ano, COUNT(*) AS n FROM Atracacao GROUP BY Ano").df()
    """
    base = Path(parquet_dir) if parquet_dir else PARQUET_DIR
    con = duckdb.connect()

    for tabela in TABELAS_ANUAIS:
        dir_tabela = base / tabela
        if dir_tabela.exists() and any(dir_tabela.glob("*.parquet")):
            glob = str(dir_tabela / "*.parquet").replace("\\", "/")
            con.execute(
                f"CREATE OR REPLACE VIEW {tabela} AS "
                f"SELECT * FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)"
            )

    for tabela in TABELAS_CADASTRO:
        path = base / "cadastro" / f"{tabela}.parquet"
        if path.exists():
            p = str(path).replace("\\", "/")
            con.execute(
                f"CREATE OR REPLACE VIEW {tabela} AS "
                f"SELECT * FROM read_parquet('{p}')"
            )

    return con


def carregar(tabela: str, anos: int | list[int] | None = None) -> pd.DataFrame:
    """
    Carrega uma tabela ANTAQ como DataFrame pandas.

    Args:
        tabela: Nome da tabela (ex: "Atracacao", "Mercadoria")
        anos:   Ano ou lista de anos para filtrar (apenas tabelas anuais).
                Se None, carrega todos os anos disponíveis.

    Exemplos:
        atracacao_2023 = antaq.carregar("Atracacao", anos=2023)
        carga_recente  = antaq.carregar("Carga", anos=[2024, 2025])
        mercadoria     = antaq.carregar("Mercadoria")
    """
    if tabela in TABELAS_CADASTRO:
        path = PARQUET_DIR / "cadastro" / f"{tabela}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Cadastro não encontrado: {path}")
        return pd.read_parquet(path)

    if tabela not in TABELAS_ANUAIS:
        raise ValueError(f"Tabela desconhecida: {tabela!r}. Use uma de: {TODAS_TABELAS}")

    base = PARQUET_DIR / tabela
    if not base.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {base}")

    arquivos = sorted(base.glob("*.parquet"))
    if anos is not None:
        anos_set = {anos} if isinstance(anos, int) else set(anos)
        arquivos = [a for a in arquivos if int(a.stem) in anos_set]

    if not arquivos:
        raise FileNotFoundError(f"Nenhum arquivo encontrado para {tabela} anos={anos}")

    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def anos_disponiveis(tabela: str) -> list[int]:
    """Retorna os anos com Parquet disponível para a tabela."""
    base = PARQUET_DIR / tabela
    if not base.exists():
        return []
    return sorted(int(a.stem) for a in base.glob("*.parquet"))


def resumo(parquet_dir: str | Path | None = None) -> None:
    """
    Imprime estatísticas de todas as tabelas disponíveis.

    Mostra: nome, intervalo de anos, contagem de linhas e tamanho em disco.
    """
    base = Path(parquet_dir) if parquet_dir else PARQUET_DIR
    con = duckdb.connect()

    print(f"\n{'Tabela':<37} {'Anos':<13} {'Linhas':>13}  {'Disco':>8}")
    print("-" * 78)

    total_mb = 0.0

    for tabela in TABELAS_ANUAIS:
        dir_tabela = base / tabela
        arquivos = sorted(dir_tabela.glob("*.parquet")) if dir_tabela.exists() else []
        if not arquivos:
            continue
        anos = [int(a.stem) for a in arquivos]
        mb = sum(a.stat().st_size for a in arquivos) / 1e6
        total_mb += mb
        glob = str(dir_tabela / "*.parquet").replace("\\", "/")
        n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{glob}', hive_partitioning=false)").fetchone()[0]
        intervalo = f"{min(anos)}-{max(anos)}"
        print(f"  {tabela:<35} {intervalo:<13} {n:>13,}  {mb:>6.1f} MB")

    print()

    for tabela in TABELAS_CADASTRO:
        path = base / "cadastro" / f"{tabela}.parquet"
        if not path.exists():
            continue
        mb = path.stat().st_size / 1e6
        total_mb += mb
        p = str(path).replace("\\", "/")
        n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone()[0]
        print(f"  {tabela:<35} {'cadastro':<13} {n:>13,}  {mb:>6.1f} MB")

    print("-" * 78)
    print(f"  {'TOTAL':<35} {'':<13} {'':<13}  {total_mb:>6.1f} MB\n")
    con.close()


# ─── Views SQL pré-construídas ─────────────────────────────────────────────────

VIEWS = {
    "carga_completa": """
        -- Carga com classificação de mercadoria e localização de origem/destino
        SELECT
            c.IDCarga,
            c.IDAtracacao,
            c.Ano,
            c."Natureza da Carga",
            c."Sentido",
            c."Tipo Navegação",
            c."VLPesoCargaBruta",
            c.TEU,
            c."FlagCabotagem",
            c."FlagLongoCurso",
            c."FlagOffshore",
            m."Grupo de Mercadoria",
            m."Mercadoria",
            m."Nomenclatura Simplificada Mercadoria",
            o."Origem Nome"        AS "Porto Origem",
            o."País Origem"        AS "País Origem",
            o."UF.Origem"          AS "UF Origem",
            o."Continente Origem",
            d."Nome Destino"       AS "Porto Destino",
            d."País Destino"       AS "País Destino",
            d."UF.Destino"         AS "UF Destino",
            d."Continente Destino"
        FROM Carga c
        LEFT JOIN Mercadoria        m ON c.CDMercadoria            = m.CDMercadoria
        LEFT JOIN InstalacaoOrigem  o ON c.Origem                  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino                 = d.Destino
    """,

    "atracacao_completa": """
        -- Atracação com tempos (T1-T4, TA, TE) em horas como DOUBLE (prontos para PMO/PMG)
        -- Os tempos são armazenados como VARCHAR com vírgula decimal; os casts convertem aqui.
        SELECT
            a.*,
            TRY_CAST(replace(t.TEsperaAtracacao,   ',', '.') AS DOUBLE) AS TEsperaAtracacao,
            TRY_CAST(replace(t.TEsperaInicioOp,    ',', '.') AS DOUBLE) AS TEsperaInicioOp,
            TRY_CAST(replace(t.TOperacao,          ',', '.') AS DOUBLE) AS TOperacao,
            TRY_CAST(replace(t.TEsperaDesatracacao,',', '.') AS DOUBLE) AS TEsperaDesatracacao,
            TRY_CAST(replace(t.TAtracado,          ',', '.') AS DOUBLE) AS TAtracado,
            TRY_CAST(replace(t.TEstadia,           ',', '.') AS DOUBLE) AS TEstadia
        FROM Atracacao a
        LEFT JOIN TemposAtracacao t USING (IDAtracacao)
    """,

    "movimentacao_porto_ano": """
        -- Tonelagem total por porto, ano e natureza de carga (sem dupla contagem)
        SELECT
            a."Porto Atracação",
            a.SGUF,
            a."Região Geográfica",
            c.Ano,
            c."Natureza da Carga",
            c."Tipo Navegação",
            SUM(c."VLPesoCargaBruta") AS "Toneladas",
            SUM(c.TEU)                AS "TEUs",
            COUNT(DISTINCT c.IDAtracacao) AS "Atracacoes"
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c."FlagMCOperacaoCarga" = 1
        GROUP BY ALL
    """,

    "ocupacao_berco_mensal": """
        -- Taxa de ocupação mensal por berço (minutos ocupados / minutos do mês)
        SELECT
            IDBerco,
            AnoTaxaOcupacao        AS Ano,
            MêsTaxaOcupacao        AS Mes,
            SUM(TempoEmMinutosdias) AS MinutosOcupados,
            -- minutos totais no mês (aproximado com 30 dias)
            30 * 24 * 60           AS MinutosMes,
            ROUND(SUM(TempoEmMinutosdias) * 100.0 / (30 * 24 * 60), 2) AS TaxaOcupacaoPct
        FROM TaxaOcupacao
        GROUP BY ALL
    """,
}


def registrar_views(con: duckdb.DuckDBPyConnection) -> None:
    """
    Registra views analíticas pré-construídas na conexão DuckDB.

    Views adicionais após registrar_views():
        carga_completa          — Carga + Mercadoria + Origem + Destino
        atracacao_completa      — Atracacao + TemposAtracacao
        movimentacao_porto_ano  — Tonelagem/TEUs por porto-ano (FlagMCOperacaoCarga=1)
        ocupacao_berco_mensal   — Taxa de ocupação % por berço/mês

    Exemplo:
        db = antaq.conectar()
        antaq.registrar_views(db)
        df = db.sql("SELECT * FROM movimentacao_porto_ano WHERE Ano = 2023").df()
    """
    for nome, sql in VIEWS.items():
        con.execute(f"CREATE OR REPLACE VIEW {nome} AS {sql}")


if __name__ == "__main__":
    resumo()
