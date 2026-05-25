"""
Metadados declarativos dos 29 indicadores ANTAQ publicados no Observatório IBI.

Cada indicador tem:
    titulo, slug       — URL e UI
    cluster            — agrupamento temático (ver CLUSTERS abaixo)
    destaque           — True para os ★ inéditos (gráfico interativo)
    granularidade      — "anual" | "mensal" | "cross-section"
    descricao          — markdown explicativo (o que o indicador mede)
    metodologia        — markdown técnico (fórmula, filtros aplicados)
    fonte              — origem primária dos dados
    premissas          — opcional, hipóteses econômicas
    modulo, funcao     — referência ao código que produz o indicador
    imagem             — slug do PNG em figs/analises/
    grafico            — opcional, spec do gráfico interativo (só destaques)
"""
from __future__ import annotations


CLUSTERS = {
    "eficiencia-operacional": {
        "ordem": 1,
        "nome": "Eficiência Operacional",
        "descricao": (
            "Decompõe a estadia portuária em tempos de espera vs operação efetiva "
            "e mede o custo nacional da ineficiência."
        ),
        "cor": "#c1322f",
    },
    "conteineres": {
        "ordem": 2,
        "nome": "Contêineres",
        "descricao": (
            "Fluxos de cheios/vazios, conteúdo NCM dos contêineres e sazonalidade "
            "do reposicionamento."
        ),
        "cor": "#233570",
    },
    "cabotagem-hidrovias": {
        "ordem": 3,
        "nome": "Cabotagem & Hidrovias",
        "descricao": (
            "Crescimento do modal aquaviário doméstico, elasticidade ao PIB e "
            "mapeamento das hidrovias brasileiras."
        ),
        "cor": "#7fb069",
    },
    "geopolitica": {
        "ordem": 4,
        "nome": "Geopolítica",
        "descricao": (
            "Concentração geográfica das exportações, dependência de fornecedores "
            "únicos e impacto de eventos globais (COVID, Rússia-Ucrânia)."
        ),
        "cor": "#5a4fcf",
    },
    "infraestrutura": {
        "ordem": 5,
        "nome": "Infraestrutura",
        "descricao": (
            "Saturação de berços, comparações entre portos públicos e privados e "
            "efeito da entrada de novos terminais."
        ),
        "cor": "#f0a04b",
    },
    "agronegocio": {
        "ordem": 6,
        "nome": "Agronegócio",
        "descricao": (
            "Pressão portuária na safra, lead times de cabotagem e anomalias "
            "correlacionadas com fases ENOS (El Niño / La Niña)."
        ),
        "cor": "#65b89e",
    },
    "ineditas": {
        "ordem": 7,
        "nome": "Análises Inéditas",
        "descricao": (
            "Indicadores originais do IBI: fingerprint operacional dos portos, "
            "custo de ineficiência por tonelada, sazonalidade latente e o "
            "PIM-PF Combinado IBI (componente DFM em horizonte bimestral)."
        ),
        "cor": "#0099D8",
    },
}


# ─── 29 indicadores ───────────────────────────────────────────────────────────
# (numeração de #01 a #28 + #30; #29 é o Harvest Oracle, fora do escopo do site)

# IDs publicados no site público. Indicadores fora dessa lista ficam
# definidos no metadata (e podem ser regenerados localmente) mas não vão
# para o pacote final em _publicar/. Pré-lançamento atual: apenas o
# PIM-PF Combinado IBI (#30).
IDS_PUBLICADOS: set[str] = {"30"}


