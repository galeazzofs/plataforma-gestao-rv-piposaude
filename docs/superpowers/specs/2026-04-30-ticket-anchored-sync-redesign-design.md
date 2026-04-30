# Sync ticket-anchored: 1 Policy por ticket de Placement

**Data:** 2026-04-30
**Status:** Draft (aguardando review)
**Escopo:** Backend — módulo `app.modules.hubspot_sync`, model `Policy`
**Substitui:** [`2026-04-30-pre-ativacao-filter-and-full-fetch-design.md`](./2026-04-30-pre-ativacao-filter-and-full-fetch-design.md) (não implementado)

## Objetivo

Reescrever o sync HubSpot para criar **uma row em `policies` por ticket de Placement** (em vez de uma por apólice). Mantém pré-ativação + full-fetch + delete-by-absence (do plano anterior descartado), mas vira tudo em torno do ticket. Operadora e número de apólice continuam vindo do deal de apólice associado, e a "data do gongo" passa a vir do `closedate` do deal default.

## Motivação

A cardinalidade per-apólice (introduzida em 2026-04-29) assumia que um ticket podia gerar múltiplas apólices (saúde + odonto). Na prática isso não acontece — cada ticket = 1 apólice. O modelo per-apólice gera duplicação visual em dashboards e complica agregações de MRR.

Adicionalmente, o `closed_date` mais "verdadeiro" para fins de comissão é o `closedate` do deal default (registra quando o gongo foi batido como negociação fechada), não o `closed_date` do ticket (que reflete quando o ticket de placement foi marcado como fechado — pode divergir).

## Critério de seleção (tickets)

Um ticket entra no sync se e somente se:

1. `hs_pipeline = "651307"` (Placement)
2. `hs_pipeline_stage = "11947921"` (Gongo)
3. `closed_date >= 2024-09-01`
4. `time_solicitante = "Vendas"` **(NOVO)**
5. Tem **≥1 deal associado de apólice** (`pipeline = "2453678"`) com:
   - `apolice___beneficio` ∈ {Saúde, Odonto, Vida, Saúde e Odonto}
   - `hs_v2_date_entered_14038792 >= 2024-09-01` (entrou em pré-ativação)
6. Tem **≥1 deal associado no pipeline default** (de onde sai o `closedate`)

Tickets que falham qualquer critério são pulados e contados em `summary["skipped"]`.

Premissa: **um ticket tem exatamente 1 apólice em pré-ativação**. Caso encontre ≥2, o sync loga warning e usa a primeira (estável: ordem retornada pela API).

## Mapeamento de campos

| Coluna Policy | Origem | Property HubSpot |
|---|---|---|
| `hubspot_ticket_id` | Ticket | (id do ticket) |
| `hubspot_apolice_id` | Deal de apólice em pré-ativação | (id do deal) |
| `numero_apolice` | Deal de apólice em pré-ativação | `numero_apolice` |
| `partner_operator` | Deal de apólice em pré-ativação | `parceiro` |
| `benefit_type` | Deal de apólice em pré-ativação | `apolice___beneficio` |
| `ev_id` | Ticket (resolvido via owner_map) | `solicitante_demanda` |
| `client_id` | Ticket (resolvido via Client.find_or_create) | `cliente___nome_da_empresa` |
| `mrr_projected` | Ticket | `mrr___receita_mensal` |
| `segment` | Ticket | `cotar___segmentacao_pipo` |
| `closed_date` | **Deal default** | `closedate` |

## Mudanças de schema

| Mudança | Coluna | Estado anterior | Estado novo |
|---|---|---|---|
| 🔄 altera | `hubspot_ticket_id` | NOT NULL, **não-único**, indexed | NOT NULL, **UNIQUE**, indexed |
| 🔄 altera | `hubspot_apolice_id` | NOT NULL, **UNIQUE**, indexed | **nullable**, **não-único**, indexed |

`hubspot_apolice_id` vira nullable: o ticket é a identidade do row, e a apólice é metadata secundário. Em produção o sync sempre seta (skip-until-pré-ativação garante isso), mas testes/manual edits podem criar Policy sem apolice — não faz sentido bloquear isso na constraint.

