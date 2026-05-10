# Nota Técnica — PIM-PF Combinado IBI (v1)

> **Draft 2 (proposto).** Este documento está marcado como rascunho até
> revisão editorial final. Conteúdo consolidado a partir de
> [`validacao/portgdp_v2/produto_final_pimpf_combinado.md`](../validacao/portgdp_v2/produto_final_pimpf_combinado.md)
> com tom adaptado para audiência semi-técnica.

**Versão:** v1 (lançamento inicial)
**Data:** 2026-05-04
**Autoria:** Instituto Brasileiro de Infraestrutura (IBI)
**Status do indicador:** Linha D · validado · re-test mai/2028

---

## Sumário executivo

O **PIM-PF Combinado IBI** é um modelo combinado para previsão da
**Produção Industrial Mensal (PIM-PF) Indústria Geral do IBGE em
horizonte bimestral**. Combina, com pesos ótimos rolling estimados sem
look-ahead, um modelo AR(1) puro do PIM-PF com um Dynamic Factor Model
(DFM) extraído de 35 séries de movimentação portuária da ANTAQ.

A combinação **iguala numericamente o AR(1) baseline** em erro médio
absoluto (3,01 vs 3,02 pp), com encompassing test rejeitando que AR(1)
"contenha" o DFM (e vice-versa) — sinal de que os dois modelos carregam
informação genuinamente complementar. Os intervalos de previsão usam
**split conformal padrão** com cobertura nominal 80%; a cobertura
empírica observada é conservadora (100%, IC 95% Wilson [88,3%, 100%]).

O indicador é publicado **em horizonte bimestral apenas** (h=2). Em
horizonte mensal (h=1) o modelo não passou no critério pré-registrado
e foi arquivado para transparência. Toda a evidência será reavaliada
em maio/2028 com janela amostral expandida — compromisso público de
publicação integral do resultado, independentemente do veredito.

---

## 1. Por que existe este indicador

A pergunta de origem foi: *a movimentação portuária brasileira contém
informação útil para prever a produção industrial?* O processo de
validação rejeitou a versão inicial (modelo univariado linear) em
2026-05, e a especificação atual nasceu da decisão metodológica de
testar se um modelo de **fatores latentes** (DFM) sobre múltiplas
séries portuárias agregaria sinal além da própria autocorrelação do
PIM-PF.

A resposta foi **parcialmente sim**: existe sinal, mas em magnitude
modesta — defendível sob convenção de "indicador complementar" e
honestidade sobre o tamanho do efeito.

## 2. Especificação

### 2.1 Combinação publicada

```
ŷ_combinado_{τ+2} = w_DFM,τ · ŷ_DFM_{τ+2}  +  (1 − w_DFM,τ) · ŷ_AR(1)_{τ+2}
```

A previsão é da **variação interanual do PIM-PF** dois meses à frente,
publicada como índice (base 2014 = 100) após reconstrução do nível.

### 2.2 Componente AR(1)

Modelo `var12m(PIM)_t = α + φ · var12m(PIM)_{t−1} + ε_t` ajustado por
OLS sobre toda a história disponível até a origem τ. Previsão iterativa
até `τ+2`.

### 2.3 Componente DFM

- **Painel**: 35 séries de movimentação portuária ANTAQ (top 10 portos
  por movimentação 2014-2024 × 4 naturezas × 2 sentidos com
  `FlagLongoCurso=1`). Filtro de cobertura: ≤24 meses zero/NA, sem
  streaks NaN > 2.
- **Tratamento**: imputação linear de NaN isolados (≤2 meses), STL para
  dessazonalização (`period=12`, `robust=True`), variação interanual
  `pct_change(12)`, padronização z-score com média e dp do treino apenas.
- **Modelo**: `DynamicFactor` em `statsmodels.tsa.statespace`, **1 fator,
  AR(2)**, sem dinâmica nos idiossincráticos (`error_order=0,
  error_var=False`). Estimação via Kalman MLE (lbfgs, fallback Powell).
- **Previsão**: regressão `var12m(PIM)_{t+2} ~ α + γ · F_t` com **HAC
  Newey-West (lag 12)**, refit em cada origem do walk-forward.

### 2.4 Pesos da combinação (Granger-Ramanathan rolling OOS)

A cada origem τ:

1. Coletar pares `(y_t, ŷ_DFM_t, ŷ_AR1_t)` de todas as origens
   estritamente anteriores a τ.
2. Estimar w_DFM por OLS sem intercepto:
   `(y − ŷ_AR1) ~ (ŷ_DFM − ŷ_AR1)`.
