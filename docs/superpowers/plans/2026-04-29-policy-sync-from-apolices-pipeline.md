# Policy sync a partir do pipeline de Apólices — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o sync atual (1 row/ticket) por um sync que parte de apólices (deals no pipeline 2453678) e cria 1 row em `policies` por apólice, validando linkagem ticket-Placement-Gongo + deal default.

**Architecture:** Reescrita em fases (search → batch enrich → batch validate → upsert), todas testáveis isoladamente, usando endpoints batch v3/v4 do HubSpot pra reduzir round-trips. Schema ganha `hubspot_apolice_id` (nova chave única) + `numero_apolice`; `hubspot_ticket_id` perde unique; `BenefitType.SAUDE_ODONTO` adicionado. Migração wipe & re-sync (Alembic única, atômica).

**Tech Stack:** Python 3.x, Flask, SQLAlchemy, Alembic, Postgres (prod) / SQLite-or-Postgres (test), pytest, unittest.mock.

**Spec:** [docs/superpowers/specs/2026-04-29-policy-sync-from-apolices-pipeline-design.md](../specs/2026-04-29-policy-sync-from-apolices-pipeline-design.md)

---

## File Structure

| File | Mudança | Responsabilidade |
|---|---|---|
| `backend/app/models/policy.py` | Modificar | Adicionar `hubspot_apolice_id`, `numero_apolice`; valor enum `SAUDE_ODONTO`; ajustar unique de `hubspot_ticket_id` |
| `backend/app/modules/hubspot_sync/mapper.py` | Modificar | Estender `BENEFIT_MAP` com `"saúde e odonto" → SAUDE_ODONTO` |
| `backend/app/modules/hubspot_sync/client.py` | Modificar | Adicionar `search_deals`, `batch_read_associations`, `batch_read_objects` |
| `backend/app/modules/hubspot_sync/sync.py` | Reescrever | Constantes + 5 fases + `_upsert_policy` + `run_sync` orquestrador |
| `backend/migrations/versions/<new>_apolice_anchored_sync.py` | Criar | Alembic única: wipe + schema |
| `backend/tests/test_modules/test_hubspot_sync/test_client_batch.py` | Criar | Testes dos novos métodos do client |
| `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py` | Criar | Testes unitários por fase do sync |
| `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py` | Criar | Teste end-to-end mockado do `run_sync` |
| `backend/tests/test_modules/test_hubspot_sync/test_sync_lock.py` | Modificar | Atualizar pra nova API `_upsert_policy(apolice, ticket, owner_map)` |
| `backend/tests/test_modules/test_policies/test_filters.py` | Modificar | Incluir `hubspot_apolice_id` no factory `_make_policy` |

---

## Task 1: Schema do model — colunas novas e enum

**Files:**
- Modify: `backend/app/models/policy.py`

- [ ] **Step 1: Atualizar `BenefitType` enum**

Em `backend/app/models/policy.py`, na classe enum existente:

```python
class BenefitType(str, enum.Enum):
    SAUDE = "SAUDE"
    ODONTO = "ODONTO"
    VIDA = "VIDA"
    SAUDE_ODONTO = "SAUDE_ODONTO"
```

- [ ] **Step 2: Atualizar `Policy` — colunas e unique**

Substituir as definições de `hubspot_ticket_id` e adicionar as colunas novas:

```python
    hubspot_apolice_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    hubspot_ticket_id = db.Column(db.String(100), nullable=False, index=True)
    numero_apolice = db.Column(db.String(100), nullable=True, index=True)
```

Mantém todas as outras colunas exatamente como estão.

- [ ] **Step 3: Atualizar `__repr__` pra usar a chave nova**

```python
    def __repr__(self):
        return f"<Policy apolice={self.hubspot_apolice_id} ticket={self.hubspot_ticket_id} ({self.commission_status})>"
```

- [ ] **Step 4: Verificar que tests existentes que constroem `Policy` ainda compilam**

Run: `cd backend && python -c "from app.models import Policy, BenefitType; print(BenefitType.SAUDE_ODONTO)"`
Expected: `BenefitType.SAUDE_ODONTO` (sem ImportError).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/policy.py
git commit -m "feat(policy): add hubspot_apolice_id and numero_apolice; SAUDE_ODONTO enum value"
```

---

## Task 2: Atualizar test_filters factory pra usar a nova chave

**Files:**
- Modify: `backend/tests/test_modules/test_policies/test_filters.py`

A tabela `policies` agora exige `hubspot_apolice_id`. O factory atual constrói policies só com `hubspot_ticket_id`, o que vai quebrar. Ajusta antes que outros testes sejam afetados.

- [ ] **Step 1: Atualizar `_make_policy`**

Substituir a função:

```python
def _make_policy(ev, ticket_id, apolice_id=None):
    p = Policy(
        hubspot_apolice_id=apolice_id or f"A-{ticket_id}",
        hubspot_ticket_id=ticket_id,
        ev_id=ev.id,
    )
    db.session.add(p)
    db.session.flush()
    return p
```

- [ ] **Step 2: Atualizar `test_excludes_policies_with_null_ev`**

Trocar a construção direta de `Policy`:

```python
def test_excludes_policies_with_null_ev(db_session):
    from app.modules.policies.filters import active_ev_policies_query

    p = Policy(hubspot_apolice_id="A-NULL", hubspot_ticket_id="T_NULL", ev_id=None)
    db.session.add(p)
    db.session.flush()

    assert active_ev_policies_query().count() == 0
```

- [ ] **Step 3: Rodar testes do filter**

Run: `cd backend && pytest tests/test_modules/test_policies/test_filters.py -v`
Expected: 2 tests passed.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_modules/test_policies/test_filters.py
git commit -m "test(policies): adapt filter tests to new hubspot_apolice_id schema"
```

---

## Task 3: Estender BENEFIT_MAP com Saúde e Odonto

**Files:**
- Modify: `backend/app/modules/hubspot_sync/mapper.py`
- Test: `backend/tests/test_modules/test_hubspot_sync/test_mapper.py` (criar se não existir)

- [ ] **Step 1: Escrever o teste falhando**

Criar `backend/tests/test_modules/test_hubspot_sync/test_mapper.py`:

```python
"""Tests for mapper helpers."""
from app.modules.hubspot_sync.mapper import map_benefit_type


def test_map_saude():
    assert map_benefit_type("Saúde") == "SAUDE"
    assert map_benefit_type("saude") == "SAUDE"


def test_map_odonto():
    assert map_benefit_type("Odonto") == "ODONTO"


def test_map_vida():
    assert map_benefit_type("Vida") == "VIDA"


def test_map_saude_odonto_with_accent():
    assert map_benefit_type("Saúde e Odonto") == "SAUDE_ODONTO"


def test_map_saude_odonto_without_accent():
    assert map_benefit_type("Saude e Odonto") == "SAUDE_ODONTO"


def test_map_unknown_returns_none():
    assert map_benefit_type("Outra Coisa") is None


def test_map_none_returns_none():
    assert map_benefit_type(None) is None
    assert map_benefit_type("") is None
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_mapper.py -v`
Expected: 2 falhas em `test_map_saude_odonto_*` (retornam `None`); resto passa.

- [ ] **Step 3: Estender `BENEFIT_MAP`**

Em `backend/app/modules/hubspot_sync/mapper.py`, substituir o dict:

