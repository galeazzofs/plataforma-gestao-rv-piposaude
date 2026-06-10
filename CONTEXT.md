# Pipo RV

This context captures the domain language for Pipo Saude's variable remuneration platform, especially rules that decide which financial amounts count toward payable commissions and finance obligations.

## Language

**Receita comissionavel**:
Financial-import revenue that counts toward EV commission and finance cash-flow obligations.
_Avoid_: revenue, faturamento, all revenue

**Comissao**:
A commissionable revenue type from the financial import.
_Avoid_: any revenue type that merely contains money

**Agenciamento**:
A commissionable revenue type from the financial import.
_Avoid_: fee, premiacao, patrocinio

**Mes de comissao pago**:
A distinct policy month in which recurring Comissao was received and paid.
_Avoid_: month with any revenue, agenciamento month

**Liquido mensal de Comissao**:
The sum of all Comissao financial-import rows for one policy in one month, including negative adjustments.
_Avoid_: raw NF amount, gross month

**Mes financeiro**:
The financial import month (`nf_mes_recebimento`) used for monthly grouping, averages, Finance dashboards, and the commission clock.
_Avoid_: exact receipt date for monthly Finance reporting

**Competencia mensal**:
The month to which commission and finance values belong in reporting, regardless of when the apuracao runs.
_Avoid_: apuracao execution month, payment batch month

**Realizado**:
A monthly Finance value that belongs to a LOCKED apuracao.
_Avoid_: projected, pending close

**A apurar**:
A monthly Finance value for a past or current competency whose apuracao is not LOCKED yet.
_Avoid_: realized, pure future projection

**Projetado**:
A monthly Finance value for a future competency estimated from the policy projection rules.
_Avoid_: realized, pending close

**Relogio de 12 meses da apolice**:
The count of recurring Comissao months that have been paid for a policy.
_Avoid_: revenue clock, agenciamento clock

**Primeiro mes de Comissao**:
The first financial month in which a policy has positive net Comissao.
_Avoid_: first received month, first agenciamento month

**Meses legados de Comissao**:
Manually curated pre-platform Comissao months already paid for a policy.
_Avoid_: recalculated legacy months, imported agenciamento months

**Media mensal legada de Comissao**:
Pre-platform paid Comissao divided by manually curated legacy Comissao months.
_Avoid_: contractual monthly potential

**Mensal projetado de Comissao**:
The monthly amount Finance uses to project future Comissao payments for a policy.
_Avoid_: paid monthly amount, agenciamento monthly amount

**Media real ponderada de Comissao**:
Legacy Comissao plus platform Comissao divided by legacy months plus positive platform Comissao months.
_Avoid_: platform-only average, contractual average

**Receita nao comissionavel**:
Financial-import revenue that must not count anywhere in the platform's commission, projected cash-flow, paid-total, potential-commission, or payable-obligation calculations.
_Avoid_: other revenue, miscellaneous revenue

**Comissao potencial da apolice**:
The full-life expected EV commission for a policy, calculated as commissionable policy MRR times 12 times the EV commission percentage.
_Avoid_: paid commission, projected cash flow, finance forecast

**Potencial a pagar**:
The future payable commission obligation for Finance, excluding amounts already paid.
_Avoid_: comissao potencial, full-life potential, paid total, inflated projection

**Apolice totalmente paga**:
A policy whose 12-month Comissao clock is complete and no longer generates payable commission or finance projection.
_Avoid_: active payable policy, future payable policy

**Apolices finalizadas**:
Review bucket for imported financial rows that matched a policy excluded because it was already fully paid.
_Avoid_: unmatched, EV payable rows

**APOLICE_FINALIZADA**:
Exclusion reason for an imported row whose matched policy had already reached 12/12 before that row's financial month.
_Avoid_: expired, unmatched

**Apolice cancelada**:
A policy that no longer generates future payments because its lifecycle was interrupted before completion.
_Avoid_: fully paid policy, settled policy

**Ciclo Mensal**:
The monthly orchestration cycle that runs the apuracao sequence — Apuracao EV, Apuracao CN, and, only on quarter-end months (March, June, September, December), Bonus CN, Bonus EV and Bonus Lideranca. Operated from a single step-rail page with global (team-less) component aggregation.
_Avoid_: ciclo trimestral, quarterly cycle, per-team cycle progress

## Relationships

