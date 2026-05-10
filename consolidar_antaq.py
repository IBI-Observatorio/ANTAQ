"""
Extrai os ZIPs da ANTAQ e consolida em Parquet particionados por tabela/ano.

Estrutura de saida:
    parquet/
        Atracacao/2010.parquet ... 2026.parquet
        Carga/2010.parquet ... 2026.parquet
        CargaConteinerizada/...
        TemposAtracacao/...
        TemposAtracacaoParalisacao/...
        TaxaOcupacao/...
        TaxaOcupacaoComCarga/...
        TaxaOcupacaoTOAtracacao/...
        CargaHidrovia/...
        CargaRegiao/...
        CargaRio/...
        cadastro/
            InstalacaoOrigem.parquet
            InstalacaoDestino.parquet
            Mercadoria.parquet
            MercadoriaConteinerizada.parquet

Como carregar depois:
    import pandas as pd
    from pathlib import Path

    def carregar(tabela, anos=None):
        base = Path("parquet") / tabela
        arquivos = sorted(base.glob("*.parquet"))
        if anos:
            arquivos = [a for a in arquivos if int(a.stem) in anos]
        return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)

    atracacao = carregar("Atracacao")
    carga_2023 = carregar("Carga", anos=[2023])
"""

import zipfile
import pandas as pd
from pathlib import Path

DADOS_DIR = Path("dados")
OUTPUT_DIR = Path("parquet")
ANOS = list(range(2010, 2027))

ZIPS_ANUAIS = [
    "Atracacao.zip",
    "Carga.zip",
    "CargaConteinerizada.zip",
    "TemposAtracacao.zip",
    "TaxaOcupacao.zip",
    "CargaRegiao_Hidrovia_Rio.zip",
]

COLUNAS_DATA_ATRACACAO = [
    "Data Atracacao",
    "Data Chegada",
    "Data Desatracacao",
    "Data Inicio Operacao",
    "Data Termino Operacao",
]

READ_OPTS = dict(
    sep=";",
    encoding="utf-8-sig",
    decimal=",",
    low_memory=False,
    on_bad_lines="warn",
)


def nome_tabela(arquivo_interno: str, ano: int) -> str:
    nome = arquivo_interno.removesuffix(".txt")
    if nome.startswith(str(ano)):
        nome = nome[4:]
    return nome.replace("_", "")


def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    return df


def ler_df(z: zipfile.ZipFile, arquivo: str, ano: int) -> pd.DataFrame:
    with z.open(arquivo) as f:
        df = pd.read_csv(f, **READ_OPTS)
    df = normalizar_colunas(df)
    if "Ano" not in df.columns:
        df.insert(0, "Ano", ano)
    return df


def converter_datas_atracacao(df: pd.DataFrame) -> pd.DataFrame:
    mapa = {
        "Data Atracacao": "Data Atracação",
        "Data Chegada": "Data Chegada",
        "Data Desatracacao": "Data Desatracação",
        "Data Inicio Operacao": "Data Início Operação",
        "Data Termino Operacao": "Data Término Operação",
    }
    for col_ascii, col_acentuado in mapa.items():
        col = col_acentuado if col_acentuado in df.columns else col_ascii if col_ascii in df.columns else None
        if col:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    return df


def processar_anuais():
    for ano in ANOS:
        print(f"\n-- {ano} " + "-" * 40)

        for zip_nome in ZIPS_ANUAIS:
            zip_path = DADOS_DIR / str(ano) / zip_nome
            if not zip_path.exists():
                continue

            try:
                with zipfile.ZipFile(zip_path) as z:
                    arquivos = [n for n in z.namelist() if n.endswith(".txt")]
                    if not arquivos:
                        continue

                    for arquivo in arquivos:
                        tabela = nome_tabela(arquivo, ano)
                        destino = OUTPUT_DIR / tabela / f"{ano}.parquet"

                        if destino.exists():
                            print(f"  {tabela}/{ano}.parquet ja existe, pulando.")
                            continue

                        print(f"  {tabela} ... ", end="", flush=True)
                        df = ler_df(z, arquivo, ano)

                        if tabela == "Atracacao":
                            df = converter_datas_atracacao(df)

                        destino.parent.mkdir(parents=True, exist_ok=True)
                        df.to_parquet(destino, index=False, compression="snappy")
                        print(f"{len(df):,} linhas -> {destino.stat().st_size / 1e6:.1f} MB")

            except Exception as e:
                print(f"\n  ERRO em {zip_path}: {e}")


def processar_cadastro():
    print("\n-- Cadastro " + "-" * 35)
    destino_base = OUTPUT_DIR / "cadastro"
    destino_base.mkdir(parents=True, exist_ok=True)

    cadastro_zips = [
        "InstalacaoOrigem.zip",
        "InstalacaoDestino.zip",
        "Mercadoria.zip",
        "MercadoriaConteinerizada.zip",
    ]

    for zip_nome in cadastro_zips:
        zip_path = DADOS_DIR / "cadastro" / zip_nome
        tabela = zip_nome.removesuffix(".zip")
        destino = destino_base / f"{tabela}.parquet"

        if destino.exists():
            print(f"  {tabela}.parquet ja existe, pulando.")
            continue

        if not zip_path.exists():
            print(f"  {zip_nome} nao encontrado.")
            continue

        try:
            with zipfile.ZipFile(zip_path) as z:
                arquivos = [n for n in z.namelist() if n.endswith(".txt")]
                if not arquivos:
                    continue
                print(f"  {tabela} ... ", end="", flush=True)
                df = ler_df(z, arquivos[0], ano=0)
                if "Ano" in df.columns and df["Ano"].eq(0).all():
                    df = df.drop(columns=["Ano"])
                df.to_parquet(destino, index=False, compression="snappy")
                print(f"{len(df):,} linhas -> {destino.stat().st_size / 1e6:.1f} MB")
        except Exception as e:
            print(f"\n  ERRO em {zip_path}: {e}")


def resumo():
    parquets = sorted(OUTPUT_DIR.rglob("*.parquet"))
    total_mb = sum(p.stat().st_size for p in parquets) / 1e6
    tabelas = {p.parent.name for p in parquets}
    print(f"\n{'='*50}")
    print(f"  Tabelas geradas : {len(tabelas)}")
    print(f"  Arquivos Parquet: {len(parquets)}")
    print(f"  Tamanho total   : {total_mb:.1f} MB")
    print(f"  Diretorio       : {OUTPUT_DIR.resolve()}")
    print(f"{'='*50}")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    print("ANTAQ -- Consolidacao de dados para Parquet")
    processar_cadastro()
    processar_anuais()
    resumo()


if __name__ == "__main__":
    main()