```python
BENEFIT_MAP = {
    "saude": "SAUDE",
    "saúde": "SAUDE",
    "odonto": "ODONTO",
    "odontológico": "ODONTO",
    "odontologico": "ODONTO",
    "vida": "VIDA",
    "saúde e odonto": "SAUDE_ODONTO",
    "saude e odonto": "SAUDE_ODONTO",
}
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_mapper.py -v`
Expected: 7 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/mapper.py backend/tests/test_modules/test_hubspot_sync/test_mapper.py
git commit -m "feat(sync): map 'Saúde e Odonto' to SAUDE_ODONTO benefit"
```

---

## Task 4: Adicionar `search_deals` ao HubSpotClient

**Files:**
- Modify: `backend/app/modules/hubspot_sync/client.py`
- Test: `backend/tests/test_modules/test_hubspot_sync/test_client_batch.py` (criar)

- [ ] **Step 1: Escrever teste falhando**

Criar `backend/tests/test_modules/test_hubspot_sync/test_client_batch.py`:

```python
"""Tests for new HubSpotClient batch helpers."""
from unittest.mock import patch, MagicMock
from app.modules.hubspot_sync.client import HubSpotClient


def _client():
    with patch("app.modules.hubspot_sync.client.current_app") as mock_app:
        mock_app.config = {"HUBSPOT_TOKEN": "test-token"}
        return HubSpotClient()


def test_search_deals_calls_correct_endpoint_and_body():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": [], "paging": {}}
        c.search_deals(
            filters=[{"propertyName": "hs_pipeline", "operator": "EQ", "value": "X"}],
            properties=["foo", "bar"],
            limit=50,
        )
        mock_req.assert_called_once()
        method, path = mock_req.call_args[0]
        assert method == "POST"
        assert path == "/crm/v3/objects/deals/search"
        body = mock_req.call_args[1]["json"]
        assert body["filterGroups"] == [{"filters": [{"propertyName": "hs_pipeline", "operator": "EQ", "value": "X"}]}]
        assert body["properties"] == ["foo", "bar"]
        assert body["limit"] == 50
        assert "after" not in body


def test_search_deals_passes_pagination_cursor():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": [], "paging": {}}
        c.search_deals(filters=[], properties=[], after="cursor-123")
        body = mock_req.call_args[1]["json"]
        assert body["after"] == "cursor-123"
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_client_batch.py -v`
Expected: 2 falhas com `AttributeError: 'HubSpotClient' object has no attribute 'search_deals'`.

- [ ] **Step 3: Implementar `search_deals`**

Em `backend/app/modules/hubspot_sync/client.py`, adicionar logo após `search_tickets`:

```python
    def search_deals(self, filters, properties, limit=100, after=None):
        """Search deals via CRM search API."""
        body = {
            "filterGroups": [{"filters": filters}],
            "properties": properties,
            "limit": limit,
        }
        if after:
            body["after"] = after
        return self._request("POST", "/crm/v3/objects/deals/search", json=body)
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_client_batch.py -v`
Expected: 2 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/client.py backend/tests/test_modules/test_hubspot_sync/test_client_batch.py
git commit -m "feat(hubspot): add search_deals client method"
```

---

## Task 5: Adicionar `batch_read_associations` ao HubSpotClient

**Files:**
- Modify: `backend/app/modules/hubspot_sync/client.py`
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_client_batch.py`

- [ ] **Step 1: Escrever teste falhando**

Adicionar ao final de `test_client_batch.py`:

```python
def test_batch_read_associations_endpoint_and_body():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": []}
        c.batch_read_associations("deals", "tickets", ["123", "456"])
        method, path = mock_req.call_args[0]
        assert method == "POST"
        assert path == "/crm/v4/associations/deals/tickets/batch/read"
        body = mock_req.call_args[1]["json"]
        assert body == {"inputs": [{"id": "123"}, {"id": "456"}]}


def test_batch_read_associations_parses_response():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {
            "results": [
                {"from": {"id": "123"}, "to": [{"toObjectId": "T1"}, {"toObjectId": "T2"}]},
                {"from": {"id": "456"}, "to": [{"toObjectId": "T3"}]},
            ]
        }
        result = c.batch_read_associations("deals", "tickets", ["123", "456"])
        assert result == {"123": ["T1", "T2"], "456": ["T3"]}


def test_batch_read_associations_empty_input_returns_empty_dict():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        result = c.batch_read_associations("deals", "tickets", [])
        assert result == {}
        mock_req.assert_not_called()
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_client_batch.py -v`
Expected: 3 novas falhas com `AttributeError: ... 'batch_read_associations'`.

- [ ] **Step 3: Implementar `batch_read_associations`**

Em `backend/app/modules/hubspot_sync/client.py`, adicionar:

```python
    def batch_read_associations(self, from_type, to_type, ids):
        """POST /crm/v4/associations/{from}/{to}/batch/read.

        Returns dict mapping each from_id (str) to a list of to_ids (str).
        IDs without associations are omitted from the result. Returns {}
        for empty input without making any API call.
        """
        if not ids:
            return {}
        body = {"inputs": [{"id": str(i)} for i in ids]}
        path = f"/crm/v4/associations/{from_type}/{to_type}/batch/read"
        result = self._request("POST", path, json=body)
        out = {}
        for entry in result.get("results", []):
            from_id = str(entry["from"]["id"])
            to_ids = [str(t["toObjectId"]) for t in entry.get("to", [])]
            out[from_id] = to_ids
        return out
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_client_batch.py -v`
Expected: 5 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/client.py backend/tests/test_modules/test_hubspot_sync/test_client_batch.py
git commit -m "feat(hubspot): add batch_read_associations client method"
```

---

## Task 6: Adicionar `batch_read_objects` ao HubSpotClient

**Files:**
- Modify: `backend/app/modules/hubspot_sync/client.py`
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_client_batch.py`

- [ ] **Step 1: Escrever teste falhando**

Adicionar ao final de `test_client_batch.py`:

```python
def test_batch_read_objects_endpoint_and_body():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {"results": []}
        c.batch_read_objects("tickets", ["T1", "T2"], ["foo", "bar"])
        method, path = mock_req.call_args[0]
        assert method == "POST"
        assert path == "/crm/v3/objects/tickets/batch/read"
        body = mock_req.call_args[1]["json"]
        assert body == {
            "properties": ["foo", "bar"],
            "inputs": [{"id": "T1"}, {"id": "T2"}],
        }


def test_batch_read_objects_parses_response():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        mock_req.return_value = {
            "results": [
                {"id": "T1", "properties": {"foo": "v1"}},
                {"id": "T2", "properties": {"foo": "v2"}},
            ]
        }
        result = c.batch_read_objects("tickets", ["T1", "T2"], ["foo"])
        assert result == {
            "T1": {"foo": "v1"},
            "T2": {"foo": "v2"},
        }


def test_batch_read_objects_empty_input_returns_empty_dict():
    c = _client()
    with patch.object(c, "_request") as mock_req:
        result = c.batch_read_objects("tickets", [], ["foo"])
        assert result == {}
        mock_req.assert_not_called()


def test_batch_read_objects_chunks_above_100():
    c = _client()
    ids = [f"id-{i}" for i in range(250)]
    with patch.object(c, "_request") as mock_req:
        # Each call returns its inputs as identity dict
        def fake_req(method, path, json=None, **kwargs):
            return {
                "results": [
                    {"id": inp["id"], "properties": {"foo": inp["id"]}}
                    for inp in json["inputs"]
                ]
            }
        mock_req.side_effect = fake_req
        result = c.batch_read_objects("tickets", ids, ["foo"])
        # 250 ids → 100 + 100 + 50 = 3 calls
        assert mock_req.call_count == 3
        assert len(result) == 250
        assert result["id-0"]["foo"] == "id-0"
        assert result["id-249"]["foo"] == "id-249"
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_client_batch.py -v`
Expected: 4 novas falhas com `AttributeError: ... 'batch_read_objects'`.

- [ ] **Step 3: Implementar `batch_read_objects`**

Em `backend/app/modules/hubspot_sync/client.py`, adicionar:

```python
    def batch_read_objects(self, object_type, ids, properties):
        """POST /crm/v3/objects/{type}/batch/read in chunks of 100.

        Returns dict mapping id (str) to its properties dict. Returns {}
        for empty input without making any API call. Caller is responsible
        for deduplicating ids before calling.
        """
        if not ids:
            return {}
        out = {}
        chunk_size = 100
        path = f"/crm/v3/objects/{object_type}/batch/read"
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            body = {
                "properties": properties,
                "inputs": [{"id": str(x)} for x in chunk],
            }
            result = self._request("POST", path, json=body)
            for entry in result.get("results", []):
                out[str(entry["id"])] = entry.get("properties", {})
        return out
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_client_batch.py -v`
Expected: 9 tests passed (todos os do arquivo).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/client.py backend/tests/test_modules/test_hubspot_sync/test_client_batch.py
git commit -m "feat(hubspot): add batch_read_objects client method with 100-item chunking"
```

