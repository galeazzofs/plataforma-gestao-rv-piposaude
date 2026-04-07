# Redesign — Financeiro & Apuração Trimestral

**Data:** 2026-04-07
**Autor:** Eric Valoz (RevOps Pipo Saúde) + Claude
**Status:** Draft (pendente review)

## Contexto

A plataforma atual tem um fluxo de apuração trimestral incompleto:

1. O parser do upload financeiro espera um XLSX com colunas inexistentes (`hubspot_ticket_id`, abas `NFs`/`Perks`) — incompatível com a planilha real "Consulta - Follow up Faturamento 2026.xlsx" que o RevOps usa.
2. O calculator (`run_quarterly_appraisal_v2`) faz match NF→Policy via `policy_id`, mas a planilha real **não tem ID de ticket**.
3. A apuração transitiona automaticamente CALCULATING → VALIDATING sem dar tempo do RevOps revisar os números calculados.
4. A tela de revisão existe mas não recebe dados (`ev_summary` não era serializado pelo backend).
5. Não há filtro global para excluir policies de EVs não-cadastrados / inativos.
6. Não há UI para editar manualmente uma Policy quando o HubSpot está errado (especialmente o campo `initial_installments_paid`, crítico para policies que já tinham parcelas pagas antes da plataforma existir).