### Migração Alembic

Faz wipe + schema swap atomicamente:

```python
def upgrade():
    # Wipe (children primeiro pra respeitar FK)
    op.execute("DELETE FROM commissions")
    op.execute("DELETE FROM ev_validations")
    op.execute("UPDATE financial_imports SET policy_id = NULL WHERE policy_id IS NOT NULL")
    op.execute("DELETE FROM policies")

    # Cleanup do cursor incremental obsoleto (do desenho 2026-04-29)
    op.execute("DELETE FROM platform_settings WHERE key = 'hubspot_sync_last_success_at'")

    # Swap UNIQUE: drop em apolice_id, cria em ticket_id
    op.drop_index("ix_policies_hubspot_apolice_id", table_name="policies")
    op.create_index("ix_policies_hubspot_apolice_id", "policies", ["hubspot_apolice_id"])
    op.drop_index("ix_policies_hubspot_ticket_id", table_name="policies")
    op.create_index("ix_policies_hubspot_ticket_id", "policies", ["hubspot_ticket_id"], unique=True)


def downgrade():
    pass  # destrutivo por design
```

(Nomes exatos dos índices precisam ser verificados na migração 2026-04-29 — o conteúdo conceitual é "swap o unique constraint".)

## Constantes em `sync.py`

```python
APOLICE_PIPELINE_ID = "2453678"
PLACEMENT_PIPELINE_ID = "651307"
GONGO_STAGE_ID = "11947921"
PRE_ATIVACAO_STAGE_ID = "14038792"
DEFAULT_DEAL_PIPELINE_ID = "default"
GONGO_DATE_FLOOR = date(2024, 9, 1)
PRE_ATIVACAO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]
TIME_SOLICITANTE_VENDAS = "Vendas"

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
    "time_solicitante",
]
DEAL_PROPERTIES = [
    "pipeline",
    "apolice___beneficio", "numero_apolice", "parceiro",
    "hs_v2_date_entered_14038792",
    "closedate",
]
```

## Fluxo

### `_fetch_tickets(client)` — full-fetch sempre

```python
filters = [
    {"propertyName": "hs_pipeline",       "operator": "EQ",  "value": PLACEMENT_PIPELINE_ID},
    {"propertyName": "hs_pipeline_stage", "operator": "EQ",  "value": GONGO_STAGE_ID},
    {"propertyName": "closed_date",       "operator": "GTE", "value": GONGO_DATE_FLOOR.isoformat()},
    {"propertyName": "time_solicitante",  "operator": "EQ",  "value": TIME_SOLICITANTE_VENDAS},
]
```

### `_resolve_ticket_deals(client, tickets, summary)` — substitui `_resolve_ticket_apolices`

Para cada ticket, identifica e retorna **um par** `(apolice, default_deal)`. Skips:
- `summary["skipped"]["no_apolice_pre_ativacao"]` — sem apólice em pré-ativação
- `summary["skipped"]["no_default_deal"]` — sem deal default
- `summary["skipped"]["multiple_apolices"]` — mais de 1 apólice em pré-ativação (warning, usa a primeira; conta mas não pula)

Retorna `dict[ticket_id, {"apolice": dict, "default_deal": dict}]`.

### `_upsert_policy(ticket_id, ticket_props, apolice, default_deal, owner_map, ev_lookup, ...)` — chave por ticket

- Lookup: `Policy.query.filter_by(hubspot_ticket_id=ticket_id).first()`
- Não-lockáveis (sempre atualiza):
  - `hubspot_apolice_id`, `numero_apolice`, `partner_operator`, `benefit_type`, `mrr_projected`
- Lockáveis (só se não locked):
  - `ev_id`, `client_id`, `segment`
  - `closed_date` ← **`parse_date(default_deal["properties"]["closedate"])`**

### `_delete_absent_policies(seen_ticket_ids, summary)`

Mesma lógica do plano descartado, mas chave por `hubspot_ticket_id`:

```python
absent = Policy.query.filter(
    Policy.hubspot_ticket_id.notin_(list(seen_ticket_ids))
).all()
```