---

## Task 7: Reescrever sync.py — constantes e `_fetch_apolices`

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`
- Test: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py` (criar)

- [ ] **Step 1: Escrever teste falhando**

Criar `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`:

```python
"""Tests for individual phases of the apolice-anchored sync."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.modules.hubspot_sync.sync import (
    _fetch_apolices,
    APOLICE_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    APOLICE_PROPERTIES,
)


def test_fetch_apolices_builds_correct_search_filters():
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}

    _fetch_apolices(client)

    client.search_deals.assert_called_once()
    call_kwargs = client.search_deals.call_args.kwargs
    filters = call_kwargs["filters"]
    # 2 filters AND-ed: pipeline + benefit IN list
    pipeline_filter = next(f for f in filters if f["propertyName"] == "hs_pipeline")
    assert pipeline_filter["operator"] == "EQ"
    assert pipeline_filter["value"] == APOLICE_PIPELINE_ID

    benefit_filter = next(f for f in filters if f["propertyName"] == "apolice___beneficio")
    assert benefit_filter["operator"] == "IN"
    assert set(benefit_filter["values"]) == set(VALID_BENEFITS_HUBSPOT)

    assert set(call_kwargs["properties"]) == set(APOLICE_PROPERTIES)


def test_fetch_apolices_paginates_until_exhausted():
    client = MagicMock()
    client.search_deals.side_effect = [
        {"results": [{"id": "A1"}, {"id": "A2"}], "paging": {"next": {"after": "cursor"}}},
        {"results": [{"id": "A3"}], "paging": {}},
    ]
    apolices = _fetch_apolices(client)
    assert [a["id"] for a in apolices] == ["A1", "A2", "A3"]
    assert client.search_deals.call_count == 2
    # Second call passes the cursor
    assert client.search_deals.call_args_list[1].kwargs["after"] == "cursor"


def test_fetch_apolices_empty_first_page_returns_empty():
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}
    assert _fetch_apolices(client) == []
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v`
Expected: `ImportError` em todos (símbolos novos ainda não existem).

- [ ] **Step 3: Implementar constantes + `_fetch_apolices`**

Em `backend/app/modules/hubspot_sync/sync.py`, **substituir o conteúdo inteiro do arquivo** pelo seguinte (vamos reconstruir incrementalmente — deixar imports + constantes + `_fetch_apolices` como única função "real" por enquanto; remover `_process_ticket` e `run_sync` antigos):

```python
"""HubSpot sync — apolice-anchored.

Orchestrates pulling apolices (deals in pipeline 2453678), validating their
ticket+default-deal linkage, and upserting one row in `policies` per apolice.

See docs/superpowers/specs/2026-04-29-policy-sync-from-apolices-pipeline-design.md
"""
import logging
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import User, Policy, Client
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import (
    map_segment, map_benefit_type, parse_date, parse_decimal,
)

logger = logging.getLogger(__name__)

# --- HubSpot pipeline / stage IDs ---
APOLICE_PIPELINE_ID = "2453678"
PLACEMENT_PIPELINE_ID = "651307"
GONGO_STAGE_ID = "11947921"
DEFAULT_DEAL_PIPELINE_ID = "default"  # TBD: confirm slug
GONGO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

APOLICE_PROPERTIES = ["apolice___beneficio", "numero_apolice", "parceiro"]
TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
]
DEAL_VALIDATION_PROPERTIES = ["hs_pipeline"]


def _fetch_apolices(client):
    """Phase 1 — search apolices in the apolice pipeline filtered by benefit.

    Returns list of apolice dicts as returned by HubSpot search
    (each has at least `id` and `properties`).
    """
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": APOLICE_PIPELINE_ID},
        {"propertyName": "apolice___beneficio", "operator": "IN", "values": VALID_BENEFITS_HUBSPOT},
    ]
    apolices = []
    after = None
    while True:
        result = client.search_deals(
            filters=filters,
            properties=APOLICE_PROPERTIES,
            after=after,
        )
        apolices.extend(result.get("results", []))
        next_cursor = result.get("paging", {}).get("next", {}).get("after")
        if not next_cursor:
            break
        after = next_cursor
    logger.info(f"_fetch_apolices: {len(apolices)} apolices found")
    return apolices
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v`
Expected: 3 tests passed.

- [ ] **Step 5: Verificar que test_sync_lock.py quebra (esperado — apaga ou skip por enquanto)**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_lock.py -v 2>&1 | head -20`
Expected: `ImportError: cannot import name '_process_ticket'` — vamos consertar na Task 12.

Marcar o arquivo inteiro como skipped temporariamente. No topo de `test_sync_lock.py`, adicionar:

```python
import pytest
pytestmark = pytest.mark.skip(reason="Refactored into _upsert_policy in Task 12")
```

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/ -v`
Expected: `test_sync_lock` skipped, `test_sync_phases` 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py backend/tests/test_modules/test_hubspot_sync/test_sync_lock.py
git commit -m "feat(sync): add _fetch_apolices phase and constants; skip old lock tests temporarily"
```

---

## Task 8: `_fetch_apolice_tickets` (apolice → ticket associations)

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`

- [ ] **Step 1: Escrever teste falhando**

Adicionar ao final de `test_sync_phases.py`:

```python
from app.modules.hubspot_sync.sync import _fetch_apolice_tickets


def test_fetch_apolice_tickets_returns_first_ticket_per_apolice():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "A1": ["T1"],
        "A2": ["T2", "T2-extra"],  # multiple tickets — take first, log warn
    }
    summary = {"skipped": {"no_ticket": 0}}
    apolices = [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}]

    result = _fetch_apolice_tickets(client, apolices, summary)

    assert result == {"A1": "T1", "A2": "T2"}
    # A3 had no associations
    assert summary["skipped"]["no_ticket"] == 1
    client.batch_read_associations.assert_called_once_with("deals", "tickets", ["A1", "A2", "A3"])


def test_fetch_apolice_tickets_empty_input():
    client = MagicMock()
    summary = {"skipped": {"no_ticket": 0}}
    result = _fetch_apolice_tickets(client, [], summary)
    assert result == {}
    assert summary["skipped"]["no_ticket"] == 0
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v`
Expected: 2 falhas com `ImportError: cannot import name '_fetch_apolice_tickets'`.

- [ ] **Step 3: Implementar `_fetch_apolice_tickets`**

Adicionar em `backend/app/modules/hubspot_sync/sync.py`, após `_fetch_apolices`:

