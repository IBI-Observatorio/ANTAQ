# PIM-PF Combinado IBI — produto final publicável

**Status:** Linha D (componente complementar com sinal preditivo
marginal validado), publicável apenas em **horizonte bimestral (h=2)**.

**Pré-registro:** [`REGRA_LANCAMENTO.md`](REGRA_LANCAMENTO.md)
**Compromisso de re-test:** [`compromisso_retest_2028.md`](compromisso_retest_2028.md)
**Decisão registrada em:** 2026-05-04

---

## 1. Especificação do modelo

A previsão publicada é a **combinação convexa** de duas previsões base
do PIM-PF Indústria Geral (variação interanual) com horizonte de 2 meses:

```
ŷ_combinado_{τ+2} = w_DFM,τ · ŷ_DFM_{τ+2}  +  (1 − w_DFM,τ) · ŷ_AR(1)_{τ+2}
```

onde, na origem τ:

- **`ŷ_AR(1)_{τ+2}`** — previsão de um modelo AR(1) ajustado por OLS sobre
  a variação interanual do PIM-PF até τ.
- **`ŷ_DFM_{τ+2}`** — previsão de um Dynamic Factor Model com **1 fator
  e dinâmica AR(2)**, ajustado via Kalman MLE em `statsmodels` sobre 35
  séries de movimentação portuária ANTAQ. Os fatores são extraídos
  defasados em 2 meses (`F_{τ}`), e o PIM-PF é regredido em `F_{τ}` via
  OLS com HAC Newey-West (lag = 12) para gerar a previsão pontual.
- **`w_DFM,τ`** — peso ótimo Granger-Ramanathan **rolling**: estimado
  em cada origem τ por OLS sem intercepto sobre todas as origens
  estritamente anteriores a τ, restringindo `w_DFM ∈ [0, 1]`. Janela
  mínima de aquecimento: 36 origens.

### Dicionário das 35 séries do DFM

- **Top 10 portos** por movimentação 2014-2024: Ponta da Madeira, Santos,
  Tubarão, Itaguaí, São Sebastião, Angra dos Reis, Paranaguá, TIG, Rio
  Grande, Itaqui.
- **4 naturezas**: Carga Conteinerizada, Carga Geral, Granel Sólido,
  Granel Líquido e Gasoso.
- **2 sentidos**: Desembarcados e Embarcados, **com `FlagLongoCurso=1`**.
- **Filtro**: ≤24 meses de zero/NA, sem streaks NaN > 2 → 35 séries
  passam.
- **Tratamento**: imputação linear de NaN isolados (≤2m), dessazonalização
  via STL (`period=12`, `robust=True`; X-13 indisponível em produção),
  variação interanual `pct_change(12)`, padronização z-score com média
  e dp do treino apenas (sem look-ahead).

---

## 2. Pesos rolling OOS (Granger-Ramanathan)

Janela: 58 origens OOS-legítimas (`min_train=36`, jan/2018 → out/2025).

| Estatística | Valor |
|---|---|
| `w_DFM` médio | **0,424** |
| `w_DFM` mediana | 0,432 |
| `w_DFM` mínimo | 0,273 |
| `w_DFM` máximo | 0,485 |
| Desvio-padrão | 0,028 |
| Truncamentos em `[0, 1]` | **0** |

**Robustez:** o peso rolling OOS (42,4%) é praticamente idêntico ao peso
in-sample (41,1%) — sinal estrutural, não artefato. Range estreito
[27,3%, 48,5%] significa que o ótimo Granger-Ramanathan jamais empurrou
o peso para os limites em nenhuma origem.

Visualização: [`gr_rolling_pesos.png`](gr_rolling_pesos.png).

---

## 3. Métricas finais (h=2, 58 origens OOS-legítimas)