INDICADORES: dict[str, dict] = {
    # ════════ Cluster 1 — Eficiência Operacional ═══════════════════════════════
    "01": {
        "titulo": "Decomposição T1-T4 por porto",
        "slug": "decomposicao-t1-t4",
        "cluster": "eficiencia-operacional",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c1_eficiencia",
        "funcao": "a01_decomposicao_t1_t4",
        "imagem": "01_decomposicao_t1_t4",
        "fonte": "ANTAQ — Estatística Aquaviária (Atracação + TemposAtracação)",
        "descricao": (
            "A estadia total de um navio (TE) decompõe em quatro tempos: "
            "**T1** (espera no fundeio até atracar), **T2** (espera após atracar até "
            "começar operação), **T3** (operação efetiva) e **T4** (espera após "
            "terminar operação até desatracar). A razão **T1/T3** quantifica quantas "
            "horas o navio espera para cada hora produtiva — proxy direto da "
            "ineficiência sistêmica do porto."
        ),
        "metodologia": (
            "Filtra `Tipo de Operação='Movimentação da Carga'` e estadias entre 0,5 e "
            "720 horas. Médias aritméticas anuais e por porto (top 15 por tonelagem)."
        ),
    },
    "02": {
        "titulo": "Aproveitamento do berço (T3/TA)",
        "slug": "aproveitamento-berco",
        "cluster": "eficiencia-operacional",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c1_eficiencia",
        "funcao": "a02_aproveitamento_berco",
        "imagem": "02_aproveitamento_berco",
        "fonte": "ANTAQ — Atracação + Carga + TemposAtracação",
        "descricao": (
            "Mede a fração do tempo atracado (TA) que efetivamente vira operação "
            "(T3). Um aproveitamento de 75% significa que 25% do tempo o navio está "
            "atracado mas parado — esperando equipamento, mão-de-obra, autorização ou "
            "carga."
        ),
        "metodologia": (
            "Razão `T3/TA` calculada por atracação, agrupada por ano e natureza de "
            "carga. Filtros: TA > 1h, T3 ≤ TA, FlagMCOperacaoCarga = 1."
        ),
    },
    "03": {
        "titulo": "Custo Brasil Portuário",
        "slug": "custo-brasil-portuario",
        "cluster": "eficiencia-operacional",
        "destaque": True,
        "granularidade": "anual",
        "modulo": "analises.c1_eficiencia",
        "funcao": "a03_custo_brasil",
        "imagem": "03_custo_brasil_portuario",
        "fonte": "ANTAQ + premissas de afretamento",
        "premissas": "US$ 25.000/dia × R$ 5,20/USD (ajustável)",
        "descricao": (
            "Estimativa monetária do tempo de navio parado (T1+T2+T4) somado em todas "
            "as atracações de movimentação de carga, multiplicado pelo custo médio de "
            "afretamento. É o **custo nacional da ineficiência logística** — recurso "
            "queimado em espera que poderia estar movimentando carga."
        ),
        "metodologia": (
            "`(T1+T2+T4)/24 × US$25k/dia × câmbio` somado por ano. Taxa de "
            "afretamento conservadora; navios maiores chegam a US$ 50k/dia."
        ),
        "achados": [
            "Em 2020-2025, os navios passaram em média 2,5 milhões de horas por ano em espera (T1+T2+T4) durante operações de movimentação de carga.",
            "Convertido pelo custo de afretamento (US$ 25 mil/dia), isso equivale a R$ 14 bilhões por ano queimados em ineficiência logística.",
            "53% do tempo total de estadia é espera, não operação efetiva — o navio está parado mais da metade do tempo em que está no porto.",
            "O patamar é estável desde 2010: apesar de novos terminais e regulação, a fração de espera não melhorou estruturalmente.",
            "O número escala linearmente com a premissa cambial (R$ 5,20/USD); a R$ 6,00/USD seria R$ 16 bi/ano.",
        ],
        "grafico": {
            "tipo": "bar",
            "x": "Ano",
            "y": "custo_brl",
            "transform_y": "div_1e9",
            "label_x": "Ano",
            "label_y": "R$ bilhões",
            "cor": "#c1322f",
        },
    },
    "04": {
        "titulo": "Recuperação pós-COVID — T2 mensal",
        "slug": "recuperacao-covid",
        "cluster": "eficiencia-operacional",
        "destaque": False,
        "granularidade": "mensal",
        "modulo": "analises.c1_eficiencia",
        "funcao": "a04_recuperacao_covid",
        "imagem": "04_curva_covid_t2",
        "fonte": "ANTAQ — TemposAtracação 2018-2025",
        "descricao": (
            "Série mensal do tempo de espera após atracar (T2). Permite ver se o "
            "choque da pandemia foi um evento isolado ou alterou estruturalmente o "
            "patamar de eficiência operacional do berço brasileiro."
        ),
        "metodologia": (
            "Média mensal de T2 entre 2018 e 2025, com média móvel de 3 meses para "
            "suavizar. Comparação com baseline pré-COVID (jan/2018 a fev/2020)."
        ),
    },
    "05": {
        "titulo": "Clustering de paralisações",
        "slug": "paralisacoes",
        "cluster": "eficiencia-operacional",
        "destaque": False,
        "granularidade": "cross-section",
        "modulo": "analises.c1_eficiencia",
        "funcao": "a05_paralisacoes",
        "imagem": "05_paralisacoes",
        "fonte": "ANTAQ — TemposAtracacaoParalisacao 2015+",
        "descricao": (
            "Categoriza textualmente os motivos de paralisação durante a operação "
            "(climática, equipamento, mão-de-obra, burocrática, operacional, "
            "acidente). Identifica que fração do tempo perdido é estrutural e "
            "evitável."
        ),
        "metodologia": (
            "Classificação por regex sobre `DescricaoTempoDesconto`. Agregação de "
            "horas perdidas por categoria sobre 2015-2025."
        ),
    },

    # ════════ Cluster 2 — Contêineres ══════════════════════════════════════════
    "06": {
        "titulo": "Desequilíbrio cheio/vazio por corredor",
        "slug": "desequilibrio-cheio-vazio",
        "cluster": "conteineres",
        "destaque": False,
        "granularidade": "cross-section",
        "modulo": "analises.c2_conteineres",
        "funcao": "a06_desequilibrio_cheio_vazio",
        "imagem": "06_desequilibrio_cheio_vazio",
        "fonte": "ANTAQ — Carga (longo curso, conteinerizada)",
        "descricao": (
            "Razão entre contêineres cheios e vazios embarcados em cada corredor "
            "(porto BR ↔ continente). Razão > 1 indica corredor exportador "
            "(saímos cheios); < 1 indica corredor que recebe cheios e devolve "
            "vazios — indício direto de desbalanceamento comercial."
        ),
        "metodologia": (
            "Agrega contêineres cheios e vazios embarcados por par "
            "(porto brasileiro, continente externo) entre 2018 e 2025."
        ),
    },
    "07": {
        "titulo": "Cheio/Vazio × câmbio (BRL/USD)",
        "slug": "cheio-vazio-cambio",
        "cluster": "conteineres",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c2_conteineres",
        "funcao": "a07_proxy_cambio",
        "imagem": "07_cheio_vazio_vs_cambio",
        "fonte": "ANTAQ + BCB SGS 3697 (USD/BRL PTAX)",
        "descricao": (
            "Compara a razão anual cheio/vazio com o câmbio. Hipótese: real fraco "
            "(USD/BRL alto) torna exportação mais competitiva → mais cheios "
            "embarcados, menos cheios desembarcados. A correlação é o termômetro "
            "da elasticidade do comércio exterior conteinerizado."
        ),
        "metodologia": (
            "Razão anual de cheios sobre vazios em embarques e desembarques de "
            "longo curso, vs média anual da PTAX venda."
        ),
    },
    "08": {
        "titulo": "Conteúdo NCM dos contêineres",
        "slug": "conteudo-ncm-conteineres",
        "cluster": "conteineres",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c2_conteineres",
        "funcao": "a08_conteudo_conteineres",
        "imagem": "08_pauta_conteinerizada_export",
        "fonte": "ANTAQ — CargaConteinerizada + MercadoriaConteinerizada",
        "descricao": (
            "Composição da pauta de exportação conteinerizada por grupo NCM. "
            "Pergunta-chave: o Brasil está exportando mais manufaturados ou "
            "commoditizando o que sai dentro do contêiner?"
        ),
        "metodologia": (
            "Agrega 144M registros NCM dentro de contêineres por grupo de "
            "mercadoria (SH4) e ano. Top 10 grupos em participação relativa."
        ),
    },
    "09": {
        "titulo": "Vazio estrutural vs sazonal",
        "slug": "vazio-estrutural-sazonal",
        "cluster": "conteineres",
        "destaque": False,
        "granularidade": "mensal",
        "modulo": "analises.c2_conteineres",
        "funcao": "a09_vazio_sazonal",
        "imagem": "09_vazio_estrutural_sazonal",
        "fonte": "ANTAQ — Carga conteinerizada 2015-2025",
        "descricao": (
            "Decompõe o percentual de vazios embarcados em componente estrutural "
            "(ano-a-ano) e sazonal (mês-a-mês). Se a amplitude estrutural domina, "
            "vazios são um problema de fluxo bilateral; se a sazonal é forte, "
            "há oportunidade de planejar reposicionamento por safra."
        ),
        "metodologia": (
            "Médias mensais 2015-2025; amplitude = max - min. Comparação entre "
            "amplitude anual (estrutural) e mensal (sazonal)."
        ),
    },

    # ════════ Cluster 3 — Cabotagem & Hidrovias ════════════════════════════════
    "10": {
        "titulo": "Cabotagem vs Longo Curso (TEUs)",
        "slug": "cabotagem-vs-longo-curso",
        "cluster": "cabotagem-hidrovias",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c3_cabotagem_hidrovias",
        "funcao": "a10_cabotagem_vs_longo_curso",
        "imagem": "10_cabotagem_vs_longo_curso",
        "fonte": "ANTAQ — Carga conteinerizada 2010-2025",
        "descricao": (
            "Crescimento dos TEUs movimentados em cabotagem comparado ao longo "
            "curso. A cabotagem cresceu mais de 300% no período enquanto longo "
            "curso cresceu menos de 100% — quando, projetando, ela deve "
            "ultrapassar?"
        ),
        "metodologia": (
            "Soma de TEUs por ano para cada modal (FlagCabotagemMovimentacao=1 vs "
            "FlagLongoCurso=1). Extrapolação log-linear sobre últimos 8 anos."
        ),
    },
    "11": {
        "titulo": "Elasticidade cabotagem × PIB",
        "slug": "elasticidade-cabotagem-pib",
        "cluster": "cabotagem-hidrovias",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c3_cabotagem_hidrovias",
        "funcao": "a11_elasticidade_pib",
        "imagem": "11_elasticidade_cab_pib",
        "fonte": "ANTAQ + BCB SGS 7326 (PIB real)",
        "descricao": (
            "Quanto a movimentação de cabotagem responde a variações do PIB? "
            "Compara com a sensibilidade do longo curso. Cabotagem tende a "
            "refletir consumo doméstico; longo curso responde a câmbio e "
            "commodities."
        ),
        "metodologia": (
            "Regressão linear simples: variação anual da tonelagem ~ variação "
            "anual do PIB real (2010-2025). β é a elasticidade pontual."
        ),
    },
    "12": {
        "titulo": "Tríade hidrográfica — rios brasileiros",
        "slug": "triade-hidrografica",
        "cluster": "cabotagem-hidrovias",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c3_cabotagem_hidrovias",
        "funcao": "a12_triade_hidrografica",
        "imagem": "12_triade_hidrografica",
        "fonte": "ANTAQ — CargaRio 2012-2025",
        "descricao": (
            "Volume movimentado por rio ao longo de 13 anos. Identifica as "
            "hidrovias que cresceram (Tapajós, Madeira) e as que perderam "
            "relevância (Paraná). Insumo para planejamento federal."
        ),
        "metodologia": (
            "Soma anual de toneladas por rio. Crescimento relativo "
            "comparando médias 2023-25 vs 2012-14."
        ),
    },
    "13": {
        "titulo": "Corredor Norte — emergência do Arco Norte",
        "slug": "arco-norte",
        "cluster": "cabotagem-hidrovias",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c3_cabotagem_hidrovias",
        "funcao": "a13_arco_norte",
        "imagem": "13_arco_norte",
        "fonte": "ANTAQ — Carga + Atracação 2012-2025",
        "descricao": (
            "Migração silenciosa do escoamento de granéis sólidos (soja, milho) "
            "do Sul/Sudeste para Norte/Nordeste — o chamado **Arco Norte**. "
            "Mostra share das exportações por região ano a ano e identifica os "
            "novos protagonistas (Itaqui, Ponta da Madeira, Vila do Conde)."
        ),
        "metodologia": (
            "Agrega tonelagem de granel sólido embarcado por região e ano "
            "(2012-2025). Top 5 portos do Arco Norte ranqueados em 2024."
        ),
        "achados": [
            "Em 2012, 35% do granel sólido brasileiro saía pelos portos do Arco Norte (Norte+Nordeste). Em 2025, essa fatia chegou a 44% — ganho de 9 pontos percentuais em 13 anos.",
            "O movimento é simétrico: Sul+Sudeste perdeu exatamente 9 pontos no mesmo período (63% → 54%).",
            "Cinco portos concentram a expansão do Arco Norte. Em 2024 movimentaram juntos cerca de 240 Mt de granéis: Ponta da Madeira (175,8 Mt), Itaqui (24,3 Mt), Santarém (16,2 Mt), Vila do Conde (14,0 Mt) e Alumar (13,3 Mt).",
            "Itaqui é o caso mais expressivo: passou de menos de 3 Mt em 2010 para mais de 16 Mt em 2024, multiplicação por mais de 5× em uma década.",
            "O Terminal Portuário Novo Remanso surgiu em 2023 já com 2,2 Mt em 2025 — sinal de que a expansão continua na próxima onda de terminais privados.",
        ],
    },

    # ════════ Cluster 4 — Geopolítica ══════════════════════════════════════════
    "14": {
        "titulo": "Concentração geográfica das exportações (HHI)",
        "slug": "hhi-exportacoes",
        "cluster": "geopolitica",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c4_geopolitica",
        "funcao": "a14_hhi_destinos",
        "imagem": "14_hhi_exportacoes",
        "fonte": "ANTAQ + InstalacaoDestino + Mercadoria",
        "descricao": (
            "Índice Herfindahl-Hirschman (HHI) dos destinos por mercadoria, em "
            "escala 0-10000. Acima de 2500 indica mercado **altamente "
            "concentrado**. Mostra quais commodities dependem demais de poucos "
            "compradores."
        ),
        "metodologia": (
            "Para cada par (mercadoria, ano): HHI = Σ(share_pais)² × 10000, com "
            "share calculado em toneladas exportadas (FlagLongoCurso=1)."
        ),
    },
    "15": {
        "titulo": "Dependência de importação — fornecedor único",
        "slug": "dependencia-importacao",
        "cluster": "geopolitica",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c4_geopolitica",
        "funcao": "a15_dependencia_importacao",
        "imagem": "15_dependencia_importacao",
        "fonte": "ANTAQ + InstalacaoOrigem + Mercadoria",
        "descricao": (
            "Para fertilizantes e combustíveis: que fração das toneladas vem do "
            "**maior fornecedor único**? Quanto maior, mais vulnerável o Brasil é "
            "a sanções, conflitos ou choques de oferta naquele país."
        ),
        "metodologia": (
            "Filtra mercadorias contendo 'fertilizant', 'adub', 'combust', 'urei', "
            "'potass'. Calcula share do top-1 país de origem por ano."
        ),
    },
    "16": {
        "titulo": "Eventos geopolíticos — COVID e Rússia-Ucrânia",
        "slug": "eventos-geopoliticos",
        "cluster": "geopolitica",
        "destaque": False,
        "granularidade": "mensal",
        "modulo": "analises.c4_geopolitica",
        "funcao": "a16_eventos_geopoliticos",
        "imagem": "16_eventos_geopoliticos",
        "fonte": "ANTAQ + Cadastro de origem/destino",
        "descricao": (
            "Toneladas mensais por bloco geopolítico (Rússia+Ucrânia, China, EUA, "
            "outros) entre 2018 e 2025. Visualiza impactos de eventos discretos: "
            "lockdowns COVID, invasão da Ucrânia, tarifas EUA-China."
        ),
        "metodologia": (
            "Agrega toneladas mensais com média móvel 3m. Marca em destaque "
            "março/2020 (COVID) e fevereiro/2022 (invasão russa)."
        ),
    },
    "17": {
        "titulo": "Blocos econômicos — Mercosul, UE, China, EUA",
        "slug": "blocos-economicos",
        "cluster": "geopolitica",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c4_geopolitica",
        "funcao": "a17_blocos_economicos",
        "imagem": "17_blocos_economicos",
        "fonte": "ANTAQ + cadastro de países",
        "descricao": (
            "Share das exportações e importações por bloco econômico ao longo do "
            "tempo. Captura a **trade diversion** silenciosa: a China saiu de "
            "~30% para mais de 50% das exportações brasileiras enquanto a UE "
            "perdeu metade do share."
        ),
        "metodologia": (
            "Mapeamento manual de país → bloco. Stacked area com share % de "
            "toneladas embarcadas e desembarcadas por bloco e ano."
        ),
    },

    # ════════ Cluster 5 — Infraestrutura ═══════════════════════════════════════
    "18": {
        "titulo": "Saturação de berço × T1",
        "slug": "saturacao-berco",
        "cluster": "infraestrutura",
        "destaque": False,
        "granularidade": "mensal",
        "modulo": "analises.c5_infraestrutura",
        "funcao": "a18_saturacao_berco",
        "imagem": "18_saturacao_berco",
        "fonte": "ANTAQ — TaxaOcupacao + TemposAtracação 2020+",
        "descricao": (
            "Confirma empiricamente o limiar de alerta dos 70% de ocupação: "
            "berços acima desse patamar têm tempo de espera (T1) **6× maior** "
            "que berços com baixa ocupação. Justifica intervenções de capacidade "
            "antes de o gargalo se manifestar."
        ),
        "metodologia": (
            "Para cada par (IDBerço, ano-mês): ocupação % × T1 médio. Buckets "
            "de ocupação <30%, 30-50%, 50-70%, 70-85%, >85%."
        ),
    },
    "19": {
        "titulo": "Porto público vs privado",
        "slug": "publico-vs-privado",
        "cluster": "infraestrutura",
        "destaque": False,
        "granularidade": "cross-section",
        "modulo": "analises.c5_infraestrutura",
        "funcao": "a19_publico_vs_privado",
        "imagem": "19_publico_vs_privado",
        "fonte": "ANTAQ — Atracação + Carga 2020-2025",
        "descricao": (
            "Compara T1, T2, T3, T4 entre **Portos Organizados** (públicos) e "
            "**Terminais Autorizados** (privados) controlando por natureza de "
            "carga. Quantifica em horas a diferença operacional histórica."
        ),
        "metodologia": (
            "Médias dos 4 tempos por (Tipo da Autoridade Portuária × Natureza), "
            "agregando 2020-2025 com FlagMCOperacaoCarga=1."
        ),
    },
    "20": {
        "titulo": "Efeito de novos terminais (diff-in-diff)",
        "slug": "novos-terminais",
        "cluster": "infraestrutura",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c5_infraestrutura",
        "funcao": "a20_novos_terminais",
        "imagem": "20_novos_terminais",
        "fonte": "ANTAQ — Atracação + Carga 2014-2025",
        "descricao": (
            "Compara crescimento de portos que ganharam berço novo a partir de "
            "2018 vs portos que não ganharam. Usa a primeira aparição de "
            "`IDBerco` como tratamento natural — quase um experimento."
        ),
        "metodologia": (
            "Identifica IDBerços com primeira aparição em 2018+. Compara índice "
            "de crescimento (base 2014=1.0) entre o grupo de portos tratados e "
            "o de controle."
        ),
    },
    "21": {
        "titulo": "PMO por natureza de carga",
        "slug": "pmo-natureza",
        "cluster": "infraestrutura",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c5_infraestrutura",
        "funcao": "a21_pmo_natureza",
        "imagem": "21_pmo_natureza",
        "fonte": "ANTAQ — Atracação + Carga 2010-2025",
        "descricao": (
            "Prancha Média Operacional (toneladas por hora de operação) por "
            "natureza de carga. Pergunta: o Brasil está movendo carga mais ou "
            "menos rápido ao longo dos anos?"
        ),
        "metodologia": (
            "PMO = Σ(VLPesoCargaBruta) / Σ(TOperacao) por natureza × ano. "
            "Atenção: atribuição multi-natureza pode inflar denominador."
        ),
    },

    # ════════ Cluster 6 — Agronegócio ══════════════════════════════════════════
    "22": {
        "titulo": "Pressão portuária na safra",
        "slug": "pressao-safra",
        "cluster": "agronegocio",
        "destaque": False,
        "granularidade": "mensal",
        "modulo": "analises.c6_agronegocio",
        "funcao": "a22_pressao_safra",
        "imagem": "22_pressao_safra",
        "fonte": "ANTAQ — Carga (granel sólido embarcado) 2015-2025",
        "descricao": (
            "Índice mensal de pressão = volume de granel sólido embarcado / "
            "capacidade portuária regional de referência (p90 de 24 meses). "
            "Valores acima de 1.0 indicam meses em que a região operou no limite."
        ),
        "metodologia": (
            "Toneladas mensais de granel sólido embarcado por região "
            "geográfica. Capacidade de referência = quantil 90% móvel de 24 "
            "meses."
        ),
    },
    "23": {
        "titulo": "Lead time porto-a-porto na cabotagem",
        "slug": "lead-time-cabotagem",
        "cluster": "agronegocio",
        "destaque": False,
        "granularidade": "cross-section",
        "modulo": "analises.c6_agronegocio",
        "funcao": "a23_lead_time_cabotagem",
        "imagem": "23_lead_time_cabotagem",
        "fonte": "ANTAQ — Carga cabotagem 2022-2024",
        "descricao": (
            "Tempo médio entre embarque na origem e desembarque no destino para "
            "os 15 pares de cabotagem mais movimentados. Insumo para planejamento "
            "de estoque e estimativa de capacidade efetiva da cabotagem."
        ),
        "metodologia": (
            "Para cada par (origem, destino): diferença entre tempo médio de "
            "atracação no destino e na origem. Filtros: lead entre 24h e 30 dias."
        ),
    },
    "24": {
        "titulo": "Anomalias de safra × ENOS",
        "slug": "anomalias-enos",
        "cluster": "agronegocio",
        "destaque": False,
        "granularidade": "anual",
        "modulo": "analises.c6_agronegocio",
        "funcao": "a24_anomalias_safra",
        "imagem": "24_anomalias_enos",
        "fonte": "ANTAQ — Mercadoria (soja, milho) 2010-2025",
        "descricao": (
            "Desvios das exportações de soja e milho em relação à tendência "
            "linear, comparados às fases ENOS (El Niño, La Niña, Neutro). "
            "Quantifica o impacto climático sobre a safra exportada."
        ),
        "metodologia": (
            "Detrend linear do volume anual exportado. Anomalia % = (real - "
            "tendência) / tendência. Anos ENOS classificados pela CPTEC/NOAA."
        ),
    },

    # ════════ Cluster 7 — Análises Inéditas ════════════════════════════════════
    "25": {
        "titulo": "★ Fingerprint operacional dos portos",
        "slug": "fingerprint-portos",
        "cluster": "ineditas",
        "destaque": True,
        "granularidade": "anual",
        "modulo": "analises.c7_ineditas",
        "funcao": "a25_fingerprint",
        "imagem": "25_fingerprint",
        "fonte": "ANTAQ — TemposAtracação + Carga 2015-2025",
        "descricao": (
            "Cada porto é representado por um vetor multidimensional (T1, T2, "
            "T3, T4, % conteinerizada, % granel sólido, % granel líquido). "
            "Aplicamos K-Means para clusterizar portos com perfil operacional "
            "similar e identificamos quais mudaram de cluster ao longo dos anos "
            "— ou seja, **quando cada porto trocou de identidade**."
        ),
        "metodologia": (
            "Top 25 portos por movimentação total. Features padronizadas via "
            "StandardScaler. KMeans com k=5 (random_state=0). Detecta a última "
            "transição de cluster por porto."
        ),
        "grafico": {
            "tipo": "heatmap",
            "x": "Ano",
            "y": "porto",
            "valor": "cluster",
            "label_x": "Ano",
            "label_y": "Porto",
            "cor": "categorica",
        },
    },
    "26": {
        "titulo": "★ Custo de ineficiência por tonelada",
        "slug": "custo-por-tonelada",
        "cluster": "ineditas",
        "destaque": True,
        "granularidade": "cross-section",
        "modulo": "analises.c7_ineditas",
        "funcao": "a26_custo_por_tonelada",
        "imagem": "26_custo_por_tonelada",
        "fonte": "ANTAQ + premissas de afretamento",
        "premissas": "US$ 25.000/dia × R$ 5,20/USD",
        "descricao": (
            "Distribui o **Custo Brasil Portuário** (#03) por tonelada e por "
            "porto. Cada porto cobra um pedágio invisível pela ineficiência: "
            "alguns granelistas chegam a R$ 100/t em custos só de espera. "
            "Insumo direto para priorizar investimentos."
        ),
        "metodologia": (
            "Por porto × natureza: `(T2+T4) × custo_hora / Σ(VLPesoCargaBruta)`. "
            "Filtros: 2020-2025, FlagMCOperacaoCarga=1, mínimo 1 Mt."
        ),
        "grafico": {
            "tipo": "bar_horizontal",
            "x": "custo_brl_por_ton",
            "y": "porto",
            "label_x": "R$/tonelada",
            "label_y": "Porto",
            "cor": "#c1322f",
            "filtro": "natureza == 'Granel Sólido'",
            "top_n": 20,
        },
    },
    "27": {
        "titulo": "★ Sazonalidade latente em T1",
        "slug": "sazonalidade-t1",
        "cluster": "ineditas",
        "destaque": True,
        "granularidade": "mensal",
        "modulo": "analises.c7_ineditas",
        "funcao": "a27_sazonalidade_t1",
        "imagem": "27_sazonalidade_t1",
        "fonte": "ANTAQ — TaxaOcupação + TemposAtracação 2020+",
        "descricao": (
            "Compara o índice sazonal mensal de T1 (espera de fundeio) com o "
            "índice sazonal de ocupação do berço. Se T1 sobe na safra mas "
            "ocupação não, o **gargalo está no canal/atracação**, não no berço — "
            "uma distinção crítica para política pública: investir em dragagem "
            "vs ampliar berço."
        ),
        "metodologia": (
            "Mediana mensal de T1 e ocupação por IDBerço (2020-2025). "
            "Normalização: cada mês ÷ média anual = índice (média = 100)."
        ),
        "grafico": {
            "tipo": "line",
            "x": "mes_n",
            "series": [
                {"y": "T1_norm", "label": "T1 (espera)", "cor": "#c1322f"},
                {"y": "ocup_norm", "label": "Ocupação", "cor": "#3a64a8"},
            ],
            "label_x": "Mês",
            "label_y": "Índice mensal (média = 100)",
        },
    },
    "28": {
        "titulo": "★ Centralidade da rede portuária",
        "slug": "centralidade-rede",
        "cluster": "ineditas",
        "destaque": True,
        "granularidade": "cross-section",
        "modulo": "analises.c7_ineditas",
        "funcao": "a28_centralidade_rede",
        "imagem": "28_centralidade",
        "fonte": "ANTAQ — Carga cabotagem 2022-2024",
        "descricao": (
            "Modela a cabotagem como grafo direcionado (origem → destino) e "
            "calcula métricas de centralidade. **Betweenness** alta indica "
            "**ponto único de falha**: portos por onde passam muitas rotas "
            "indiretas. Insumo para planejamento de redundância logística."
        ),
        "metodologia": (
            "Grafo direcionado com peso = toneladas. Métricas: betweenness "
            "centrality (não-pesado), in-degree, out-degree, eigenvector "
            "centrality (na maior componente fracamente conexa)."
        ),
        "grafico": {
            "tipo": "bar_horizontal",
            "x": "betweenness",
            "y": "porto",
            "label_x": "Betweenness centrality",
            "label_y": "Porto",
            "cor": "#3a64a8",
            "top_n": 12,
        },
    },
    "30": {
        "titulo": "PIM-PF Combinado IBI — componente DFM em horizonte bimestral",
        "subtitulo": "Previsão da produção industrial brasileira com 2 meses de antecedência.",
        "slug": "portgdp",
        "cluster": "ineditas",
        "destaque": True,
        "categoria": "Inédita",
        "granularidade": "bimestral",  # apenas h=2 publicado
        "modulo": "analises.c7_ineditas",
        "funcao": "a30_portgdp",
        "imagem": "30_portgdp",
        "fonte": "ANTAQ — Estatística Aquaviária + BCB SGS 28503 (PIM-PF Indústria Geral)",
        "tags": [
            "pim-pf",
            "producao-industrial",
            "previsao",
            "dfm",
            "bimestral",
        ],
        "links_transparencia": {
            "nota_tecnica":     "docs/nota_tecnica_pimpf_combinado_v1.md",
            "h1_arquivado":     "validacao/portgdp_v2/h1_arquivado/README.md",
            "compromisso_retest": "validacao/portgdp_v2/compromisso_retest_2028.md",
        },
        "descricao": (
            "Combinação convexa entre uma previsão AR(1) do PIM-PF Indústria Geral "
            "(IBGE) e uma previsão de Dynamic Factor Model (DFM) extraído de 35 "
            "séries de movimentação portuária ANTAQ. Os pesos da combinação são "
            "estimados rolling OOS por Granger-Ramanathan a cada origem, sem "
            "look-ahead. Indicador validado **apenas em horizonte bimestral (h=2)**; "
            "em h=1 não passou no critério pré-registrado e está documentado em "
            "`h1_arquivado/`."
        ),
        "metodologia": (
            "Pipeline completo: dicionário de 35 séries (top 10 portos × 4 naturezas × "
            "2 sentidos com `FlagLongoCurso=1`, filtro de cobertura). STL para "
            "dessaz, var12m para estacionariedade. DFM-1f (1 fator, AR(2)) via "
            "Kalman MLE em `statsmodels`. Regressão de previsão `var12m(PIM)_{t+2} ~ "
            "α + γ·F_t` com HAC Newey-West (lag 12). Combinação Granger-Ramanathan "
            "rolling OOS (aquecimento 36 origens). Intervalos via split conformal "
            "padrão (Lei et al. 2018) com cobertura nominal 80%. Decisão Linha D "
            "aplicada mecanicamente conforme pré-registro em `REGRA_LANCAMENTO.md`."
        ),
        # Achados removidos do indicador #30 por decisão editorial — o
        # conteúdo essencial é reproduzido nos blocos visuais dedicados:
        # Card de Previsão atual, Track record, Disclaimer vintage e
        # Bloco de transparência. Manter lista vazia faz o componente
        # IndicadorPage não renderizar a seção "Achados" (verificação
        # achados?.length > 0).
        "achados": [],
        "grafico": {
            "tipo": "line_dual",
            "x": "mes",
            # Apenas séries históricas. A previsão oficial pública é
            # exibida no Card de Previsão Atual (lido do pipeline em
            # data/previsoes/historico.csv), não no gráfico.
            "series": [
                {"y": "portgdp_imp", "label": "PortGDP Importações", "cor": "#7fb069"},
                {"y": "pim_pf",      "label": "PIM-PF (IBGE)",       "cor": "#c1322f"},
            ],
            "label_x": "Mês",
            "label_y": "Índice (base 2014 = 100)",
        },
    },
}


