# Conferência EV por EV na Apuração Mensal — Design

**Data:** 2026-07-07
**Status:** Aprovado (design validado em sessão de brainstorming)

## Problema

A Apuração EV é uma entidade única por mês: o cálculo roda para todos os EVs
de uma vez e a revisão é uma página única com todos os EVs. RevOps precisa de
um fluxo de trabalho incremental: conferir EV por EV, ir fechando cada um, e
só liberar a apuração para a validação dos EVs quando todos estiverem
conferidos — sem perder o trabalho de conferência quando um recálculo é
necessário no meio do caminho.

## Decisões de produto (registro)

| Pergunta | Decisão |
|---|---|
| O que é "fechar um EV"? | Conferência interna do RevOps — o state machine global não muda |
| "Calcular 1 por 1"? | Recalc por EV na UI; por baixo, recálculo global + fingerprint que preserva conferências de quem não mudou (abordagem A) |
| Quem aparece na lista? | Todos os EVs ativos (incl. sem movimento no mês) + desligados com comissão |
| Gate na liberação? | Trava dura: "Liberar para EVs" só com 100% conferido (server-side) |
| Onde vive a UI? | Página de revisão atual turbinada (aba Por EV) — sem página nova |

### Por que recálculo global e não escopado por EV

A fórmula é `Comissão = (Total NF do cliente − Perks do cliente) × %`,
rateada proporcionalmente entre as apólices do cliente — e apólices do mesmo
cliente podem pertencer a EVs diferentes. Um recálculo escopado a um EV
deixaria o rateio de perk do outro EV obsoleto no banco, e o LOCK travaria
número errado. O recálculo é sempre global (rápido — um mês de NFs,
síncrono); a proteção do trabalho de conferência vem do fingerprint, não do
escopo do cálculo.

## Arquitetura

Nenhuma mudança no state machine global
(`DRAFT → CALCULATING → VALIDATING → LIDER_REVIEW → REVOPS_REVIEW → LOCKED`).
A conferência é uma camada de trabalho dentro do **CALCULATING**:

1. RevOps roda o cálculo (como hoje).
2. Confere EV por EV na aba Por EV da revisão; pode recalcular no meio —
   conferências de EVs cujos valores não mudaram sobrevivem.
3. `CALCULATING → VALIDATING` ("Liberar para EVs") é bloqueado no chokepoint
   do state machine enquanto houver EV do escopo sem conferência.
4. Do VALIDATING em diante, tudo segue como hoje; os registros de conferência
   viram histórico read-only.

Nomenclatura: código em inglês, UI em português (padrão do repo —
`EvValidation` = validação). Entidade: **`EvSignoff`**; termo de UI:
**"conferência" / "conferido"**.

## Modelo de dados

Tabela nova `ev_signoffs` (uma migration Alembic, aditiva):

| campo | tipo | nota |
|---|---|---|
| id | GUID PK | |
| appraisal_id | GUID FK `appraisals.id`, not null | `UniqueConstraint(appraisal_id, ev_id)` |
| ev_id | GUID FK `users.id`, not null | |
| status | enum `SignoffStatus` {`PENDING`, `DONE`} | default `PENDING` |
| fingerprint | String, nullable | sha256 dos valores no momento da conferência |
| values_changed | Boolean, default false | true quando um recálculo invalidou a conferência |
| signed_off_by | GUID FK `users.id`, nullable | |
| signed_off_at | DateTime(timezone), nullable | |
| created_at | DateTime(timezone) | |

Modelo em `backend/app/models/ev_signoff.py`, exportado em
`app/models/__init__.py`.

### Fingerprint

`sha256` do JSON canônico (`sort_keys`, sem espaços) da lista ordenada por
`policy_id` de tuplas `(policy_id, total_actual, commission_pct,
achievement_pct)` das rows de `Commission` do EV em `(month, year)`. Campos
`Decimal` serializados como string normalizada (`str(Decimal)`), nunca float —
o hash precisa ser estável entre runs idênticos. EV sem movimento → hash da
lista vazia (estável entre recálculos até o EV ganhar comissão). Fonte: banco
(`Commission`), não o payload — uma única fonte de verdade.

### Escopo da conferência

```
scope(month, year) =
    {EVs com User.role == EV, active == true, left_company == false}
  ∪ {ev_id de qualquer Commission em (month, year)}
```

- EV desligado com comissão no mês: entra (RevOps confere por ele — coerente
  com o auto-approve de validação de desligados).
- EV ativo sem movimento: entra, aparece zerado, e a conferência dele é o
  registro explícito de "sem movimento este mês".
- EV desativado sem comissão: sai do escopo sozinho (escopo é recomputado a
  cada checagem, nunca congelado).
- Linhas `ev_signoffs` fora do escopo atual são ignoradas pelo gate (ficam
  como histórico; não são apagadas).