```python
def _fetch_apolice_tickets(client, apolices, summary):
    """Phase 2 — batch fetch ticket associations for all apolices.

    Returns dict {apolice_id: first_ticket_id}. Apolices without any ticket
    are skipped (counted in summary["skipped"]["no_ticket"]). When an apolice
    has multiple tickets, takes the first and logs a warning.
    """
    if not apolices:
        return {}
    apolice_ids = [a["id"] for a in apolices]
    associations = client.batch_read_associations("deals", "tickets", apolice_ids)
    out = {}
    for apolice_id in apolice_ids:
        ticket_ids = associations.get(apolice_id, [])
        if not ticket_ids:
            summary["skipped"]["no_ticket"] += 1
            logger.warning(f"Apolice {apolice_id} has no associated ticket — skipped")
            continue
        if len(ticket_ids) > 1:
            logger.warning(
                f"Apolice {apolice_id} has {len(ticket_ids)} associated tickets; "
                f"using first ({ticket_ids[0]})"
            )
        out[apolice_id] = ticket_ids[0]
    logger.info(f"_fetch_apolice_tickets: {len(out)}/{len(apolice_ids)} apolices linked to tickets")
    return out
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py::test_fetch_apolice_tickets_returns_first_ticket_per_apolice tests/test_modules/test_hubspot_sync/test_sync_phases.py::test_fetch_apolice_tickets_empty_input -v`
Expected: 2 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py
git commit -m "feat(sync): add _fetch_apolice_tickets batch association phase"
```

---

## Task 9: `_fetch_and_validate_tickets` (batch ticket fetch + filter)

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`

- [ ] **Step 1: Escrever testes falhando**

Adicionar ao final de `test_sync_phases.py`:

```python
from app.modules.hubspot_sync.sync import _fetch_and_validate_tickets


def _ticket_props(pipeline=None, stage=None, closed_date=None):
    """Helper: build ticket properties with defaults for valid-ticket fields."""
    return {
        "hs_pipeline": pipeline or "651307",
        "hs_pipeline_stage": stage or "11947921",
        "closed_date": closed_date or "2025-06-01T00:00:00Z",
        "mrr___receita_mensal": "1000",
        "solicitante_demanda": "ev@x",
        "cliente___nome_da_empresa": "ClientCo",
        "cotar___segmentacao_pipo": "M",
    }


def _new_summary():
    return {"skipped": {"no_ticket": 0, "wrong_pipeline": 0,
                        "not_gongo": 0, "too_old": 0, "no_default_deal": 0}}


def test_validate_tickets_keeps_valid():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(),
        "T2": _ticket_props(),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1", "T2"], summary)
    assert set(result.keys()) == {"T1", "T2"}
    client.batch_read_objects.assert_called_once_with(
        "tickets", ["T1", "T2"], list(__import__("app.modules.hubspot_sync.sync",
                                                  fromlist=["TICKET_PROPERTIES"]).TICKET_PROPERTIES)
    )


def test_validate_tickets_drops_wrong_pipeline():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(pipeline="999999"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["wrong_pipeline"] == 1


def test_validate_tickets_drops_wrong_stage():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(stage="555"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["not_gongo"] == 1


def test_validate_tickets_drops_too_old():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(closed_date="2024-01-15T00:00:00Z"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["too_old"] == 1


def test_validate_tickets_drops_missing_closed_date():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(closed_date=""),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["too_old"] == 1


def test_validate_tickets_empty_input():
    client = MagicMock()
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, [], summary)
    assert result == {}
    client.batch_read_objects.assert_not_called()
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k validate_tickets`
Expected: 6 falhas com `ImportError`.

- [ ] **Step 3: Implementar `_fetch_and_validate_tickets`**

Adicionar em `backend/app/modules/hubspot_sync/sync.py`:

```python
def _fetch_and_validate_tickets(client, ticket_ids, summary):
    """Phase 3 — batch fetch tickets and filter by pipeline/stage/date.

    `ticket_ids` is an iterable; duplicates are deduped before the API call.
    Returns dict {ticket_id: properties_dict} for tickets that pass all filters.
    Skipped tickets are counted in summary by reason.
    """
    unique_ids = list(set(ticket_ids))
    if not unique_ids:
        return {}
    all_props = client.batch_read_objects("tickets", unique_ids, TICKET_PROPERTIES)
    out = {}
    for ticket_id, props in all_props.items():
        if props.get("hs_pipeline") != PLACEMENT_PIPELINE_ID:
            summary["skipped"]["wrong_pipeline"] += 1
            continue
        if props.get("hs_pipeline_stage") != GONGO_STAGE_ID:
            summary["skipped"]["not_gongo"] += 1
            continue
        closed = parse_date(props.get("closed_date"))
        if closed is None or closed < GONGO_DATE_FLOOR:
            summary["skipped"]["too_old"] += 1
            continue
        out[ticket_id] = props
    logger.info(f"_fetch_and_validate_tickets: {len(out)}/{len(unique_ids)} tickets valid")
    return out
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k validate_tickets`
Expected: 6 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py
git commit -m "feat(sync): add _fetch_and_validate_tickets phase with pipeline/stage/date filters"
```

---

## Task 10: `_filter_tickets_with_default_deal`

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`

- [ ] **Step 1: Escrever testes falhando**

Adicionar ao final de `test_sync_phases.py`:

```python
from app.modules.hubspot_sync.sync import _filter_tickets_with_default_deal


def test_filter_tickets_keeps_those_with_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D1"],
        "T2": ["D2", "D3"],
    }
    client.batch_read_objects.return_value = {
        "D1": {"hs_pipeline": "default"},
        "D2": {"hs_pipeline": "999999"},  # not default
        "D3": {"hs_pipeline": "default"},
    }
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1", "T2"], summary)
    assert result == {"T1", "T2"}  # T2 has at least one default deal
    assert summary["skipped"]["no_default_deal"] == 0


def test_filter_tickets_drops_those_without_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D1"],
    }
    client.batch_read_objects.return_value = {
        "D1": {"hs_pipeline": "999999"},
    }
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1"], summary)
    assert result == set()
    assert summary["skipped"]["no_default_deal"] == 1


def test_filter_tickets_drops_those_without_any_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {}  # T1 has no deals
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1"], summary)
    assert result == set()
    assert summary["skipped"]["no_default_deal"] == 1


def test_filter_tickets_empty_input():
    client = MagicMock()
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, [], summary)
    assert result == set()
    client.batch_read_associations.assert_not_called()
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k filter_tickets`
Expected: 4 falhas com `ImportError`.

- [ ] **Step 3: Implementar `_filter_tickets_with_default_deal`**

Adicionar em `backend/app/modules/hubspot_sync/sync.py`:

```python
def _filter_tickets_with_default_deal(client, ticket_ids, summary):
    """Phase 4 — verify each ticket has at least one associated deal in the
    default pipeline. Returns set of ticket_ids that pass.
    """
    ticket_ids = list(ticket_ids)
    if not ticket_ids:
        return set()
    ticket_to_deals = client.batch_read_associations("tickets", "deals", ticket_ids)
    all_deal_ids = list({d for deals in ticket_to_deals.values() for d in deals})
    deal_props = client.batch_read_objects(
        "deals", all_deal_ids, DEAL_VALIDATION_PROPERTIES
    )
    valid = set()
    for ticket_id in ticket_ids:
        deals_for_ticket = ticket_to_deals.get(ticket_id, [])
        has_default = any(
            deal_props.get(d, {}).get("hs_pipeline") == DEFAULT_DEAL_PIPELINE_ID
            for d in deals_for_ticket
        )
        if has_default:
            valid.add(ticket_id)
        else:
            summary["skipped"]["no_default_deal"] += 1
    logger.info(f"_filter_tickets_with_default_deal: {len(valid)}/{len(ticket_ids)} tickets pass")
    return valid
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k filter_tickets`
Expected: 4 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py
git commit -m "feat(sync): add _filter_tickets_with_default_deal validation phase"
```

---

## Task 11: `_upsert_policy` — persistência

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py`

- [ ] **Step 1: Escrever testes falhando**

Adicionar ao final de `test_sync_phases.py`:

```python
from app.extensions import db
from app.models import User, UserRole, Policy, Client, Segment, BenefitType
from app.modules.hubspot_sync.sync import _upsert_policy


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(apolice_id, beneficio="Saúde", numero="AP-001", parceiro="Bradesco"):
    return {
        "id": apolice_id,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": numero,
            "parceiro": parceiro,
        },
    }


def _ticket(ev_email="ev@x", client_name="ClientCo", mrr="1500",
            closed="2025-06-01T00:00:00Z", segment="M"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client_name,
        "mrr___receita_mensal": mrr,
        "closed_date": closed,
        "cotar___segmentacao_pipo": segment,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
    }


def test_upsert_creates_new_policy(db_session):
    ev = _ev("ev@x")
    owner_map = {}  # solicitante_demanda is already an email here
    apolice = _apolice("A1", beneficio="Saúde", numero="AP-001", parceiro="Bradesco")
    ticket = _ticket(ev_email="ev@x", client_name="Acme", mrr="2500")

    is_new = _upsert_policy(apolice, ticket, owner_map)
    db.session.flush()

    assert is_new is True
    policy = Policy.query.filter_by(hubspot_apolice_id="A1").one()
    assert policy.numero_apolice == "AP-001"
    assert policy.partner_operator == "Bradesco"
    assert policy.benefit_type == BenefitType.SAUDE
    assert policy.mrr_projected == Decimal("2500")
    assert policy.ev_id == ev.id
    assert policy.client.name == Client.find_or_create("Acme").name
    assert policy.segment == Segment.M
    assert policy.closed_date == date(2025, 6, 1)


def test_upsert_updates_existing_policy(db_session):
    ev = _ev("ev2@x")
    owner_map = {}
    # Pre-create
    existing = Policy(
        hubspot_apolice_id="A2",
        hubspot_ticket_id="T2",
        ev_id=ev.id,
        mrr_projected=Decimal("100"),
    )
    db.session.add(existing)
    db.session.flush()

    apolice = _apolice("A2", numero="AP-NEW")
    ticket = _ticket(ev_email="ev2@x", mrr="9999")
    ticket_id_passed_via_apolice_lookup = "T2-NEW"
    # We'll set hubspot_ticket_id via a parameter — see implementation below.
    # For this test, the API of _upsert_policy must accept (apolice, ticket, owner_map)
    # and the ticket_id is read from somewhere. Simplest: pass it as kwarg.

    # Adjust: actual signature is _upsert_policy(apolice, ticket, owner_map, ticket_id)
    is_new = _upsert_policy(apolice, ticket, owner_map, ticket_id="T2-NEW")
    db.session.flush()

    assert is_new is False
    db.session.refresh(existing)
    assert existing.mrr_projected == Decimal("9999")
    assert existing.numero_apolice == "AP-NEW"
    assert existing.hubspot_ticket_id == "T2-NEW"


def test_upsert_saude_e_odonto_maps_to_combined_enum(db_session):
    _ev("ev3@x")
    apolice = _apolice("A3", beneficio="Saúde e Odonto")
    ticket = _ticket(ev_email="ev3@x")
    _upsert_policy(apolice, ticket, {}, ticket_id="T3")
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_apolice_id="A3").one()
    assert policy.benefit_type == BenefitType.SAUDE_ODONTO


def test_upsert_multiple_apolices_same_ticket(db_session):
    _ev("ev4@x")
    ticket = _ticket(ev_email="ev4@x", mrr="3000")
    for apolice_id, beneficio in [("A4-S", "Saúde"), ("A4-O", "Odonto"), ("A4-V", "Vida")]:
        apolice = _apolice(apolice_id, beneficio=beneficio)
        _upsert_policy(apolice, ticket, {}, ticket_id="T4")
    db.session.flush()

    rows = Policy.query.filter_by(hubspot_ticket_id="T4").order_by(Policy.hubspot_apolice_id).all()
    assert len(rows) == 3
    assert {r.hubspot_apolice_id for r in rows} == {"A4-S", "A4-O", "A4-V"}
    assert {r.benefit_type for r in rows} == {BenefitType.SAUDE, BenefitType.ODONTO, BenefitType.VIDA}
    # All share the same MRR (replicated)
    assert {r.mrr_projected for r in rows} == {Decimal("3000")}


def test_upsert_respects_is_locked_for_lockable_fields(db_session):
    ev_old = _ev("locked-old@x")
    ev_new = _ev("locked-new@x")
    locked = Policy(
        hubspot_apolice_id="A-LOCK",
        hubspot_ticket_id="T-LOCK",
        ev_id=ev_old.id,
        segment=Segment.M,
        closed_date=date(2025, 1, 1),
        is_locked=True,
    )
    db.session.add(locked)
    db.session.flush()

    apolice = _apolice("A-LOCK", parceiro="NewOp")
    ticket = _ticket(ev_email="locked-new@x", segment="G", closed="2026-03-01T00:00:00Z", mrr="7777")
    _upsert_policy(apolice, ticket, {}, ticket_id="T-LOCK-NEW")
    db.session.flush()
    db.session.refresh(locked)

    # Lockable: preserved
    assert locked.ev_id == ev_old.id
    assert locked.segment == Segment.M
    assert locked.closed_date == date(2025, 1, 1)
    # Non-lockable: updated
    assert locked.mrr_projected == Decimal("7777")
    assert locked.partner_operator == "NewOp"
    assert locked.hubspot_ticket_id == "T-LOCK-NEW"


def test_upsert_resolves_ev_via_owner_map(db_session):
    ev = _ev("from-owner@x")
    owner_map = {"99999": "from-owner@x"}
    apolice = _apolice("A-OWN")
    ticket = _ticket(ev_email="99999")  # solicitante_demanda is an owner_id, not email
    _upsert_policy(apolice, ticket, owner_map, ticket_id="T-OWN")
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_apolice_id="A-OWN").one()
    assert policy.ev_id == ev.id
```

- [ ] **Step 2: Rodar pra ver falhar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k upsert`
Expected: 6 falhas com `ImportError`.

- [ ] **Step 3: Implementar `_upsert_policy`**

Adicionar em `backend/app/modules/hubspot_sync/sync.py`:

```python
def _upsert_policy(apolice, ticket_props, owner_map, ticket_id=None):
    """Phase 5 — create or update one Policy row from an apolice + its ticket.

    Args:
        apolice: dict from HubSpot search (has `id` and `properties`)
        ticket_props: dict of ticket properties (already validated/filtered)
        owner_map: dict {owner_id_str: email}
        ticket_id: HubSpot ticket id; pulled from caller's apolice→ticket map.
                   Optional for backward-compat in tests but production passes it.

    Returns True if a new row was created, False if updated.
    Respects Policy.is_locked: locked rows keep ev_id, client_id, segment, closed_date.
    """
    apolice_id = apolice["id"]
    apolice_props = apolice.get("properties", {})

    # Resolve EV: solicitante_demanda may be an owner_id (lookup in map) or already an email
    raw_ev = ticket_props.get("solicitante_demanda")
    ev_email = owner_map.get(str(raw_ev), raw_ev) if raw_ev else None
    ev = User.query.filter_by(email=ev_email).first() if ev_email else None

    # Upsert client (always — even when locked we may need it)
    client_name = ticket_props.get("cliente___nome_da_empresa") or ""
    client_obj = None
    if client_name:
        client_obj = Client.find_or_create(client_name, ev_id=ev.id if ev else None)
        db.session.flush()

    # Find or create policy
    policy = Policy.query.filter_by(hubspot_apolice_id=str(apolice_id)).first()
    is_new = policy is None
    if is_new:
        policy = Policy(hubspot_apolice_id=str(apolice_id))
        db.session.add(policy)

    locked = bool(getattr(policy, "is_locked", False))

    # Always update (non-lockable):
    policy.hubspot_ticket_id = str(ticket_id) if ticket_id else policy.hubspot_ticket_id
    policy.numero_apolice = apolice_props.get("numero_apolice") or None
    policy.partner_operator = apolice_props.get("parceiro") or None
    policy.benefit_type = map_benefit_type(apolice_props.get("apolice___beneficio"))
    policy.mrr_projected = parse_decimal(ticket_props.get("mrr___receita_mensal"))

    # Lockable — only update if not locked
    if not locked:
        if ev:
            policy.ev_id = ev.id
        if client_obj:
            policy.client_id = client_obj.id
        policy.segment = map_segment(ticket_props.get("cotar___segmentacao_pipo"))
        policy.closed_date = parse_date(ticket_props.get("closed_date"))

    db.session.flush()
    return is_new
