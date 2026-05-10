"""
JSON Schema dos arquivos publicados em public/data/antaq/.

Validação leve sem dependência externa (jsonschema/Pydantic). Foco em garantir
que cada indicador exportado tenha os campos mínimos para o front-end.
"""
from __future__ import annotations
from typing import Any


GRANULARIDADES = {"anual", "mensal", "bimestral", "cross-section"}


def validar_indicador(d: dict[str, Any]) -> list[str]:
    """Retorna lista de erros (vazia = válido)."""
    erros: list[str] = []
    obrig = ["id", "slug", "titulo", "cluster", "destaque", "granularidade",
             "ultima_atualizacao", "fonte", "descricao", "metodologia",
             "achados", "imagem", "dados"]
    for c in obrig:
        if c not in d:
            erros.append(f"campo obrigatório ausente: {c}")
    if d.get("granularidade") not in GRANULARIDADES:
        erros.append(f"granularidade inválida: {d.get('granularidade')!r}")
    if d.get("destaque") and not d.get("grafico"):
        erros.append("destaque=True exige campo 'grafico'")
    if not isinstance(d.get("achados"), list):
        erros.append("achados deve ser lista de strings")
    elif any(not isinstance(a, str) for a in d["achados"]):
        erros.append("achados contém item não-string")
    if not isinstance(d.get("dados"), list):
        erros.append("dados deve ser lista de records (lista de dicts)")
    elif d["dados"] and not isinstance(d["dados"][0], dict):
        erros.append("dados[0] não é dict")
    cob = d.get("cobertura")
    if cob is not None:
        if not isinstance(cob, dict) or "inicio" not in cob or "fim" not in cob:
            erros.append("cobertura deve ter 'inicio' e 'fim'")
    return erros


def validar_manifest(d: dict[str, Any]) -> list[str]:
    erros: list[str] = []
    for c in ["gerado_em", "total_indicadores", "clusters", "destaques"]:
        if c not in d:
            erros.append(f"manifest: campo obrigatório ausente: {c}")
    clusters = d.get("clusters")
    if not isinstance(clusters, list):
        erros.append("manifest.clusters deve ser lista")
    else:
        for i, c in enumerate(clusters):
            for k in ["slug", "nome", "indicadores"]:
                if k not in c:
                    erros.append(f"manifest.clusters[{i}]: campo {k!r} ausente")
    return erros