- **Receita comissionavel** is exactly **Comissao** plus **Agenciamento**.
- **Receita nao comissionavel** includes Fee por Vida, Premiacao, Patrocinio, and any imported revenue type other than **Comissao** or **Agenciamento**.
- EV commission and Finance projected cash flow must use the same **Receita comissionavel** boundary.
- **Comissao potencial da apolice** belongs to the policy lifecycle and appears on the Policies page.
- **Potencial a pagar** belongs to Finance and represents only future cash obligation, not amounts already paid.
- **Comissao** increments the **Relogio de 12 meses da apolice** by one **Mes de comissao pago** per distinct month.
- A **Mes de comissao pago** exists only when the **Liquido mensal de Comissao** is positive.
- **Primeiro mes de Comissao** starts the **Relogio de 12 meses da apolice**.
- **Meses legados de Comissao** reduce remaining months in the **Relogio de 12 meses da apolice** and must not be automatically recalculated or overwritten.
- **Media mensal legada de Comissao** calibrates **Potencial a pagar** when no platform Comissao months exist yet.
- **Mensal projetado de Comissao** uses **Media real ponderada de Comissao** when any real legacy or platform Comissao exists, and policy contractual monthly potential only as fallback.
- **Media real ponderada de Comissao** is not capped by **Comissao potencial da apolice** because policy MRR is also a forecast.
- **Mes financeiro** defines monthly grouping for the **Relogio de 12 meses da apolice**, **Liquido mensal de Comissao**, Finance dashboards, and projected cash flow.
- Finance uses **Competencia mensal** for cash-flow display: the monthly apuracao changes monthly values from projected to realized when LOCKED, but does not move them into the apuracao execution month.
- Finance monthly cash flow distinguishes **Realizado**, **A apurar**, and **Projetado** values.
- **A apurar** uses imported matched financial rows when available and falls back to projection only when no imported value exists for that competency.
- For each policy and **Mes financeiro**, **A apurar** replaces **Projetado** when imported matched values exist; the same policy-month must never be counted twice.
- **A apurar** values do not recalibrate **Mensal projetado de Comissao** until their apuracao becomes LOCKED.
- **A apurar** months with positive net Comissao reserve a month in the 12-month clock for projection purposes, but do not officially update paid months until LOCKED.
- **Agenciamento** is paid and accumulated on the policy, but does not increment the **Relogio de 12 meses da apolice**.
- **Agenciamento** can appear by itself in an **A apurar** month, often at the beginning of a policy, and still does not start or reserve the commission clock.
- **Agenciamento** is not projected into future Finance cash flow unless a future rule explicitly makes it predictable.
- **Agenciamento** is payable during an open **Relogio de 12 meses da apolice**, including the same financial month that completes the twelfth Comissao month.
- Imported **Agenciamento** in an **A apurar** month contributes to **Potencial a pagar** until LOCKED; future **Projetado** months do not include Agenciamento.
- **Apolice totalmente paga** is excluded from future apuracao, **Potencial a pagar**, and Finance projected cash flow.
- Finance projected cash flow is the monthly distribution of **Potencial a pagar** and must reconcile to it.
- Financial-month processing checks whether a policy was already an **Apolice totalmente paga** before the month; if not, eligible Comissao and Agenciamento for that month are paid before the policy can become fully paid for future months.
- Financial-month processing is chronological; once a policy reaches 12/12 in a month, later months are no longer eligible.
- **Apolice totalmente paga** should be visually explicit in policy views because it must not enter any financial calculation.
- **Apolice totalmente paga** remains visible in policy views for history and audit, but is excluded from operational calculation views and projections.
- Imported rows excluded because of **Apolice totalmente paga** appear in the review area under **Apolices finalizadas**, not inside payable EV apuracao detail.
- **APOLICE_FINALIZADA** rows should explain the month in which the policy reached 12/12 when that happened inside the same apuracao.
- **Apolice totalmente paga** and **Apolice cancelada** both have zero **Potencial a pagar**, but are distinct states with different business reasons.
- **Apolice cancelada** is set before apuracao starts and is excluded from that apuracao and future financial calculations.
- The **Ciclo Mensal** replaces the former quarterly cycle: one cycle per month, auto-LOCKED when every component in its sequence is LOCKED.
- Bonus CN, Bonus EV and Bonus Lideranca remain quarterly aggregations; they attach to the **Ciclo Mensal** of the quarter-end month.

## Example Dialogue

> **Dev:** "Should Fee por Vida contribute to the EV's commission potential or the Finance cash-flow projection?"
> **Domain expert:** "No. Only Comissao and Agenciamento count; the rest should not be counted anywhere in the platform."

> **Dev:** "What should the Policies page show as commission potential?"
> **Domain expert:** "MRR da apolice x 12 x percentual de comissao."

> **Dev:** "If the first received month only has Agenciamento, does it count as month 1 of the policy?"
> **Domain expert:** "No. Pay and store the Agenciamento, but the 12-month clock starts only when Comissao is received."

> **Dev:** "Should Finance's Potencial a pagar include commission and agenciamento already paid?"
> **Domain expert:** "No. Finance needs the future obligation; paid amounts should reduce what remains to spend."

> **Dev:** "Should Finance project future Agenciamento before a financial import exists?"
> **Domain expert:** "No, not for now. Agenciamento is paid when imported, but future Agenciamento projection may be added later."

> **Dev:** "If a month has a positive Comissao NF and a negative adjustment, how does it affect the clock?"
> **Domain expert:** "Use the monthly net Comissao. If the month is still positive, it counts as one paid commission month."

