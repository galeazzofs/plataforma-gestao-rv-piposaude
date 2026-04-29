# Policy sync a partir do pipeline de Apólices

**Data:** 2026-04-29
**Status:** Draft (aguardando review)
**Escopo:** Backend — módulo `app.modules.hubspot_sync`

## Objetivo

Substituir a lógica atual de sync de policies — que parte de **tickets** no pipeline Placement em estágio Gongo e cria 1 row em `policies` por ticket — por uma lógica que parte de **apólices** (deals no pipeline `2453678`) e cria 1 row em `policies` por apólice.

A motivação é alinhar o modelo de dados ao HubSpot real, onde uma negociação ganha (gongo) pode resultar em múltiplas apólices distintas (uma por benefício / operadora) e cada apólice precisa ser apurada individualmente contra a planilha de faturamento via `numero_apolice`.

## Critérios de seleção

Uma apólice (deal no pipeline `2453678`) entra no sync se e somente se:

1. `apolice___beneficio` ∈ {`Saúde`, `Odonto`, `Vida`, `Saúde e Odonto`} (case-insensitive, com/sem acento).
2. Tem **pelo menos um ticket associado** com:
   - `hs_pipeline = "651307"` (Placement)
   - `hs_pipeline_stage = "11947921"` (Gongo)
   - `closed_date >= 2024-09-01`
3. Esse ticket tem **pelo menos um deal associado no pipeline default** (apenas validação de existência — não puxa dados desse deal).

Apólices que falham qualquer critério são puladas e logadas (warn level com motivo). Erros isolados em uma apólice não interrompem o lote.

## Mudanças de schema

Tabela `policies`:

| Mudança | Coluna | Tipo | Notas |
|---|---|---|---|
| ➕ adiciona | `hubspot_apolice_id` | `String(100)` UNIQUE NOT NULL, indexed | Chave HubSpot nova; ID do deal de apólice |
| ➕ adiciona | `numero_apolice` | `String(100)` nullable, indexed | Bate com a planilha de faturamento |
| 🔄 altera | `hubspot_ticket_id` | mantém NOT NULL, **perde UNIQUE**, mantém index | Vários rows podem compartilhar |
| 🔄 altera | `partner_operator` | sem mudança de tipo | Passa a ser populado pelo sync (de `parceiro` da apólice) |

Enum `BenefitType`:

| Mudança | Valor | Notas |
|---|---|---|
| ➕ adiciona | `SAUDE_ODONTO` | Para apólices conjugadas Saúde + Odonto (1 row, MRR inteiro) |

Colunas mantidas (sem mudança de definição) que **deixam de ser populadas pelo sync**:

- `deploy_date`, `first_payment_prev`, `mrr_post_deploy`, `deal_stage`

Decisão: **não dropar** essas colunas neste spec — pode haver dependências em commission calculation / dashboards que precisam ser auditadas separadamente. Ficam nullable e o sync simplesmente para de escrever nelas.

### Migrações Alembic

Faremos **uma única migração** combinando wipe + schema, na ordem abaixo (operações atômicas dentro do mesmo upgrade), pra evitar a janela transitória onde `hubspot_apolice_id` precisaria ser NOT NULL com rows existentes ainda na tabela:

1. `DELETE FROM commissions;` (respeita FK).
2. `DELETE FROM policies;`
3. ALTER TYPE `benefit_type` ADD VALUE `'SAUDE_ODONTO'` (Postgres). **Nota:** em Postgres, `ALTER TYPE ... ADD VALUE` não pode rodar dentro de transação. Alembic precisa de `op.execute(...)` com `connection.execution_options(isolation_level="AUTOCOMMIT")` ou separar essa instrução em um passo dedicado.
4. ADD COLUMN `hubspot_apolice_id String(100) NOT NULL` (sem default — tabela vazia, NOT NULL é seguro).
5. ADD COLUMN `numero_apolice String(100)` nullable.
6. CREATE UNIQUE INDEX em `hubspot_apolice_id`.
7. DROP UNIQUE constraint em `hubspot_ticket_id` (mantém index regular).

Downgrade: reverte 7→6→5→4. Não recupera dados (wipe é destrutivo). O passo 3 (enum) não tem downgrade limpo em Postgres — aceitar como migração one-way nesse aspecto.

Fora da migração: o arquivo `reset_sync.sql` (untracked) continua válido — só reseta o status do sync. Sem mudança nele.

## Novos métodos no `HubSpotClient`

Adicionar em `backend/app/modules/hubspot_sync/client.py`:

```python
def search_deals(self, filters, properties, limit=100, after=None):
    """Search deals via CRM search API. Mirror de search_tickets."""

def batch_read_associations(self, from_type, to_type, ids):
    """POST /crm/v4/associations/{from}/{to}/batch/read.
    Retorna dict {from_id_str: [to_id_str, ...]}."""

def batch_read_objects(self, object_type, ids, properties):
    """POST /crm/v3/objects/{type}/batch/read (limite 100 por chamada,
    fazer chunking interno se len(ids) > 100).
    Retorna dict {id_str: properties_dict}."""
```