Existe um **app antigo** (https://github.com/galeazzofs/pipo-gestao-rv) em React+Supabase que tinha a lógica de apuração funcionando. A função `processCommissions` no arquivo `src/components/ev/ProcessingEngine.tsx` é a referência. Este redesign porta essa lógica para o app novo, mantendo o modelo de Policies sincronizadas do HubSpot (sem cadastro manual de contratos).

## Objetivos

1. Parser que entende a planilha real.
2. Calculator que faz match NF→Policy por `(cliente, operadora, produto)` normalizados.
3. Vigência de 12 meses contada a partir de `policy.first_payment_real`, descontando `initial_installments_paid`.
4. Atingimento % por trimestre 100% manual, editável para qualquer trimestre (passado ou futuro).
5. Tela de revisão completa com rastreabilidade EV → Policy → linha de NF.
6. Filtro global excluindo policies sem EV ativo cadastrado.
7. UI para editar campos críticos da Policy (override do HubSpot).
8. Apuração para em CALCULATING após o cálculo; RevOps libera manualmente para VALIDATING.

## Não-objetivos (YAGNI)

- Cadastro manual de contratos (mantemos Policies do HubSpot como fonte).
- Versionamento de uploads financeiros (substitui o anterior).
- Suporte a Mental e Fitness como tipos de benefício (linhas são persistidas e marcadas como `PRODUTO_NAO_SUPORTADO` na tela de revisão, mas não geram comissão).
- Fuzzy matching de nomes (match exato com normalização).
- Multi-tenancy / multi-empresa.
- Rollback granular pós-LOCKED.

## Decisões-chave (do brainstorming)

| # | Decisão | Resposta |
|---|---|---|
| 1 | Origem dos contratos | Policies HubSpot, sem cadastro manual |
| 2 | Edição manual da Policy | Sim, com flag `is_locked` que protege do sync |
| 3 | Match key NF→Policy | `(cliente_mae, operadora, produto)` normalizados (lowercase, sem acento, trim) |
| 4 | Caso de policies duplicadas | Pega a mais recente (maior `closed_date`) ainda dentro da vigência |
| 5 | Início da vigência | `policy.first_payment_real` |
| 6 | Vigência | 12 meses, descontando `initial_installments_paid` |
| 7 | Status Recebimento | Só `RECEBIDO` |
| 8 | Tipo Receita | Todos contam (Comissão, Fee por Vida, Premiação, Patrocínio, Agenciamento) |
| 9 | Estornos (NF Líquido < 0) | Entram na soma (subtraem da comissão) |
| 10 | Produtos Mental/Fitness | Persistidos como `PRODUTO_NAO_SUPORTADO`, visíveis na revisão, não entram na comissão |
| 11 | Atingimento % | 100% manual, editável por trimestre, snapshot do trimestre do gongo |
| 12 | Auto-update de `installments_paid` | Sim, conforme NFs entram no cálculo |
| 13 | Reprocessamento | Botão "Recalcular" zera Commissions e roda do zero |
| 14 | Upload duplicado | Substitui o anterior do mesmo trimestre |
| 15 | Mapeamento segment → matriz | PP→PP/P, P→PP/P, M→M, G→G+ |
| 16 | "EV ativo" | `User.role == EV AND User.active == true` (coluna existente é `active`, não `is_active`) |
| 17 | Endpoint auto-cálculo achievements | Manter (como ferramenta de baseline opcional) |

## Arquitetura

### Camadas afetadas

```
Frontend (CLJS)
├── views/revops/policies.cljs           [novo: edit modal]
├── views/revops/appraisal_review.cljs   [completar drill-down]
├── views/revops/financial_upload.cljs   [novo flow de feedback]
├── views/revops/achievements.cljs       [novo: editor por trimestre]
└── api/endpoints.cljs                   [novos endpoints]

Backend (Flask)
├── api/v1/policies.py                   [PUT, edição com lock]
├── api/v1/financial.py                  [novo upload, novo serializer]
├── api/v1/workflow.py                   [serializer enriquecido com ev_summary]
├── api/v1/admin.py                      [achievements editor]
├── modules/financial/
│   ├── parser.py                        [reescrever]
│   ├── matcher.py                       [novo: match NF→Policy]
│   └── processor.py                     [reescrever]
├── modules/commissions/calculator.py    [reescrever run_quarterly_appraisal]
├── modules/workflow/state_machine.py    [já corrigido: para em CALCULATING]
└── modules/hubspot_sync/sync.py         [respeitar is_locked]

DB (Postgres)
├── policies                             [+ is_locked]
├── financial_imports                    [schema redesenhado]
├── commission_pct_table                 [seed da matriz]
└── audit_logs                           [novas entradas para edits]
```

### Fluxo end-to-end

```
1. Sync HubSpot                  → policies (auto, mas respeita is_locked)
2. RevOps edita Policy           → grava override + is_locked=true
3. RevOps cadastra achievements  → ev_quarter_achievements (manual por EV/trimestre)
4. RevOps faz upload XLSX        → financial_imports (substitui período)
5. RevOps cria Apuração Q1/2026  → status DRAFT
6. RevOps clica "Iniciar Cálculo"→ status CALCULATING (sync), roda calculator
7. Calculator                    → matches, valida vigência, calcula commissions
8. RevOps revisa em /review      → drill-down completo
9. RevOps clica "Liberar"        → status VALIDATING, EVs validam
10. EVs validam/contestam        → status REVIEWING (fluxo existente, não muda)
11. Finance aprova               → APPROVED → LOCKED
```

## Componentes detalhados

### 1. Filtro global "EVs ativos"

**Problema:** policies de EVs ex-funcionários ou EVs não cadastrados na plataforma estão poluindo dashboards e cálculos.

**Solução:** helper centralizado.

```python
# backend/app/modules/policies/filters.py (novo)
from app.models import Policy, User, UserRole
from app.extensions import db

def active_ev_policies_query():
    """Base query that returns only policies tied to an active EV user."""
    return (
        db.session.query(Policy)
        .join(User, Policy.ev_id == User.id)
        .filter(User.role == UserRole.EV, User.active.is_(True))
    )
```

Todos os endpoints que listam/processam policies usam essa base. Específicos:
- `GET /policies` (listagem)
- `GET /dashboard/*` (RevOps, Finance, Gerente)
- `run_quarterly_appraisal()` (cálculo)
- Tela de Apólices

O sync do HubSpot continua puxando tudo (não filtra na entrada) — o filtro é só na leitura.

**Migration:** **NÃO precisa** adicionar coluna — `User.active` (Boolean, default true, NOT NULL) já existe em `backend/app/models/user.py:25`.

### 2. Edição manual da Policy

**Schema:**

```sql
ALTER TABLE policies ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT false;
```

**Endpoint:**

```
PUT /api/v1/policies/{id}
Body: { ev_id?, first_payment_real?, closed_date?, initial_installments_paid?,
        segment?, partner_operator?, client_id? }
```

- Requires role: ADMIN
- Sets `is_locked = true` automaticamente
- Atualiza `updated_at`
- Grava entrada em `audit_logs` (`table_name='policies'`, `record_id=policy.id`, `action='UPDATE'`, `old_values={...}`, `new_values={...}`, `user_id=current_user.id`) — colunas reais do model `AuditLog`

**Sync respeita o lock:**

```python
# Em sync._process_ticket(), antes de atualizar campos:
if policy.is_locked:
    # Só atualiza campos que não estão na lista de "lockable":
    # mantém ev_id, first_payment_real, closed_date, segment, partner_operator
    # ainda atualiza: hubspot_ticket_id, deal_id, mrr_actual, etc.
    pass
```

**Frontend:** modal de edição na página `/policies` (admin) abrindo ao clicar numa linha. Campos do form correspondem ao endpoint.

**Audit:** toda edição visível na página `/admin/audit-log`.

### 3. Atingimento % manual

**Schema:** `ev_quarter_achievements` já existe. Sem mudança.

**Endpoint existente:** `POST /api/v1/admin/ev-achievements` (já implementado).

**Manter:** `POST /api/v1/admin/ev-achievements/calculate` (auto-baseline opcional).

**Pré-check do calculator (snapshot por gongo, não pelo trimestre da apuração):**

```python
def validate_achievements_for_appraisal(quarter, year):
    """Verifies that every (ev, gongo_quarter, gongo_year) combination
    needed by this appraisal has a stored achievement.

    The calculator looks up achievement using the gongo quarter of each
    policy (NOT the apuração quarter), so we need to validate the union
    of all gongo quarters that policies in the active set fall into.
    """
    from app.modules.policies.filters import active_ev_policies_query

    # All policies that COULD generate commission this apuração:
    # any active-EV policy whose first_payment_real makes it possible
    # for an NF in (quarter, year) to land in vigência.
    policies = active_ev_policies_query().all()

    needed = set()  # set of (ev_id, gongo_q, gongo_y)
    for p in policies:
        if not p.closed_date or not p.ev_id:
            continue
        gongo_q = (p.closed_date.month - 1) // 3 + 1
        needed.add((p.ev_id, gongo_q, p.closed_date.year))

    missing = []
    for ev_id, gq, gy in needed:
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=gq, year=gy
        ).first()
        if ach is None or ach.achievement_pct is None:
            user = User.query.get(ev_id)
            missing.append(f"{user.name if user else ev_id} → Q{gq}/{gy}")

    return missing
```

Se `missing` não vazio, calculator levanta `MissingAchievementsError("Faltam achievements: <list>")` antes de iniciar qualquer processamento.

**Snapshot por gongo:** quando uma NF de Q1/2026 é processada para uma Policy gongada em Q4/2025, o calculator usa o achievement de Q4/2025 do EV (não o de Q1/2026).

**Interação com filtro "EV ativo":** `active_ev_policies_query` exclui policies de EVs inativos **antes** do calculator. Logo `validate_achievements_for_appraisal` só pede achievements de EVs cujas policies passaram no filtro. Edge case: EV ativo em Q4/2025 mas hoje inativo → suas policies somem do cálculo. Se isso for indesejado, admin deve reativar o EV temporariamente.

**Frontend:** nova página `/admin/achievements` com:
- Filtro por ano + trimestre
- Tabela: EV | Total MRR Q | Meta MRR | % atingimento (editável) | Final?
- Botão "Auto-calcular baseline" → chama o endpoint de auto-cálculo
- Botão "Salvar" → POST individual ou batch

Permite editar passado e futuro (sem restrição de data).

### 4. Parser do financeiro (reescrita)

**Arquivo novo:** `backend/app/modules/financial/parser.py`

**Assinatura:**

```python
def parse_financial_xlsx(filepath: str, target_quarter: int, target_year: int) -> ParseResult
```

**Lógica:**

1. Abrir XLSX, pegar primeira aba (qualquer nome).
2. Detectar linha de header: scanear primeiras 20 linhas, encontrar a que tem `Cliente "Mãe"` ou `Operadora`.
3. Mapear índices das colunas necessárias (busca tolerante a case e espaços):
   - `cliente_mae` ← coluna que contém "cliente" e ("mae" ou "mãe")
   - `operadora` ← coluna que contém "operadora"
   - `produto` ← coluna que contém "produto"
   - `nf_liquido` ← coluna que contém "nf" e "liquido"
   - `data_recebimento` ← coluna que contém "data" e "recebimento"
   - `mes_recebimento` ← coluna que contém "mes" e "recebimento" (fallback: extrair do data_recebimento)
   - `status_recebimento` ← coluna que contém "status" e "recebimento"
   - `tipo_receita` ← coluna que contém "tipo" e "receita"
4. Iterar linhas de dados.
5. Aplicar pré-filtros (apenas estes — Mental/Fitness NÃO são descartados):
   - `status_recebimento != 'RECEBIDO'` → skip (descarta A RECEBER)
   - `cliente_mae` vazio → skip (lixo)
   - `nf_liquido` None → skip (linha sem valor; mas 0 e negativos passam)
   - `data_recebimento` não cai em `target_quarter/target_year` → skip (escopo da apuração)
6. Linhas que passam o filtro são **persistidas** em `financial_imports` com `match_status='UNMATCHED'` (default). O calculator depois sobrescreve esse status.
7. Retornar `ParseResult` com:
   ```
   { rows: [...], stats: { total_lidas, descartadas_status, descartadas_periodo, persistidas }, errors: [] }
   ```

**Tolerância:** datas vêm como `datetime` do openpyxl (com `data_only=True`). Se vier string, tenta `dd/mm/yyyy`.

**Não persiste nada.** Só parseia. A persistência é responsabilidade do `processor`.

### 5. Matcher NF→Policy

**Arquivo novo:** `backend/app/modules/financial/matcher.py`

```python
import unicodedata
from collections import defaultdict
from datetime import date

def normalize(s: str) -> str:
    """lowercase + strip accents + trim spaces"""
    if not s:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower().strip())
        if unicodedata.category(c) != 'Mn'
    )

def build_policy_index(policies):
    """Build O(1) lookup index keyed by (cliente_n, operadora_n, benefit_type).

    Each value is a list of policies sorted by closed_date DESC, so the
    caller can iterate from most-recent to oldest when picking the policy
    whose vigência window includes a given NF date.
    """
    index = defaultdict(list)
    for p in policies:
        if not p.client or not p.benefit_type:
            continue
        key = (
            normalize(p.client.name),
            normalize(p.partner_operator or ''),
            p.benefit_type.value,  # already SAUDE/ODONTO/VIDA
        )
        index[key].append(p)
    # Sort each bucket by closed_date desc
    for key in index:
        index[key].sort(key=lambda p: p.closed_date or date.min, reverse=True)
    return dict(index)
```

**Match key:** `(normalize(cliente_mae), normalize(operadora), benefit_type)`. The benefit_type is mapped from the XLSX's `produto` column at the calculator level (`Saúde→SAUDE`, etc).

**Performance:** O(N) build + O(1) lookup per NF row. For 1670 policies + 9k NFs/quarter, total < 1s.

**Tests:** unit tests para `normalize` (acentos, espaços, vazio, None) e `build_policy_index` (buckets por chave, sort por closed_date desc, policies sem client ou benefit_type ignoradas).

### 5b. Matriz `commission_pct_table`

**Colunas reais (do model `CommissionPctTable`):** `version, segment, achievement_min, achievement_max, commission_pct, valid_from, valid_until, created_by`. Helper de consulta existente: `lookup_commission_pct(segment, achievement_pct)` em `app/modules/commissions/pct_lookup.py` — **reusar, não criar função nova**.

**Seed (12 entradas — 4 segments × 3 faixas, em formato decimal 0–1):**

| segment | achievement_min | achievement_max | commission_pct |
|---|---|---|---|
| PP | 0.0000 | 0.4999 | 0.07 |
| PP | 0.5000 | 0.9999 | 0.08 |
| PP | 1.0000 | 99.9999 | 0.10 |
| P  | 0.0000 | 0.4999 | 0.07 |
| P  | 0.5000 | 0.9999 | 0.08 |
| P  | 1.0000 | 99.9999 | 0.10 |
| M  | 0.0000 | 0.4999 | 0.05 |
| M  | 0.5000 | 0.9999 | 0.06 |
| M  | 1.0000 | 99.9999 | 0.08 |
| G  | 0.0000 | 0.4999 | 0.03 |
| G  | 0.5000 | 0.9999 | 0.04 |
| G  | 1.0000 | 99.9999 | 0.06 |

**Idempotência da migration:** verifica se já existe uma versão `current_version` com essas 12 linhas exatas. Se sim → no-op. Se não → cria `version = current_version + 1` com as 12 linhas e marca `valid_from = today`.

**Unidades de `achievement_pct`:**
- **Storage** (DB): Decimal `0–99.9999` em forma fracionária (75% → `0.7500`, 120% → `1.2000`)
- **Display/UI** (frontend): apresentado como percentual (`achievement_pct × 100`)
- **API JSON** (`ev_summary.achievement_pct`): convertido pra percentual no serializer (78.5 = 78.5%)
- **Input do RevOps** na tela de achievements: aceita o valor em percentual, converte pra fração antes de gravar

A faixa "≥100%" do seed cobre até 99.9999 (=9999%) pra não quebrar com superatingimento. **Sem produto-específico** — a matriz é a mesma pra Saúde/Odonto/Vida.

**Coluna `nf_valor_liquido` no model `FinancialImport`:** já existe (`Numeric(12,2)`). A spec usa o nome real `nf_valor_liquido` em todo o calculator e migration. **Aliasing pro JSON da API**: o serializer expõe como `nf_liquido` no `ev_summary` (mais curto, alinha com a coluna da planilha). É só um rename de display; o backend persiste/lê `nf_valor_liquido`.

### 6. Schema novo `financial_imports`

**Estado atual no DB:** vazio (`SELECT count(*) FROM financial_imports → 0`). Confirmado pela query inicial de diagnóstico (Q1/2026 não tem NFs cadastradas). **A migration é destrutiva: TRUNCATE da tabela.** Não há audit trail histórico a preservar — o schema antigo nunca foi usado em produção.

**Migration (idempotente):**

```sql
-- Wipe (safe: tabela está vazia)
TRUNCATE TABLE financial_imports;

-- Drop legacy unique constraint
ALTER TABLE financial_imports DROP CONSTRAINT IF EXISTS uq_financial_policy_month;

-- Make policy_id nullable
ALTER TABLE financial_imports ALTER COLUMN policy_id DROP NOT NULL;

-- Add new columns
ALTER TABLE financial_imports
  ADD COLUMN IF NOT EXISTS cliente_mae VARCHAR(500),
  ADD COLUMN IF NOT EXISTS operadora VARCHAR(255),
  ADD COLUMN IF NOT EXISTS produto VARCHAR(50),
  ADD COLUMN IF NOT EXISTS tipo_receita VARCHAR(100),
  ADD COLUMN IF NOT EXISTS status_recebimento VARCHAR(50),
  ADD COLUMN IF NOT EXISTS data_recebimento DATE,
  ADD COLUMN IF NOT EXISTS match_status VARCHAR(30) NOT NULL DEFAULT 'UNMATCHED',
  ADD COLUMN IF NOT EXISTS matched_at TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS ix_financial_imports_quarter_year ON financial_imports(quarter, year);
CREATE INDEX IF NOT EXISTS ix_financial_imports_match_status ON financial_imports(match_status);
CREATE INDEX IF NOT EXISTS ix_financial_imports_policy_id ON financial_imports(policy_id);
```

**`cliente_mae VARCHAR(500)`** — folga generosa porque nomes de clientes na planilha podem ser longos (razão social completa).

**`match_status` valores possíveis:**
- `MATCHED` — bateu com policy, dentro da vigência, conta na comissão
- `UNMATCHED` — não achou policy correspondente
- `EXPIRED` — bateu, mas vigência da policy já passou
- `PRE_VIGENCIA` — bateu, mas data_recebimento < first_payment_real
- `PRODUTO_NAO_SUPORTADO` — produto da NF é Mental ou Fitness (persistido pra ficar visível na revisão)
- ~~`EV_INATIVO`~~ — **REMOVIDO da enum.** O filtro global (`active_ev_policies_query`) já exclui policies de EVs inativos antes do matching, então essas NFs caem em `UNMATCHED` (correto: do ponto de vista do calculator, a policy não existe). Se ainda for útil rastrear separadamente, criar um relatório à parte cruzando NFs UNMATCHED com policies inativas.

**IMPORTANTE:** todas as linhas que passam pelo parser são **persistidas** (mesmo as que vão ser descartadas do cálculo), pra que apareçam na tela de revisão. O parser **não filtra** Mental/Fitness — só marca o `match_status` correto. O **único** filtro do parser é `status_recebimento != 'RECEBIDO'` (descarta A RECEBER) e linhas com `cliente_mae` ou `nf_liquido` vazios.

**Substituição (re-upload do mesmo trimestre):**

```python
# Bloqueia se a apuração desse trimestre já está LOCKED
appraisal = Appraisal.query.filter_by(quarter=q, year=y).first()
if appraisal and appraisal.status == AppraisalStatus.LOCKED:
    raise UploadBlockedError(f"Apuração de Q{q}/{y} já está LOCKED. Re-upload não permitido.")

# Caso contrário, deleta e regrava
FinancialImport.query.filter_by(quarter=q, year=y).delete()
db.session.flush()
# ... insere as novas linhas
```

**`import_batches`:** uma linha por upload. Campos: `filename`, `uploaded_by`, `nf_count` (linhas inseridas), `status` (sempre `CONFIRMED` no novo flow — não tem mais 2-step preview). Batches antigos do mesmo (q,y) ficam órfãos no histórico (`import_batches.status='SUPERSEDED'`) — não bloqueiam nada, só servem de histórico de quem subiu o quê e quando.

### 7. Calculator (reescrita)

**Arquivo:** `backend/app/modules/commissions/calculator.py`

**Mudança crítica em `is_final`:** o calculator **NÃO** seta `commission.is_final = True` em nenhuma circunstância. O flag é setado **somente** quando `transition_appraisal(appraisal, LOCKED)` é chamado (no `state_machine.py`), via:

```python
# em state_machine.py, dentro de transition_appraisal:
if new_status == AppraisalStatus.LOCKED:
    appraisal.locked_at = datetime.now(timezone.utc)
    appraisal.approved_by_finance = kwargs.get("approved_by")
    # Marca todas as commissions desta apuração como finais
    Commission.query.filter_by(
        quarter=appraisal.quarter, year=appraisal.year, is_final=False
    ).update({"is_final": True})
```

Isso garante que recalcular antes do LOCK funciona (todas as commissions estão `is_final=False`).

**Vigência — REGRA ÚNICA (date-based):**

A vigência de uma policy é o intervalo `[start, end]`:

- `start = policy.first_payment_real` (se nulo, policy não pode gerar comissão → PRE_VIGENCIA)
- `end = first_payment_real + relativedelta(months=12 - initial_installments_paid)`

**`initial_installments_paid` ENCURTA a janela pela direita** (não desloca o início). Exemplo: se `initial_installments_paid = 6` e `first_payment_real = 2026-01-15`, então `end = 2026-07-15` (6 meses depois). Antes da plataforma, presumimos que esses 6 primeiros meses já foram pagos pelo sistema antigo, então só os próximos 6 contam.

`installments_paid` (sem o "initial") **não** afeta a janela — é só métrica informativa, recomputada determinísticamente a cada cálculo (ver passo 5 abaixo).

**Função principal:**

```python
def run_quarterly_appraisal(quarter: int, year: int) -> dict:
    """
    Pre-conditions:
    - validate_achievements_for_appraisal(quarter, year) returns []
    - financial_imports populated for this quarter (parser already ran)

    Process:
    """
    # ── 1. Pre-check ──────────────────────────────────────────
    missing = validate_achievements_for_appraisal(quarter, year)
    if missing:
        raise MissingAchievementsError(missing)

    # ── 2. Wipe non-final commissions and reset installments_paid ─
    # Reset to baseline: installments_paid = initial_installments_paid + count(NFs from LOCKED commissions)
    # This makes recalc idempotent.
    Commission.query.filter_by(quarter=quarter, year=year, is_final=False).delete()
    db.session.flush()

    # Reset installments_paid for all active-EV policies to baseline
    policies = active_ev_policies_query().all()
    locked_nfs_per_policy = dict(
        db.session.query(
            FinancialImport.policy_id,
            db.func.count(FinancialImport.id),
        ).join(Commission, Commission.policy_id == FinancialImport.policy_id)
         .filter(Commission.is_final.is_(True),
                 FinancialImport.match_status == 'MATCHED')
         .group_by(FinancialImport.policy_id)
         .all()
    )
    for p in policies:
        p.installments_paid = (p.initial_installments_paid or 0) + locked_nfs_per_policy.get(p.id, 0)

    # ── 3. Build matcher index (O(1) lookup) ─────────────────
    from app.modules.financial.matcher import build_policy_index, normalize
    policy_index = build_policy_index(policies)
    # policy_index: dict[(cliente_n, operadora_n, benefit_type)] -> sorted list of policies (by closed_date desc)

    # ── 4. Iterate financial_imports for this quarter ────────
    nfs = FinancialImport.query.filter_by(
        quarter=quarter, year=year, status_recebimento='RECEBIDO'
    ).all()

    benefit_map = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}

    for nf in nfs:
        produto_n = normalize(nf.produto or '')
        benefit = benefit_map.get(produto_n)
        if benefit is None:
            nf.match_status = 'PRODUTO_NAO_SUPORTADO'
            nf.policy_id = None
            continue

        key = (normalize(nf.cliente_mae or ''), normalize(nf.operadora or ''), benefit)
        candidates = policy_index.get(key, [])
        if not candidates:
            nf.match_status = 'UNMATCHED'
            nf.policy_id = None
            continue

        # Pick most recent policy whose vigência window includes data_recebimento
        matched = None
        for policy in candidates:  # already sorted desc by closed_date
            if not policy.first_payment_real:
                continue
            window_end = policy.first_payment_real + relativedelta(
                months=12 - (policy.initial_installments_paid or 0)
            )
            if nf.data_recebimento < policy.first_payment_real:
                continue
            if nf.data_recebimento > window_end:
                continue
            matched = policy
            break

        if matched is None:
            # Has candidates but none in vigência → mark with the closest reason
            best = candidates[0]  # most recent
            if not best.first_payment_real:
                nf.match_status = 'PRE_VIGENCIA'
            elif nf.data_recebimento < best.first_payment_real:
                nf.match_status = 'PRE_VIGENCIA'
            else:
                nf.match_status = 'EXPIRED'
            nf.policy_id = best.id
            continue

        # Lookup achievement at gongo quarter (NOT current quarter)
        gongo_q = (matched.closed_date.month - 1) // 3 + 1
        gongo_y = matched.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=matched.ev_id, quarter=gongo_q, year=gongo_y
        ).first()
        achievement = ach.achievement_pct if ach else Decimal('0')

        commission_pct, version = lookup_commission_pct(
            matched.segment.value if matched.segment else 'P',
            achievement,
        )
        if commission_pct is None:
            commission_pct = Decimal('0')

        commission_amount = (Decimal(nf.nf_valor_liquido) * commission_pct).quantize(Decimal('0.01'))

        # Upsert Commission (accumulate per policy/quarter)
        comm = Commission.query.filter_by(
            policy_id=matched.id, quarter=quarter, year=year
        ).first()
        if comm is None:
            comm = Commission(
                policy_id=matched.id, ev_id=matched.ev_id,
                quarter=quarter, year=year,
                segment=matched.segment.value if matched.segment else None,
                achievement_pct=achievement,
                commission_pct=commission_pct,
                commission_pct_version=version,
                monthly_actual=Decimal('0'),
                total_actual=Decimal('0'),
                is_final=False,  # never set to True here
            )
            db.session.add(comm)
        comm.monthly_actual = (comm.monthly_actual or Decimal('0')) + commission_amount
        comm.total_actual = (comm.total_actual or Decimal('0')) + commission_amount

        # Bookkeeping on the NF row
        nf.policy_id = matched.id
        nf.match_status = 'MATCHED'
        nf.matched_at = datetime.now(timezone.utc)

        # Increment counter (reset to baseline at start of this fn)
        matched.installments_paid = (matched.installments_paid or 0) + 1

    db.session.flush()
    return build_summary(quarter, year)
```

**Performance:**

Volume real: ~109k linhas no XLSX → após filtro `RECEBIDO` ≈ 26k → após filtro de período (1 trimestre) ≈ 6-9k. Policies ativas: ~1670, mas só as que matcham por chave entram no candidato.

A função `build_policy_index(policies)` retorna `dict[(cliente_n, operadora_n, benefit_type)] -> [policies sorted by closed_date desc]`. Construção: O(N×k) com k=3 normalizações. Lookup por NF: O(1) + O(c) onde c = nº de policies do cliente (geralmente 1-2).

Total estimado: < 3s pra um trimestre. Bulk commit único no final.

**Erros:**

- `MissingAchievementsError` antes de qualquer escrita → cálculo aborta, nada mudou
- `OperationalError` no commit → rollback automático do SQLAlchemy
- Linhas individuais que dão pau (ex: data inválida): marcam o NF com `match_status='UNMATCHED'` e seguem; cálculo não é interrompido
- `lookup_commission_pct` retorna None se a faixa não existe → tratado como `commission_pct = 0` (linha vai pra revisão zerada)

### 8. Tela de revisão (drill-down)

**Endpoint:** `GET /api/v1/appraisals/{id}` retorna `ev_summary` enriquecido.

**Schema da resposta:**

```json
{
  "data": {
    "id": "...", "quarter": 1, "year": 2026, "status": "CALCULATING",
    "totals": {
      "total_commission": 123456.78,
      "total_nf_processed": 1000000.00,
      "ev_count": 12,
      "policy_count": 145,
      "nf_row_count": 26000,
      "unmatched_count": 432,
      "expired_count": 89
    },
    "ev_summary": [
      {
        "ev_id": "...", "ev_name": "...",
        "achievement_pct": 78.5,
        "policies_count": 12,
        "nf_count": 47,
        "total_commission": 12345.67,
        "policies": [
          {
            "policy_id": "...", "client_name": "...", "operadora": "...",
            "produto": "Saúde", "segment": "M",
            "first_payment_real": "2026-01-15",
            "vigencia_month": 3, "vigencia_total": 12,
            "achievement_used_pct": 75.0,
            "achievement_quarter": "Q4/2025",
            "nfs": [
              {
                "data_recebimento": "2026-02-10",
                "tipo_receita": "Comissão",
                "nf_liquido": 5000.00,
                "commission_pct": 0.06,
                "commission_amount": 300.00,
                "status": "MATCHED"
              }
            ],
            "subtotal": 850.00
          }
        ]
      }
    ],
    "unmatched": [
      { "cliente_mae": "...", "operadora": "...", "produto": "...",
        "data_recebimento": "...", "nf_liquido": 1000.00, "reason": "UNMATCHED" }
    ],
    "expired": [ /* mesmo formato + policy_id que casou + reason */ ]
  }
}
```

**UI:** tabs `Por EV` / `Não matcheadas` / `Fora de vigência` / `Não suportado`.

- **Por EV**: tabela colapsável, expand → drill por policy → expand → linhas de NF. Filtros laterais: por **Tipo Receita** (Comissão / Fee por Vida / Premiação / Patrocínio / Agenciamento / Todos) e por **Operadora**.
- **Não matcheadas** (`UNMATCHED`): tabela com export CSV. Mostra cliente/operadora/produto/data/valor.
- **Fora de vigência** (`EXPIRED` + `PRE_VIGENCIA`): tabela com export CSV + link pro edit da policy que casou. Útil pra ajustar `first_payment_real` ou `initial_installments_paid`.
- **Não suportado** (`PRODUTO_NAO_SUPORTADO`): linhas de Mental/Fitness só pra visibilidade.

**Botões header:**
- `🔄 Recalcular` → `POST /appraisals/{id}/recalculate` (chama `run_quarterly_appraisal` de novo)
- `📤 Re-upload financeiro` → navega pro upload page
- `✅ Liberar para Validação EVs` → `POST /appraisals/{id}/transition` body `{to: "VALIDATING"}`

### 9. State machine

Já corrigido na sessão anterior: `transition_appraisal` roda o calculator quando vai pra CALCULATING e fica nesse status (não auto-transitiona).

`VALID_TRANSITIONS` permanece igual.

**Renomeação do calculator:**

- Hoje em `calculator.py` existem `run_quarterly_appraisal()` (linha 136) e `run_quarterly_appraisal_v2()` (linha 144). A V1 já é apenas um alias que chama a V2.
- **Mudança:** apagar a função `run_quarterly_appraisal_v2`, escrever a nova implementação direto em `run_quarterly_appraisal` (sem sufixo). Atualizar o import em `state_machine.py:46` de `run_quarterly_appraisal_v2` → `run_quarterly_appraisal`.
- Tests que importam `run_quarterly_appraisal_v2` são atualizados (busca + replace global).

**Adicional ao LOCK transition:** marcar todas as commissions do trimestre como `is_final=True` (ver seção 7).

## Modelo de dados final

```
users
├── id (PK)
├── email, name, role (ADMIN/REVOPS/EV/GERENTE/FINANCE)
└── active

policies
├── id (PK), hubspot_ticket_id (unique)
├── ev_id (FK users), client_id (FK clients)
├── segment (PP/P/M/G)
├── partner_operator (text)
├── benefit_type (SAUDE/ODONTO/VIDA)
├── closed_date (gongo date — base do snapshot de achievement)
├── first_payment_real (base da vigência de 12m)
├── installments_paid (int)
├── initial_installments_paid (int) ⭐
├── is_locked (bool) ⭐ NOVO
└── ...

ev_quarter_achievements
├── id (PK)
├── ev_id (FK users), quarter, year
├── total_mrr, mrr_target, achievement_pct (manual)
└── is_final

financial_imports (REDESENHADO)
├── id (PK)
├── policy_id (FK policies, NULL se UNMATCHED)
├── import_batch_id (FK)
├── quarter, year
├── nf_valor_liquido (NUMERIC, pode ser negativo)
├── nf_mes_recebimento (YYYY-MM)
├── data_recebimento (DATE) ⭐ NOVO
├── cliente_mae, operadora, produto, tipo_receita, status_recebimento ⭐ NOVO
├── match_status (MATCHED/UNMATCHED/EXPIRED/PRE_VIGENCIA/PRODUTO_NAO_SUPORTADO) ⭐ NOVO
└── matched_at ⭐ NOVO

commissions
├── id (PK)
├── policy_id, ev_id, quarter, year
├── segment, achievement_pct, commission_pct, commission_pct_version
├── monthly_actual, total_actual
├── monthly_estimated, total_estimated
└── is_final

commission_pct_table
├── id (PK), version
├── version, segment, achievement_min, achievement_max, commission_pct, valid_from, valid_until, created_by
└── (seed: 12 entradas — 4 segments × 3 faixas)
```

## Erros e edge cases

| Caso | Tratamento |
|---|---|
| Achievement faltando pra um EV ativo | `MissingAchievementsError` antes de rodar; cálculo aborta |
| Policy sem `first_payment_real` | NF marcada como `PRE_VIGENCIA` |
| Policy com `is_locked=true` | Sync HubSpot não sobrescreve campos lockáveis |
| Múltiplas policies no mesmo (cliente,operadora,produto) | Pega a mais recente; antiga aparece em log de "ambiguidade" |
| NF Líquido negativo | Entra na soma normalmente; pode dar comissão negativa |
| Produto Mental/Fitness | Persistido com `match_status=PRODUTO_NAO_SUPORTADO`, visível na revisão, não soma na comissão |
| Cliente sem normalização match | UNMATCHED, RevOps revisa manualmente |
| Re-upload | DELETE FROM financial_imports WHERE quarter=q AND year=y; INSERT |
| Recalcular após edição de policy | Botão "Recalcular" zera Commissions e roda do zero |
| Apuração já LOCKED | Recalcular bloqueado; Commissions com is_final=true protegidas |
| EV inativado depois do cálculo | Próxima execução exclui suas NFs (filtro global) |

## Permissões

**Nota sobre roles:** o sistema tem 5 roles: `ADMIN, FINANCE, GERENTE, EV, CN`. **Não existe role `REVOPS`** — o que chamamos de RevOps no negócio é mapeado para `ADMIN` no model. Eric (RevOps Pipo Saúde) tem role `ADMIN`.

| Ação | Roles |
|---|---|
| Editar Policy | ADMIN |
| Editar achievement | ADMIN |
| Upload financeiro | ADMIN, FINANCE |
| Iniciar/recalcular apuração | ADMIN |
| Liberar pra VALIDATING | ADMIN |
| Validar deals (EV) | EV (própria) |
| Aprovar pagamento | FINANCE |

## Plano de testes

**Backend (pytest):**
- `test_parser.py`: planilha real (sample 100 linhas), planilha vazia, headers em linha errada, valores negativos, datas como string vs datetime
- `test_matcher.py`: normalize (acentos, espaços, case), match exato, multi-policy escolhe mais recente, produto não suportado
- `test_calculator.py`: cenário feliz (1 EV, 1 policy, 3 NFs), policy expirada, NF pre-vigência, achievement faltando, recalculo limpa antigas, idempotência
- `test_workflow.py`: state machine para em CALCULATING, transição manual pra VALIDATING

**Frontend (manual smoke):**
- Editar policy → reflete na lista
- Upload da planilha real → preview → confirma → financial_imports populado
- Cadastrar achievements → rodar apuração → ver tela de revisão com drill-down
- Recalcular após edição
- Liberar pra VALIDATING → confirma transição

## Migrations

Ordem:

1. `add_is_locked_to_policies.py`
2. `redesign_financial_imports.py` (drop constraint, add columns)
3. `seed_commission_pct_table.py` (popular as 12 entradas da matriz, idempotente — ver tabela em **Componentes detalhados → Matriz**)
<!-- migration #4 removida: User.active já existe no model atual -->


## Riscos

| Risco | Mitigação |
|---|---|
| Match cliente errado por nome divergente | Tela de "não matcheadas" deixa RevOps ver e ajustar a Policy ou cliente |
| Performance: 26k NFs × 1670 policies | Bulk load + dict lookup; estimativa < 5s |
| Valores negativos zerando comissão de EV | Visível na revisão; RevOps decide se ajusta |
| Re-upload acidental destruindo dados | Confirmação obrigatória + audit log |
| Sync HubSpot atropelando edição manual | `is_locked` previne; teste cobre |

## Entregas (escopo do redesign)

1. Migrations DB
2. Backend: parser, matcher, calculator, endpoints, sync com lock
3. Frontend: edit policy modal, achievements page, upload page (novo flow), review page (drill-down completo), filtro global aplicado
4. Tests backend + smoke manual frontend
5. Reset do DB de Q1/2026 e teste end-to-end com a planilha real