### Ciclo de vida das linhas

`_ensure_ev_signoffs(appraisal)` cria linhas `PENDING` que faltam para o
escopo. Chamada: (a) na transição para CALCULATING, logo após
`run_monthly_appraisal`; (b) no endpoint de recalculate, após o cálculo;
(c) defensivamente no endpoint de confer. EV contratado depois do cálculo
aparece no próximo recálculo e bloqueia o gate até ser conferido.

## Backend

### Endpoints (blueprint `workflow_bp`)

- `POST /api/v1/appraisals/<id>/signoffs/<ev_id>` — marca conferido.
  - `require_role(ADMIN)`.
  - 409 `INVALID_STATE` se `appraisal.status != CALCULATING`.
  - 400 se `ev_id` fora do escopo atual.
  - Idempotente: já `DONE` → 200 sem efeito.
  - Efeitos: `status=DONE`, `fingerprint=computado agora`,
    `values_changed=false`, `signed_off_by/at`, audit log
    (`table_name="ev_signoffs"`, action `CREATE`/`UPDATE` com old/new values).
  - Resposta: `{"data": {"ev_id": …, "signoff": {…}, "signoff_totals": {…}}}`
    (delta — o frontend atualiza o app-db em lugar, sem refetch do detail).
- `DELETE /api/v1/appraisals/<id>/signoffs/<ev_id>` — reabre (volta a
  `PENDING`, limpa fingerprint/by/at). Mesmas regras de role/estado.
  Idempotente.

### Gate no state machine

Em `transition_appraisal` (chokepoint, mesmo padrão de
`_assert_no_open_contestation`):

```python
def _assert_signoffs_complete(appraisal, new_status):
    # só guarda a liberação CALCULATING → VALIDATING
    if new_status != AppraisalStatus.VALIDATING:
        return
    if appraisal.status != AppraisalStatus.CALCULATING:
        return
    pending = _pending_signoff_evs(appraisal)   # escopo − DONE
    if pending:
        raise InvalidTransitionError(
            f"{len(pending)} EV(s) sem conferência: {nomes…}"
        )
```

Confirmado em `VALID_TRANSITIONS`: o único caminho para VALIDATING é a partir
de CALCULATING, então o gate cobre todas as liberações. A resolução de
contestação (que volta a VALIDATING por escrita direta de status) não passa —
correto: a conferência já aconteceu naquele ciclo. As voltas
`LIDER_REVIEW/REVOPS_REVIEW → CALCULATING` re-armam o gate na próxima
liberação; os fingerprints preservam as conferências de quem não mudou.

### Hook pós-recálculo

`refresh_signoffs_after_recalc(appraisal) -> {"invalidated": [nomes], "kept": n}`

Chamado logo após `run_monthly_appraisal` nos dois call sites (transição para
CALCULATING no state machine; endpoint `POST /appraisals/<id>/recalculate`):

1. `_ensure_ev_signoffs(appraisal)` (novos EVs do escopo).
2. Para cada linha `DONE`: re-hasheia; se o fingerprint mudou →
   `status=PENDING`, `values_changed=true`, limpa `signed_off_by/at`
   (audit log da invalidação).
3. Retorno vai na resposta do recalculate (campo `signoffs`) para o toast.

O recalculate continua permitido em VALIDATING/LIDER_REVIEW/REVOPS_REVIEW
(como hoje); nesses estados o hook ainda roda e marca `values_changed`
(informativo — o gate já passou, a UI mostra o aviso na revisão).

### Payload do detail (`_serialize_appraisal(detail=True)`)

- Cada bloco de `ev_summary` ganha:
  `"signoff": {"status", "signed_off_by_name", "signed_off_at", "values_changed"}`
  (null quando a apuração está em DRAFT / linha inexistente).
- `ev_summary` passa a incluir os EVs ativos sem movimento — blocos zerados
  com `"no_movement": true`, `policies: []`. Injetado em
  `_build_appraisal_detail` (detail da apuração), **não** em
  `_build_period_detail` — o preview (`POST /appraisals/preview`) não muda.
- Top-level: `"signoff_totals": {"total", "done", "all_done"}` (total =
  tamanho do escopo).
- Visão escopada do líder (`_scope_detail_payload`): blocos de signoff passam
  read-only; `signoff_totals` recalculado sobre os EVs visíveis; EVs sem
  movimento do time aparecem.

### Agregador do ciclo mensal

`_ev_apuracao_status` (cycle_aggregator) ganha `signoffs_total` /
`signoffs_done` quando a apuração está em CALCULATING, para o trilho mostrar
"X/Y EVs conferidos". O botão inline "Liberar para validação" do trilho
continua existindo — se clicado antes de 100%, o servidor responde 422 e o
trilho mostra o erro (comportamento já existente para erros de transição).

