# Pré-registro — Spike DFM (PortGDP v2)

**Carimbo de tempo (commit antes de qualquer execução):** 2026-05-04
**Stop firme:** 5 dias úteis. Encerra e fecha Linha E se não estiver
rodando limpo até lá.

Toda decisão abaixo é **pré-registrada**. Modificação posterior exige log
explícito (motivo, momento, quem decidiu) antes da modificação.

---

## 1. Dicionário de séries

### Critério mecânico (sem inspeção visual prévia)

- **Portos**: top 10 por movimentação total acumulada 2014–2024 (toneladas,
  sem filtro de natureza ou sentido). Lista determinada por query SQL
  determinística sobre `Atracacao + Carga`.
- **Naturezas**: Carga Conteinerizada, Carga Geral, Granel Sólido,
  Granel Líquido e Gasoso (4).
- **Sentidos**: Desembarcados, Embarcados (2).
- **Filtro**: `FlagLongoCurso = 1` (mantém hipótese de comércio internacional).
- **Granularidade**: mensal, toneladas.

Universo bruto: 10 × 4 × 2 = **80 séries candidatas**.

### Filtro de cobertura

Descartar série se:
- mais de 24 meses de zeros **ou** faltantes em jan/2014 – dez/2025

Documentar quantas/quais foram descartadas em
`validacao/portgdp_v2/dicionario_series.csv` com motivo de exclusão.

Esperado pós-filtro: **25–50 séries efetivas**.

## 2. Tratamento

Cada série, individualmente:

1. **Imputação** de faltantes isolados (≤ 2 meses consecutivos): interpolação
   linear. Maiores → exclusão da série.
2. **Dessazonalização**: X-13 ARIMA-SEATS via
   `statsmodels.tsa.x13_arima_analysis`. Se X-13 falhar para uma série
   (binário não disponível ou erro de ajuste), **fallback documentado**
   para `statsmodels.tsa.STL`.
3. **var12m**: variação interanual (mesma transformação do PIM-PF).
4. **Padronização (z-score)**: aplicada apenas com **média e desvio da
   janela de treino** em cada origem do walk-forward (sem look-ahead).

## 3. Especificação DFM

`statsmodels.tsa.statespace.dynamic_factor.DynamicFactor`, MLE via Kalman.

### Variantes a testar (apenas estas)

- **DFM-1f**: 1 fator, dinâmica AR(2)
- **DFM-2f**: 2 fatores, dinâmica VAR(1) conjunta

### Parâmetros fixos

- `error_order = 0` (idiossincráticos sem dinâmica)
- `error_var   = False` (idiossincráticos não-correlacionados)
- `maxiter = 500`, `disp = False`. Não convergência → log + exclusão da
  variante naquela origem.

### Equação preditiva

$$\Delta_{12}\text{PIM}_{t+h} = \alpha + \sum_{k=1}^{K} \gamma_k F_{k, t-2} + \varepsilon_{t+h}$$

- $F_{k, t-2}$: fatores latentes defasados 2 meses (mantém defasagem
  estrutural do v1).
- OLS com HAC Newey-West (lag = 12) para estimar $\gamma_k$ a cada origem.

## 4. Validação

Reaproveita a bateria `analises/validacao/` integralmente:

- 95–96 origens (jan/2018 a out/2025)
- h ∈ {1, 2}
- Baselines: AR(1), RW, sazonal naive, ARDL
- Métricas: MAE, RMSE, pinball loss, CRPS
- DM-HLN: DFM-1f vs AR(1), DFM-2f vs AR(1), DFM (melhor) vs ARDL
- Encompassing test (HLN 1998), convenção corrigida explícita:
  testar `(encompasser=AR(1), encompassed=DFM)`, buscando `rejeita_H0=True`
  como sinal de que DFM agrega valor.
- Granger-Ramanathan restrito (soma=1, OLS sem intercepto, HAC SE):
  pesos w_DFM e w_AR1.

## 5. Regra de decisão pré-registrada

| Linha | Condição | Comunicação |
|---|---|---|
| **A** | DFM bate AR(1) por DM (p<0,05) em h=1 **e** h=2 | "Indicador antecedente do PIM-PF via fatores de comércio internacional" — claim preditivo completo |
| **B** | DFM bate AR(1) por DM (p<0,05) em **h=2 apenas** | "Indicador antecedente em horizonte bimestral" — claim restrito |
| **C** | DFM não bate isolado, **mas** combinação GR atribui peso ≥ 15% ao DFM com p<0,10 **e** MAE combinado < MAE AR(1) por DM | "Componente do modelo combinado IBI" — DFM entra como feature |
| **D** | Encompassing rejeita "AR(1) encompasses DFM" (p<0,05) **mas** DM e GR não favorecem | "Comovimento estrutural com componente preditivo marginal" — descritivo, com transparência sobre marginalidade |
| **E** | Nenhuma das condições acima | **Linha E definitiva.** PortGDP v1 sobe descritivo; DFM v2 fica documentado como tentativa não-bem-sucedida no arquivo do Observatório |

Aplicação **mecânica**. Múltiplas linhas → vence a mais forte (A > B > C > D > E).

## 6. Outputs esperados

```
validacao/portgdp_v2/
├── REGRA_DECISAO.md              ← este arquivo (pré-registro)
├── log_modificacoes.md            ← log de exceções (vazio se tudo correr)
├── dicionario_series.csv          ← dicionário com motivo de exclusão
├── series_tratadas.parquet        ← séries dessaz + var12m + cobertura
├── loadings_fatores.csv           ← pesos de cada série em cada fator
├── fatores_estimados.csv          ← fatores latentes (séries)
├── walkforward_dfm_previsoes.csv  ← previsões por origem
├── dm_completo.csv                ← todos os pares DM
├── encompassing.csv               ← convenção explícita
├── granger_ramanathan.csv         ← pesos ótimos restritos
└── sumario_executivo.md           ← decisão aplicada
```

## 7. Disciplina anti-garimpagem

- **Não inspecionar previsões DFM** antes do walk-forward terminar
  completamente. Ver previsões por origem antes do agregado convida ajuste
  post-hoc.
- **Não modificar dicionário, especificação ou regra** depois de iniciar
  estimação.
- Se aparecer problema técnico que exija modificação, **logar em
  `log_modificacoes.md`** com timestamp, motivo, decisor — antes de
  modificar.
- **Diagnósticos de resíduo do DFM** (Ljung-Box, ARCH-LM, normalidade)
  reportados em paralelo, **não usados para selecionar variante**.
  Servem para a nota técnica de transparência, não para escolher
  vencedor.

## 8. Cronograma

| Dia | Entrega |
|---|---|
| 1 | Dicionário, filtro, X-13/STL, padronização. Saída: 25–50 séries em DataFrame único. |
| 2 | DFM-1f e DFM-2f full-sample. Loadings + interpretação econômica (sanity). |
| 3 | Walk-forward implementado e rodando. Caminho crítico — começar cedo. |
| 4 | Bateria DM + encompassing + GR rodada e tabelada. |
| 5 | Regra aplicada, sumário executivo, decisão final. |

Se Dia 3 não estiver com walk-forward rodando, escala — caminho crítico.
