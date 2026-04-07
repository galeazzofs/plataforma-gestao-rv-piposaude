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
- Suporte a Mental e Fitness como tipos de benefício (descartados no parser).
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
| 10 | Produtos Mental/Fitness | Descartados pelo parser (não suportados) |
| 11 | Atingimento % | 100% manual, editável por trimestre, snapshot do trimestre do gongo |
| 12 | Auto-update de `installments_paid` | Sim, conforme NFs entram no cálculo |
| 13 | Reprocessamento | Botão "Recalcular" zera Commissions e roda do zero |
| 14 | Upload duplicado | Substitui o anterior do mesmo trimestre |
| 15 | Mapeamento segment → matriz | PP→PP/P, P→PP/P, M→M, G→G+ |
| 16 | "EV ativo" | `User.role == EV AND User.is_active == true` |
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
        .filter(User.role == UserRole.EV, User.is_active.is_(True))
    )
```

Todos os endpoints que listam/processam policies usam essa base. Específicos:
- `GET /policies` (listagem)
- `GET /dashboard/*` (RevOps, Finance, Gerente)
- `run_quarterly_appraisal()` (cálculo)
- Tela de Apólices

O sync do HubSpot continua puxando tudo (não filtra na entrada) — o filtro é só na leitura.

**Migration:** confirmar que `users` tem coluna `is_active`. Se não tiver, adicionar com default `true`.

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
- Grava entrada em `audit_logs` (table=policies, action=UPDATE, old/new values)

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

**Pré-check do calculator:**

```python
def validate_achievements(quarter, year):
    """Returns list of EVs without achievement for the given quarter."""
    active_evs = User.query.filter_by(role=UserRole.EV, is_active=True).all()
    missing = []
    for ev in active_evs:
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev.id, quarter=quarter, year=year
        ).first()
        if ach is None or ach.achievement_pct is None:
            missing.append(ev.name)
    return missing
```

Se `missing` não vazio, calculator levanta `MissingAchievementsError("Faltam achievements: ...")`.

**Snapshot por gongo:** quando uma NF de Q1/2026 é processada para uma Policy gongada em Q4/2025, o calculator usa o achievement de Q4/2025 do EV (não o de Q1/2026).

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
5. Aplicar pré-filtros:
   - `status_recebimento != 'RECEBIDO'` → skip
   - `cliente_mae` vazio → skip
   - `nf_liquido` None ou 0 → skip
   - `produto` não está em {Saúde, Odonto, Vida} → skip (com contador para relatório)
   - `data_recebimento` não cai em `target_quarter/target_year` → skip
6. Retornar `ParseResult` com:
   ```
   { rows: [{cliente_mae, operadora, produto, nf_liquido, data_recebimento, mes_recebimento, tipo_receita, status_recebimento, _row}],
     stats: { total_lidas, descartadas_status, descartadas_produto, descartadas_periodo, validas },
     errors: [] }
   ```

**Tolerância:** datas vêm como `datetime` do openpyxl (com `data_only=True`). Se vier string, tenta `dd/mm/yyyy`.

**Não persiste nada.** Só parseia. A persistência é responsabilidade do `processor`.

### 5. Matcher NF→Policy

**Arquivo novo:** `backend/app/modules/financial/matcher.py`

```python
def normalize(s: str) -> str:
    """lowercase + strip accents + trim spaces"""
    if not s: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower().strip())
                   if unicodedata.category(c) != 'Mn')

def match_policy(nf_row: dict, policies: list[Policy]) -> Policy | None:
    """Returns the most recent policy still in vigência that matches by
    (cliente_mae, operadora, produto). Returns None if no match."""
    cliente_n = normalize(nf_row['cliente_mae'])
    operadora_n = normalize(nf_row['operadora'])
    produto_n = normalize(nf_row['produto'])

    benefit_map = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}
    benefit_type = benefit_map.get(produto_n)
    if not benefit_type: return None

    candidates = []
    for p in policies:
        if not p.client or normalize(p.client.name) != cliente_n: continue
        if normalize(p.partner_operator or '') != operadora_n: continue
        if not p.benefit_type or p.benefit_type.value != benefit_type: continue
        candidates.append(p)

    if not candidates: return None
    # Pega a mais recente
    return max(candidates, key=lambda p: p.closed_date or date.min)
```

**Performance:** o calculator pré-carrega todas as policies do batch (`active_ev_policies_query().all()`) e passa a lista pro matcher; matching é em memória (1670 policies × 26k NFs ≈ aceitável).

**Tests:** unit tests para `normalize` (acentos, espaços) e `match_policy` (não encontrado, multi-policy escolhe a mais recente, produto não suportado).

### 6. Schema novo `financial_imports`

**Migration:**

```sql
ALTER TABLE financial_imports DROP CONSTRAINT uq_financial_policy_month;
ALTER TABLE financial_imports ALTER COLUMN policy_id DROP NOT NULL;

ALTER TABLE financial_imports
  ADD COLUMN cliente_mae VARCHAR(255),
  ADD COLUMN operadora VARCHAR(255),
  ADD COLUMN produto VARCHAR(50),
  ADD COLUMN tipo_receita VARCHAR(100),
  ADD COLUMN status_recebimento VARCHAR(50),
  ADD COLUMN data_recebimento DATE,
  ADD COLUMN match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED',
  ADD COLUMN matched_at TIMESTAMP NULL;

CREATE INDEX ix_financial_imports_quarter_year ON financial_imports(quarter, year);
CREATE INDEX ix_financial_imports_match_status ON financial_imports(match_status);
```

**`match_status` valores:** `MATCHED`, `UNMATCHED`, `EXPIRED`, `PRE_VIGENCIA`, `PRODUTO_NAO_SUPORTADO`, `EV_INATIVO`.

**Substituição:** ao fazer upload de Q1/2026 quando já existem linhas:

```python
FinancialImport.query.filter_by(quarter=q, year=y).delete()
db.session.flush()
# ... insere as novas
```

### 7. Calculator (reescrita)

**Arquivo:** `backend/app/modules/commissions/calculator.py`

**Função principal:**

```python
def run_quarterly_appraisal(quarter: int, year: int) -> dict:
    """
    Pre-conditions:
    - All active EVs have ev_quarter_achievements for this quarter
    - financial_imports populated for this quarter

    Process:
    1. Wipe existing Commissions for (quarter, year) where is_final=False
    2. Load active-EV policies (active_ev_policies_query)
    3. Load financial_imports for (quarter, year, status_recebimento=RECEBIDO)
    4. For each NF row:
       a. Match policy
       b. If no match → financial_import.match_status = UNMATCHED, continue
       c. If policy has no first_payment_real → match_status = PRE_VIGENCIA, continue
       d. Compute vigência window: [first_payment_real, first_payment_real + 12 months]
       e. If data_recebimento < window.start → PRE_VIGENCIA, continue
       f. Effective months remaining = 12 - initial_installments_paid - count(prior NFs of this policy in (q,y))
       g. If installments_paid >= (12 - initial_installments_paid) OR data_recebimento > window.end → EXPIRED
       h. Lookup achievement of policy.closed_date's quarter for policy.ev_id
       i. Lookup commission_pct from matrix using policy.segment + achievement
       j. commission_amount = nf_valor_liquido * commission_pct (negativos OK)
       k. Upsert Commission(policy_id, ev_id, q, y) accumulating
       l. policy.installments_paid += 1
       m. financial_import.policy_id = policy.id, match_status = MATCHED
    5. Return summary { ev_summary, totals, unmatched_count, expired_count }
    """
```

**Pré-check:** `validate_achievements(quarter, year)` antes do passo 1. Se algum EV ativo está sem achievement, raise `MissingAchievementsError`.

**Idempotência:** chamar de novo limpa Commissions de (q,y) com is_final=False e recalcula. Commissions com `is_final=True` (apuração já LOCKED) NÃO são tocadas.

**Performance:** todas as queries em bulk; matching em memória; commit único no final.

**Erros:** linhas que falham são marcadas no `match_status` mas não interrompem o processo.

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

**UI:** tabs `Por EV` / `Não matcheadas` / `Fora de vigência`.

- Por EV: tabela colapsável, expand → drill por policy → expand → linhas de NF.
- Não matcheadas: tabela com export CSV.
- Fora de vigência: tabela com export CSV + link pro edit da policy.

**Botões header:**
- `🔄 Recalcular` → `POST /appraisals/{id}/recalculate` (chama `run_quarterly_appraisal` de novo)
- `📤 Re-upload financeiro` → navega pro upload page
- `✅ Liberar para Validação EVs` → `POST /appraisals/{id}/transition` body `{to: "VALIDATING"}`

### 9. State machine

Já corrigido na sessão anterior: `transition_appraisal` roda `run_quarterly_appraisal` quando vai pra CALCULATING e fica nesse status (não auto-transitiona).

`VALID_TRANSITIONS` permanece igual.

`run_quarterly_appraisal_v2` é renomeado para `run_quarterly_appraisal` (sem v2). A versão antiga vira deprecated alias por compatibilidade dos testes.

## Modelo de dados final

```
users
├── id (PK)
├── email, name, role (ADMIN/REVOPS/EV/GERENTE/FINANCE)
└── is_active

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
├── match_status (MATCHED/UNMATCHED/EXPIRED/PRE_VIGENCIA/PRODUTO_NAO_SUPORTADO/EV_INATIVO) ⭐ NOVO
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
├── segment, faixa_min, faixa_max, pct
└── (seed: 9 entradas conforme matriz acima)
```

## Erros e edge cases

| Caso | Tratamento |
|---|---|
| Achievement faltando pra um EV ativo | `MissingAchievementsError` antes de rodar; cálculo aborta |
| Policy sem `first_payment_real` | NF marcada como `PRE_VIGENCIA` |
| Policy com `is_locked=true` | Sync HubSpot não sobrescreve campos lockáveis |
| Múltiplas policies no mesmo (cliente,operadora,produto) | Pega a mais recente; antiga aparece em log de "ambiguidade" |
| NF Líquido negativo | Entra na soma normalmente; pode dar comissão negativa |
| Produto Mental/Fitness | Descartado pelo parser, contador reportado |
| Cliente sem normalização match | UNMATCHED, RevOps revisa manualmente |
| Re-upload | DELETE FROM financial_imports WHERE quarter=q AND year=y; INSERT |
| Recalcular após edição de policy | Botão "Recalcular" zera Commissions e roda do zero |
| Apuração já LOCKED | Recalcular bloqueado; Commissions com is_final=true protegidas |
| EV inativado depois do cálculo | Próxima execução exclui suas NFs (filtro global) |

## Permissões

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
3. `seed_commission_pct_table.py` (popular as 9 entradas da matriz, idempotente)
4. `add_is_active_to_users.py` (se ainda não existir)

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
