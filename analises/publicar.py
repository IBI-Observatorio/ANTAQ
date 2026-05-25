"""
Gera o pacote de publicação dos 29 indicadores ANTAQ para o Observatório IBI.

Uso:
    python -m analises.publicar
    python -m analises.publicar --output ../IBI-Observatorio/ibi-observatorio/public/data/antaq
    python -m analises.publicar --apenas 03 25 30      # subset de indicadores
    python -m analises.publicar --validar ./_publicar  # só valida estrutura

Para cada indicador definido em metadata.INDICADORES:
  1. Importa dinamicamente o módulo da análise
  2. Executa a função, capturando stdout
  3. Extrai 'achados' das linhas indentadas do stdout
  4. Serializa o DataFrame retornado em records JSON
  5. Lê metadados (titulo, descrição, etc)
  6. Copia o PNG correspondente
  7. Escreve <slug>.json validado contra schema

Ao final gera manifest.json com a lista global.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .metadata import (CLUSTERS, INDICADORES, IDS_PUBLICADOS,
                         destaques, por_cluster, validar)
from .schema import validar_indicador, validar_manifest

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "figs" / "analises"
DEFAULT_OUT = ROOT / "_publicar"


# ─── Utilidades ────────────────────────────────────────────────────────────────
def _records(obj) -> list[dict]:
    """Converte DataFrame/Series/dict-com-df em lista de records JSON-safe."""
    if isinstance(obj, dict):
        # Funções como a05/a25/a30 retornam DataFrame ou pivot diretamente,
        # mas algumas retornam dict {nome: valor}. Vamos lidar com o que vier.
        for chave in ("df", "data", "result"):
            if chave in obj and isinstance(obj[chave], (pd.DataFrame, pd.Series)):
                return _records(obj[chave])
        return [obj]
    if isinstance(obj, pd.Series):
        obj = obj.to_frame(name=obj.name or "valor")
    if not isinstance(obj, pd.DataFrame):
        return []
    df = obj.copy()
    # Achata MultiIndex em colunas
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["__".join(str(x) for x in tup if x != "") for tup in df.columns]
    # Reset do índice se não for o RangeIndex padrão (caso contrário, valores
    # do índice — ex: nomes de porto — seriam descartados na serialização)
    indice_default = (
        isinstance(df.index, pd.RangeIndex)
        and df.index.start == 0 and df.index.step == 1
        and df.index.name is None
    )
    if not indice_default:
        df = df.reset_index()
        # Se a coluna nova ficou com nome 'index' (índice anônimo), renomeia
        # para algo mais informativo quando possível
        if "index" in df.columns and "porto" not in df.columns:
            df = df.rename(columns={"index": "rotulo"})
    df.columns = [str(c) for c in df.columns]
    return _saneia(df.to_dict(orient="records"))


def _saneia(records: list[dict]) -> list[dict]:
    """Remove NaN/Infinity, converte timestamps e numpy scalars para tipos JSON."""
    out = []
    for r in records:
        novo = {}
        for k, v in r.items():
            if isinstance(v, float):
                if np.isnan(v) or np.isinf(v):
                    novo[k] = None
                else:
                    novo[k] = float(v)
            elif isinstance(v, (np.integer,)):
                novo[k] = int(v)
            elif isinstance(v, (np.floating,)):
                f = float(v)
                novo[k] = None if (np.isnan(f) or np.isinf(f)) else f
            elif isinstance(v, (np.bool_,)):
                novo[k] = bool(v)
            elif isinstance(v, (pd.Timestamp, datetime)):
                novo[k] = v.isoformat()[:10] if hasattr(v, "isoformat") else str(v)
            elif isinstance(v, np.ndarray):
                novo[k] = v.tolist()
            elif isinstance(v, pd.Interval):
                novo[k] = str(v)
            elif isinstance(v, pd.Categorical):
                novo[k] = str(v)
            elif v is pd.NA or v is None:
                novo[k] = None
            else:
                # fallback: tenta serializar; se falhar, vira string
                try:
                    json.dumps(v)
                    novo[k] = v
                except (TypeError, ValueError):
                    novo[k] = str(v)
        out.append(novo)
    return out


_PADRAO_LINHA = re.compile(r"^  +(?P<corpo>.+?)$")


def _extrair_achados(stdout: str) -> list[str]:
    """
    Extrai linhas indentadas (≥2 espaços) do stdout, ignorando o cabeçalho da
    seção (─── Análise #NN — ───). Cada linha relevante vira um achado.
    """
    achados: list[str] = []
    for linha in stdout.splitlines():
        if not linha.strip():
            continue
        # ignora cabeçalhos e separadores
        if linha.startswith("─") or "Análise #" in linha:
            continue
        m = _PADRAO_LINHA.match(linha)
        if not m:
            continue
        corpo = m.group("corpo").strip()
        if not corpo:
            continue
        # ignora linhas que são puramente tabelas pandas (continuam linhas anteriores)
        if corpo.startswith(("Sentido", "fase ", "ano ", "grupo ")) and len(corpo) < 40:
            continue
        achados.append(corpo)
    return achados


def _cobertura_de(records: list[dict]) -> dict | None:
    """Tenta inferir cobertura temporal (inicio/fim em ano)."""
    candidatos = ("Ano", "ano", "mes", "Mes", "data")
    for r in records[:5]:
        for c in candidatos:
            if c not in r:
                continue
            valores = [rec.get(c) for rec in records if rec.get(c) is not None]
            if not valores:
                continue
            try:
                if c.lower().startswith("ano"):
                    anos = [int(v) for v in valores]
                else:
                    anos = [int(str(v)[:4]) for v in valores]
                return {"inicio": min(anos), "fim": max(anos)}
            except (ValueError, TypeError):
                continue
    return None


def _executar(ind_id: str) -> tuple[list[dict], list[str], dict]:
    """Importa o módulo, executa a função, captura stdout.

    Retorna (records, achados_stdout, extras), onde extras pode conter
    'achados' dinâmicos retornados pela função (sobrescrevem stdout) e
    qualquer outra chave da função (ex: 'previsao', 'modelo').
    """
    meta = INDICADORES[ind_id]
    modulo = importlib.import_module(meta["modulo"])
    funcao = getattr(modulo, meta["funcao"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            resultado = funcao()
        except Exception as e:
            raise RuntimeError(f"erro executando {meta['funcao']}: {e}") from e
    achados_stdout = _extrair_achados(buf.getvalue())

    extras: dict = {}
    if isinstance(resultado, dict) and "df" in resultado:
        records = _records(resultado["df"])
        extras = {k: v for k, v in resultado.items() if k != "df"}
    else:
        records = _records(resultado)

    return records, achados_stdout, extras


def _copiar_imagem(meta: dict, dir_figs_out: Path) -> str | None:
    src = FIGS / f"{meta['imagem']}.png"
    if not src.exists():
        return None
    dst = dir_figs_out / f"{meta['imagem']}.png"
    dir_figs_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"figs/{dst.name}"


# ─── Geração ───────────────────────────────────────────────────────────────────
def gerar_indicador(ind_id: str, out_dir: Path) -> dict:
    meta = INDICADORES[ind_id]
    print(f"\n  [{ind_id}] {meta['titulo']}", flush=True)
    t0 = time.time()
    records, achados_stdout, extras = _executar(ind_id)
    # Prioridade dos achados (lista vazia EXPLÍCITA suprime fallback):
    #   1. retorno da função {"achados": [...]} — se chave presente, vence
    #   2. metadata.achados — se chave presente, vence stdout
    #   3. linhas extraídas do stdout — fallback final
    if "achados" in extras:
        achados = extras["achados"]
    elif "achados" in meta:
        achados = meta["achados"]
    else:
        achados = achados_stdout
    imagem = _copiar_imagem(meta, out_dir / "figs")

    doc = {
        "id": ind_id,
        "slug": meta["slug"],
        "titulo": meta["titulo"],
        "cluster": meta["cluster"],
        "destaque": meta.get("destaque", False),
        "granularidade": meta["granularidade"],
        "ultima_atualizacao": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "cobertura": _cobertura_de(records),
        "fonte": meta["fonte"],
        "descricao": meta["descricao"].strip(),
        "metodologia": meta["metodologia"].strip(),
        "achados": achados,
        "imagem": imagem,
        "dados": records,
    }
    if "premissas" in meta:
        doc["premissas"] = meta["premissas"]
    if meta.get("grafico"):
        doc["grafico"] = meta["grafico"]
    # Campos editoriais opcionais (lançamento PIM-PF Combinado IBI etc.)
    for campo in ("subtitulo", "categoria", "badge", "tags",
                   "links_transparencia"):
        if meta.get(campo):
            doc[campo] = meta[campo]
    # Blocos opcionais vindos do retorno da função (modelo, previsão, etc.)
    if extras.get("previsao"):
        doc["previsao"] = _saneia([
            {**p, "mes": p["mes"].strftime("%Y-%m-%d") if hasattr(p.get("mes"), "strftime") else p.get("mes")}
            for p in extras["previsao"]
        ])
    if extras.get("modelo"):
        doc["modelo"] = _saneia([extras["modelo"]])[0]
    # Blocos editoriais do PIM-PF Combinado IBI (card de previsão, track
    # record, métricas em produção, disclaimer de vintage)
    for chave in ("card_previsao_atual", "metricas_producao",
                   "disclaimer_vintage"):
        if extras.get(chave) is not None:
            if isinstance(extras[chave], dict):
                doc[chave] = _saneia([extras[chave]])[0]
            else:
                doc[chave] = extras[chave]
    if extras.get("track_record"):
        doc["track_record"] = _saneia(extras["track_record"])
    # Blocos de renderização estruturada (pirâmide invertida, achado #30)
    for chave in ("o_que_e", "como_funciona", "por_que_bimestral",
                  "detalhes_tecnicos", "limitacoes", "reprodutibilidade"):
        if extras.get(chave) is not None:
            doc[chave] = extras[chave]

    erros = validar_indicador(doc)
    if erros:
        raise ValueError(f"  ✗ Indicador {ind_id} inválido: {erros}")

    # Escreve o JSON
    arq = out_dir / "indicadores" / f"{ind_id}-{meta['slug']}.json"
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    dt = time.time() - t0
    print(f"    ✓ {arq.relative_to(out_dir.parent)}  "
          f"({len(records)} registros, {len(achados)} achados, {dt:.1f}s)")
    return doc


def gerar_manifest(docs: list[dict], out_dir: Path) -> dict:
    clusters_out = []
    for slug, ids in por_cluster().items():
        c = CLUSTERS[slug]
        ids_pub = [i for i in ids if any(d["id"] == i for d in docs)]
        if not ids_pub:
            # Cluster sem indicadores publicados: omitido do manifest.
            continue
        clusters_out.append({
            "slug": slug,
            "nome": c["nome"],
            "ordem": c["ordem"],
            "descricao": c["descricao"],
            "cor": c["cor"],
            "indicadores": ids_pub,
        })
    clusters_out.sort(key=lambda x: x["ordem"])

    manifest = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_indicadores": len(docs),
        "clusters": clusters_out,
        "destaques": [d["id"] for d in docs if d["destaque"]],
        "indicadores": [
            {
                "id": d["id"],
                "slug": d["slug"],
                "titulo": d["titulo"],
                "cluster": d["cluster"],
                "destaque": d["destaque"],
                "granularidade": d["granularidade"],
                "imagem": d["imagem"],
            }
            for d in docs
        ],
    }
    erros = validar_manifest(manifest)
    if erros:
        raise ValueError(f"manifest inválido: {erros}")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


# ─── CLI ───────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Gera pacote de publicação ANTAQ.")
    parser.add_argument("--output", default=str(DEFAULT_OUT),
                        help=f"Diretório de saída (default: {DEFAULT_OUT})")
    parser.add_argument("--apenas", nargs="+", default=None,
                        help="IDs específicos (ex: 03 25 30). "
                             "Default: apenas IDS_PUBLICADOS de metadata.")
    parser.add_argument("--todos", action="store_true",
                        help="Regenera todos os 29 indicadores, ignorando "
                             "IDS_PUBLICADOS.")
    parser.add_argument("--validar", default=None,
                        help="Apenas valida JSONs num diretório existente.")
    args = parser.parse_args()

    if args.validar:
        return _comando_validar(Path(args.validar))

    validar()                                # sanity-check do metadata
    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.apenas:
        ids = args.apenas
    elif args.todos:
        ids = list(INDICADORES)
    else:
        # Default: apenas indicadores na lista de IDS_PUBLICADOS.
        ids = sorted(IDS_PUBLICADOS)

    # Limpeza automática: se vamos regenerar tudo (não --apenas), remove
    # JSONs/PNGs órfãos que sobraram de execuções anteriores. Garante que
    # _publicar reflete EXATAMENTE o set ids atual, sem lixo.
    if not args.apenas:
        for sub in ("indicadores", "figs"):
            d = out_dir / sub
            if d.exists():
                for f in d.glob("*"):
                    f.unlink()
    desconhecidos = [i for i in ids if i not in INDICADORES]
    if desconhecidos:
        print(f"  ✗ IDs desconhecidos: {desconhecidos}", file=sys.stderr)
        return 1

    print(f"\n  Gerando {len(ids)} indicador(es) → {out_dir}")
    if not args.apenas and not args.todos:
        print(f"    (apenas IDS_PUBLICADOS = {sorted(IDS_PUBLICADOS)} · "
              f"use --todos para regenerar todos)")
    inicio = time.time()
    docs: list[dict] = []
    falhas: list[tuple[str, str]] = []

    for ind_id in ids:
        try:
            docs.append(gerar_indicador(ind_id, out_dir))
        except Exception as e:
            print(f"    ✗ FALHA: {e}", file=sys.stderr)
            falhas.append((ind_id, str(e)))

    if docs:
        manifest = gerar_manifest(docs, out_dir)
        print(f"\n  ✓ manifest.json gerado ({manifest['total_indicadores']} indicadores)")

    total = time.time() - inicio
    print(f"\n  Concluído em {total:.1f}s — {len(docs)} sucesso, {len(falhas)} falha(s)")
    if falhas:
        for i, e in falhas:
            print(f"    {i}: {e}", file=sys.stderr)
        return 2
    return 0


def _comando_validar(d: Path) -> int:
    if not d.exists():
        print(f"  ✗ Diretório não existe: {d}", file=sys.stderr)
        return 1
    erros_total = 0
    arquivos = sorted((d / "indicadores").glob("*.json"))
    for arq in arquivos:
        doc = json.loads(arq.read_text(encoding="utf-8"))
        e = validar_indicador(doc)
        if e:
            print(f"  ✗ {arq.name}: {e}")
            erros_total += 1
    manifest_arq = d / "manifest.json"
    if manifest_arq.exists():
        e = validar_manifest(json.loads(manifest_arq.read_text(encoding="utf-8")))
        if e:
            print(f"  ✗ manifest.json: {e}")
            erros_total += 1
    if erros_total == 0:
        print(f"  ✓ {len(arquivos)} indicador(es) válido(s) em {d}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
