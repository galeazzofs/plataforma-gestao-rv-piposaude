# Plano: Potencial a Pagar e Relogio de Comissao

**Data:** 2026-05-06  
**Status:** Pronto para implementacao  
**Contexto:** regras registradas em `CONTEXT.md`

## Resumo

Reestruturar os calculos financeiros da plataforma para separar claramente:

- **Comissao Potencial da Apolice**: referencia contratual na pagina de Apolices, calculada como `MRR x 12 x % comissao`.
- **Potencial a pagar**: obrigacao futura/pendente do Finance, excluindo valores ja realizados.
- **Relogio de 12 meses da apolice**: conta apenas meses financeiros com **Comissao** liquida positiva.

A plataforma deve contar apenas **Comissao** e **Agenciamento**. Qualquer outro `tipo_receita` nao deve entrar em apuracao, Finance, potencial, fluxo de caixa ou totais pagos.

## Decisoes de Dominio

- **Receita comissionavel** e exatamente `Comissao + Agenciamento`.
- **Agenciamento** e pagavel enquanto a apolice esta aberta, mas nao inicia, nao avanca e nao reserva o relogio de 12 meses.
- O relogio de 12 meses usa `nf_mes_recebimento` como mes financeiro.
- Um mes de Comissao conta no relogio somente se o liquido mensal de Comissao da apolice for positivo.
- NFs negativas entram no liquido do proprio mes. Um mes com liquido de Comissao `<= 0` nao conta no relogio.
- `initial_installments_paid` representa meses legados reais de Comissao e nao deve ser recalculado nem sobrescrito automaticamente.
- `commission_paid_legacy` e receita real legada e deve compor a media real ponderada.
- A media usada pelo Finance e:
  `media = (commission_paid_legacy + soma Comissao realizada LOCKED) / (initial_installments_paid + meses Comissao LOCKED positivos)`
- Se nao houver historico real, usar fallback:
  `commission_potential / 12`.
- A media real nao deve ser limitada pelo potencial contratual mensal, porque MRR tambem e uma previsao.
- Ao completar 12/12 meses de Comissao, a apolice vira **Totalmente paga** (`SETTLED`) e sai de todos os calculos futuros.
- Apolices `SETTLED` continuam visiveis na pagina de Apolices para historico/auditoria, com estado visual claro.
- Apolices `CANCELLED` sao excluidas antes da apuracao e nao precisam de logica por data de cancelamento.

## Finance: Realizado, A Apurar, Projetado

O dashboard Finance deve operar por **competencia mensal**, nao pelo mes em que a apuracao trimestral e executada.

Estados mensais:

- **Realizado**: mes pertence a uma apuracao `LOCKED`; nao entra no Potencial a pagar.
- **A apurar**: mes passado/atual de trimestre ainda nao `LOCKED`; usa NF importada matched quando existir.
- **Projetado**: mes sem NF importada; usa media real ponderada ou fallback contratual.

Regras:

- Para cada apolice + mes financeiro, **A apurar substitui Projetado** quando houver NF matched importada.
- O mesmo policy-month nunca pode ser contado duas vezes.
- `A apurar` com Comissao liquida positiva reserva temporariamente um mes do relogio para evitar projecao 13/12.
- `A apurar` nao recalibra a media futura ate a apuracao virar `LOCKED`.
- Agenciamento importado em mes `A apurar` entra no Potencial a pagar, mas Agenciamento futuro nao e projetado.
- **Potencial a pagar** e a soma dos policy-months nao realizados, onde cada mes entra como `A apurar` ou `Projetado`.
- O fluxo de caixa projetado deve reconciliar com o Potencial a pagar e mostrar os valores por competencia mensal.

## Apuracao EV

Alterar o calculator para processar por apolice e mes financeiro em ordem cronologica.

Fluxo recomendado:

1. Carregar apolices elegiveis, excluindo `CANCELLED` e ja `SETTLED`.
2. Agrupar NFs matched por apolice, `nf_mes_recebimento` e tipo de receita.
3. Para cada apolice, iniciar contador com `initial_installments_paid`.
4. Para cada mes em ordem cronologica:
   - se a apolice ja estava 12/12 antes do mes, marcar linhas como `APOLICE_FINALIZADA`;
   - se ainda estava aberta, pagar Comissao e Agenciamento elegiveis do mes;
   - se o liquido mensal de Comissao for positivo, avancar o relogio em 1;
   - se chegar em 12/12, marcar `SETTLED` para meses futuros.
5. O mes que completa 12/12 ainda paga Comissao e Agenciamento daquele mesmo mes.
6. Meses posteriores no mesmo trimestre nao geram pagamento e vao para revisao como `APOLICE_FINALIZADA`.

Adicionar bucket de revisao **Apolices finalizadas**, semelhante a `UNMATCHED`, sem misturar essas linhas na visao pagavel por EV.

Motivo canonico:

- `APOLICE_FINALIZADA`: linha importada casou com apolice, mas ficou fora porque a apolice ja tinha completado 12/12 antes daquele mes financeiro.

