# Regra de decisão pré-registrada — PortGDP × PIM-PF

**Data do registro:** 2026-05-04 (anterior à execução do script `ardl_robustez.py`)

**Fundamento:** este arquivo é commitado **antes** de rodar a bateria de
robustez do item 2 do plano metodológico. Pré-registrar a regra é o que
distingue ciência de *motivated reasoning*: quando o resultado vier, já está
decidido como será comunicado, sem possibilidade de re-classificar para
acomodar o que ficou ruim.

---

## Modelo principal — especificação ARDL

```
y_t = α + φ·y_{t-1} + β·x_{t-2} + γ·D_covid + δ·(D_covid · x_{t-2}) + ε_t
```

onde:
- `y_t` = variação interanual do PIM-PF Indústria Geral (BCB SGS 28503, dessaz)
- `x_{t-2}` = variação interanual do PortGDP-Importações defasada 2 meses
- `D_covid` = 1 se `t ∈ [2020-03, 2021-12]`, 0 caso contrário
- `φ` = persistência (AR(1))
- Inferência com erros-padrão **HAC Newey-West com lag = 12** (não-negociável
  por sobreposição mecânica das var12m)

Ordem AR (`p`): começa em 1; sobe para 2 se Breusch-Godfrey (lag 12) rejeitar
ausência de autocorrelação residual.

## Bateria de robustez

1. **HAC Newey-West**, `maxlags=12`, em todos os intervalos de confiança.
2. **Diagnósticos de resíduo** sobre o ajuste full-sample:
   - Ljung-Box (lags 12 e 24)
   - Breusch-Godfrey (lag 12) — se rejeita H0, sobe `p`
   - Jarque-Bera (normalidade)
   - ARCH-LM (heterocedasticidade)
3. **Versão sem COVID**: re-ajusta ARDL excluindo `mar/2020–dez/2021` inteiro
   e **sem dummies**. Compara `β` com versão completa. Mudança grande
   indica que dummy não está capturando o regime — registrar como sinal de
   quebra estrutural (Bai-Perron candidato).
4. **Versão em log-diferença mensal** (sem var12m): mesma especificação,
   mas com `Δlog(PIM_t)` e `Δlog(Port_t)`. Forecast em `Δlog`,
   agregação para var12m via soma dos 12 últimos. Se essa versão bate
   AR(1) e a var12m não bate → evidência de que sobreposição mecânica
   é o problema central.
5. **Encompassing test (HLN 1998)** com HAC:
   - Testa se ARDL contém AR(1) (ARDL útil) ou se AR(1) contém ARDL
     (ARDL redundante).
   - Implementação: regredir `e_AR1` em `(ŷ_ARDL − ŷ_AR1)`; testar
     `λ = 0` com SE HAC.

## Plano B — combinação

- `mediana(AR(1), ARDL)` e `média(AR(1), ARDL)` em walk-forward.
- Cada combinação testada via DM-HLN contra **cada componente individual**.

---

## Tabela de decisão (pré-registrada)

| # | Resultado | Comunicação pública |
|---|---|---|
| **A** | ARDL bate AR(1) por DM com p<0,05 em h=1 **e** h=2 | "Indicador antecedente do PIM-PF" — claim original sustentado |
| **B** | ARDL bate AR(1) em h=2 mas não em h=1 | "Indicador antecedente em horizonte bimestral" — claim restrito, honesto |
| **C** | ARDL não bate AR(1) isolado, mas ensemble (mediana ou média) bate AR(1) | "Componente do modelo combinado IBI" — port entra como feature, não como protagonista |
| **D** | ARDL não bate, ensemble não bate, mas encompassing test favorece ARDL | "Indicador descritivo de comovimento com componente preditivo marginal" — publica com transparência |
| **E** | Nada bate AR(1) e encompassing favorece AR(1) | "Indicador de comovimento contemporâneo (lag estrutural −2)" — descritivo, não preditivo. Recua do claim original |

A linha aplicada será determinada **mecanicamente** pelos resultados, sem
ajustes pós-hoc. Se múltiplas linhas se aplicam, vence a mais conservadora
(do A para E).

## Critérios auxiliares de gatilho

- Se a versão **log-diferença mensal** vencer AR(1) por DM **e** a versão
  var12m perder, a tabela acima é re-aplicada à versão log-diferença, e a
  comunicação menciona explicitamente que "var12m era o problema".
- Se a versão **sem COVID** mudar `β` em mais de 50% relativo, registra-se
  alerta de quebra estrutural (independente de qual linha A–E se aplica).
- Se Breusch-Godfrey rejeitar com `p<0,05` mesmo com `p=2`, modelo é
  considerado mal-especificado e nenhuma linha A–E é defensável até
  diagnóstico passar.

## Observabilidade

Todos os números (coeficientes, t-stats, p-valores DM, p-valores
encompassing, métricas em ensemble, diagnósticos) saem em
`resultados_robustez.md` e em CSV individuais por seção da bateria.