3. **Truncar em `[0, 1]`** se cair fora.
4. Aplicar peso na previsão pontual da origem τ.

Janela mínima de aquecimento: **36 origens**. Antes disso, sem
combinação publicada.

### 2.5 Intervalos de previsão (split conformal padrão)

Procedimento de Lei et al. (2018):

1. Calibração: erros absolutos `|y − ŷ_combinado|` da primeira metade
   da janela OOS-legítima.
2. Quantil conformal:
   `q̂ = ⌈(n+1)(1−α)⌉-ésimo menor erro absoluto` da calibração.
3. Intervalo: `[ŷ − q̂, ŷ + q̂]`.

Garantia formal de Vovk: cobertura marginal ≥ 1 − α sob exchangeability.
Configuração publicada: **α = 0,20** (cobertura nominal 80%).

## 3. Validação

### 3.1 Walk-forward rolling-origin

- **Janela total**: 95 origens (jan/2018 → out/2025).
- **Janela OOS-legítima**: 58 origens (≥ 36 de aquecimento + 1).
- **Refit completo** do DFM e regressão de previsão a cada origem.
- **Baselines comparados**: AR(1), Random Walk, sazonal naive, ARDL.

### 3.2 Métricas (h=2, n=58)

| Modelo | MAE (pp) | RMSE (pp) |
|---|---|---|
| **PIM-PF Combinado IBI** | **3,01** | **5,88** |
| AR(1) baseline | 3,02 | 6,03 |
| DFM-1f isolado | 3,49 | 6,54 |

### 3.3 Diebold-Mariano com correção HLN

| Comparação | DM stat | p-valor | Conclusão |
|---|---|---|---|
| Combinação vs AR(1) | −0,31 | 0,75 | Empate estatístico |
| Combinação vs DFM puro | −1,38 | 0,17 | Empate estatístico |

A combinação não rejeita igualdade contra nenhum componente — falta de
poder com n=58. A direção numérica favorece a combinação.

### 3.4 Encompassing test (HLN 1998) com HAC

| Encompasser | Encompassed | λ̂ | p-valor | Rejeita H0 |
|---|---|---|---|---|
| DFM-1f | AR(1) | 0,51 | <0,001 | **Sim** |
| AR(1) | DFM-1f | 0,49 | <0,001 | **Sim** |

**Ambas direções rejeitam** — DFM e AR(1) carregam informação
**genuinamente complementar**. Nenhum encompassa o outro. É a evidência
mais forte a favor do indicador.

### 3.5 Pesos rolling OOS

| Estatística | Valor |
|---|---|
| `w_DFM` médio | **42,4%** |
| `w_DFM` mediana | 43,2% |
| Range | [27,3%, 48,5%] |
| Desvio-padrão | 0,028 |
| Truncamentos em [0, 1] | **0** |

Robustez: o peso rolling OOS é praticamente idêntico ao peso in-sample
(41,1%), nunca foi truncado e tem variabilidade pequena ao longo das 58
origens.

### 3.6 Cobertura conformal

| Métrica | Valor |
|---|---|
| Cobertura nominal | 80% |
| Cobertura empírica observada | **100%** |
| IC 95% Wilson | [88,3%, 100%] |
| Largura média do intervalo | 10,70 pp |
| n_calibração / n_teste | 29 / 29 |

A cobertura empírica acima da nominal indica intervalos
**conservadores** — o lado seguro. Não foi aplicado shrink empírico
para preservar a garantia formal de Vovk. A pequena janela (n_teste=29)
limita o que se pode afirmar sobre cobertura real; o re-test em 2028
acrescenta ~24 origens novas.

### 3.7 Diagnósticos de resíduo da combinação (h=2)

| Teste | p-valor | Conclusão |
|---|---|---|
| Ljung-Box (lag 12) | 0,007 | Autocorrelação residual em lags curtos |
| Ljung-Box (lag 24) | 0,28 | Sem autocorrelação em lags longos |
| Jarque-Bera | <10⁻¹⁵² | Não-normalidade severa (caudas pesadas) |
| ARCH-LM (lag 12) | 0,25 | Homocedasticidade OK |

A autocorrelação residual em lag 12 e a não-normalidade são limitações
reconhecidas. DM-HLN e conformal **não pressupõem normalidade** — não
invalidam o produto, mas explicam parte da sobrecobertura conformal e
sugerem possíveis melhorias para o re-test (ARDL com mais lags ou DFM
com `error_order > 0`).

## 4. O que o indicador é, e o que não é