Quando a apolice completar 12/12 dentro do proprio trimestre, linhas posteriores devem informar em que mes a apolice completou o ciclo.

## Mudancas Provaveis

Backend:

- Criar helpers compartilhados para:
  - normalizar/classificar `tipo_receita`;
  - calcular liquido mensal de Comissao;
  - calcular meses realizados, a apurar e projetados;
  - decidir elegibilidade por apolice/mes;
  - calcular Potencial a pagar.
- Ajustar `backend/app/modules/commissions/calculator.py`.
- Ajustar `backend/app/api/v1/finance_dashboard.py`.
- Ajustar `backend/app/modules/financial/policy_paid_totals.py` para manter separacao Comissao/Agenciamento e ignorar tipos nao comissionaveis.
- Ajustar serializers de revisao de apuracao para expor bucket **Apolices finalizadas**.

Frontend:

- Renomear KPI Finance de `Comissao Potencial` para **Potencial a pagar**.
- Exibir no fluxo mensal os estados `Realizado`, `A apurar` e `Projetado`.
- Adicionar estado visual **Totalmente paga** na pagina de Apolices para apolices 12/12.
- Adicionar aba/secao **Apolices finalizadas** na revisao da apuracao.

Dados/schema:

- Preferir nao criar coluna nova no primeiro passo.
- Usar `commission_status = SETTLED` como estado tecnico de **Totalmente paga**.
- Se o status/motivo `APOLICE_FINALIZADA` precisar persistir em `financial_imports.match_status`, verificar se a coluna aceita o tamanho/valores e adicionar teste.

## Plano de Implementacao

### Fatia 1: motor financeiro mensal

- Implementar helpers puros e testaveis para classificacao de receita, agrupamento mensal, media real ponderada, reserva de meses `A apurar` e distribuicao de `Projetado`.
- Cobrir com testes unitarios antes de mudar endpoints.

### Fatia 2: apuracao EV

- Alterar calculator para usar somente Comissao + Agenciamento.
- Processar meses em ordem cronologica.
- Fazer Agenciamento pagar sem alterar relogio.
- Marcar `SETTLED` ao completar 12/12.
- Separar linhas `APOLICE_FINALIZADA`.

### Fatia 3: Finance dashboard

- Trocar KPI para **Potencial a pagar**.
- Construir serie mensal com `Realizado`, `A apurar`, `Projetado`.
- Garantir que fluxo mensal reconcilia com Potencial a pagar.
- Garantir que `A apurar` substitui `Projetado` por apolice + mes.

### Fatia 4: UI de revisao e apolices

- Adicionar aba/secao **Apolices finalizadas** na revisao.
- Mostrar badge/estado **Totalmente paga** em Apolices.
- Ajustar labels/captions do Finance para evitar confusao com Comissao Potencial da Apolice.

## Testes Obrigatorios

Backend:

- Agenciamento sozinho no primeiro mes: paga, mas nao inicia relogio.
- Comissao + Agenciamento no mesmo mes: paga ambos; Comissao conta 1 mes.
- Estorno no mesmo mes: usa liquido mensal; conta so se liquido de Comissao for positivo.
- Tipo Receita diferente de Comissao/Agenciamento: nao entra em nada.
- Apolice 11/12 com Abril e Maio tendo Comissao: Abril fecha 12/12; Maio vira `APOLICE_FINALIZADA`.
- Apolice 11/12 com Abril Comissao + Agenciamento: paga ambos e fecha.
- Apolice 12/12 antes da apuracao: todas as linhas matched vao para **Apolices finalizadas**.
- `initial_installments_paid` preservado e usado como meses legados.
- `commission_paid_legacy` entra na media real ponderada.
- Media real maior que potencial contratual mensal nao e capada.
- `A apurar` substitui `Projetado` sem duplicar policy-month.
- `A apurar` reserva mes do relogio, mas nao recalibra media ate `LOCKED`.
- `LOCKED` transforma meses em Realizado, atualiza totais pagos, media futura e status `SETTLED`.

Frontend/smoke:

- Finance mostra **Potencial a pagar**, nao Comissao Potencial.
- Fluxo mensal diferencia `Realizado`, `A apurar`, `Projetado`.
- Q2 apurado em Julho aparece em Abr/Mai/Jun por competencia mensal.
- Apos Q2 `LOCKED`, Abr/Mai/Jun mudam para realizado automaticamente.
- Apolices 12/12 ficam visiveis com badge **Totalmente paga**.
- Revisao da apuracao mostra **Apolices finalizadas** separado da visao por EV.

## Criterios de Aceite

- Nao existe calculo financeiro usando tipos de receita fora de Comissao + Agenciamento.
- Finance e apuracao usam a mesma regra de elegibilidade por apolice/mes.
- Potencial a pagar nunca soma `A apurar` e `Projetado` para o mesmo policy-month.
- Apolices 12/12 nao entram em apuracao futura, Potencial a pagar ou fluxo projetado.
- Valores por competencia mensal nao sao movidos para o mes em que a apuracao trimestral e executada.
- As regras novas estao documentadas em `CONTEXT.md` e cobertas por testes.