def por_cluster() -> dict[str, list[str]]:
    """Retorna {slug_cluster: [id_indicador, ...]} ordenado por id."""
    out: dict[str, list[str]] = {c: [] for c in CLUSTERS}
    for ind_id, meta in INDICADORES.items():
        out[meta["cluster"]].append(ind_id)
    for c in out:
        out[c].sort()
    return out


def destaques() -> list[str]:
    """IDs dos indicadores ★ marcados como destaque."""
    return sorted(i for i, m in INDICADORES.items() if m.get("destaque"))


def validar() -> None:
    """Sanity-check: todo cluster referenciado existe; ids únicos."""
    ids = set()
    for ind_id, meta in INDICADORES.items():
        assert ind_id not in ids, f"id duplicado: {ind_id}"
        ids.add(ind_id)
        assert meta["cluster"] in CLUSTERS, f"{ind_id}: cluster {meta['cluster']!r} desconhecido"
        for campo in ("titulo", "slug", "modulo", "funcao", "imagem",
                      "descricao", "metodologia", "fonte", "granularidade"):
            assert meta.get(campo), f"{ind_id}: campo {campo!r} ausente"
        if meta.get("destaque"):
            assert meta.get("grafico"), f"{ind_id}: destaque sem spec de gráfico"
    print(f"  ✓ {len(INDICADORES)} indicadores validados, {len(destaques())} ★ em destaque.")


if __name__ == "__main__":
    validar()
    print("\nIndicadores por cluster:")
    for slug, ids in por_cluster().items():
        nome = CLUSTERS[slug]["nome"]
        print(f"  [{slug:25s}] {nome:30s} → {len(ids)} indicadores: {ids}")