### É

- **Componente complementar** ao AR(1) baseline na previsão da produção
  industrial em **horizonte bimestral**.
- **Modelo validado rolling OOS** com pesos sem look-ahead.
- **Intervalos com garantia formal Vovk** (split conformal padrão).
- **Indicador transparente** com pré-registro completo, log de
  modificações sem desvios e compromisso público de re-test.

### Não é

- ❌ **Indicador antecedente do PIB** ou da atividade econômica como
  um todo. O alvo é estritamente o **PIM-PF Indústria Geral do IBGE**.
- ❌ **Indicador mensal**. Em h=1 o modelo não passou no critério
  pré-registrado. Ver
  [`validacao/portgdp_v2/h1_arquivado/README.md`](../validacao/portgdp_v2/h1_arquivado/README.md).
- ❌ **Substituto** de modelos macroeconômicos do BCB ou IBGE.
- ❌ **Indicador autônomo**. O componente DFM isolado tem MAE
  significativamente pior que o AR(1) baseline; o valor está na
  combinação.

## 5. Como ler os intervalos de previsão

O intervalo conformal de 80% cobre **pelo menos** 80% das observações
realizadas, sob a hipótese de exchangeability dos erros. Na janela
disponível para teste (n=29 origens), a cobertura empírica observada
foi 100% — todos os pontos de teste caíram dentro do intervalo.

**Interpretação correta:** "o intervalo é conservador, com largura
provavelmente maior que o estritamente necessário para cobertura 80%."

**Interpretação incorreta:** "cobertura é sempre 100%". A
exchangeability é uma hipótese; choques estruturais (ex: outro evento
do tipo COVID) podem violá-la, e a cobertura real cair.

## 6. Limitações reconhecidas

1. **Falta de poder estatístico**: DM-HLN não rejeita com n=58. Não
   significa ausência de efeito — significa que a janela é pequena
   demais para detectá-lo com poder ≥ 80% se o efeito for da magnitude
   observada (Δ MAE ≈ 0,01 pp).
2. **Sobrecobertura conformal**: cobertura empírica 100% vs nominal
   80%. IC95% Wilson [88,3%, 100%] não inclui 80%. Pode ser
   conservadorismo estrutural ou variabilidade amostral; n_teste=29
   limita resolução.
3. **Autocorrelação residual em lag 12**: modelo provavelmente subestima
   persistência sazonal de curto prazo. Não invalida previsão pontual.
4. **Não-normalidade severa**: caudas pesadas dos erros (especialmente
   COVID) dominam o quantil de calibração — parte da sobrecobertura
   vem daqui.
5. **Janela única**: validação em uma única passagem walk-forward sobre
   2018–2025. Sem validação cruzada inter-períodos. Re-test em 2028
   atende parcialmente.

## 7. Compromisso de re-test

Re-test pré-registrado para **maio de 2028**. Bateria idêntica à
atual, regra de decisão completa (sem zonas mortas), publicação
integral do resultado mesmo que seja **rebaixamento para Linha E**.

Detalhes em
[`validacao/portgdp_v2/compromisso_retest_2028.md`](../validacao/portgdp_v2/compromisso_retest_2028.md).

**Importante:** o cron de maio/2028 **não rebaixa o indicador
automaticamente**. O cron apenas dispara um lembrete (issue + notificação
humana). Rebaixamento ou promoção dependem de **re-execução da bateria
completa por equipe humana** sobre dados novos.

## 8. Reprodutibilidade

Todo o código de validação está em `analises/validacao/`:

- `portgdp_v2_dicionario.py` — construção determinística do dicionário
- `portgdp_v2_preparacao.py` — tratamento das séries
- `portgdp_v2_dfm_fullsample.py` — DFM full-sample (sanity)
- `portgdp_v2_walkforward.py` — walk-forward rolling-origin
- `portgdp_v2_decisao.py` — bateria DM/encompassing/GR
- `portgdp_v2_lancamento.py` — Itens 1+2 (rolling GR + conformal)
- `portgdp_v2_produto_final.py` — diagnósticos do produto

Outputs CSV em `validacao/portgdp_v2/` (incluindo h=1 arquivado).

## 9. Autoria e contato

Equipe IBI — Observatório de Infraestrutura. Comentários metodológicos
e questões podem ser abertos como issues no repositório
`IBI-Observatorio/IBI-Observatorio` no GitHub. Críticas que apontem
problemas no pré-registro, na execução ou na interpretação são
explicitamente bem-vindas — toda a evidência está documentada
publicamente justamente para isso.
