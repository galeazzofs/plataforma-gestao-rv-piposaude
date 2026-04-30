# Filtro de Pré-ativação + sync full-fetch com delete-by-absence

**Data:** 2026-04-30
**Status:** Draft (aguardando review)
**Escopo:** Backend — módulo `app.modules.hubspot_sync`

## Objetivo

Restringir o sync de apólices para incluir **apenas** apólices cujo deal_stage tenha entrado na etapa "Pré-ativação" (HubSpot stage `14038792`) em ou após 2024-09-01. Adicionalmente, abandonar o sync incremental (cursor por `hs_lastmodifieddate` no ticket) em favor de full-fetch, e adicionar lógica de delete-by-absence para que `policies` reflita 1:1 o estado atual do HubSpot.

## Motivação

Hoje o sync entrega à plataforma apólices que ainda estão em estágios iniciais (cotação, draft) do pipeline de Apólices. Isso polui dashboards e contagens de comissão. A regra de negócio é: apólice só é "real" para a plataforma a partir do momento em que entra na etapa de Pré-ativação.

Adicionalmente, o sync incremental atual não pega:
- Mudanças no estágio do deal de apólice (não bate `lastmodifieddate` no ticket).
- Tickets que saem de Gongo ("dado como perdido", reaberto, etc.) — esses ficam stale na plataforma.

Full-fetch + delete-by-absence resolvem os dois.

## Critério de seleção (apólices)

Uma apólice (deal no pipeline `2453678`) é incluída no sync se e somente se, **adicionalmente** aos critérios já existentes (definidos em `2026-04-29-policy-sync-from-apolices-pipeline-design.md`):

4. `hs_v2_date_entered_14038792` está preenchido **e** representa uma data ≥ 2024-09-01.

Apólices que falham esse critério são puladas e contadas em `summary["skipped"]["not_pre_activation"]`.

## Mudanças no `sync.py`

### Constantes novas

```python
PRE_ATIVACAO_STAGE_ID = "14038792"
PRE_ATIVACAO_DATE_FLOOR = date(2024, 9, 1)
```

### `DEAL_PROPERTIES`

Adicionar `"hs_v2_date_entered_14038792"` à lista — assim a propriedade é puxada no mesmo `batch_read_objects` existente, sem round-trip extra.

### `_resolve_ticket_apolices`

No loop sobre `deals_for_ticket`, ao identificar um deal no pipeline de apólices com benefício válido, aplicar o filtro adicional:

```python
entered = parse_date(props.get("hs_v2_date_entered_14038792"))
if entered is None or entered < PRE_ATIVACAO_DATE_FLOOR:
    summary["skipped"]["not_pre_activation"] += 1
    continue
apolices.append({"id": d, "properties": props})
```

A apólice só é adicionada ao output se passar todos os filtros.

### `_fetch_tickets` — remover cursor incremental

- Eliminar o parâmetro `since`.
- Eliminar o filtro `hs_lastmodifieddate >= since` da lista de `filters`.
- Eliminar log "incremental since X" — sempre full-fetch.

### `run_sync` — remover cursor

- Eliminar leitura de `last_success = PlatformSetting.get(LAST_SUCCESS_KEY)`.
- Eliminar a escrita do cursor no final (`PlatformSetting.set(LAST_SUCCESS_KEY, ...)`).
- Eliminar a constante `LAST_SUCCESS_KEY` do módulo.

### Nova função `_delete_absent_policies`

```python
def _delete_absent_policies(seen_apolice_ids: set[str], summary: dict) -> None:
    """Deleta policies cujo hubspot_apolice_id não apareceu nesta sync.

    Cascade aplicado:
    - DELETE FROM commissions WHERE policy_id IN (...)
    - DELETE FROM ev_validations WHERE policy_id IN (...)
    - UPDATE financial_imports SET policy_id = NULL WHERE policy_id IN (...)
    - DELETE FROM policies WHERE id IN (...)

    Inclui locked policies — lock protege contra overwrite de campos durante
    upsert, mas não impede deleção quando a fonte sumiu.

    Atualiza summary["deleted"].
    """
```