```

- [ ] **Step 4: Rodar de novo**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_phases.py -v -k upsert`
Expected: 6 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/test_sync_phases.py
git commit -m "feat(sync): add _upsert_policy with is_locked respect and benefit mapping"
```

---

## Task 12: Substituir `test_sync_lock.py` pela versão nova

O arquivo antigo testava `_process_ticket`, que não existe mais. Reescrevemos pra cobrir `_upsert_policy` (no estilo do teste antigo, focado em is_locked).

**Files:**
- Modify: `backend/tests/test_modules/test_hubspot_sync/test_sync_lock.py`

- [ ] **Step 1: Reescrever o arquivo inteiro**

Substituir todo o conteúdo de `backend/tests/test_modules/test_hubspot_sync/test_sync_lock.py` por:

```python
"""Tests for HubSpot sync respecting Policy.is_locked.

When is_locked=True, fields ev_id, closed_date, segment, and client_id
must NOT be overwritten by the sync. Non-lockable fields like mrr_projected,
partner_operator, numero_apolice, and benefit_type are still updated.
"""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
)
from app.modules.hubspot_sync.sync import _upsert_policy


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(apolice_id, beneficio="ODONTO", parceiro="OpA"):
    return {
        "id": apolice_id,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": f"AP-{apolice_id}",
            "parceiro": parceiro,
        },
    }


def _ticket_props(ev_email, client_name, segment="G", mrr="5000",
                  closed="2026-01-15T00:00:00Z"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client_name,
        "cotar___segmentacao_pipo": segment,
        "mrr___receita_mensal": mrr,
        "closed_date": closed,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
    }


def test_sync_preserves_locked_fields(db_session):
    """A locked policy keeps its ev_id, closed_date, segment, and client_id
    intact when the sync re-processes its apolice with different values."""
    old_ev = _ev("old-ev@x")
    _ev("new-ev@x")
    old_client = Client.find_or_create("OldClient")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="LOCK-A1",
        hubspot_ticket_id="LOCK-T1",
        ev_id=old_ev.id,
        client_id=old_client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        is_locked=True,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("LOCK-A1", beneficio="Odonto")
    ticket = _ticket_props(ev_email="new-ev@x", client_name="NewClient",
                           segment="G", closed="2026-01-15T00:00:00Z")

    _upsert_policy(apolice, ticket, {}, ticket_id="LOCK-T1")
    db.session.flush()
    db.session.refresh(policy)

    # Lockable fields preserved
    assert policy.ev_id == old_ev.id
    assert policy.client_id == old_client.id
    assert policy.segment == Segment.M
    assert policy.closed_date == date(2025, 6, 1)
    # Non-lockable: updated
    assert policy.benefit_type == BenefitType.ODONTO


def test_sync_updates_unlocked_policy_normally(db_session):
    _ev("unlocked-ev1@x")
    ev2 = _ev("unlocked-ev2@x")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="UNLOCK-A1",
        hubspot_ticket_id="UNLOCK-T1",
        ev_id=ev2.id,  # will be re-resolved
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        is_locked=False,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("UNLOCK-A1", beneficio="Odonto")
    ticket = _ticket_props(ev_email="unlocked-ev2@x", client_name="SomeClient",
                           segment="G", closed="2026-01-15T00:00:00Z")

    _upsert_policy(apolice, ticket, {}, ticket_id="UNLOCK-T1")
    db.session.flush()
    db.session.refresh(policy)

    assert policy.ev_id == ev2.id
    assert policy.closed_date == date(2026, 1, 15)
    assert policy.segment == Segment.G


def test_sync_updates_non_lockable_fields_on_locked_policy(db_session):
    old_ev = _ev("mrr-ev@x")
    old_client = Client.find_or_create("MrrClient")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="MRR-A1",
        hubspot_ticket_id="MRR-T1",
        ev_id=old_ev.id,
        client_id=old_client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        mrr_projected=None,
        is_locked=True,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("MRR-A1", beneficio="Saúde", parceiro="NewPartner")
    ticket = _ticket_props(ev_email="mrr-ev@x", client_name="MrrClient",
                           mrr="9999", closed="2026-02-01T00:00:00Z")

    _upsert_policy(apolice, ticket, {}, ticket_id="MRR-T1")
    db.session.flush()
    db.session.refresh(policy)

    # Non-lockable: updated
    assert policy.mrr_projected == Decimal("9999")
    assert policy.partner_operator == "NewPartner"
    # Lockable: preserved
    assert policy.closed_date == date(2025, 6, 1)
```

- [ ] **Step 2: Rodar testes**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_lock.py -v`
Expected: 3 tests passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_modules/test_hubspot_sync/test_sync_lock.py
git commit -m "test(sync): rewrite is_locked tests for new _upsert_policy API"
```

---

## Task 13: `run_sync` orquestrador + summary

**Files:**
- Modify: `backend/app/modules/hubspot_sync/sync.py`

- [ ] **Step 1: Adicionar `run_sync` no fim de `sync.py`**

Adicionar em `backend/app/modules/hubspot_sync/sync.py`:

```python
def _new_summary():
    return {
        "timestamp": None,
        "created": 0,
        "updated": 0,
        "skipped": {
            "no_ticket": 0,
            "wrong_pipeline": 0,
            "not_gongo": 0,
            "too_old": 0,
            "no_default_deal": 0,
        },
        "errors": [],
        "error_count": 0,
    }


def run_sync():
    """Main sync job: pull apolices from HubSpot, validate linkage, upsert into policies.

    Returns summary dict.
    """
    client = HubSpotClient()
    summary = _new_summary()

    try:
        owner_map = client.get_all_owners()
        logger.info(f"Loaded {len(owner_map)} HubSpot owners")
    except Exception as e:
        logger.warning(f"Could not load owners: {e}")
        owner_map = {}

    try:
        apolices = _fetch_apolices(client)
        apolice_to_ticket = _fetch_apolice_tickets(client, apolices, summary)
        tickets = _fetch_and_validate_tickets(
            client, apolice_to_ticket.values(), summary
        )
        valid_ticket_ids = _filter_tickets_with_default_deal(
            client, tickets.keys(), summary
        )
    except Exception as e:
        logger.error(f"HubSpot fetch failed: {e}")
        summary["errors"].append(f"Fetch failed: {e}")
        summary["error_count"] = len(summary["errors"])
        summary["timestamp"] = datetime.now(timezone.utc).isoformat()
        return summary

    for apolice in apolices:
        apolice_id = apolice["id"]
        ticket_id = apolice_to_ticket.get(apolice_id)
        if not ticket_id or ticket_id not in valid_ticket_ids:
            continue
        try:
            was_created = _upsert_policy(
                apolice, tickets[ticket_id], owner_map, ticket_id=ticket_id
            )
            if was_created:
                summary["created"] += 1
            else:
                summary["updated"] += 1
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing apolice {apolice_id}: {e}")
            summary["errors"].append(f"Apolice {apolice_id}: {e}")

    db.session.commit()
    summary["error_count"] = len(summary["errors"])
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"HubSpot sync completed: {summary}")
    return summary