Cascade idêntico (commissions/ev_validations DELETE; financial_imports SET NULL). Guarda contra wipe acidental quando `seen_ticket_ids` está vazio mas DB tem rows.

### Summary

```python
{
    "timestamp": None,
    "created": 0,
    "updated": 0,
    "deleted": 0,
    "skipped": {
        "no_apolice_pre_ativacao": 0,
        "no_default_deal": 0,
        "multiple_apolices": 0,    # contagem de tickets com >1 apólice (warning)
        "no_active_ev": 0,
    },
    "errors": [],
    "error_count": 0,
}
```

## Riscos e mitigações

**Múltiplas apólices em pré-ativação no mesmo ticket** — premissa do usuário é que não acontece. Se acontecer, o sync usa a primeira (ordem da API HubSpot, normalmente por id) e loga `summary["skipped"]["multiple_apolices"] += 1`. Não bloqueia o sync mas dá visibilidade.

**`closedate` ausente no deal default** — a row é criada com `closed_date = None`, e `commissions/calculator.py` já pula policies sem `closed_date`. Comportamento aceitável (operador resolve manualmente via lock + edit).

**`time_solicitante` ausente em tickets antigos** — tickets que não têm a property setada não passam o filtro. Premissa: tickets de Vendas têm essa property preenchida. Se não, eles ficam fora do sync (e do delete-by-absence consegue removê-los caso já tenham row criada antes).

**Filtro de pré-ativação implicitamente retroativo** — apólices que entraram em pré-ativação no passado e voltaram pra etapa anterior continuam tendo `hs_v2_date_entered_14038792` preenchido. Comportamento aceitável (once-passed-always-passed) — explicitado no spec original 2026-04-30.

## Testes

Reescrever `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py` e `test_sync_integration.py` para refletir o novo modelo:

**`_fetch_tickets`:**
- Filtros incluem `time_solicitante = "Vendas"`.
- Sem cursor incremental (full-fetch).

**`_resolve_ticket_deals`:**
- Ticket com 1 apólice em pré-ativação + 1 deal default → incluído.
- Apólice sem `hs_v2_date_entered_14038792` → skip + counter.
- Apólice com data antes do floor → skip + counter.
- Sem deal default → skip.
- ≥2 apólices em pré-ativação → primeira usada, counter incrementado, ticket incluído.

**`_upsert_policy`:**
- 1 row por ticket (lookup por `hubspot_ticket_id`).
- `closed_date` populado do `closedate` do deal default.
- `hubspot_apolice_id`, `numero_apolice`, `parceiro`, `benefit_type` do deal de apólice.
- Idempotente: rodar 2× não duplica.
- Lock preserva campos lockáveis incluindo `closed_date`.

**`_delete_absent_policies`:**
- Mesmo set de testes do plano descartado, mas chave por `hubspot_ticket_id`.

**Integração E2E:**
- Sync completo cria 1 row por ticket válido.
- Tickets velhos (sem apólice em pré-ativação) são pulados.
- Sync subsequente dropa tickets que sumiram do HubSpot.

## Fora de escopo

- **Backfill histórico de `closed_date`**: o wipe descarta tudo. Sync popula do zero a partir do deal default.
- **Mudanças em commission calculation**: `calculator.py` já lê `policy.closed_date` — só vai consumir o valor novo automaticamente.
- **Frontend**: pode haver código que assumia múltiplas rows por ticket (agregações com DISTINCT). Auditoria em PR separado se aparecer regressão.
- **Drop de colunas mortas** (`deal_id`, `deal_stage`, `deploy_date`, `first_payment_prev`, `mrr_post_deploy`): adiar pra outro PR.

## Sequência de implementação

1. Atualizar `Policy` model (UNIQUE swap).
2. Migração Alembic (wipe + schema + cleanup do cursor).
3. Reescrever `sync.py` (constantes, `_fetch_tickets` com filtro novo, `_resolve_ticket_deals`, `_upsert_policy` por ticket, `_delete_absent_policies`).
4. Reescrever `test_sync_phases.py` e `test_sync_integration.py`.
5. Rodar suíte completa e ajustar regressões em outros módulos (matcher/calculator).