Operação roda em uma transação. Resolve as policies absentes via uma query única:

```python
absent = Policy.query.filter(
    Policy.hubspot_apolice_id.notin_(list(seen_apolice_ids))
).all()
```

**Guarda contra wipe acidental:** se `seen_apolice_ids` estiver vazio mas existirem policies em DB, abortar o delete e logar `error`. Cenário típico: HubSpot retornou zero resultados sem levantar exception (mudança silenciosa de pipeline, token expirado retornando 200 vazio, etc.). Nesse caso é mais seguro deixar os dados antigos do que arriscar wipe completo. Adicionar entrada em `summary["errors"]` para sinalizar a inconsistência.

```python
if not seen_apolice_ids and Policy.query.count() > 0:
    summary["errors"].append(
        "Delete-by-absence abortado: fetch retornou zero apólices mas DB não está vazio"
    )
    summary["error_count"] = len(summary["errors"])
    return
```

### Orquestração em `run_sync`

Logo antes do `_persist_last_sync`, adicionar:

```python
if summary["error_count"] == 0:
    seen = {
        a["id"] for apolices in ticket_to_apolices.values()
        for a in apolices
    }
    _delete_absent_policies(seen, summary)
    db.session.commit()
```

Importante: o set `seen` reflete apólices que **passaram** todos os filtros (incluindo pré-ativação). Apólices skipped não estão no set — então policies em DB com `hubspot_apolice_id` que agora falham o filtro **serão deletadas**. Esse é o comportamento desejado para integrar o filtro novo retroativamente.

### Summary

```python
def _new_summary():
    return {
        "timestamp": None,
        "created": 0,
        "updated": 0,
        "deleted": 0,                            # NOVO
        "skipped": {
            "no_default_deal": 0,
            "no_apolice": 0,
            "no_active_ev": 0,
            "not_pre_activation": 0,             # NOVO
        },
        "errors": [],
        "error_count": 0,
    }
```

`_persist_last_sync` adiciona persistência de `hubspot_last_sync_deleted = summary["deleted"]`.

### Logging

```python
logger.info(
    f"Delete-by-absence: {summary['deleted']} policies removidas "
    f"(commissions/ev_validations cascateadas, financial_imports unlinked)"
)
```

Se `summary["deleted"] > 0.5 * total_existing_before`, emitir `logger.warning(...)` com a proporção. Sem bloqueio automático.

## Migração Alembic — wipe one-time

Arquivo: `backend/migrations/versions/XXXX_reset_for_pre_activation_filter.py`

```python
def upgrade():
    op.execute("DELETE FROM commissions;")
    op.execute("DELETE FROM ev_validations;")
    op.execute("UPDATE financial_imports SET policy_id = NULL;")
    op.execute("DELETE FROM policies;")
    op.execute(
        "DELETE FROM platform_settings WHERE key = 'hubspot_sync_last_success_at';"
    )

def downgrade():
    pass  # destrutiva por design — igual à 2026-04-29
```

Sem schema changes. Sem alteração no `reset_sync.sql` (que continua só resetando o status de lock).

Após deploy, primeiro sync popula `policies` zerada com apólices que passem o filtro novo.

