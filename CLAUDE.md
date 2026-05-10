# ANTAQ — Base Estatística Aquaviária

Dados de movimentação portuária da ANTAQ (2010–2026) em formato Parquet.

## Pipeline

```
download_antaq.py  →  dados/  →  consolidar_antaq.py  →  parquet/
```

- `download_antaq.py` — baixa ZIPs de `estatistica.antaq.gov.br/ea/txt/`
- `consolidar_antaq.py` — extrai e converte para Parquet (snappy, por tabela/ano)
- `antaq.py` — módulo de acesso: DuckDB views + pandas

## Usar a base

```python
import antaq

# ── DuckDB (recomendado para consultas analíticas) ──────────────────────────
db = antaq.conectar()

# Query simples
df = db.sql("SELECT * FROM Atracacao WHERE Ano = 2023 LIMIT 10").df()

# Views analíticas prontas
antaq.registrar_views(db)
df = db.sql("SELECT * FROM movimentacao_porto_ano WHERE Ano = 2023").df()

# ── Pandas (útil para anos específicos) ────────────────────────────────────
atracacao = antaq.carregar("Atracacao", anos=2023)
carga     = antaq.carregar("Carga", anos=[2022, 2023])
mercadoria = antaq.carregar("Mercadoria")   # cadastro, sem filtro de ano

# ── Ver o que está disponível ──────────────────────────────────────────────
antaq.resumo()
antaq.anos_disponiveis("TaxaOcupacao")   # [2020, 2021, ..., 2026]
```

## Tabelas disponíveis

### Anuais (2010–2026)

| Tabela | Chave | Descrição |
|---|---|---|
| `Atracacao` | `IDAtracacao` | Registro de cada atracação |
| `Carga` | `IDCarga` → `IDAtracacao` | Movimento de carga por atracação |
| `CargaConteinerizada` | `IDCarga` | Mercadoria declarada dentro do contêiner |
| `CargaHidrovia` | `IDCarga` | Hidrovia utilizada + toneladas |
| `CargaRegiao` | `IDCarga` | Região hidrográfica + toneladas |
| `CargaRio` | `IDCarga` | Rio utilizado + toneladas |
| `TemposAtracacao` | `IDAtracacao` | T1-T4, TA, TE em horas (PMO/PMG) |
| `TemposAtracacaoParalisacao` | `IDAtracacao` | Motivo e intervalo de paralisação |
| `TaxaOcupacao` | `IDBerco` + data | Minutos/dia berço ocupado (2020+) |
| `TaxaOcupacaoComCarga` | `IDBerco` + data | Igual, só operações com carga (2020+) |
| `TaxaOcupacaoTOAtracacao` | `IDBerco` + tipo + data | Por tipo de operação (2020+) |

### Cadastro (estáticas)

| Tabela | Chave | Descrição |
|---|---|---|
| `InstalacaoOrigem` | `Origem` | Detalhes do porto de origem |
| `InstalacaoDestino` | `Destino` | Detalhes do porto de destino |
| `Mercadoria` | `CDMercadoria` | Classificação NCM SH4 + SH2 |
| `MercadoriaConteinerizada` | `CDMercadoriaConteinerizada` | NCM da carga dentro do contêiner |

### Views analíticas (`antaq.registrar_views(db)`)

| View | Descrição |
|---|---|
| `carga_completa` | Carga + Mercadoria + InstalacaoOrigem + InstalacaoDestino |
| `atracacao_completa` | Atracacao + TemposAtracacao |
| `movimentacao_porto_ano` | Tonelagem/TEUs por porto-ano (sem dupla contagem) |
| `ocupacao_berco_mensal` | Taxa de ocupação % por berço/mês |

## Relacionamentos