> **Dev:** "Should monthly Finance calculations use the exact receipt date or the financial import month?"
> **Domain expert:** "Use the financial month. The exact date is only for vigencia validation."

> **Dev:** "If Agenciamento arrives in January and Comissao starts in March, when does the 12-month clock start?"
> **Domain expert:** "March. The clock starts at the first positive Comissao month, not at the first received money."

> **Dev:** "Can we recalculate legacy months from imported data?"
> **Domain expert:** "No. The existing legacy month counts were manually curated and must be preserved."

> **Dev:** "If a policy has legacy paid commission but no platform commission months yet, how should Finance project it?"
> **Domain expert:** "Use legacy paid Comissao divided by legacy Comissao months, then multiply by remaining months."

> **Dev:** "What should Finance use for monthly projection when real platform Comissao, legacy Comissao, and contractual potential all exist?"
> **Domain expert:** "Combine real legacy Comissao and real platform Comissao as a weighted average; use contractual monthly potential only when no real Comissao exists."

> **Dev:** "Should Finance cap the real weighted average at the policy's contractual monthly potential?"
> **Domain expert:** "No. MRR is also a forecast; real NF revenue can be higher and should drive the Finance forecast."

> **Dev:** "If a policy reaches 12 paid Comissao months, should later revenue still generate payment?"
> **Domain expert:** "No. Once a policy is fully paid, it should not generate future apuracao, Potencial a pagar, or projected cash flow."

> **Dev:** "If the twelfth Comissao month also has Agenciamento, do we pay the Agenciamento?"
> **Domain expert:** "Yes. Agenciamento is paid while the Comissao clock is still open; it just does not start or advance the clock."

> **Dev:** "How should the system treat policies that are already 12/12 before a month is processed?"
> **Domain expert:** "They should not enter any calculation, and policy views should make that fully-paid state visually explicit."

> **Dev:** "Should fully paid policies disappear from the Policies page?"
> **Domain expert:** "No. Keep them visible for history and audit, but exclude them from calculations and projections."

> **Dev:** "Is a cancelled policy the same thing as a fully paid policy?"
> **Domain expert:** "No. Fully paid means the 12-month commission clock completed; cancelled means payments stopped because the policy lifecycle was interrupted."

> **Dev:** "Do we need cancellation-date logic during apuracao?"
> **Domain expert:** "No. Cancellation happens before apuracao starts, so cancelled policies simply do not enter the calculation."

> **Dev:** "Should Finance's cash-flow projection reconcile to Potencial a pagar?"
> **Domain expert:** "Yes. The projected cash flow is the month-by-month distribution of Potencial a pagar."

> **Dev:** "If Q2 is apurado in July, should April, May, and June appear in July or in their own months?"
> **Domain expert:** "In their own months. They are projected until the quarterly apuracao is LOCKED, then become realized for those monthly competencies."

> **Dev:** "What should April-June show as in July before Q2 is LOCKED?"
> **Domain expert:** "A apurar. They already belong to past monthly competencies but are not realized until the quarterly apuracao is locked."

> **Dev:** "If NFs for an open quarter have already been imported, should A apurar use them or keep the forecast?"
> **Domain expert:** "Use the imported matched values. Forecast is only the fallback when no imported value exists yet."

> **Dev:** "Does A apurar add on top of Projetado?"
> **Domain expert:** "No. A apurar replaces Projetado for that policy-month when imported matched values exist."

> **Dev:** "Should an imported but not locked month recalibrate future projections?"
> **Domain expert:** "No. It replaces that month only; it enters the projection average after the quarterly apuracao is LOCKED."

> **Dev:** "Should an A apurar month with positive Comissao prevent projecting an extra thirteenth month?"
> **Domain expert:** "Yes. It reserves one clock month for projection, but only becomes an official paid month when LOCKED."

> **Dev:** "If an A apurar month only has Agenciamento, does it reserve a commission month?"
> **Domain expert:** "No. It is payable while the policy is open, but it does not start or reserve the Comissao clock."

> **Dev:** "Does pending imported Agenciamento enter Potencial a pagar?"
> **Domain expert:** "Yes, while it is A apurar. Future projected months do not include Agenciamento."

> **Dev:** "If a policy reaches 12/12 in April during a Q2 apuracao, can May or June still generate payment?"
> **Domain expert:** "No. Process months chronologically and stop eligibility after the month that completes 12/12."

> **Dev:** "Where should imported rows excluded by 12/12 appear?"
> **Domain expert:** "In a separate Apolices finalizadas review area, like unmatched lines, not inside the payable EV view."

> **Dev:** "If a policy completes 12/12 in April, what reason should May rows show?"
> **Domain expert:** "APOLICE_FINALIZADA, with context that the policy completed 12/12 in April."

## Flagged Ambiguities

- "tipo de receita" was previously treated inconsistently across calculation and finance views. Resolved: only **Comissao** and **Agenciamento** are **Receita comissionavel**.