Métodos existentes (`get_associations`, `get_deal`, `get_ticket`, `search_tickets`, `get_all_owners`) ficam intocados.

## Fluxo de sync

Reescrever `backend/app/modules/hubspot_sync/sync.py` em fases. Cada fase em função privada testável isoladamente.

### Constantes (no topo do módulo)

```python
APOLICE_PIPELINE_ID = "2453678"
PLACEMENT_PIPELINE_ID = "651307"
GONGO_STAGE_ID = "11947921"
DEFAULT_DEAL_PIPELINE_ID = "default"  # TBD: confirmar slug literal vs ID numérico
GONGO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

APOLICE_PROPERTIES = ["apolice___beneficio", "numero_apolice", "parceiro"]
TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
]
```

### `run_sync()` — orquestrador

```python
def run_sync():
    client = HubSpotClient()
    owner_map = client.get_all_owners()
    summary = {"created": 0, "updated": 0, "skipped": {...}, "errors": []}

    apolices = _fetch_apolices(client)
    apolice_to_ticket = _fetch_apolice_tickets(client, apolices, summary)
    tickets = _fetch_and_validate_tickets(client, set(apolice_to_ticket.values()), summary)
    valid_ticket_ids = _filter_tickets_with_default_deal(client, set(tickets.keys()), summary)

    for apolice in apolices:
        try:
            ticket_id = apolice_to_ticket.get(apolice["id"])
            if not ticket_id or ticket_id not in valid_ticket_ids:
                continue
            was_created = _upsert_policy(apolice, tickets[ticket_id], owner_map)
            summary["created" if was_created else "updated"] += 1
        except Exception as e:
            db.session.rollback()
            summary["errors"].append(f"Apolice {apolice['id']}: {e}")

    db.session.commit()
    return summary
```

### Fases

**`_fetch_apolices(client)`** — busca via search:
```
filterGroups: [
  { filters: [
      {propertyName: "hs_pipeline", operator: "EQ", value: APOLICE_PIPELINE_ID},
      {propertyName: "apolice___beneficio", operator: "IN", values: VALID_BENEFITS_HUBSPOT}
  ]}
]
```
Pagina via `after` até esgotar. Retorna `list[dict]` de apólices.

**`_fetch_apolice_tickets(client, apolices, summary)`** — batch:
- Chama `batch_read_associations("deals", "tickets", [a["id"] for a in apolices])`.
- Para cada apólice: pega o **primeiro** ticket associado (se >1, loga warn — caso raro, esperado é 1).
- Apólices sem ticket: `summary["skipped"]["no_ticket"] += 1`, log warn.
- Retorna `dict[apolice_id → ticket_id]`.

**`_fetch_and_validate_tickets(client, ticket_ids, summary)`** — batch:
- Chama `batch_read_objects("tickets", list(ticket_ids), TICKET_PROPERTIES)`.
- Filtra localmente:
  - `hs_pipeline == PLACEMENT_PIPELINE_ID` → senão skip (`wrong_pipeline`).
  - `hs_pipeline_stage == GONGO_STAGE_ID` → senão skip (`not_gongo`).
  - `closed_date >= GONGO_DATE_FLOOR` → senão skip (`too_old`).
- Retorna `dict[ticket_id → ticket_properties]` apenas dos válidos.

**`_filter_tickets_with_default_deal(client, ticket_ids, summary)`** — batch:
- Chama `batch_read_associations("tickets", "deals", list(ticket_ids))`.
- Para cada ticket, busca os deals associados em batch via `batch_read_objects("deals", all_deal_ids, ["hs_pipeline"])`.
- Ticket é válido se ≥1 deal associado tem `hs_pipeline == DEFAULT_DEAL_PIPELINE_ID`.
- Tickets inválidos: `summary["skipped"]["no_default_deal"] += 1`.
- Retorna `set[ticket_id]` dos válidos.

**`_upsert_policy(apolice, ticket, owner_map)`** — persistência:
- `policy = Policy.query.filter_by(hubspot_apolice_id=apolice["id"]).first()`
- Se não existe: cria, retorna `True`.
- Popula sempre (não-lockáveis):
  - `hubspot_apolice_id`, `hubspot_ticket_id`
  - `numero_apolice` (de `apolice["properties"]["numero_apolice"]`)
  - `partner_operator` (de `apolice["properties"]["parceiro"]`)
  - `benefit_type` (mapeado de `apolice___beneficio`)
  - `mrr_projected` (de `ticket["properties"]["mrr___receita_mensal"]`)
- Popula respeitando `is_locked` (lockáveis):
  - `ev_id` (resolvido via `solicitante_demanda` + `owner_map`)
  - `client_id` (upsert via `cliente___nome_da_empresa`)
  - `segment` (mapeado de `cotar___segmentacao_pipo`)
  - `closed_date` (do ticket)