| Modelo | n | MAE (pp) | RMSE (pp) |
|---|---|---|---|
| **PIM-PF Combinado IBI** | 58 | **3,01** | **5,88** |
| AR(1) baseline | 58 | 3,02 | 6,03 |
| DFM-1f isolado | 58 | 3,49 | 6,54 |

A combinação iguala numericamente o AR(1) em MAE (Δ = 0,01 pp) e melhora
em RMSE (Δ = 0,15 pp) — o ganho é mais visível em meses de erro grande,
onde o DFM modera o pico do AR(1).

Comparação visual nas últimas 36 origens: [`produto_final/comparacao_36_origens_h2.png`](produto_final/comparacao_36_origens_h2.png).

---

## 4. Intervalos de previsão (calibração conformal)

**Método:** Split conformal padrão de Lei et al. (2018).

```
q̂_{1-α} = ⌈(n+1)(1-α)⌉-ésimo menor erro absoluto da calibração
intervalo:  [ŷ_combinado − q̂, ŷ_combinado + q̂]
```

Configuração:

| Parâmetro | Valor |
|---|---|
| Cobertura nominal | 80% (α = 0,20) |
| Conjunto de calibração | primeiras 29 origens da janela OOS-legítima |
| Conjunto de teste | últimas 29 origens |
| Quantil de calibração | 5,35 pp |

### Cobertura empírica avaliada (h=2)

| Métrica | Valor |
|---|---|
| Cobertura nominal | 80% |
| **Cobertura empírica** | **100%** |
| **IC 95% Wilson** | **[88,3%, 100%]** |
| Largura média | 10,70 pp |

**Comunicação pública obrigatória:** "Os intervalos publicados são
**conservadores em h=2**. A cobertura empírica observada (100%) está
acima da cobertura nominal (80%) — o intervalo cobre eventos realizados
mais frequentemente do que o nominal sugere. Esta sobrecobertura é
consequência do tamanho amostral (n_teste = 29) e de caudas pesadas dos
erros. A garantia formal de Vovk sob exchangeability está preservada;
**não foi aplicado shrink empírico** que reduziria a largura mas
removeria a garantia."

---

## 5. Diagnósticos de resíduo da combinação (h=2)

| Teste | Estatística | p-valor | Conclusão |
|---|---|---|---|
| Ljung-Box (lag 12) | 27,18 | **0,007** | Autocorrelação residual em lags curtos |
| Ljung-Box (lag 24) | 27,60 | 0,28 | Sem autocorrelação em lags longos |
| Jarque-Bera (normalidade) | 700,98 | <10⁻¹⁵² | **Não-normalidade severa** (caudas pesadas) |
| ARCH-LM (lag 12) | 14,79 | 0,25 | Homocedasticidade OK |

**Caveats honestos:**

1. **Autocorrelação residual em lag 12** é estatisticamente significativa
   (p = 0,007). Sinal de que o modelo subestima persistência sazonal de
   curto prazo. Não invalida a previsão pontual, mas sugere que um
   ARDL(p=2) ou DFM com `error_order > 0` poderia agregar — registrado
   para o re-test 2028.
2. **Não-normalidade severa** dos resíduos é esperada em variação
   interanual (eventos COVID, choques de commodities geram caudas
   pesadas). DM-HLN e conformal **não pressupõem normalidade**, então
   o produto não fica inválido — mas as caudas pesadas explicam parte
   da sobrecobertura conformal.

---

## 6. Que claim faz e que claim não faz

### Faz
- "A movimentação portuária de insumos industriais (longo curso,
  desembarcado, naturezas não-agrícolas) carrega informação **estrutural
  complementar** ao componente autorregressivo do PIM-PF do IBGE em
  horizonte bimestral."
- "Em uma combinação convexa ótima Granger-Ramanathan, o componente
  portuário recebe peso médio de **42,4%** rolling OOS (n = 58 origens)
  com range [27,3%, 48,5%]."
