"""
Download completo da base de dados estatísticos da ANTAQ.
Fonte: https://estatistica.antaq.gov.br/ea/sense/download.html
"""

import os
import sys
import time
import requests
from pathlib import Path

BASE_URL = "https://estatistica.antaq.gov.br/ea/txt/"

ANOS = list(range(2010, 2027))  # 2010 a 2026

# Tabelas disponíveis por ano
TABELAS_ANUAIS = [
    "Atracacao.zip",
    "Carga.zip",
    "CargaConteinerizada.zip",
    "TemposAtracacao.zip",
    "TaxaOcupacao.zip",
    "CargaRegiao_Hidrovia_Rio.zip",
]

# Tabelas de cadastro (sem ano, estáticas)
TABELAS_CADASTRO = [
    "InstalacaoOrigem.zip",
    "InstalacaoDestino.zip",
    "Mercadoria.zip",
    "MercadoriaConteinerizada.zip",
    "MetadadosMovimentacao.zip",
]

OUTPUT_DIR = Path("dados")


def formatar_bytes(n_bytes: int) -> str:
    for unidade in ["B", "KB", "MB", "GB"]:
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unidade}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def download_arquivo(url: str, destino: Path, sessao: requests.Session) -> str:
    """
    Faz download de um arquivo com barra de progresso simples.
    Retorna: 'baixado', 'ja_existe', '404', 'erro'
    """
    if destino.exists():
        return "ja_existe"

    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")

    try:
        resp = sessao.get(url, stream=True, timeout=60)

        if resp.status_code == 404:
            return "404"

        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        baixado = 0
        inicio = time.time()

        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    baixado += len(chunk)

                    if total:
                        pct = baixado / total * 100
                        velocidade = baixado / max(time.time() - inicio, 0.001)
                        print(
                            f"\r    {pct:5.1f}%  {formatar_bytes(baixado)}/{formatar_bytes(total)}"
                            f"  ({formatar_bytes(velocidade)}/s)    ",
                            end="",
                            flush=True,
                        )

        tmp.rename(destino)
        print(f"\r    {formatar_bytes(baixado)} baixados" + " " * 30)
        return "baixado"

    except requests.exceptions.RequestException as e:
        if tmp.exists():
            tmp.unlink()
        print(f"\r    ERRO: {e}" + " " * 30)
        return "erro"


def main():
    print("=" * 60)
    print("  Download da Base Estatística Aquaviária - ANTAQ")
    print("=" * 60)

    sessao = requests.Session()
    sessao.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ANTAQ-Downloader/1.0)"})

    stats = {"baixado": 0, "ja_existe": 0, "nao_disponivel": 0, "erro": 0}

    # ── Tabelas de cadastro ──────────────────────────────────────
    print("\n[ Tabelas de Cadastro ]\n")
    destino_cadastro = OUTPUT_DIR / "cadastro"

    for arquivo in TABELAS_CADASTRO:
        url = BASE_URL + arquivo
        destino = destino_cadastro / arquivo
        print(f"  {arquivo}")
        resultado = download_arquivo(url, destino, sessao)
        stats[resultado if resultado in stats else "erro"] += 1
        if resultado == "ja_existe":
            print("    já existe, pulando.")
        elif resultado == "404":
            stats["nao_disponivel"] += 1
            print("    não disponível (404).")

    # ── Tabelas anuais ───────────────────────────────────────────
    for ano in ANOS:
        print(f"\n[ Ano {ano} ]\n")
        destino_ano = OUTPUT_DIR / str(ano)
        algum_disponivel = False

        for tabela in TABELAS_ANUAIS:
            url = BASE_URL + str(ano) + tabela
            destino = destino_ano / tabela
            print(f"  {ano}{tabela}")
            resultado = download_arquivo(url, destino, sessao)

            if resultado == "404":
                stats["nao_disponivel"] += 1
                print("    não disponível.")
            elif resultado == "ja_existe":
                stats["ja_existe"] += 1
                algum_disponivel = True
                print("    já existe, pulando.")
            elif resultado == "baixado":
                stats["baixado"] += 1
                algum_disponivel = True
            elif resultado == "erro":
                stats["erro"] += 1

        if not algum_disponivel:
            print(f"  (nenhuma tabela disponível para {ano})")

    # ── Resumo ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Resumo")
    print("=" * 60)
    print(f"  Baixados agora:       {stats['baixado']}")
    print(f"  Já existiam:          {stats['ja_existe']}")
    print(f"  Não disponíveis:      {stats['nao_disponivel']}")
    print(f"  Erros:                {stats['erro']}")
    print(f"\n  Arquivos em: {OUTPUT_DIR.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