## Testes

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`:

**Filtro pré-ativação:**
- `test_resolve_ticket_apolices_includes_apolice_past_pre_activation` — `hs_v2_date_entered_14038792 = "2025-01-15"` → incluída.
- `test_resolve_ticket_apolices_skips_apolice_without_pre_activation_date` — propriedade ausente → `skipped["not_pre_activation"] += 1`.
- `test_resolve_ticket_apolices_skips_apolice_with_pre_activation_before_floor` — `hs_v2_date_entered_14038792 = "2024-08-15"` → `skipped["not_pre_activation"] += 1`.

**Full-fetch:**
- `test_fetch_tickets_full_fetch_only` — confirma que `_fetch_tickets()` (sem args) gera 3 filtros (pipeline, stage, closed_date) — sem `hs_lastmodifieddate`.
- Remover testes legados: `test_fetch_tickets_adds_modified_since_filter_when_incremental`, `test_fetch_tickets_normalizes_datetime_since_to_iso`.

**Delete-by-absence (novo arquivo de teste ou append em `test_sync_phases.py`):**
- `test_delete_absent_policies_removes_policies_not_in_fetch` — 3 policies em DB, sync vê 2, a terceira é deletada.
- `test_delete_absent_policies_no_op_when_all_seen` — sync vê todas, nada é deletado.
- `test_delete_absent_policies_cascades_commissions` — policy a deletar tem 1 commission; ambas somem.
- `test_delete_absent_policies_cascades_ev_validations` — idem para ev_validations.
- `test_delete_absent_policies_nulls_financial_imports` — `financial_imports.policy_id` vai a NULL.
- `test_delete_absent_policies_deletes_locked_rows` — locked row é deletada normalmente.
- `test_delete_absent_policies_skipped_when_errors` — `summary["error_count"] > 0` → função não é chamada (verificado em integration test).
- `test_delete_absent_policies_aborts_when_seen_empty_but_db_nonempty` — guarda contra wipe: nada é deletado, erro é adicionado ao summary.

Em `test_sync_integration.py`: atualizar o flow ponta-a-ponta para incluir o filtro novo e a fase de delete.

## Riscos e mitigações

**Falsos positivos no delete-by-absence:**
- Risco: HubSpot retorna parcialmente (ex: rate limit + retries esgotaram pra alguns tickets) e a sync conclui sem erro mas com dados incompletos → policies legítimas seriam deletadas.
- Mitigação: a sync já trata exceptions no fetch e marca `error_count > 0`. O delete só roda se `error_count == 0`. Erros silenciosos em paginação seriam o caminho de risco — `_request` faz `raise_for_status` e re-raise após 3 retries, então erros HTTP devem propagar.

**Custo de full-fetch:**
- Risco: cada sync agora pega todos os tickets em Gongo desde 2024-09-01 (centenas a milhares) e seus deals/associações.
- Mitigação: HubSpot batch APIs (`batch_read_associations`, `batch_read_objects`) já são usadas; full-fetch deve ser ~30-50 chamadas com paginação. Aceitável pra agendamento (atual scheduler).

**Apólice volta de Pré-ativação para etapa anterior:**
- Risco: deal entra em Pré-ativação (data setada), depois é movido pra trás → `hs_v2_date_entered_14038792` permanece preenchida, sync continua incluindo.
- Mitigação: comportamento aceitável — once-passed-always-passed é a regra explícita do filtro. Se o negócio precisar refletir movimento de volta, é outra mudança de spec.

## Resumo dos arquivos a tocar

| Arquivo | Mudança |
|---|---|
| `backend/app/modules/hubspot_sync/sync.py` | Constantes novas, filtro em `_resolve_ticket_apolices`, full-fetch em `_fetch_tickets`, nova `_delete_absent_policies`, summary expandido, orquestração em `run_sync` |
| `backend/migrations/versions/XXXX_reset_for_pre_activation_filter.py` | Wipe one-time |
| `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py` | Testes novos do filtro + delete-by-absence; remover testes incrementais |
| `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py` | Atualizar flow E2E |

## Decisões registradas

- Locked rows são deletadas pelo delete-by-absence (não há fonte para mantê-las).
- Sem warning bloqueante em volume alto de deleção — só log.
- Floor de pré-ativação reusa a mesma data do `GONGO_DATE_FLOOR` (2024-09-01), mas mantido como constante separada (`PRE_ATIVACAO_DATE_FLOOR`) para permitir tuning independente.
- Migração de wipe é destrutiva por design; downgrade é no-op.
