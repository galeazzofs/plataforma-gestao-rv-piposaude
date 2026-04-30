# Filtro Pré-ativação + Full-Fetch + Delete-by-Absence — Implementation Plan

> ⚠️ **SUPERSEDED — não implementado.** Substituído por [`2026-04-30-ticket-anchored-sync-redesign.md`](./2026-04-30-ticket-anchored-sync-redesign.md). O redesign incorpora pré-ativação + full-fetch + delete-by-absence dentro de uma cardinalidade nova (1 Policy por ticket em vez de 1 por apólice).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar filtro `hs_v2_date_entered_14038792 ≥ 2024-09-01` ao sync de apólices, remover o cursor incremental por `hs_lastmodifieddate` (full-fetch sempre) e introduzir delete-by-absence para manter `policies` em paridade com o estado HubSpot.

**Architecture:** Mudanças localizadas em `backend/app/modules/hubspot_sync/sync.py` (constantes, filtro em `_resolve_ticket_apolices`, full-fetch em `_fetch_tickets`, nova função `_delete_absent_policies`, summary com `deleted` e `not_pre_activation`). Migração Alembic one-time faz wipe + cleanup do cursor órfão. Testes unitários por fase + integration E2E.

**Tech Stack:** Python 3, Flask, SQLAlchemy, Alembic (Flask-Migrate), pytest, HubSpot CRM v3/v4 APIs.

**Spec:** `docs/superpowers/specs/2026-04-30-pre-ativacao-filter-and-full-fetch-design.md`

---

### Task 1: Atualizar estrutura do summary

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py:305-318`

- [ ] **Step 1: Atualizar `_new_summary` adicionando `deleted` e `skipped["not_pre_activation"]`**

Substituir a função `_new_summary` em `backend/app/modules/hubspot_sync/sync.py`:

```python
def _new_summary():
    return {
        "timestamp": None,
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": {
            "no_default_deal": 0,
            "no_apolice": 0,
            "no_active_ev": 0,
            "not_pre_activation": 0,
        },
        "errors": [],
        "error_count": 0,
    }