```

- [ ] **Step 2: Verificar que sync.py compila e o import top-level funciona**

Run: `cd backend && python -c "from app.modules.hubspot_sync.sync import run_sync; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Rodar todos os testes hubspot_sync pra confirmar que nada quebrou**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/ -v`
Expected: todos passando (mapper: 7, client_batch: 9, sync_phases: 21, sync_lock: 3) = 40 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/hubspot_sync/sync.py
git commit -m "feat(sync): add run_sync orchestrator coordinating all 5 phases"
```

---

## Task 14: Teste de integração end-to-end (mockado)

**Files:**
- Create: `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py`

- [ ] **Step 1: Criar teste**

Criar `backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py`:

```python
"""End-to-end mocked test for run_sync.

Stubs the HubSpotClient at the module level and walks through a realistic
scenario with multiple apolices, tickets in mixed states, and verifies the
final state of `policies` plus the summary counts.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import Policy, User, UserRole, BenefitType


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(aid, beneficio):
    return {
        "id": aid,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": f"AP-{aid}",
            "parceiro": "BradescoTest",
        },
    }


def _ticket_props(ev_email="ev@x", client="ClientCo", mrr="2000",
                  closed="2025-09-01T00:00:00Z", pipeline="651307",
                  stage="11947921"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client,
        "mrr___receita_mensal": mrr,
        "closed_date": closed,
        "cotar___segmentacao_pipo": "M",
        "hs_pipeline": pipeline,
        "hs_pipeline_stage": stage,
    }


def test_run_sync_end_to_end(db_session):
    _ev("ev@x")

    # Scenario:
    #   A1 (Saúde) → T1 (valid Placement+Gongo+date+default deal) → KEEP
    #   A2 (Odonto) → T1 (same ticket as A1) → KEEP (multiple per ticket)
    #   A3 (Vida) → T2 (wrong pipeline) → SKIP wrong_pipeline
    #   A4 (Saúde e Odonto) → T3 (no default deal associated) → SKIP no_default_deal
    #   A5 (Saúde) → no ticket → SKIP no_ticket
    #   A6 (Saúde) → T4 (closed_date too old) → SKIP too_old

    fake_client = MagicMock()

    # Phase 1: search_deals — apolices
    fake_client.search_deals.return_value = {
        "results": [
            _apolice("A1", "Saúde"),
            _apolice("A2", "Odonto"),
            _apolice("A3", "Vida"),
            _apolice("A4", "Saúde e Odonto"),
            _apolice("A5", "Saúde"),
            _apolice("A6", "Saúde"),
        ],
        "paging": {},
    }

    # Phase 2: batch_read_associations(deals→tickets)
    # Phase 4 also calls batch_read_associations(tickets→deals).
    # We need to differentiate by argument.
    def fake_batch_assoc(from_type, to_type, ids):
        if (from_type, to_type) == ("deals", "tickets"):
            return {
                "A1": ["T1"],
                "A2": ["T1"],
                "A3": ["T2"],
                "A4": ["T3"],
                # A5 absent → no ticket
                "A6": ["T4"],
            }
        if (from_type, to_type) == ("tickets", "deals"):
            return {
                "T1": ["D1"],          # default deal exists
                "T3": ["D-NONDEFAULT"],  # no default deal
                # T4 was filtered out before this phase
            }
        return {}
    fake_client.batch_read_associations.side_effect = fake_batch_assoc

    # Phase 3 + Phase 4: batch_read_objects — tickets first, then deals
    def fake_batch_objects(object_type, ids, properties):
        if object_type == "tickets":
            return {
                "T1": _ticket_props(),
                "T2": _ticket_props(pipeline="999999"),  # wrong pipeline
                "T3": _ticket_props(),
                "T4": _ticket_props(closed="2024-01-01T00:00:00Z"),  # too old
            }
        if object_type == "deals":
            return {
                "D1": {"hs_pipeline": "default"},
                "D-NONDEFAULT": {"hs_pipeline": "999999"},
            }
        return {}
    fake_client.batch_read_objects.side_effect = fake_batch_objects

    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    # Verify summary
    assert summary["created"] == 2  # A1 and A2
    assert summary["updated"] == 0
    assert summary["skipped"]["no_ticket"] == 1     # A5
    assert summary["skipped"]["wrong_pipeline"] == 1  # T2 (filtered → A3 dropped)
    assert summary["skipped"]["too_old"] == 1       # T4 (filtered → A6 dropped)
    assert summary["skipped"]["no_default_deal"] == 1  # T3 → A4 dropped
    assert summary["error_count"] == 0

    # Verify DB state
    rows = Policy.query.order_by(Policy.hubspot_apolice_id).all()
    assert [r.hubspot_apolice_id for r in rows] == ["A1", "A2"]
    a1 = Policy.query.filter_by(hubspot_apolice_id="A1").one()
    a2 = Policy.query.filter_by(hubspot_apolice_id="A2").one()
    assert a1.hubspot_ticket_id == "T1"
    assert a2.hubspot_ticket_id == "T1"
    assert a1.benefit_type == BenefitType.SAUDE
    assert a2.benefit_type == BenefitType.ODONTO
    assert a1.mrr_projected == Decimal("2000")
    assert a2.mrr_projected == Decimal("2000")  # MRR replicated across rows
    assert a1.partner_operator == "BradescoTest"
    assert a1.numero_apolice == "AP-A1"
```

- [ ] **Step 2: Rodar**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/test_sync_integration.py -v`
Expected: 1 test passed.

- [ ] **Step 3: Rodar a suíte inteira de hubspot_sync**

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/ -v`
Expected: 41 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_modules/test_hubspot_sync/test_sync_integration.py
git commit -m "test(sync): add end-to-end mocked integration test for run_sync"
```

---

## Task 15: Migração Alembic (wipe + schema)

**Files:**
- Create: `backend/migrations/versions/<auto>_apolice_anchored_sync.py`

- [ ] **Step 1: Gerar migration vazia**

Run: `cd backend && alembic revision -m "apolice anchored sync wipe and schema"`
Expected: cria um novo arquivo em `migrations/versions/<rev>_apolice_anchored_sync.py`. Anota o `rev` gerado e confirma que `down_revision` aponta pra `080bc8ca92f5` (a última atual). Se não, ajusta manualmente.

- [ ] **Step 2: Implementar `upgrade()`**

Substituir o conteúdo do arquivo gerado por (preservando os IDs `revision`/`down_revision` que o alembic gerou):

```python
"""apolice anchored sync wipe and schema

