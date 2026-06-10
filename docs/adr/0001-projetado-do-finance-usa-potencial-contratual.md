# ADR-0001: Projetado do Finance usa o potencial contratual, não a média de NFs

**Data:** 2026-06-10
**Status:** Aceito
**Decisor:** Fernando (domain expert)

## Contexto

O KPI "comissão a pagar projetada" do Finance dashboard mostrava R$3,69M quando a
obrigação real era ~R$792k. Causa: o monthly engine usava a "média real ponderada"
— média mensal derivada das NFs LOCKED (`nf_valor_liquido`) — como valor mensal a
pagar, e valorava meses "A apurar" pela NF bruta.

Existem **duas escalas de dinheiro** no domínio que não podem ser misturadas:

- **Escala NF bruta**: comissão que a Pipo *recebe* das operadoras (linhas de
  `FinancialImport`). Em abril/2026: R$668.662 matched.
- **Escala pagável ao EV**: o que a Pipo *paga* aos EVs — NF × `commission_pct`
  (3–10% por achievement). Em abril/2026: R$51.669,78 (`Commission.monthly_actual`).

A média real ponderada projetava a escala errada (~13× maior) por até 11 meses
restantes do relógio. O próprio fallback do engine (`commission_potential / 12`)
sempre esteve na escala pagável — o KPI somava as duas.

## Decisão

1. **Mensal projetado de Comissão = `commission_potential / 12`, sempre.**
   NF importada ou LOCKED nunca recalibra a projeção. A "média real ponderada"
   (e a "média mensal legada") deixam de existir.
2. **Potencial a pagar = mensal projetado × meses restantes do relógio.**
   Meses legados (`initial_installments_paid`) e meses LOCKED com Comissão
   líquida positiva consomem o relógio, mas não alteram o valor mensal.
3. **A apurar** continua marcando competências com NF importada não-LOCKED e
   reservando relógio quando a Comissão líquida é positiva, mas vale o mensal
   projetado — nunca a NF bruta.
4. **Agenciamento pendente sai do Potencial a pagar** (era somado em NF bruta).
   É pago via apuração e aparece em Realizado/totais pagos quando LOCKED.
5. **Realizado e Comissão Paga seguem em escala NF** (dinheiro de fato recebido
   nos meses LOCKED) — confirmado pelo domain expert como correto, inclusive
   por haver comissões pagas antes da plataforma existir.

## Consequências

- O KPI cai de R$3,69M para R$792.246,94 (base de dev, 2026-06-10) e fica ≤ à
  soma dos potenciais contratuais das apólices ativas por construção.
- `compute_real_weighted_average` removida de `monthly_engine.py`;
  `PolicyFinancialState` perde `commission_paid_legacy`; código morto
  `_project_policy`/`_sum_paid_for_policy` removido de `finance_dashboard.py`.
- Teste de regressão cobre o regime NF ≫ potencial/12
  (`test_projected_monthly_is_contractual_potential_even_with_real_history`) —
  as fixtures antigas só usavam NF ≈ potencial/12 e nunca pegariam o bug.
- O label "recebíveis projetados" (artefato de 2026-05-05) vira
  "comissão a pagar projetada".
- Limitação aceita: se o MRR do HubSpot estiver corrompido/desatualizado, a
  projeção herda esse erro — mas em escala consistente e auditável contra a
  página de Apólices.