```
Atracacao (IDAtracacao)
    ├── Carga (IDCarga)
    │     ├── CargaConteinerizada
    │     ├── CargaHidrovia / CargaRegiao / CargaRio
    │     ├── InstalacaoOrigem  (via Origem)
    │     ├── InstalacaoDestino (via Destino)
    │     └── Mercadoria (via CDMercadoria)
    │              └── MercadoriaConteinerizada (via CDMercadoriaConteinerizada)
    ├── TemposAtracacao
    └── TemposAtracacaoParalisacao

Berco (IDBerco)
    └── TaxaOcupacao / TaxaOcupacaoComCarga / TaxaOcupacaoTOAtracacao
```

## Colunas-chave da tabela Atracacao

| Coluna | Tipo | Valores |
|---|---|---|
| `IDAtracacao` | int | PK |
| `CDTUP` | str | Código do porto (Porto Público: Bigrama+Trigrama) |
| `Porto Atracação` | str | Nome do porto |
| `SGUF` | str | Sigla da UF |
| `Região Geográfica` | str | Norte / Nordeste / Sudeste / Sul / Centro-Oeste |
| `Tipo de Operação` | int | 1=Mov.Carga 2=Passageiro 3=Apoio 4=Marinha 5=Abast. 6=Reparo 7=Misto 8=Resíduos |
| `Tipo de Navegação da Atracação` | int | 1=Interior 2=Ap.Portuário 3=Cabotagem 4=Ap.Marítimo 5=Longo Curso |
| `Data Atracação` | datetime | yyyy-MM-dd HH:MM:SS |
| `FlagMCOperacaoAtracacao` | int | 1 = conta para movimentação de carga |

## Colunas-chave da tabela Carga

| Coluna | Tipo | Notas |
|---|---|---|
| `IDCarga` | int | PK |
| `IDAtracacao` | int | FK → Atracacao |
| `Natureza da Carga` | str | Granel Sólido / Granel Líquido / Carga Geral / Carga Conteinerizada |
| `Sentido` | int | 1=Desembarque 2=Embarque |
| `VLPesoCargaBruta` | float | Toneladas |
| `TEU` | float | Unidade de contêiner 20' (apenas contêineres) |
| `FlagCabotagem` | int | 1 = evitar dupla contagem no transporte de cabotagem |
| `FlagMCOperacaoCarga` | int | 1 = conta para movimentação de carga |
| `CDMercadoria` | str | NCM SH4 → join com Mercadoria |

## Tempos de atracação (TemposAtracacao)

```
TE (Estadia) = T1 + T2 + T3 + T4
TA (Atracado) = T2 + T3 + T4

T1: chegada → atracação   (espera no fundeio + canal de acesso)
T2: atracação → início op  (espera após atracar)
T3: início → término op    (operação efetiva — base do PMO)
T4: término op → desatracação

PMO = carga / T3   (Prancha Média Operacional)
PMG = carga / TA   (Prancha Média Geral)
```

## Dupla contagem — cabotagem

A navegação de cabotagem gera registro de carga tanto na origem quanto no destino.
Use as flags de acordo com o que se quer medir:

- **Transporte** (toneladas embarcadas): `WHERE FlagCabotagem = 1`
- **Movimentação portuária** (tudo que passou pelo berço): `WHERE FlagCabotagemMovimentacao = 1`
- **Movimentação consolidada** (inclui todas as navegações): `WHERE FlagMCOperacaoCarga = 1`

## Estrutura de arquivos

```
ANTAQ/
├── antaq.py                  ← módulo de acesso (DuckDB + pandas)
├── download_antaq.py         ← baixa ZIPs da ANTAQ
├── consolidar_antaq.py       ← converte ZIPs → Parquet
├── dados/
│   ├── 2010/ … 2026/        ← ZIPs anuais brutos
│   └── cadastro/            ← ZIPs de tabelas de referência
└── parquet/
    ├── Atracacao/            ← 2010.parquet … 2026.parquet
    ├── Carga/
    ├── … (demais tabelas)
    └── cadastro/             ← InstalacaoOrigem.parquet etc.
```