Revision ID: <kept from generated file>
Revises: 080bc8ca92f5
Create Date: <kept from generated file>

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '<kept from generated file>'
down_revision = '080bc8ca92f5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. Wipe existing data (commissions FK → policies)
    op.execute("DELETE FROM commissions")
    op.execute("DELETE FROM policies")

    # 2. Add SAUDE_ODONTO to benefit_type enum (Postgres only — SQLite uses VARCHAR check)
    if dialect == "postgresql":
        # ALTER TYPE ADD VALUE cannot run inside a transaction block
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE benefit_type ADD VALUE IF NOT EXISTS 'SAUDE_ODONTO'")

    # 3. Add new columns and adjust unique constraints on policies
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hubspot_apolice_id', sa.String(length=100), nullable=False))
        batch_op.add_column(sa.Column('numero_apolice', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_policies_hubspot_apolice_id', ['hubspot_apolice_id'], unique=True)
        batch_op.create_index('ix_policies_numero_apolice', ['numero_apolice'])
        # Drop old unique on hubspot_ticket_id but keep a regular index
        batch_op.drop_index('ix_policies_hubspot_ticket_id')
        batch_op.create_index('ix_policies_hubspot_ticket_id', ['hubspot_ticket_id'], unique=False)


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_index('ix_policies_hubspot_ticket_id')
        batch_op.create_index('ix_policies_hubspot_ticket_id', ['hubspot_ticket_id'], unique=True)
        batch_op.drop_index('ix_policies_numero_apolice')
        batch_op.drop_index('ix_policies_hubspot_apolice_id')
        batch_op.drop_column('numero_apolice')
        batch_op.drop_column('hubspot_apolice_id')

    # NOTE: Postgres has no clean way to remove an enum value. SAUDE_ODONTO
    # remains in the type definition after downgrade. Acceptable trade-off.
```

- [ ] **Step 3: Verificar nome real do índice antigo**

Run: `cd backend && alembic upgrade head 2>&1 | tail -20`
Se der erro tipo "index does not exist", inspecionar o nome real do índice no schema atual:

```bash
cd backend && python -c "
from app import create_app
from app.extensions import db
app = create_app('test')
with app.app_context():
    db.create_all()
    insp = db.inspect(db.engine)
    for ix in insp.get_indexes('policies'):
        print(ix)
"
```

Ajustar o `drop_index('ix_policies_hubspot_ticket_id')` pro nome real (pode ser `policies_hubspot_ticket_id_key` em Postgres se foi criado como UNIQUE constraint, não index).

- [ ] **Step 4: Rodar upgrade local**

Em ambiente de dev (Postgres ou SQLite — confirmar qual o time usa):

Run: `cd backend && alembic upgrade head`
Expected: sem erros; nova revisão aplicada.

Verificar:
```bash
cd backend && python -c "
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    insp = db.inspect(db.engine)
    cols = [c['name'] for c in insp.get_columns('policies')]
    assert 'hubspot_apolice_id' in cols
    assert 'numero_apolice' in cols
    print('OK:', cols)
"
```

- [ ] **Step 5: Rodar downgrade pra confirmar reversibilidade**

Run: `cd backend && alembic downgrade -1 && alembic upgrade head`
Expected: ambos sem erros.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/
git commit -m "feat(sync): alembic migration — wipe data, add hubspot_apolice_id + numero_apolice, SAUDE_ODONTO enum"
```

---

## Task 16: Resolver TBDs (slug do pipeline default + property `parceiro`)

**Files:**
- Modify (possivelmente): `backend/app/modules/hubspot_sync/sync.py`

- [ ] **Step 1: Confirmar slug do pipeline default de deals**

Run (em terminal com `HUBSPOT_TOKEN` exportado):
```bash
curl -s -H "Authorization: Bearer $HUBSPOT_TOKEN" \
  "https://api.hubapi.com/crm/v3/pipelines/deals" | jq '.results[] | {id, label}'
```
Expected: lista de pipelines. Procurar o que tem `label: "Sales Pipeline"` (default do HubSpot). Anotar o `id` retornado — pode ser literal `"default"` ou um ID numérico.

Se for diferente de `"default"`:

Em `backend/app/modules/hubspot_sync/sync.py`, ajustar:
```python
DEFAULT_DEAL_PIPELINE_ID = "<id real>"
```

E também atualizar o teste `test_filter_tickets_keeps_those_with_default_deal` em `test_sync_phases.py` pra usar o mesmo valor. (Procurar `"default"` no arquivo e substituir.)

Run: `cd backend && pytest tests/test_modules/test_hubspot_sync/ -v`
Expected: tudo passando.

- [ ] **Step 2: Confirmar property `parceiro` na apólice**

Run:
```bash
curl -s -H "Authorization: Bearer $HUBSPOT_TOKEN" \
  "https://api.hubapi.com/crm/v3/properties/deals/parceiro" | jq '.name, .label'
```
Expected: `"parceiro"` e algum label tipo `"Parceiro"` ou `"Operadora"`. Se a property não existe (404), procurar pelo slug correto:

```bash
curl -s -H "Authorization: Bearer $HUBSPOT_TOKEN" \
  "https://api.hubapi.com/crm/v3/properties/deals" | jq '.results[] | select(.label | test("operadora|parceiro"; "i")) | {name, label}'
```

Ajustar `APOLICE_PROPERTIES` em `sync.py` e o lookup `apolice_props.get("parceiro")` em `_upsert_policy` pro slug correto.

- [ ] **Step 3: Confirmar property `numero_apolice`**

Run:
```bash
curl -s -H "Authorization: Bearer $HUBSPOT_TOKEN" \
  "https://api.hubapi.com/crm/v3/properties/deals/numero_apolice" | jq '.name, .label'
```
Expected: confirmação de que existe. Se não, mesmo procedimento de busca por label.

- [ ] **Step 4: Smoke test do sync em ambiente dev**

Run (com app rodando localmente, banco vazio):
```bash
cd backend && python -c "
from app import create_app
app = create_app()
with app.app_context():
    from app.modules.hubspot_sync.sync import run_sync
    summary = run_sync()
    print(summary)
"
```
Expected: summary com `created > 0`, `error_count == 0` (ou erros conhecidos rastreáveis).

Verificar contagem de rows:
```bash
cd backend && python -c "
from app import create_app
from app.extensions import db
from app.models import Policy
app = create_app()
with app.app_context():
    print('Total policies:', Policy.query.count())
    print('Distinct tickets:', db.session.query(Policy.hubspot_ticket_id).distinct().count())
    print('Sample row:', Policy.query.first().__dict__ if Policy.query.first() else None)
"
```

- [ ] **Step 5: Commit (se houve ajustes)**

```bash
git add backend/app/modules/hubspot_sync/sync.py backend/tests/test_modules/test_hubspot_sync/
git commit -m "fix(sync): use confirmed HubSpot pipeline/property slugs"
```

(Se nenhum ajuste foi necessário, pular esse step.)

---

## Self-review

### Spec coverage

| Spec section | Implemented in |
|---|---|
| Schema: `hubspot_apolice_id`, `numero_apolice`, drop unique on ticket | Tasks 1, 15 |
| Enum `SAUDE_ODONTO` | Tasks 1, 3, 15 |
| `search_deals` | Task 4 |
| `batch_read_associations` | Task 5 |
| `batch_read_objects` (com chunking 100) | Task 6 |
| Constants (pipeline IDs, date floor, properties) | Task 7 |
| `_fetch_apolices` | Task 7 |
| `_fetch_apolice_tickets` | Task 8 |
| `_fetch_and_validate_tickets` (pipeline+stage+date filters) | Task 9 |
| `_filter_tickets_with_default_deal` | Task 10 |
| `_upsert_policy` (is_locked respeitado, MRR replicado) | Tasks 11, 12 |
| `run_sync` orquestrador + summary com skipped breakdown | Task 13 |
| Mapper update | Task 3 |
| Testes por fase | Tasks 4–11 |
| Teste integration (multiple apolices same ticket, end-to-end) | Task 14 |
| Migração Alembic única (wipe + schema, ALTER TYPE em autocommit) | Task 15 |
| TBD: pipeline default slug | Task 16 step 1 |
| TBD: property `parceiro` | Task 16 step 2 |

Tudo coberto.

### Type / signature consistency check

- `_upsert_policy(apolice, ticket_props, owner_map, ticket_id=None)` — assinatura usada em Tasks 11, 12, 13 idêntica.
- `batch_read_associations(from_type, to_type, ids) → dict[str, list[str]]` — usado em `_fetch_apolice_tickets` e `_filter_tickets_with_default_deal` consistentemente.
- `batch_read_objects(object_type, ids, properties) → dict[str, dict]` — usado em `_fetch_and_validate_tickets` e `_filter_tickets_with_default_deal`.
- `summary["skipped"]` keys: `no_ticket`, `wrong_pipeline`, `not_gongo`, `too_old`, `no_default_deal` — definidos em `_new_summary` (Task 13) e referenciados consistentemente nas fases (Tasks 8, 9, 10).
- `Policy.hubspot_apolice_id` (Task 1) usado como filter key em `_upsert_policy` (Task 11).