- "A combinação tem **MAE numericamente menor** que o AR(1) baseline
  isolado (3,01 vs 3,02 pp em variação interanual), com encompassing
  test rejeitando que AR(1) encompasse o DFM (`λ_AR1->DFM = 0,49`,
  p < 0,001)."

### Não faz
- ❌ "Indicador antecedente do PIB industrial" (claim original do v1) —
  Diebold-Mariano não rejeita igualdade de acurácia da combinação vs
  AR(1) puro com p < 0,05 (p = 0,75). Falta de poder com n = 58.
- ❌ "Substitui modelos macroeconômicos do BCB ou IBGE" — a marginalidade
  do ganho impede esse uso.
- ❌ "Funciona em horizonte mensal (h=1)" — ver `h1_arquivado/`. Em h=1 a
  combinação **não passa o critério de Linha D**: `w_DFM = 15,5%` no
  piso da banda, DM p = 0,64. Não publicado.

---

## 7. Onde a evidência fica frágil — para releitura em 2028

1. **Falta de poder** no DM-HLN com n=58. Re-test em 2028 ganha ~24
   origens novas → poder esperado de detectar Δ = 0,2 pp em MAE sobe de
   ~50% para ~75%.
2. **Conformal sobrecoberto em h=2** com IC95% Wilson [88,3%, 100%] não
   incluindo nominal (80%). Mais dados → IC mais estreito → conformal
   pode convergir para nominal ou confirmar conservadorismo estrutural.
3. **Autocorrelação residual em lag 12**: especificações alternativas
   (ARDL com mais lags, DFM com `error_order > 0`) podem reduzir.
4. **Não-normalidade severa** dos resíduos limita a interpretação dos
   diagnósticos.

Tudo registrado no [`compromisso_retest_2028.md`](compromisso_retest_2028.md).

---

## 8. Outputs do produto final

```
validacao/portgdp_v2/
├── REGRA_LANCAMENTO.md                          # pré-registro completo
├── compromisso_retest_2028.md                   # compromisso público
├── produto_final_pimpf_combinado.md             # este arquivo
├── sumario_itens_1_2.md                         # síntese da bateria
├── log_modificacoes.md                          # zero desvios pré-registro
├── gr_rolling_pesos.csv                         # 188 linhas (h × origem)
├── gr_rolling_pesos.png                         # série dos pesos
├── gr_rolling_metricas.csv
├── gr_rolling_dm.csv
├── conformal_calibracao.csv
├── conformal_intervalos_teste.csv
├── conformal_cobertura.csv                      # com IC Wilson
├── walkforward_dfm_previsoes.csv                # previsões base
├── dicionario_series.csv                        # 35 ok / 45 excluídas
├── series_tratadas.parquet                      # painel após STL + var12m
├── loadings_fatores.csv                         # interpretação econômica
├── h1_arquivado/                                # h=1 não publicado
│   ├── README.md
│   └── ... (artefatos preservados)
└── produto_final/
    ├── metricas_finais_h2.csv
    ├── diagnosticos_residuos_h2.csv
    └── comparacao_36_origens_h2.png
```

---

## 9. Como o site comunica

Indicador entra na seção `/portos/ineditas/portgdp` do Observatório IBI
com:

- **Título**: "PIM-PF Combinado IBI"
- **Subtítulo**: "Componente complementar ao AR(1) baseline na previsão
  bimestral da Produção Industrial"
- **Status**: badge "Linha D" + "horizonte bimestral apenas"
- **Achados editoriais** (em `analises/metadata.py`, indicador #30):
  reescritos refletindo decisão final em vez do claim original
- **Gráfico interativo**: linhas históricas + dois pontos da previsão
  bimestral combinada com intervalo conformal 80% (sombreado, com nota
  de cobertura conservadora)
- **Link**: para este `produto_final_pimpf_combinado.md` na sidebar
  como "metodologia completa"

A reescrita dos achados em `metadata.py` e do componente
`a30_portgdp` em `c7_ineditas.py` é o último passo operacional
antes do lançamento.