- **Não** popula: `deal_id`, `deal_stage`, `deploy_date`, `first_payment_prev`, `mrr_post_deploy`.

### Logging por fase

Cada fase loga: nº de itens processados, nº de skips por motivo. `summary["skipped"]` agregado:
```python
{"no_ticket": int, "wrong_pipeline": int, "not_gongo": int,
 "too_old": int, "no_default_deal": int}
```

## Mudanças no `mapper.py`

Adicionar mapeamento:
```python
BENEFIT_MAP = {
    "saude": "SAUDE", "saúde": "SAUDE",
    "odonto": "ODONTO", "odontológico": "ODONTO", "odontologico": "ODONTO",
    "vida": "VIDA",
    "saúde e odonto": "SAUDE_ODONTO",
    "saude e odonto": "SAUDE_ODONTO",
}
```

E em `app/models/policy.py`:
```python
class BenefitType(str, enum.Enum):
    SAUDE = "SAUDE"
    ODONTO = "ODONTO"
    VIDA = "VIDA"
    SAUDE_ODONTO = "SAUDE_ODONTO"
```

## Testes

Localização: `backend/tests/test_modules/test_hubspot_sync/`.

Estilo: mock do `HubSpotClient` via `unittest.mock`, sem chamadas reais. Padrão de `test_sync_lock.py` (já existente).

| Teste | Verifica |
|---|---|
| `test_search_filters_pipeline_and_benefit` | `_fetch_apolices` constrói filtros corretos |
| `test_skip_apolice_without_ticket` | Sem ticket → pulada e contada em `summary["skipped"]["no_ticket"]` |
| `test_skip_ticket_wrong_pipeline` | Ticket fora de Placement → skip |
| `test_skip_ticket_not_gongo` | Stage != Gongo → skip |
| `test_skip_ticket_old_closed_date` | `closed_date < 2024-09-01` → skip |
| `test_skip_ticket_without_default_deal` | Ticket sem deal default → skip |
| `test_multiple_apolices_same_ticket` | 1 ticket → 3 apólices = 3 rows, mesmo `hubspot_ticket_id`, mesmo MRR replicado |
| `test_benefit_saude_odonto_maps_to_new_enum` | `"Saúde e Odonto"` → `BenefitType.SAUDE_ODONTO` |
| `test_is_locked_preserved` | Campos lockáveis não sobrescrevem |
| `test_numero_apolice_and_parceiro_persisted` | Campos novos populam |
| `test_upsert_idempotent_by_apolice_id` | Rodar 2× não duplica |

Migrações: roda upgrade/downgrade em CI no banco de teste; valida que UNIQUE moveu corretamente e que enum aceita o novo valor.

## Fora de escopo (explícito)

- **Commission calculation**: continua lendo `mrr_for_commission` da Policy igual hoje. Não mexer.
- **Dashboards / endpoints de listagem**: vão começar a ver múltiplas linhas por ticket. **Risco a sinalizar**: agregações que somam MRR podem inflar — auditoria/ajuste em PR separado.
- **Backfill histórico de `partner_operator`**: só novo sync popula. Dados antigos seriam perdidos no wipe de qualquer forma.
- **Drop das colunas mortas** (`deploy_date`, `first_payment_prev`, `mrr_post_deploy`, `deal_stage`): adiar pra PR separado após auditoria de dependências.
- **Scheduler**: continua a cada 30min, sem mudança em `scheduler.py`.

## Itens TBD (resolver antes da implementação)

1. **Slug do pipeline default de deals** — a constante `DEFAULT_DEAL_PIPELINE_ID = "default"` é o valor literal retornado pelo HubSpot, ou um ID numérico? Verificar com:
   ```bash
   curl -s -H "Authorization: Bearer $HUBSPOT_TOKEN" \
     "https://api.hubapi.com/crm/v3/pipelines/deals" | jq '.results[] | {id, label}'
   ```
   Atualizar a constante antes de mergear.

2. **Property real de operadora na apólice** — confirmado como `parceiro`. Validar com 1 chamada de teste antes da implementação:
   ```bash
   curl -s -H "Authorization: Bearer $HUBSPOT_TOKEN" \
     "https://api.hubapi.com/crm/v3/properties/deals/parceiro" | jq '.name, .label'
   ```

3. **Riscos de inflar dashboards** — abrir TODO/issue separado pra ajustar agregações com `DISTINCT hubspot_ticket_id` onde aplicável (calcular total de MRR sem duplicar).

## Sequência sugerida de implementação

1. Atualizar `BenefitType` enum + `BENEFIT_MAP` (`policy.py`, `mapper.py`).
2. Adicionar métodos batch no `HubSpotClient`.
3. Reescrever `sync.py` (fases + `_upsert_policy`).
4. Testes unitários por fase.
5. Migração Alembic única (wipe + schema, ordem definida acima).
6. Resolver os TBDs (slug do pipeline default, validar property `parceiro`).
7. Rodar sync manual em staging, validar logs/contagens.
8. Mergear, deixar scheduler popular produção.
