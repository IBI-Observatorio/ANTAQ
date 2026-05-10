"""
Fetch de snapshots mensais — PIM-PF (BCB SGS 28503) e ANTAQ.

Cada execução:
  1. Baixa snapshot atual de PIM-PF e salva em
     data/snapshots/pimpf/AAAA-MM-DD.csv
  2. Re-executa pipeline ANTAQ (download_antaq.py + consolidar_antaq.py)
     e tira snapshot do parquet consolidado em
     data/snapshots/antaq/AAAA-MM-DD.parquet
  3. Computa SHA-256 de cada snapshot e adiciona linha ao manifest
     data/snapshots/manifest.csv

Idempotente: se já existe snapshot do dia corrente, pula o fetch e
loga "ja_existe".

Uso:
    python -m pipelines.pimpf_combinado.fetch_dados
    python -m pipelines.pimpf_combinado.fetch_dados --pular-antaq
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd                                  # noqa: E402
from analises.macro import sgs                        # noqa: E402

SNAP_PIMPF = ROOT / "data" / "snapshots" / "pimpf"
SNAP_ANTAQ = ROOT / "data" / "snapshots" / "antaq"
MANIFEST   = ROOT / "data" / "snapshots" / "manifest.csv"


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _append_manifest(linha: dict) -> None:
    novo = not MANIFEST.exists()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["data", "fonte", "arquivo",
                                            "sha256", "n_observacoes"])
        if novo:
            w.writeheader()
        w.writerow(linha)


def fetch_pimpf(data_str: str, force: bool = False) -> dict | None:
    arq = SNAP_PIMPF / f"{data_str}.csv"
    if arq.exists() and not force:
        print(f"  [pimpf] ja_existe: {arq.relative_to(ROOT)}")
        return None
    SNAP_PIMPF.mkdir(parents=True, exist_ok=True)
    s = sgs(28503, force=True)        # força refresh do cache da macro
    s.to_frame(name="pim_pf_dessaz").reset_index() \
     .rename(columns={"index": "mes"}) \
     .to_csv(arq, index=False, float_format="%.4f", encoding="utf-8")
    info = {"data": data_str, "fonte": "BCB_SGS_28503",
             "arquivo": str(arq.relative_to(ROOT)),
             "sha256": _sha256_file(arq), "n_observacoes": len(s)}
    _append_manifest(info)
    print(f"  [pimpf] novo snapshot: {arq.relative_to(ROOT)} "
          f"({len(s)} obs, sha {info['sha256'][:8]})")
    return info


def fetch_antaq(data_str: str, force: bool = False, pular: bool = False) -> dict | None:
    if pular:
        print("  [antaq] pular_antaq=True — usando parquet atual sem refetch.")
        return None
    arq = SNAP_ANTAQ / f"{data_str}.parquet"
    if arq.exists() and not force:
        print(f"  [antaq] ja_existe: {arq.relative_to(ROOT)}")
        return None
    SNAP_ANTAQ.mkdir(parents=True, exist_ok=True)

    # Re-executa pipeline ANTAQ existente
    print("  [antaq] download_antaq.py + consolidar_antaq.py …")
    subprocess.run([sys.executable, str(ROOT / "download_antaq.py")],
                    cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "consolidar_antaq.py")],
                    cwd=ROOT, check=True)

    # Snapshot do dicionário PIM-PF Combinado IBI (35 séries) em vez do
    # parquet inteiro (que tem ~1 GB). Usa o pipeline de preparação v2.
    from analises.validacao.portgdp_v2_preparacao import main as prep_main
    prep_main()
    src = ROOT / "validacao" / "portgdp_v2" / "series_tratadas.parquet"
    if not src.exists():
        raise FileNotFoundError(f"falta {src} — preparação v2 não rodou")
    pd.read_parquet(src).to_parquet(arq)

    info = {"data": data_str, "fonte": "ANTAQ_pipeline",
             "arquivo": str(arq.relative_to(ROOT)),
             "sha256": _sha256_file(arq),
             "n_observacoes": len(pd.read_parquet(arq))}
    _append_manifest(info)
    print(f"  [antaq] novo snapshot: {arq.relative_to(ROOT)} "
          f"(sha {info['sha256'][:8]})")
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=None,
                        help="Data do snapshot (AAAA-MM-DD). Default: hoje UTC.")
    parser.add_argument("--force", action="store_true",
                        help="Sobrescreve snapshot existente do dia.")
    parser.add_argument("--pular-antaq", action="store_true",
                        help="Não re-executa pipeline ANTAQ (usa parquet atual).")
    args = parser.parse_args()

    data_str = args.data or datetime.utcnow().strftime("%Y-%m-%d")
    print(f"\n  ── fetch_dados — snapshot {data_str} ──")
    fetch_pimpf(data_str, force=args.force)
    fetch_antaq(data_str, force=args.force, pular=args.pular_antaq)
    print(f"\n  ✓ manifest: {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