```

- [ ] **Step 2: Persistir `deleted` em `_persist_last_sync`**

Em `backend/app/modules/hubspot_sync/sync.py`, na função `_persist_last_sync`, adicionar a linha de `hubspot_last_sync_deleted` logo após `hubspot_last_sync_updated`:

```python
def _persist_last_sync(summary):
    """Mirror sync summary into PlatformSetting so the admin UI can show it."""
    PlatformSetting.set("hubspot_last_sync", summary["timestamp"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_errors", summary["errors"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_created", summary["created"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_updated", summary["updated"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_deleted", summary["deleted"], user_id=None)
    skipped_total = sum(summary["skipped"].values()) if isinstance(summary["skipped"], dict) else summary["skipped"]
    PlatformSetting.set("hubspot_last_sync_skipped", skipped_total, user_id=None)
    db.session.commit()
```

- [ ] **Step 3: Rodar testes existentes pra garantir que ainda passam**

Run: `cd backend && python -m pytest tests/test_modules/test_hubspot_sync/ -v`
Expected: PASS (todas as suítes existentes ainda devem passar — só adicionamos campos novos com defaults).

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py
git commit -m "feat(sync): add deleted + not_pre_activation counters to summary"
```

---

### Task 2: Adicionar filtro de Pré-ativação em `_resolve_ticket_apolices`

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py:37-58` (constantes + DEAL_PROPERTIES)
- Modify: `backend/app/modules/hubspot_sync/sync.py:181-224` (`_resolve_ticket_apolices`)
- Test: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`

- [ ] **Step 1: Escrever os 3 testes de filtro (devem falhar)**

Adicionar ao final da seção `# --- _resolve_ticket_apolices ---` em `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`:

```python
def test_resolve_ticket_apolices_includes_apolice_past_pre_activation():
    """Apólice com hs_v2_date_entered_14038792 >= 2024-09-01 é incluída."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert "T1" in result
    assert len(result["T1"]) == 1
    assert summary["skipped"]["not_pre_activation"] == 0


def test_resolve_ticket_apolices_skips_apolice_without_pre_activation_date():
    """Apólice sem hs_v2_date_entered_14038792 → skip + counter."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            # hs_v2_date_entered_14038792 ausente
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    # Sem apólices válidas — ticket cai em no_apolice
    assert result == {}
    assert summary["skipped"]["not_pre_activation"] == 1
    assert summary["skipped"]["no_apolice"] == 1


def test_resolve_ticket_apolices_skips_apolice_with_pre_activation_before_floor():
    """Apólice com data anterior a 2024-09-01 → skip + counter."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            "hs_v2_date_entered_14038792": "2024-08-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["not_pre_activation"] == 1
    assert summary["skipped"]["no_apolice"] == 1
```

Importar `_new_summary` no topo do arquivo de teste se ainda não estiver:

Verificar a linha de imports no topo. Já existe importação de várias coisas de `app.modules.hubspot_sync.sync`. Adicionar `_new_summary` ao import:

Localizar a importação existente:

```python
from app.modules.hubspot_sync.sync import (
    _fetch_tickets,
    _resolve_ticket_apolices,
    APOLICE_PIPELINE_ID,
    PLACEMENT_PIPELINE_ID,
    GONGO_STAGE_ID,
    GONGO_DATE_FLOOR,
    DEFAULT_DEAL_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    TICKET_PROPERTIES,
    DEAL_PROPERTIES,
)
```

E substituir adicionando `_new_summary`:

```python
from app.modules.hubspot_sync.sync import (
    _fetch_tickets,
    _resolve_ticket_apolices,
    _new_summary,
    APOLICE_PIPELINE_ID,
    PLACEMENT_PIPELINE_ID,
    GONGO_STAGE_ID,
    GONGO_DATE_FLOOR,
    DEFAULT_DEAL_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    TICKET_PROPERTIES,
    DEAL_PROPERTIES,
)
```

Atualizar a função local `_new_summary` no arquivo de teste (linha ~96) para refletir os campos novos — caso contrário ela diverge do real e os outros testes podem mascarar bugs:

Localizar:
```python
def _new_summary():
    return {"skipped": {"no_default_deal": 0, "no_apolice": 0, "no_active_ev": 0}}
```

E substituir por:
```python
def _new_summary():
    return {
        "skipped": {
            "no_default_deal": 0,
            "no_apolice": 0,
            "no_active_ev": 0,
            "not_pre_activation": 0,
        },
    }
```

- [ ] **Step 2: Rodar os novos testes (devem FALHAR)**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py::test_resolve_ticket_apolices_includes_apolice_past_pre_activation tests/test_modules/test_hubspot_sync/test_sync_phases.py::test_resolve_ticket_apolices_skips_apolice_without_pre_activation_date tests/test_modules/test_hubspot_sync/test_sync_phases.py::test_resolve_ticket_apolices_skips_apolice_with_pre_activation_before_floor -v
```

Expected: 2 dos 3 falham (o "skips without date" pode passar por acaso pois a apólice teria sido aceita sob a regra antiga e sem o filtro a contagem `not_pre_activation` nunca incrementa). O critério mínimo: contagem de `not_pre_activation` ainda não existe efetivamente no fluxo, então testes que esperam `>= 1` no contador devem falhar.

- [ ] **Step 3: Adicionar constantes e atualizar `DEAL_PROPERTIES`**

Em `backend/app/modules/hubspot_sync/sync.py`, na seção de constantes (linhas ~37-58), modificar:

```python
# --- HubSpot pipeline / stage IDs ---
APOLICE_PIPELINE_ID = "2453678"
PLACEMENT_PIPELINE_ID = "651307"
GONGO_STAGE_ID = "11947921"
DEFAULT_DEAL_PIPELINE_ID = "default"
GONGO_DATE_FLOOR = date(2024, 9, 1)

PRE_ATIVACAO_STAGE_ID = "14038792"
PRE_ATIVACAO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
]
# Single batch_read pulls both classification (`pipeline`) and the apolice-
# specific properties — saves a round trip per ticket batch.
DEAL_PROPERTIES = [
    "pipeline",
    "apolice___beneficio", "numero_apolice", "parceiro",
    "hs_v2_date_entered_14038792",
]
```

- [ ] **Step 4: Aplicar filtro em `_resolve_ticket_apolices`**

Em `backend/app/modules/hubspot_sync/sync.py`, localizar o loop dentro de `_resolve_ticket_apolices`:

```python
        for d in deals_for_ticket:
            props = deal_props.get(d, {})
            pipeline = props.get("pipeline")
            if pipeline == APOLICE_PIPELINE_ID:
                if props.get("apolice___beneficio") in VALID_BENEFITS_HUBSPOT:
                    apolices.append({"id": d, "properties": props})
            elif pipeline == DEFAULT_DEAL_PIPELINE_ID:
                has_default = True
```

Substituir por:

```python
        for d in deals_for_ticket:
            props = deal_props.get(d, {})
            pipeline = props.get("pipeline")
            if pipeline == APOLICE_PIPELINE_ID:
                if props.get("apolice___beneficio") not in VALID_BENEFITS_HUBSPOT:
                    continue
                entered = parse_date(props.get("hs_v2_date_entered_14038792"))
                if entered is None or entered < PRE_ATIVACAO_DATE_FLOOR:
                    summary["skipped"]["not_pre_activation"] += 1
                    continue
                apolices.append({"id": d, "properties": props})
            elif pipeline == DEFAULT_DEAL_PIPELINE_ID:
                has_default = True
```

- [ ] **Step 5: Rodar todos os testes da fase 2 (devem PASSAR)**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k "resolve_ticket_apolices"
```

Expected: PASS — incluindo os 3 novos. Os existentes devem continuar passando porque eles não setavam `hs_v2_date_entered_14038792` e portanto cairiam no skip novo... isso é um problema. Vou voltar e atualizar.

- [ ] **Step 6: Atualizar testes existentes pra incluir `hs_v2_date_entered_14038792`**

Os testes existentes em `_resolve_ticket_apolices` que esperam apólices serem aceitas (`test_resolve_ticket_apolices_keeps_ticket_with_valid_apolice_and_default`, `test_resolve_ticket_apolices_keeps_multiple_apolices_per_ticket`, etc.) precisam adicionar `"hs_v2_date_entered_14038792": "2025-01-15"` aos props das apólices que esperam ser aceitas.

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`, atualizar:

`test_resolve_ticket_apolices_keeps_ticket_with_valid_apolice_and_default` — modificar o `batch_read_objects.return_value`:

```python
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
```

`test_resolve_ticket_apolices_keeps_multiple_apolices_per_ticket` — modificar:

```python
    client.batch_read_objects.return_value = {
        "D-S": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-O": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Odonto",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
```

`test_resolve_ticket_apolices_drops_ticket_without_default_deal` — apólice é dropada por falta de default, mas para o teste validar isso bem precisa ter `hs_v2_date_entered_14038792` setado:

```python
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
    }
```

`test_resolve_ticket_apolices_drops_apolice_with_invalid_benefit` — não precisa de mudança (a apólice é dropada antes do filtro de pré-ativação rodar — benefício inválido `continue` antes).

- [ ] **Step 7: Rodar todos os testes de fase**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v
```

Expected: PASS em todos.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py
git commit -m "feat(sync): filter apolices by pre-activation date entry (>= 2024-09-01)"
```

---

### Task 3: Remover cursor incremental (`hs_lastmodifieddate`)

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py:142-178` (`_fetch_tickets`)
- Modify: `backend/app/modules/hubspot_sync/sync.py:331-436` (`run_sync` — remove cursor)
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py` (remove old tests, add full-fetch test)
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py` (remove cursor tests)

- [ ] **Step 1: Adicionar teste novo de full-fetch**

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`, adicionar logo após `test_fetch_tickets_builds_correct_search_filters_full_fetch`:

```python
def test_fetch_tickets_no_longer_accepts_since_argument():
    """_fetch_tickets perdeu o parâmetro `since` — full-fetch sempre."""
    import inspect
    from app.modules.hubspot_sync.sync import _fetch_tickets
    sig = inspect.signature(_fetch_tickets)
    assert "since" not in sig.parameters
```

- [ ] **Step 2: Rodar o novo teste (deve FALHAR)**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py::test_fetch_tickets_no_longer_accepts_since_argument -v
```

Expected: FAIL — o parâmetro ainda existe.

- [ ] **Step 3: Modificar `_fetch_tickets` removendo `since`**

Em `backend/app/modules/hubspot_sync/sync.py`, substituir a função `_fetch_tickets` inteira por:

```python
def _fetch_tickets(client):
    """Phase 1 — search tickets matching all gating criteria upfront.

    Filters applied at source:
    - hs_pipeline = PLACEMENT_PIPELINE_ID    (placement / sales pipeline)
    - hs_pipeline_stage = GONGO_STAGE_ID     (gongo stage = closed-won)
    - closed_date >= GONGO_DATE_FLOOR        (project-defined recent floor)

    Full-fetch every run — apólice deal stage changes don't update the ticket's
    hs_lastmodifieddate, so an incremental cursor on tickets would miss them.

    Returns the raw list of ticket dicts (each with `id` and `properties`).
    """
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": PLACEMENT_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": GONGO_STAGE_ID},
        {"propertyName": "closed_date", "operator": "GTE", "value": GONGO_DATE_FLOOR.isoformat()},
    ]

    tickets = []
    after = None
    while True:
        result = client.search_tickets(
            filters=filters, properties=TICKET_PROPERTIES, after=after,
        )
        tickets.extend(result.get("results", []))
        next_cursor = result.get("paging", {}).get("next", {}).get("after")
        if not next_cursor:
            break
        after = next_cursor
    logger.info(f"_fetch_tickets: {len(tickets)} tickets matched (full fetch)")
    return tickets
```

- [ ] **Step 4: Remover testes incrementais antigos**

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`, deletar **completamente** estas funções:
- `test_fetch_tickets_adds_modified_since_filter_when_incremental`
- `test_fetch_tickets_normalizes_datetime_since_to_iso`

- [ ] **Step 5: Rodar testes da fase 1**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k "fetch_tickets"
```

Expected: PASS — incluindo o teste novo, e os 3 que sobraram (`builds_correct_search_filters_full_fetch`, `paginates_until_exhausted`, `empty_first_page_returns_empty`, `no_longer_accepts_since_argument`).

- [ ] **Step 6: Remover cursor de `run_sync`**

Em `backend/app/modules/hubspot_sync/sync.py`, na função `run_sync`:

Localizar e remover o bloco:

```python
    # Incremental cursor — None on first run triggers a full fetch.
    last_success = PlatformSetting.get(LAST_SUCCESS_KEY) or None

    try:
        tickets = _fetch_tickets(client, since=last_success)
        ticket_to_apolices = _resolve_ticket_apolices(client, tickets, summary)
```

Substituir por:

```python
    try:
        tickets = _fetch_tickets(client)
        ticket_to_apolices = _resolve_ticket_apolices(client, tickets, summary)
```

E logo abaixo do upsert loop, localizar e remover:

```python
    # Bump the incremental cursor only on a clean run. Partial failures
    # full-fetch on retry rather than silently miss the failed records.
    if summary["error_count"] == 0:
        PlatformSetting.set(LAST_SUCCESS_KEY, sync_started_at.isoformat(), user_id=None)
        db.session.commit()
```

(Deixar o `db.session.commit()` que já existe acima dessa linha — só remover o bloco do cursor.)

A variável `sync_started_at = datetime.now(timezone.utc)` no topo de `run_sync` fica órfã. Remove ela também.

- [ ] **Step 7: Remover constante `LAST_SUCCESS_KEY` do módulo**

Em `backend/app/modules/hubspot_sync/sync.py`, na seção de constantes, deletar a linha:

```python
LAST_SUCCESS_KEY = "hubspot_sync_last_success_at"
```

- [ ] **Step 8: Atualizar testes de integração que dependem do cursor**

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py`:

(8a) Remover `LAST_SUCCESS_KEY` do bloco de imports:

```python
from app.modules.hubspot_sync.sync import (
    APOLICE_PIPELINE_ID,
    DEFAULT_DEAL_PIPELINE_ID,
    LAST_SUCCESS_KEY,
)
```

Substituir por:

```python
from app.modules.hubspot_sync.sync import (
    APOLICE_PIPELINE_ID,
    DEFAULT_DEAL_PIPELINE_ID,
)
```

(8b) **Deletar inteiramente** as funções `test_run_sync_passes_modified_since_when_cursor_present` e `test_run_sync_does_not_bump_cursor_on_error` (tudo da assinatura `def test_run_sync_passes_modified_since...` até o `db.session.commit()` final, e idem para a outra).

(8c) Em `test_run_sync_end_to_end`, remover o bloco do cursor:

```python
    # Incremental cursor bumped on zero-error run
    last_success = PlatformSetting.get(LAST_SUCCESS_KEY)
    assert last_success is not None
    # ISO-formatted datetime
    parsed = datetime.fromisoformat(last_success)
    assert parsed.tzinfo is not None
```

E o cleanup ao final:

```python
    PlatformSetting.query.filter_by(key=LAST_SUCCESS_KEY).delete()
```

(Deixar o `PlatformSetting.query.filter(PlatformSetting.key.like("hubspot_last_sync%")).delete()` — esse continua válido.)

(8d) Remover import órfão de `datetime` se ele não for mais usado:

Verificar se `datetime` é usado no resto do arquivo. Se não, remover do import.

(8e) Adicionar `hs_v2_date_entered_14038792` aos `_apolice_props` do test_sync_integration.py — caso contrário todas as apólices serão filtradas:

Localizar:

```python
def _apolice_props(beneficio, numero="AP-X", parceiro="BradescoTest"):
    return {
        "pipeline": APOLICE_PIPELINE_ID,
        "apolice___beneficio": beneficio,
        "numero_apolice": numero,
        "parceiro": parceiro,
    }
```

Substituir por:

```python
def _apolice_props(beneficio, numero="AP-X", parceiro="BradescoTest", entered_pre_ativacao="2025-01-15"):
    return {
        "pipeline": APOLICE_PIPELINE_ID,
        "apolice___beneficio": beneficio,
        "numero_apolice": numero,
        "parceiro": parceiro,
        "hs_v2_date_entered_14038792": entered_pre_ativacao,
    }
```

- [ ] **Step 9: Rodar suíte completa de hubspot_sync**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/ -v
```

Expected: PASS em todos. Sem `LAST_SUCCESS_KEY` errors. Os 3 testes incrementais antigos não existem mais.

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/
git commit -m "refactor(sync): full-fetch always — drop hs_lastmodifieddate cursor"
```

---

### Task 4: Função `_delete_absent_policies`

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py` (adicionar nova função)
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py` (testes da nova função)

- [ ] **Step 1: Adicionar testes do delete-by-absence**

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`, adicionar uma nova seção ao final do arquivo:

```python
# --- _delete_absent_policies ---

from app.models import Commission, EvValidation, FinancialImport, ImportBatch, Appraisal, AppraisalStatus
from app.models.ev_validation import ValidationStatus
from app.modules.hubspot_sync.sync import _delete_absent_policies


def _make_policy(apolice_id, ev_id, locked=False):
    p = Policy(
        hubspot_apolice_id=apolice_id,
        hubspot_ticket_id=f"T-{apolice_id}",
        ev_id=ev_id,
        is_locked=locked,
    )
    db.session.add(p)
    db.session.flush()
    return p


def _make_appraisal(creator_id, quarter=1, year=2099):
    """Helper — appraisal NÃO tem unique constraint por user, mas TEM por (quarter, year).
    Usar year=2099 + offset pra evitar conflito entre testes na mesma sessão."""
    import random
    a = Appraisal(
        quarter=quarter,
        year=year + random.randint(0, 99999),
        status=AppraisalStatus.DRAFT,
        created_by=creator_id,
    )
    db.session.add(a)
    db.session.flush()
    return a


def _make_batch(uploaded_by):
    b = ImportBatch(filename="test.csv", uploaded_by=uploaded_by)
    db.session.add(b)
    db.session.flush()
    return b


def test_delete_absent_policies_removes_policies_not_in_fetch(db_session):
    ev = _ev("delete-test@x")
    _make_policy("KEEP-1", ev.id)
    _make_policy("DROP-1", ev.id)

    summary = _new_summary()
    _delete_absent_policies({"KEEP-1"}, summary)
    db.session.flush()

    assert Policy.query.filter_by(hubspot_apolice_id="KEEP-1").one()
    assert Policy.query.filter_by(hubspot_apolice_id="DROP-1").first() is None
    assert summary["deleted"] == 1


def test_delete_absent_policies_no_op_when_all_seen(db_session):
    ev = _ev("delete-noop@x")
    _make_policy("A1", ev.id)
    _make_policy("A2", ev.id)

    summary = _new_summary()
    _delete_absent_policies({"A1", "A2"}, summary)
    db.session.flush()

    assert Policy.query.count() == 2
    assert summary["deleted"] == 0


def test_delete_absent_policies_cascades_commissions(db_session):
    ev = _ev("delete-cascade-c@x")
    p_keep = _make_policy("CASC-KEEP", ev.id)
    p_drop = _make_policy("CASC-C", ev.id)
    c_keep = Commission(policy_id=p_keep.id, ev_id=ev.id, quarter=1, year=2025)
    c_drop = Commission(policy_id=p_drop.id, ev_id=ev.id, quarter=1, year=2025)
    db.session.add_all([c_keep, c_drop])
    db.session.flush()
    c_drop_id = c_drop.id

    summary = _new_summary()
    _delete_absent_policies({"CASC-KEEP"}, summary)
    db.session.flush()

    assert Commission.query.filter_by(id=c_drop_id).first() is None
    assert Commission.query.filter_by(policy_id=p_keep.id).count() == 1
    assert summary["deleted"] == 1


def test_delete_absent_policies_cascades_ev_validations(db_session):
    ev = _ev("delete-cascade-v@x")
    p_keep = _make_policy("CASC-V-KEEP", ev.id)
    p_drop = _make_policy("CASC-V-DROP", ev.id)
    appraisal = _make_appraisal(ev.id)
    v_drop = EvValidation(
        appraisal_id=appraisal.id,
        policy_id=p_drop.id,
        ev_id=ev.id,
        status=ValidationStatus.PENDING,
    )
    db.session.add(v_drop)
    db.session.flush()
    v_drop_id = v_drop.id

    summary = _new_summary()
    _delete_absent_policies({"CASC-V-KEEP"}, summary)
    db.session.flush()

    assert EvValidation.query.filter_by(id=v_drop_id).first() is None


def test_delete_absent_policies_nulls_financial_imports(db_session):
    ev = _ev("delete-fi@x")
    p_keep = _make_policy("FI-KEEP", ev.id)
    p_drop = _make_policy("FI-DROP", ev.id)
    batch = _make_batch(uploaded_by=ev.id)
    fi = FinancialImport(
        import_batch_id=batch.id,
        policy_id=p_drop.id,
        numero_apolice="X",
        nf_valor_liquido=Decimal("100.00"),
        nf_mes_recebimento="2025-01",
        quarter=1,
        year=2025,
    )
    db.session.add(fi)
    db.session.flush()
    fi_id = fi.id

    summary = _new_summary()
    _delete_absent_policies({"FI-KEEP"}, summary)
    db.session.flush()

    fi_after = FinancialImport.query.filter_by(id=fi_id).one()
    assert fi_after.policy_id is None  # unlinked, not deleted


def test_delete_absent_policies_deletes_locked_rows(db_session):
    ev = _ev("delete-locked@x")
    _make_policy("LOCK-DROP", ev.id, locked=True)

    summary = _new_summary()
    _delete_absent_policies({"OTHER"}, summary)
    db.session.flush()

    assert Policy.query.filter_by(hubspot_apolice_id="LOCK-DROP").first() is None
    assert summary["deleted"] == 1


def test_delete_absent_policies_aborts_when_seen_empty_but_db_nonempty(db_session):
    ev = _ev("delete-guard@x")
    _make_policy("GUARD-1", ev.id)
    _make_policy("GUARD-2", ev.id)

    summary = _new_summary()
    summary["errors"] = []
    _delete_absent_policies(set(), summary)
    db.session.flush()

    assert Policy.query.count() == 2
    assert summary["deleted"] == 0
    assert any("Delete-by-absence" in e for e in summary["errors"])
    assert summary["error_count"] >= 1


def test_delete_absent_policies_empty_db_empty_seen_is_safe(db_session):
    """Edge case: nada em DB, nada visto — sem erro, sem delete."""
    summary = _new_summary()
    _delete_absent_policies(set(), summary)
    assert summary["deleted"] == 0
    assert summary["errors"] == []
```

**Nota sobre fixtures:** verificar antes de rodar se os modelos `EvValidation` e `FinancialImport` exigem outros campos NOT NULL além dos cobertos acima — abrir `backend/app/models/ev_validation.py` e `backend/app/models/financial_import.py` e ajustar caso a caso. Os helpers `_make_appraisal` e `_make_batch` foram criados para isolar essas dependências; se a configuração mudar, basta atualizar os helpers.

Atualizar `_new_summary` no topo do arquivo de teste para incluir o campo `deleted`:

```python
def _new_summary():
    return {
        "deleted": 0,
        "errors": [],
        "error_count": 0,
        "skipped": {
            "no_default_deal": 0,
            "no_apolice": 0,
            "no_active_ev": 0,
            "not_pre_activation": 0,
        },
    }
```

Adicionar import de `Decimal` se ainda não estiver no arquivo:

```python
from decimal import Decimal
```

(Já está, no topo. OK.)

- [ ] **Step 2: Rodar os testes (devem FALHAR — função não existe)**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k "delete_absent"
```

Expected: FAIL com `ImportError: cannot import name '_delete_absent_policies'`.

- [ ] **Step 3: Implementar `_delete_absent_policies`**

Em `backend/app/modules/hubspot_sync/sync.py`, adicionar **antes da seção `# --- Orchestrator ---`** (logo após `_upsert_policy`):

```python
def _delete_absent_policies(seen_apolice_ids, summary):
    """Phase 4 — delete policies whose hubspot_apolice_id wasn't seen in this sync.

    Cascade:
    - DELETE FROM commissions WHERE policy_id IN (...)
    - DELETE FROM ev_validations WHERE policy_id IN (...)
    - UPDATE financial_imports SET policy_id = NULL WHERE policy_id IN (...)
    - DELETE FROM policies WHERE id IN (...)

    Includes locked policies — lock prevents overwrite during upsert, but
    not deletion when the source disappears.

    Safety guard: if `seen_apolice_ids` is empty AND the policies table has
    rows, abort with an error in `summary["errors"]`. A zero-result fetch
    against a populated DB is more likely a HubSpot anomaly (silent pipeline
    change, expired token returning 200) than a real wipe.

    Updates summary["deleted"].
    """
    from app.models import Commission, EvValidation, FinancialImport

    if not seen_apolice_ids and Policy.query.count() > 0:
        msg = "Delete-by-absence abortado: fetch retornou zero apólices mas DB não está vazio"
        logger.error(msg)
        summary["errors"].append(msg)
        summary["error_count"] = len(summary["errors"])
        return

    absent = Policy.query.filter(
        Policy.hubspot_apolice_id.notin_(list(seen_apolice_ids))
    ).all()

    if not absent:
        return

    absent_ids = [p.id for p in absent]

    # Cascade order matters: clear children before parent (no ON DELETE CASCADE configured).
    Commission.query.filter(Commission.policy_id.in_(absent_ids)).delete(synchronize_session=False)
    EvValidation.query.filter(EvValidation.policy_id.in_(absent_ids)).delete(synchronize_session=False)
    FinancialImport.query.filter(FinancialImport.policy_id.in_(absent_ids)).update(
        {FinancialImport.policy_id: None}, synchronize_session=False
    )
    Policy.query.filter(Policy.id.in_(absent_ids)).delete(synchronize_session=False)

    summary["deleted"] = len(absent_ids)
    logger.info(
        f"Delete-by-absence: {len(absent_ids)} policies removidas "
        f"(commissions/ev_validations cascateadas, financial_imports unlinked)"
    )
```

- [ ] **Step 4: Rodar os testes do delete-by-absence**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k "delete_absent"
```

Expected: PASS em todos os 7 testes.

Se algum teste falhar com erro de schema (campos obrigatórios faltando em `Commission`/`EvValidation`/`FinancialImport`/`ImportBatch`), inspecione os modelos em `backend/app/models/` e ajuste os campos do test fixture (cada model pode requerer campos NOT NULL adicionais que não foram cobertos no exemplo).

- [ ] **Step 5: Rodar suíte completa de hubspot_sync pra garantir que nada quebrou**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/ -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py
git commit -m "feat(sync): add _delete_absent_policies with cascade + safety guard"
```

---

### Task 5: Wire `_delete_absent_policies` no orquestrador

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py` (`run_sync`)
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py`

- [ ] **Step 1: Adicionar teste de integração do delete**

Em `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py`, adicionar ao final do arquivo:

```python
def test_run_sync_deletes_policies_not_in_fetch(db_session):
    """Policy pre-existente cujo apolice id não aparece no fetch é deletada."""
    ev = _ev("ev-del@x")

    # Pre-existing policy not in HubSpot anymore
    stale = Policy(
        hubspot_apolice_id="STALE-A1",
        hubspot_ticket_id="STALE-T1",
        ev_id=ev.id,
    )
    db.session.add(stale)
    db.session.flush()

    fake_client = MagicMock()
    fake_client.search_tickets.return_value = {
        "results": [_ticket("T1", {"solicitante_demanda": "ev-del@x"})],
        "paging": {},
    }
    fake_client.batch_read_associations.return_value = {
        "T1": ["D-FRESH", "D-DEFAULT"],
    }
    fake_client.batch_read_objects.return_value = {
        "D-FRESH": _apolice_props("Saúde", numero="AP-FRESH"),
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    assert summary["created"] == 1
    assert summary["deleted"] == 1
    assert Policy.query.filter_by(hubspot_apolice_id="STALE-A1").first() is None
    assert Policy.query.filter_by(hubspot_apolice_id="D-FRESH").one()

    # Cleanup
    Policy.query.delete()
    Client.query.delete()
    User.query.filter_by(email="ev-del@x").delete()
    PlatformSetting.query.filter(PlatformSetting.key.like("hubspot_last_sync%")).delete()
    db.session.commit()


def test_run_sync_does_not_delete_when_errors_occur(db_session):
    """Sync com erro NÃO roda delete-by-absence."""
    ev = _ev("ev-err@x")
    stale = Policy(
        hubspot_apolice_id="STALE-A2",
        hubspot_ticket_id="STALE-T2",
        ev_id=ev.id,
    )
    db.session.add(stale)
    db.session.flush()

    fake_client = MagicMock()
    fake_client.search_tickets.return_value = {
        "results": [_ticket("T-ERR", {"solicitante_demanda": "ev-err@x"})],
        "paging": {},
    }
    fake_client.batch_read_associations.return_value = {
        "T-ERR": ["D-A", "D-DEFAULT"],
    }
    fake_client.batch_read_objects.return_value = {
        "D-A": _apolice_props("Saúde"),
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client), \
         patch("app.modules.hubspot_sync.sync._upsert_policy", side_effect=RuntimeError("boom")):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    assert summary["error_count"] >= 1
    assert summary["deleted"] == 0
    assert Policy.query.filter_by(hubspot_apolice_id="STALE-A2").one()  # preserved

    # Cleanup
    Policy.query.delete()
    Client.query.delete()
    User.query.filter_by(email="ev-err@x").delete()
    PlatformSetting.query.filter(PlatformSetting.key.like("hubspot_last_sync%")).delete()
    db.session.commit()
```

- [ ] **Step 2: Rodar os testes (devem FALHAR — wiring não existe ainda)**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_integration.py::test_run_sync_deletes_policies_not_in_fetch tests/test_modules/test_hubspot_sync/test_sync_integration.py::test_run_sync_does_not_delete_when_errors_occur -v
```

Expected: FAIL — `summary["deleted"]` é 0 ou stale policy ainda existe.

- [ ] **Step 3: Wire `_delete_absent_policies` em `run_sync`**

Em `backend/app/modules/hubspot_sync/sync.py`, na função `run_sync`, **antes** da linha `summary["error_count"] = len(summary["errors"])` que aparece logo após o loop de upsert, adicionar:

Localizar:

```python
    db.session.commit()
    summary["error_count"] = len(summary["errors"])
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
```

Substituir por:

```python
    db.session.commit()
    summary["error_count"] = len(summary["errors"])

    if summary["error_count"] == 0:
        seen_apolice_ids = {
            a["id"] for apolices in ticket_to_apolices.values()
            for a in apolices
        }
        _delete_absent_policies(seen_apolice_ids, summary)
        db.session.commit()
        # Re-evaluate error_count: _delete_absent_policies may have appended
        # to errors via the seen-empty safety guard.
        summary["error_count"] = len(summary["errors"])

    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Rodar testes de integração**

Run:
```bash
cd backend && python -m pytest tests/test_modules/test_hubspot_sync/test_sync_integration.py -v
```

Expected: PASS em todos.

- [ ] **Step 5: Rodar a suíte completa pra checar regressões**

Run:
```bash
cd backend && python -m pytest tests/ -v
```

Expected: PASS — sem regressões em outras suítes (commission, financial, etc.).

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py
git commit -m "feat(sync): run delete-by-absence after clean upsert phase"
```

---

### Task 6: Migração Alembic de wipe + cleanup

**Files:**
- Create: `backend/migrations/versions/<hash>_reset_for_pre_activation_filter.py`

- [ ] **Step 1: Gerar arquivo de migração via Flask-Migrate**

Run:
```bash
cd backend && flask db revision -m "reset for pre activation filter"
```

Expected: cria um arquivo em `backend/migrations/versions/<hash>_reset_for_pre_activation_filter.py` com `revision`, `down_revision` e funções vazias.

Caso o comando não funcione (sem env apropriado), criar o arquivo manualmente:

Run:
```bash
ls backend/migrations/versions/*.py
```

Identificar a revisão atual (o `down_revision` do novo arquivo será o `revision` do migration mais recente — vai ser `86eb3ff84c01` se nenhum migration novo foi adicionado entre o 2026-04-29 e agora).

Criar arquivo `backend/migrations/versions/9a1b2c3d4e5f_reset_for_pre_activation_filter.py` (substituir hash por algo único de 12 chars hex):

```python
"""reset for pre activation filter

Revision ID: 9a1b2c3d4e5f
Revises: 86eb3ff84c01
Create Date: 2026-04-30

"""
from alembic import op


revision = '9a1b2c3d4e5f'
down_revision = '86eb3ff84c01'
branch_labels = None
depends_on = None


def upgrade():
    pass  # populated in next step


def downgrade():
    pass
```

(Ajustar `down_revision` se a head atual não for `86eb3ff84c01`.)

- [ ] **Step 2: Implementar `upgrade()` com wipe + cleanup**

Editar a função `upgrade()` no arquivo recém-criado:

```python
def upgrade():
    # Wipe data to apply the new pre-activation filter from a clean state.
    # FK order matters: child tables first, then policies. financial_imports
    # has nullable policy_id — unlink instead of delete to preserve history.
    op.execute("DELETE FROM commissions")
    op.execute("DELETE FROM ev_validations")
    op.execute("UPDATE financial_imports SET policy_id = NULL WHERE policy_id IS NOT NULL")
    op.execute("DELETE FROM policies")

    # Remove the now-obsolete incremental cursor PlatformSetting key.
    op.execute(
        "DELETE FROM platform_settings WHERE key = 'hubspot_sync_last_success_at'"
    )
```

`downgrade()` permanece `pass` (destrutivo por design — não recupera dados).

- [ ] **Step 3: Rodar a migração local**

Run:
```bash
cd backend && flask db upgrade
```

Expected: aplica a migração sem erro. Se a aplicação não estiver configurada localmente, esse step roda na CI/deploy.

- [ ] **Step 4: Rodar testes pra confirmar que nada quebra com a nova migração**

Run:
```bash
cd backend && python -m pytest tests/ -v
```

Expected: PASS — testes usam `_db.create_all()` baseado nos models, não nas migrations, então não devem ser afetados.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/
git commit -m "migrate: wipe policies + cleanup orphan sync cursor for pre-activation filter"
```

---

### Task 7: Testes de smoke + verificação manual final

**Files:**
- N/A (verificação)

- [ ] **Step 1: Rodar a suíte completa do backend**

Run:
```bash
cd backend && python -m pytest tests/ -v
```

Expected: 100% PASS.

- [ ] **Step 2: Verificar que a função `run_sync` ainda é importável e tem a assinatura esperada**

Run:
```bash
cd backend && python -c "from app.modules.hubspot_sync.sync import run_sync, _delete_absent_policies, PRE_ATIVACAO_STAGE_ID, PRE_ATIVACAO_DATE_FLOOR; print(PRE_ATIVACAO_STAGE_ID, PRE_ATIVACAO_DATE_FLOOR)"
```

Expected: imprime `14038792 2024-09-01`.

- [ ] **Step 3: Confirmar que `LAST_SUCCESS_KEY` foi removido**

Run:
```bash
cd backend && python -c "from app.modules.hubspot_sync.sync import LAST_SUCCESS_KEY" 2>&1 | head -5
```

Expected: `ImportError`.

- [ ] **Step 4: Confirmar que `_fetch_tickets` não aceita `since`**

Run:
```bash
cd backend && python -c "import inspect; from app.modules.hubspot_sync.sync import _fetch_tickets; print(inspect.signature(_fetch_tickets))"
```

Expected: `(client)` — apenas o argumento `client`.

- [ ] **Step 5: Commit final (apenas se houver mudanças não commitadas)**

```bash
git status
```

Se houver mudanças, revisar e commitar com mensagem apropriada. Caso contrário, prosseguir.

- [ ] **Step 6: Push para review**

A integração está pronta. Próximo passo manual: deploy → rodar `flask db upgrade` em produção → rodar o sync e verificar contagens (`hubspot_last_sync_*` em PlatformSetting).

---

## Self-Review

### Spec coverage

- ✅ Filtro de Pré-ativação (`hs_v2_date_entered_14038792 ≥ 2024-09-01`) → Task 2
- ✅ Constantes novas (`PRE_ATIVACAO_STAGE_ID`, `PRE_ATIVACAO_DATE_FLOOR`) → Task 2
- ✅ DEAL_PROPERTIES atualizado → Task 2
- ✅ Skip counter `not_pre_activation` → Tasks 1 e 2
- ✅ Remover cursor incremental (`_fetch_tickets`, `run_sync`, `LAST_SUCCESS_KEY`) → Task 3
- ✅ `_delete_absent_policies` com cascata e guard → Task 4
- ✅ Wire em `run_sync` (gating por error_count) → Task 5
- ✅ Summary com `deleted` + persist → Tasks 1 e 5
- ✅ Migração one-time wipe + cleanup → Task 6
- ✅ Testes (filtro, full-fetch, delete-by-absence, integration) → Tasks 2, 3, 4, 5

### Placeholder scan

Sem TBDs ou implementações deferidas. O hash da migração no Task 6 é genérico (`9a1b2c3d4e5f`) — engineer deve gerar via `flask db revision` ou substituir por algo único.

### Type consistency

- `seen_apolice_ids: set[str]` — usado consistentemente (Task 4 implementação, Task 5 wiring).
- `_delete_absent_policies(seen, summary)` — assinatura igual nos testes e no wiring.
- `summary["deleted"]` (int) e `summary["skipped"]["not_pre_activation"]` (int) — referenciados consistentemente em Tasks 1, 2, 4, 5.