### Delete da apuração

`DELETE /appraisals/<id>` passa a apagar `ev_signoffs` da apuração antes do
delete (mesmo padrão das `ev_validations`).

## Frontend

Tudo em `appraisal_review.cljs` + eventos/subs re-frame + CSS
(`pipo-design.css`). Sem página nova, sem rota nova.

Na aba **Por EV**, quando `status == CALCULATING` (e usuário ADMIN):

- **Banda de progresso da conferência** acima da lista: "Conferência: 12 de
  18 EVs" + barra + chips de filtro [Pendentes | Conferidos | Todos].
  Ordenação: pendentes primeiro, depois alfabético.
- **Linha do EV** (header): badge de conferência —
  `⏳ Conferência pendente` (status `PENDING`) /
  `✓ Conferido por {nome} em {DD/MM}` (status `DONE`) /
  `⚠ Valores mudaram` (status `PENDING` com `values_changed=true` — substitui
  o ⏳; não é um terceiro status no banco).
- **EVs sem movimento**: linha zerada com meta "sem movimento no mês";
  conferível como qualquer outro.
- **Painel expandido do EV**: botões
  - "Marcar como conferido" (primário; visível quando `PENDING`),
  - "Reabrir conferência" (ghost; quando `DONE`),
  - "Recalcular" (secundário; dispara o `:revops/recalculate-appraisal`
    existente — o toast de sucesso lista `signoffs.invalidated` quando não
    vazio: "Recalculado. Conferências invalidadas: Fulano, Beltrano").
- **Header "Liberar para EVs"**: desabilitado até `all_done`, com subtítulo
  "faltam N conferências". (Servidor também bloqueia — defesa em
  profundidade.)
- Em VALIDATING+ : badges de conferência viram histórico read-only (sem
  botões). Líder vê badges read-only na visão escopada.

Eventos novos: `:revops/signoff-ev` (POST), `:revops/reopen-signoff`
(DELETE) — on-success fazem merge do delta (`signoff` + `signoff_totals`) no
appraisal do app-db, sem refetch pesado.

## Edge cases

- **Confer duplo-clique / repetido**: idempotente (200, sem efeito).
- **Confer fora de CALCULATING**: 409.
- **EV contratado após o cálculo**: entra no escopo no próximo recálculo →
  linha PENDING → gate bloqueia até conferir.
- **EV desativado no meio da conferência**: sem comissão, sai do escopo no
  próximo check do gate; a linha órfã fica como histórico e é ignorada.
- **Recálculo que não muda nada**: fingerprints iguais → zero invalidação.
- **Recálculo que muda cliente compartilhado**: invalida os signoffs de
  TODOS os EVs afetados (é exatamente o caso que o design existe para pegar).
- **Apurações em CALCULATING criadas antes da feature**: ganham linhas no
  próximo recálculo ou no primeiro confer (ensure defensivo); o gate passa a
  valer imediatamente para elas (desejado).
- **Preview**: intocado (sem signoffs).

## Testes

Backend (`backend/tests/test_api/test_ev_signoffs.py` + ajustes em
`test_appraisal_review.py`), padrão do conftest (Postgres, savepoints):

1. Fluxo feliz: CALCULATING cria linhas do escopo (ativos + sem movimento +
   desligado com comissão); transição VALIDATING → 422 com pendentes; confere
   todos → 200.
2. Confer/reopen: idempotência, 409 fora de CALCULATING, 400 fora do escopo,
   403 para não-ADMIN (líder/EV), audit log gravado.
3. Fingerprint: (a) recalc sem mudança preserva DONE; (b) mudança de
   atingimento do EV A invalida só A; (c) NF nova em cliente compartilhado
   por A e B invalida ambos; (d) `values_changed` setado e limpo no próximo
   confer.
4. Escopo: EV inativo sem comissão fora do gate; zero-movement dentro;
   linha órfã ignorada.
5. Payload: `signoff` por EV, `signoff_totals`, `no_movement`, visão do líder
   escopada, preview sem signoffs.
6. Delete da apuração remove signoffs.
7. Ciclo: `_ev_apuracao_status` expõe contadores.

Frontend (`frontend/test/app/views/revops/appraisal_review_test.cljs`,
karma): funções puras — cálculo de progresso, ordenação pendentes-primeiro,
seleção de badge, lógica de habilitação do "Liberar para EVs".

## Fora de escopo (explícito)

- Mudanças no state machine global, nas validações dos EVs, no fluxo do
  líder, em Slack, ou no preview.
- Recálculo verdadeiramente escopado por EV (rejeitado — ver "Por que
  recálculo global").
- Página/rota nova de conferência (rejeitado em decisão de produto).
- Notas/comentários na conferência (YAGNI; audit log cobre o rastro).
