# Plataforma de Comissões — Design Spec

**Versão**: 1.1
**Data**: 2026-03-27
**Autor**: Eric Valoz (RevOps) + Claude
**Stakeholders**: Frederico Lofredo (Finance), Felipe Valença (Vendas), Fernando Galeazzo (RevOps)

---

## 1. Contexto e Objetivo

A Pipo Saúde precisa de visibilidade e automação sobre o processo de comissionamento de vendas. Hoje a apuração é feita manualmente via planilha, com baixa previsibilidade de fluxo de caixa e pouca visibilidade para os vendedores.

Esta plataforma resolve isso com: database central de apólices, motor de cálculo automático, workflow de apuração trimestral e visões por persona (RevOps, Finance, EVs/CNs).

### Personas e Dores

| Persona | Dor | Solução |
|---------|-----|---------|
| RevOps (Eric, Fernando) | Apuração manual via planilha, envio de prints pra validação | Automação do cálculo, workflow digital, resumo trimestral |
| Finance (Fred) | Sem visibilidade do saldo devedor nem projeção de fluxo | Saldo por ano, projeção mensal, orçado vs realizado, export |
| EVs / CNs | Sem visibilidade do saldo a receber, validação precária | Painel tempo real, projeção de recebimentos, validação digital |

---

## 2. Arquitetura Geral

### Abordagem: Monolito Modular

Um único serviço Python/Flask com módulos bem separados internamente + frontend ClojureScript separado.

```
plataforma-comissoes/
├── backend/                        # Flask API (Python)
│   ├── app/
│   │   ├── __init__.py             # Flask app factory
│   │   ├── config.py               # Settings por ambiente (stag/prod)
│   │   ├── extensions.py           # SQLAlchemy, Flask-Migrate, etc.
│   │   ├── auth/                   # Google SSO + RBAC
│   │   │   ├── google_sso.py
│   │   │   ├── roles.py            # ADMIN(RevOps), FINANCE, EV, CN, GERENTE
│   │   │   └── decorators.py       # @require_role('ADMIN')
│   │   ├── models/                 # SQLAlchemy models
│   │   │   ├── user.py
│   │   │   ├── team.py
│   │   │   ├── policy.py           # Apólice (âncora: ticket cotação)
│   │   │   ├── commission.py
│   │   │   ├── goal.py             # Metas por EV/trimestre
│   │   │   ├── financial_import.py # Upload planilha
│   │   │   ├── appraisal.py        # Apuração trimestral
│   │   │   ├── audit_log.py        # Log de auditoria
│   │   │   └── config.py           # Tabela %, prazos, etc.
│   │   ├── modules/
│   │   │   ├── hubspot_sync/       # Cron sync HubSpot → PostgreSQL
│   │   │   ├── commissions/        # Motor de cálculo de comissão
│   │   │   ├── financial/          # Import XLSX + processamento
│   │   │   ├── workflow/           # Máquina de estados da apuração
│   │   │   └── notifications/      # In-app + Slack
│   │   └── api/
│   │       ├── v1/                 # Endpoints REST versionados
│   │       │   ├── auth.py
│   │       │   ├── policies.py
│   │       │   ├── commissions.py
│   │       │   ├── goals.py
│   │       │   ├── workflow.py
│   │       │   ├── financial.py
│   │       │   ├── reports.py      # Export Excel/CSV/PDF
│   │       │   └── admin.py        # Cadastros RevOps
│   │       └── middlewares.py
│   ├── migrations/                 # Alembic
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                       # ClojureScript/Reagent
│   ├── src/
│   │   ├── app/
│   │   │   ├── core.cljs           # Entry point
│   │   │   ├── routes.cljs         # Reitit routing
│   │   │   ├── auth/               # Google SSO flow
│   │   │   ├── views/
│   │   │   │   ├── ev/             # Visão EV (dashboard, validação)
│   │   │   │   ├── finance/        # Visão Finance (fluxo, saldo)
│   │   │   │   ├── revops/         # Visão RevOps (admin, apuração)
│   │   │   │   └── shared/         # Componentes compartilhados
│   │   │   ├── components/         # Design system components
│   │   │   ├── state/              # Re-frame subscriptions/events
│   │   │   └── api/                # HTTP client → backend
│   ├── shadow-cljs.edn
│   ├── package.json
│   └── Dockerfile
├── .k8s/
│   └── helm/
│       ├── stag/values.yaml
│       └── prod/values.yaml
├── .tf/
│   ├── global/                     # ECR repos
│   ├── stag/
│   └── prod/
└── .gitlab-ci.yml
```

### Comunicação

Frontend faz chamadas REST ao backend. Backend é a única camada que toca HubSpot, PostgreSQL e Slack.

### Roles

| Role | Quem | Acesso |
|------|------|--------|
| ADMIN | RevOps (Eric, Fernando) | Tudo: cadastros, metas, apuração, import, todas as visões |
| FINANCE | Fred | Dashboard finance, aprovar pagamento, exports |
| GERENTE | Líder de time | Vê consolidado do time, não valida individualmente |
| EV | Executivo de vendas | Seu dashboard, validar/contestar deals |
| CN | Consultor de negócios | Mesmo que EV |

RevOps (ADMIN) é o superusuário — tem acesso a tudo que Finance, Gerente e EV veem, além dos cadastros e administração.

---

## 3. Modelo de Dados (PostgreSQL)

### Tabelas Principais

#### users
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| email | VARCHAR UNIQUE | Email @piposaude.com |
| name | VARCHAR | Nome completo |
| role | ENUM | ADMIN, FINANCE, GERENTE, EV, CN |
| google_id | VARCHAR | ID Google OAuth |
| team_id | FK → teams | Time do usuário |
| active | BOOLEAN | Ativo/inativo |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### teams
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| name | VARCHAR | Nome do time |
| leader_id | FK → users | Gerente do time |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### clients (empresa normalizada)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| name | VARCHAR UNIQUE | Nome normalizado da empresa |
| hubspot_company_id | VARCHAR | ID da empresa no HubSpot |
| ev_id | FK → users | EV responsável (1 EV por empresa) |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

A tabela `clients` normaliza empresas e garante a regra "1 EV por empresa" via FK. Match entre planilha/HubSpot e `clients` usa nome normalizado (lowercase, sem acentos, trim).

#### policies (âncora: ticket de cotação gongado)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| hubspot_ticket_id | VARCHAR UNIQUE | ID do ticket de cotação |
| ev_id | FK → users | EV responsável |
| client_id | FK → clients | Empresa (normalizada) |
| deal_id | VARCHAR | ID do deal no HubSpot |
| benefit_type | ENUM | SAUDE, ODONTO, VIDA |
| segment | ENUM | PP, P, M, G (ver mapeamento abaixo) |
| headcount | INTEGER | Qtd vidas/funcionários (origem: HubSpot) |
| mrr_projected | DECIMAL | MRR previsto no gongo |
| mrr_post_deploy | DECIMAL | MRR pós-implantação |
| mrr_actual | DECIMAL | MRR real faturado |
| closed_date | DATE | Data do gongo |
| deploy_date | DATE | Data de implantação |
| first_payment_prev | DATE | Previsão 1º pagamento |
| first_payment_real | DATE | 1º recebimento efetivo |
| installments_paid | INTEGER | Faturas pagas (0-12) |
| commission_status | ENUM | PROJECTED, IN_PAYMENT, SETTLED, CANCELLED |
| partner_operator | VARCHAR | Parceiro/operadora |
| deal_stage | VARCHAR | Estágio do deal |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### financial_imports
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| policy_id | FK → policies | |
| nf_valor_liquido | DECIMAL | Valor líquido recebido |
| nf_mes_recebimento | VARCHAR | Mês (YYYY-MM) |
| quarter | INTEGER | Trimestre derivado do mês (1-4) |
| year | INTEGER | Ano derivado do mês |
| import_batch_id | UUID | Lote de importação |
| created_at | TIMESTAMP | |

#### perks
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| client_id | FK → clients | Empresa (normalizada) |
| quarter | INTEGER | Trimestre (1-4) |
| year | INTEGER | Ano |
| amount | DECIMAL | Total de perks |
| import_batch_id | UUID | Lote de importação |
| created_at | TIMESTAMP | |

#### goals
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| ev_id | FK → users | |
| quarter | INTEGER | Trimestre (1-4) |
| year | INTEGER | Ano |
| mrr_target | DECIMAL | Meta de MRR |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Unique constraint**: `(ev_id, quarter, year)` — um EV tem exatamente uma meta por trimestre.

#### commissions
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| policy_id | FK → policies | |
| ev_id | FK → users | |
| quarter | INTEGER | |
| year | INTEGER | |
| segment | ENUM | Porte do deal |
| achievement_pct | DECIMAL | % atingimento do EV |
| commission_pct | DECIMAL | % comissão aplicado |
| commission_pct_version | INTEGER | Versão da tabela de % usada no cálculo |
| monthly_estimated | DECIMAL | Comissão mensal estimada |
| monthly_actual | DECIMAL | Comissão mensal real (ver lifecycle abaixo) |
| total_estimated | DECIMAL | Total estimado (12x) |
| total_actual | DECIMAL | Total real |
| is_final | BOOLEAN | Apuração fechada? |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Unique constraint**: `(policy_id, quarter, year)` — uma comissão por policy por trimestre.

#### appraisals (apurações trimestrais)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| quarter | INTEGER | |
| year | INTEGER | |
| status | ENUM | DRAFT, CALCULATING, VALIDATING, REVIEWING, APPROVED, LOCKED |
| validation_deadline | DATE | Prazo para EVs validarem |
| created_by | FK → users | |
| approved_by_finance | FK → users | |
| locked_at | TIMESTAMP | |
| created_at | TIMESTAMP | |

**Unique constraint**: `(quarter, year)` — uma apuração por trimestre.

#### commission_pct_table (versionada)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| version | INTEGER | Versão da tabela |
| segment | ENUM | PP, P, M, G (mesmo enum das policies) |
| achievement_min | DECIMAL | Mínimo da faixa (%) |
| achievement_max | DECIMAL | Máximo da faixa (%) |
| commission_pct | DECIMAL | % de comissão |
| valid_from | DATE | Vigência início (informativo) |
| valid_until | DATE | Vigência fim (null = atual, informativo) |
| created_by | FK → users | |

Nota: O campo `version` é a referência primária para lookups. `commissions.commission_pct_version` aponta para `commission_pct_table.version`. Os campos `valid_from`/`valid_until` são informativos para o admin saber quando cada versão entrou em vigor. O motor de cálculo usa sempre o `version` mais recente (maior) com `valid_until IS NULL`.

**Unique constraints**: `(version, segment, achievement_min)` — garante que não existam linhas duplicadas dentro de uma mesma versão.

#### ev_validations
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| appraisal_id | FK → appraisals | |
| policy_id | FK → policies | |
| ev_id | FK → users | |
| status | ENUM | PENDING, APPROVED, CONTESTED, RESOLVED, AUTO_APPROVED |
| comment | TEXT | Comentário (obrigatório na contestação) |
| contested_at | TIMESTAMP | |
| resolved_at | TIMESTAMP | |
| resolved_by | FK → users | |
| created_at | TIMESTAMP | |

#### notifications
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| user_id | FK → users | |
| type | VARCHAR | Tipo da notificação |
| title | VARCHAR | |
| message | TEXT | |
| read | BOOLEAN | |
| metadata | JSONB | Dados extras (links, IDs) |
| created_at | TIMESTAMP | |

#### audit_logs
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| table_name | VARCHAR | Tabela afetada |
| record_id | UUID | ID do registro |
| action | ENUM | CREATE, UPDATE, DELETE |
| old_values | JSONB | Valores anteriores |
| new_values | JSONB | Valores novos |
| user_id | FK → users | Quem fez |
| created_at | TIMESTAMP | |

#### platform_settings
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| key | VARCHAR UNIQUE | Chave da config |
| value | JSONB | Valor |
| updated_by | FK → users | |
| updated_at | TIMESTAMP | |

### Enums

- `commission_status`: PROJECTED → IN_PAYMENT → SETTLED (ou CANCELLED em caso de churn)
- `appraisal.status`: DRAFT → CALCULATING → VALIDATING → REVIEWING → APPROVED → LOCKED
- `ev_validations.status`: PENDING → APPROVED → CONTESTED → RESOLVED → AUTO_APPROVED
- `benefit_type`: SAUDE, ODONTO, VIDA
- `segment`: PP, P, M, G
- `role`: ADMIN, FINANCE, GERENTE, EV, CN

### Mapeamento de Segmentos

O campo `segment` é derivado do `headcount` (vidas/funcionários) do deal:

| Segmento | Headcount | Faixa comissão |
|----------|-----------|----------------|
| PP | 1 a 80 | P e PP (até 199) |
| P | 81 a 199 | P e PP (até 199) |
| M | 200 a 999 | M |
| G | 1000+ | G+ |

Nota: O campo `cotar___segmentacao_pipo` do HubSpot traz valores como "Startup (1-80)", "P (81-200)", etc. O sync normaliza para o enum PP/P/M/G. Para fins de comissão, PP e P usam a mesma faixa de %.

### Indexes Recomendados

- `policies.ev_id` + `policies.closed_date` (cálculo de achievement)
- `policies.client_id` (agrupamento por empresa)
- `commissions.ev_id` + `commissions.quarter` + `commissions.year`
- `financial_imports.policy_id` + `financial_imports.nf_mes_recebimento`
- `perks.client_id` + `perks.quarter` + `perks.year`
- `audit_logs.table_name` + `audit_logs.record_id`
- `notifications.user_id` + `notifications.read`

### Regras de Imutabilidade

- Quando `appraisal.status = LOCKED`, nenhum registro vinculado pode ser alterado
- Toda alteração passa pelo `audit_logs` com old/new values em JSONB
- Tabela de % nunca deleta, cria nova versão. Comissões referenciam a versão vigente

---

## 4. Motor de Cálculo de Comissões

### Tabela de Percentuais

| Segmento (enum) | Porte (headcount) | 0% a 49,9% | 50% a 99,9% | 100%+ |
|------------------|--------------------|------------|-------------|-------|
| PP, P | Até 199 vidas | 7% | 8% | 10% |
| M | 200 a 999 vidas | 5% | 6% | 8% |
| G | 1000+ vidas | 3% | 4% | 6% |

### Projeção (automática, a cada sync HubSpot)

Para cada policy com status PROJECTED ou IN_PAYMENT:

1. **Determinar MRR comissão** (cascata):
   - Se tem `mrr_actual` (faturado real) → usa `mrr_actual`
   - Se tem `mrr_post_deploy` → usa `mrr_post_deploy`
   - Senão → usa `mrr_projected` (do gongo)

2. **Buscar achievement do EV no trimestre atual**:
   - `achievement_pct = SUM(mrr gongos do EV no tri) / meta_mrr do EV no tri`

3. **Aplicar % da faixa MÉDIA (50-99.9%) como estimativa**:
   - `commission_pct = tabela[segment][faixa_media]`

4. **Calcular**:
   - `monthly_estimated = mrr_comissao × commission_pct`
   - `total_estimated = monthly_estimated × 12`
   - `saldo_devedor = (12 - installments_paid) × monthly_estimated`

### Apuração (fechamento trimestral)

Para cada EV no trimestre:

1. **Achievement FINAL**: `SUM(mrr gongos do EV no tri) / meta_mrr`
2. **Faixa FINAL de %**: lookup na `commission_pct_table` vigente
3. **Calcular base por empresa**:
   - `total_liquido_empresa = SUM(nf_valor_liquido)` de todas as policies do mesmo `client_id` no tri
   - `base_empresa = total_liquido_empresa - perks_empresa` (perks do tri via tabela `perks`)
4. **Ratear para cada policy** (pro-rata por MRR):
   - `peso_policy = mrr_comissao_policy / SUM(mrr_comissao de todas policies do client no tri)`
   - `base_policy = base_empresa × peso_policy`
   - `comissao_real_policy = base_policy × commission_pct` (faixa final)
   - Grava em `commissions.monthly_actual` e `commissions.total_actual`
5. **Retroatividade**: % final aplica em TODOS os deals do EV naquele trimestre
6. Marca `is_final = true`

### Regras de Negócio Críticas

| Regra | Descrição |
|-------|-----------|
| Retroatividade | % definido no fechamento do tri aplica retroativamente em todos os deals do tri |
| Imutabilidade | Uma vez LOCKED, % e valores não mudam mais |
| Relógio 12 faturas | Só inicia no recebimento EFETIVO (planilha financeiro), não na previsão |
| Perks por empresa | Abatidos do total líquido da empresa, não da apólice individual |
| 1 EV por empresa | Não existe caso de EVs diferentes na mesma empresa |
| MRR cascata | Projetado → pós-implantação → real faturado (usa o mais recente disponível) |

### Lifecycle de monthly_actual e total_actual

Os campos `monthly_actual` e `total_actual` na tabela `commissions` seguem este ciclo:

1. **Antes da apuração**: `monthly_actual = NULL`, `total_actual = NULL`. Só `monthly_estimated` e `total_estimated` existem.
2. **Na apuração (CALCULATING)**: Motor calcula `monthly_actual` e `total_actual` com base no rateio empresa (ver passo 4 da Apuração). `is_final = false` até LOCKED.
3. **Após LOCKED**: `monthly_actual` e `total_actual` ficam imutáveis. Este é o valor definitivo da comissão.
4. **Pagamento mensal**: A policy continua recebendo NFs por até 12 meses. O `monthly_actual` calculado na apuração é o valor mensal que o EV tem direito. As NFs subsequentes não recalculam o valor — ele já foi definido no fechamento do tri.
5. **Cross-quarter**: Uma policy gongada no Q1 tem comissão calculada no fechamento do Q1 (com % do Q1). Os pagamentos continuam nos trimestres seguintes, mas o `monthly_actual` não muda. Apenas `installments_paid` incrementa.

### Status da Policy

```
PROJECTED ────────────────▶ IN_PAYMENT ────────────────▶ SETTLED
 (gongado, sem pgto real)    (1ª NF recebida,            (12/12 faturas
  projeção com MRR previsto)  relógio iniciou)             pagas)
```

---

## 5. Workflow de Apuração Trimestral

Máquina de estados com 6 etapas.

```
DRAFT → CALCULATING → [RevOps revisa] → VALIDATING → REVIEWING → APPROVED → LOCKED
```

### Etapas

**1. DRAFT** (RevOps inicia)
- Upload planilha financeiro (NFs + perks)
- Confirma/ajusta metas dos EVs
- Ação: botão "Iniciar Apuração"

**2. CALCULATING** (automático + gate RevOps)
- Plataforma executa motor de cálculo
- Calcula achievement final de cada EV
- Aplica % retroativo em todos os deals
- Gera consolidado por EV com detalhe por deal
- Notifica RevOps que o cálculo terminou (in-app + Slack)
- RevOps revisa os números calculados
- Ação: botão **"Liberar para Validação"** → avança pra VALIDATING e dispara notificação pros EVs

**3. VALIDATING** (EVs)
- Cada EV vê seus deals com valores calculados
- Pode aprovar ou contestar deal por deal (comentário obrigatório na contestação)
- Prazo configurável pelo RevOps
- Deals não contestados dentro do prazo = auto-aprovados
- Gerente vê consolidado do time mas não valida
- Quando todos terminam (ou prazo expira) → avança pra REVIEWING

**4. REVIEWING** (RevOps)
- Lista de contestações para resolver
- Aceita ajuste ou rejeita com justificativa
- Deals sem contestação já aprovados
- Pode recalcular (volta pra CALCULATING)
- Ação: botão "Enviar pra Finance"

**5. APPROVED** (Finance)
- Consolidado final: total por EV, total geral, orçado vs realizado
- Export Excel/CSV/PDF
- Ação: "Liberar Pagamento" ou "Devolver pro RevOps" (volta pra REVIEWING)

**6. LOCKED** (imutável)
- Todos os registros do trimestre ficam imutáveis
- Audit log registra quem e quando travou
- Dados viram histórico consultável

### Auto-aprovação

Cron job diário verifica: se `appraisal.status == VALIDATING` e `today > validation_deadline`, todas as validações pendentes são marcadas como AUTO_APPROVED e o workflow avança pra REVIEWING.

---

## 6. Visões por Persona

### Visão EV / CN

**Dashboard principal** (acesso contínuo, tempo real):
- Card saldo a receber estimado
- Atingimento no trimestre atual (barra de progresso MRR vendido / meta, faixa de %)
- Tabela de deals: cliente, benefício, segmento, MRR, %, comissão estimada, parcelas (X/12), status
- Projeção 12 meses (gráfico de recebimentos mensais)

**Histórico**: trimestres anteriores, filtro por ano/trimestre, valores finais.

**Validação** (só durante VALIDATING): lista de deals, botão aprovar/contestar, status geral, prazo restante.

**Restrição**: EV só vê seus próprios dados.

### Visão Gerente

- Consolidado do time: EVs com atingimento, saldo, total comissão
- Drill-down por EV (read-only)
- Não valida deals

### Visão Finance

**Dashboard**:
- Saldo devedor total
- Separação por ano (dinâmico: todos os anos com saldo)
- Fluxo de caixa mensal (realizadas vs projetadas)
- Orçado vs realizado (mensal e trimestral)

**Tabela**: por EV com drill-down por deal.
**Exports**: Excel, CSV, PDF com filtros.
**Aprovação**: durante etapa APPROVED do workflow.

### Visão RevOps (Admin — acesso total)

RevOps tem acesso a tudo: todas as visões de Finance, Gerente e EV, além de:

**Cadastros**: EVs, CNs, Gerentes, times. Metas (import xlsx + edição). Tabela de % (versionada). Configurações.

**Apuração**: iniciar, revisar cálculo, liberar pra validação, resolver contestações.

**Monitoramento**: status sync HubSpot, audit log, histórico de imports.

---

## 7. Integração HubSpot (Sync)

### Cron Job

- Frequência: a cada 30 minutos (configurável)
- HubSpot CRM API v3 (REST)
- Autenticação: Private App Token (AWS Secrets Manager)

### Fluxo

1. Buscar tickets de cotação gongados (status: ganho, MRR > 0)
2. Para cada ticket novo/atualizado:
   - Buscar deal associado
   - Buscar apólice ativada
   - Buscar ticket de implantação (via apólice ou deal)
   - **Upsert em `clients`**: normalizar `cliente___nome_da_empresa` (lowercase, sem acentos, trim) e criar/atualizar na tabela `clients`. Se o client já existe, verificar que o `ev_id` é o mesmo (regra 1 EV por empresa)
   - Criar/atualizar registro em `policies` usando o `client_id` resultante
3. Log do sync (timestamp, criados, atualizados, erros)

### Campos Mapeados

| Campo HubSpot | Campo policies | Origem |
|---|---|---|
| solicitante_demanda | ev_id (match por email) | Ticket cotação |
| cotar___segmentacao_pipo | segment | Ticket cotação |
| mrr___receita_mensal | mrr_projected | Ticket cotação |
| closed_date | closed_date | Ticket cotação |
| apolice___beneficio | benefit_type | Ticket cotação |
| cliente___nome_da_empresa | client_id (via upsert em clients) | Ticket cotação |
| dealstage | deal_stage | Deal |
| hs_v2_date_entered_8438574 | deploy_date | Deal |
| previsao_primeiro_pagamento | first_payment_prev | Ticket implant. |
| mrr_pos_implantacao | mrr_post_deploy | Ticket implant. |

### Tratamento de Erros

- Falha em um ticket não trava o sync inteiro
- Retry com backoff exponencial (max 3 tentativas)
- RevOps vê status no painel admin

### Rate Limiting

- 200 requests/10 segundos (HubSpot Private App)
- Batch de 100 registros por request
- Respeita `Retry-After` header

---

## 8. Import Financeiro (Planilha Excel)

### Template XLSX

**Aba 1 — NFs**:

| Coluna | Tipo | Descrição |
|---|---|---|
| hubspot_ticket_id | Texto | ID do ticket de cotação |
| client_name | Texto | Nome da empresa |
| nf_valor_liquido | Moeda | Valor líquido recebido no mês |
| nf_mes_recebimento | Texto (YYYY-MM) | Mês de recebimento |

**Aba 2 — Perks**:

| Coluna | Tipo | Descrição |
|---|---|---|
| client_name | Texto | Nome da empresa |
| quarter | Inteiro (1-4) | Trimestre |
| year | Inteiro | Ano |
| amount | Moeda | Total de perks |

### Fluxo

1. Upload do .xlsx pelo RevOps
2. Validação: formato, colunas, ticket_id existe, valores numéricos, sem duplicata
3. Preview: X NFs novas, Y atualizadas, Z erros (com linha e motivo)
4. RevOps confirma → grava com `import_batch_id`
5. Atualiza automaticamente: `installments_paid`, `first_payment_real`, `commission_status`

### Futuro (Snowflake)

Mesma lógica mas via job automático. Preview e confirmação continuam existindo.

---

## 9. Notificações

### In-app

- Ícone sino no header com badge
- Dropdown com notificações recentes
- Marcar como lida individual ou todas
- Persistidas na tabela `notifications`

### Slack

| Evento | Destinatário | Canal |
|---|---|---|
| Cálculo finalizado | RevOps | DM |
| Apuração liberada pra validação | EVs do trimestre | Canal do time ou DM |
| Deal contestado | RevOps | DM |
| 1 dia pro prazo expirar | EVs pendentes | DM |
| Apuração enviada pra Finance | Finance | DM |
| Pagamento liberado (LOCKED) | RevOps | DM |

Mensagens com Slack blocks: header, resumo, botão com link direto.

Tipos de notificação configuráveis pelo RevOps. Canal Slack configurável por time.

---

## 10. Autenticação e Segurança

### Google SSO

- Google OAuth 2.0 (contas @piposaude.com)
- Domínio restrito
- Primeiro login cria usuário sem role (RevOps atribui)
- JWT (access token) em memória no frontend (nunca localStorage)
- Refresh token em httpOnly cookie (seguro contra XSS)
- Access token expira em 8h, refresh em 7 dias
- Endpoint `/auth/refresh` renova o access token
- Logout revoga o refresh token no backend

### RBAC

| Endpoint | ADMIN | FINANCE | GERENTE | EV/CN |
|---|---|---|---|---|
| GET /policies (próprias) | x | - | - | x |
| GET /policies (time) | x | - | x | - |
| GET /policies (todas) | x | x | - | - |
| POST /financial/upload | x | - | - | - |
| POST /goals | x | - | - | - |
| POST /appraisal/start | x | - | - | - |
| POST /appraisal/release-validation | x | - | - | - |
| POST /validation/approve-contest | - | - | - | x |
| POST /appraisal/resolve | x | - | - | - |
| POST /appraisal/approve-payment | x | x | - | - |
| GET /finance/dashboard | x | x | - | - |
| GET /admin/* | x | - | - | - |
| GET /reports/export | x | x | - | - |
| GET /audit-log | x | - | - | - |

### Segurança

- HTTPS (TLS no ingress K8s)
- Rate limiting por usuário
- CORS restrito ao domínio do frontend
- Tokens no AWS Secrets Manager
- Audit log de login/logout e alterações
- Senhas de banco via CI/CD variables

---

## 11. Infraestrutura e Deploy

### Kubernetes + Helm

Namespace `default`, chart `pipoengineering/platform/charts/microservice`.

**Backend**: ECR `plataforma-comissoes-backend`, stag=1 / prod=2 replicas, 256-512Mi RAM.
**Frontend**: ECR `plataforma-comissoes-frontend`, Nginx + build estático, stag=1 / prod=2 replicas.

Cron jobs (namespace `cronjobs`):
- `hubspot-sync`: a cada 30min
- `auto-approve-validation`: diário às 9h

### Terraform

```
.tf/
├── global/ecr.tf           # 2 repos ECR
├── stag/rds.tf + secrets.tf
└── prod/rds.tf + secrets.tf
```

Tags: Squad=RevOps, Domain=Comissoes, Environment=prod/stag, Service=plataforma-comissoes.

### GitLab CI/CD

Stages: test → lint → build → push → deploy-stag → deploy-prod (manual).

Variables (GitLab CI, nunca no código): HUBSPOT_TOKEN, GOOGLE_CLIENT_ID/SECRET, SLACK_BOT_TOKEN, DATABASE_URL, AWS credentials.

### Ambientes

| | Staging | Prod |
|---|---|---|
| URL | comissoes-stag.piposaude.com | comissoes.piposaude.com |
| DB | RDS t3.micro, 20GB | RDS t3.small, 50GB |
| Replicas | 1+1 | 2+2 |
| HubSpot | Sandbox | Prod |

---

## 12. Design System

### Cores

- **Primária**: #000000
- **Fundos**: #EDECE7, #F7F6F3
- **Texto principal**: #2B2B2B
- **Texto secundário**: #6B6B6B
- **Desabilitados/ícones**: #BDBDBD
- **Divisores/fundos**: #E2E2E2, #F5F5F5
- **Bege apoio**: #6E6A63, #C6B58A, #E6DEC8, #F3EFE4
- **Overlay**: rgba(0, 0, 0, 0.4)

### Cores Semânticas

- **Success**: #1FA971
- **Warning**: #FFB703
- **Error**: #EF4444

### Cores Complementares (gráficos)

- Azul: #1E40AF, #3B82F6
- Roxo: #7C3AED, #C4B5FD
- Rosa: #F472B6, #FBCFE8
- Pêssego: #FDBA74, #FED7AA

### Espaçamento

Múltiplos de 8px: 0, 4, 8, 16, 24, 32, 48, 64, 128.

### Breakpoints

576px, 768px, 960px, 1140px.

### Princípios

Visual limpo, moderno e funcional. Cores com uso consciente e semântico. Hierarquia clara e espaçamento consistente.

---

## 13. Stack Tecnológica (Resumo)

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.10+ / Flask |
| Frontend | ClojureScript / Shadow-cljs / Reagent / Re-frame |
| Banco | PostgreSQL (RDS) |
| Infra | AWS EKS / Kubernetes / Helm |
| IaC | Terraform |
| CI/CD | GitLab CI |
| Auth | Google OAuth 2.0 (SSO) |
| Secrets | AWS Secrets Manager |
| Notificações | In-app + Slack Bot |
| Integrações | HubSpot API v3 (cron sync) |
| Import | Excel (.xlsx) → futuro Snowflake |
| Design System | Custom Pipo (Obentô base) |

---

## 14. Edge Cases e Regras Especiais

### EV sai da empresa no meio do trimestre

- Deals já gongados permanecem com o EV original (comissão é devida)
- Meta do EV é mantida integral (não pro-rateada)
- RevOps pode reatribuir deals futuros manualmente via admin
- EV inativo continua visível no histórico mas não aparece em novos cadastros

### Policy cancelada / churn antes de 12 parcelas

- Se o cliente cancela, a policy recebe status `CANCELLED` (novo estado adicionado ao enum)
- Comissão para de ser devida a partir do cancelamento
- Parcelas já pagas não sofrem clawback (não há estorno)
- `commission_status`: PROJECTED/IN_PAYMENT → CANCELLED
- RevOps registra o cancelamento manualmente (ou via sync HubSpot se deal_stage mudar)

### Meta alterada no meio do trimestre

- Metas podem ser editadas a qualquer momento antes da apuração (DRAFT)
- Uma vez que a apuração entra em CALCULATING, a meta fica congelada para aquele trimestre
- Tabela `goals` tem `updated_at` para rastreio, mas não é versionada (audit_log cobre o histórico)

### Dados iniciais / migração

- A plataforma começa do zero a partir de um trimestre definido pelo RevOps (ex: Q1 2026)
- Dados históricos anteriores NÃO são migrados no MVP
- Se necessário, RevOps pode fazer import retroativo via upload de planilha

---

## 15. Contrato de API

### Padrões Gerais

- **Base URL**: `/api/v1`
- **Auth header**: `Authorization: Bearer <jwt_token>`
- **Content-Type**: `application/json` (exceto upload que é `multipart/form-data`)
- **Paginação**: offset-based com `?page=1&per_page=20` (default 20, max 100)
- **Ordenação**: `?sort=field&order=asc|desc`

### Formato de Resposta Padrão

```json
{
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

### Formato de Erro Padrão

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Descrição legível do erro",
    "details": [
      {"field": "mrr_target", "message": "Deve ser maior que zero"}
    ]
  }
}
```

HTTP status codes: 200 (ok), 201 (created), 400 (validation), 401 (unauthorized), 403 (forbidden), 404 (not found), 409 (conflict), 422 (unprocessable), 500 (internal).

### Endpoints Principais

#### Auth
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| POST | /auth/google | Callback OAuth Google → retorna JWT | público |
| POST | /auth/refresh | Refresh do JWT | autenticado |
| GET | /auth/me | Dados do usuário logado | autenticado |

#### Policies
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET | /policies | Lista policies (filtros: ev_id, client_id, quarter, year, status) | EV(próprias), GERENTE(time), ADMIN/FINANCE(todas) |
| GET | /policies/:id | Detalhe de uma policy | EV(própria), GERENTE(time), ADMIN/FINANCE |

#### Commissions
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET | /commissions | Lista comissões (filtros: ev_id, quarter, year, is_final) | EV(próprias), GERENTE(time), ADMIN/FINANCE(todas) |
| GET | /commissions/summary | Resumo: saldo a receber, atingimento, projeção | EV(próprio), ADMIN |
| GET | /commissions/projection | Projeção 12 meses de recebimentos | EV(próprio), ADMIN |

#### Goals
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET | /goals | Lista metas (filtros: ev_id, quarter, year) | ADMIN |
| POST | /goals | Criar/atualizar meta individual | ADMIN |
| POST | /goals/import | Upload XLSX de metas em massa | ADMIN |

#### Financial
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| POST | /financial/upload | Upload XLSX financeiro → retorna preview | ADMIN |
| POST | /financial/confirm/:batch_id | Confirma import após preview | ADMIN |
| GET | /financial/history | Histórico de imports | ADMIN |
| GET | /financial/template | Download do template XLSX | ADMIN |

#### Workflow (Apuração)
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| POST | /appraisals | Criar apuração (DRAFT) | ADMIN |
| POST | /appraisals/:id/calculate | Disparar cálculo (DRAFT → CALCULATING) | ADMIN |
| POST | /appraisals/:id/release | Liberar para validação (CALCULATING → VALIDATING) | ADMIN |
| POST | /appraisals/:id/send-to-finance | Enviar pra Finance (REVIEWING → APPROVED) | ADMIN |
| POST | /appraisals/:id/approve-payment | Liberar pagamento (APPROVED → LOCKED) | ADMIN, FINANCE |
| POST | /appraisals/:id/return | Devolver pro RevOps (APPROVED → REVIEWING) | FINANCE |
| GET | /appraisals/:id | Detalhe da apuração com consolidado | ADMIN, FINANCE |

#### Validações (EV)
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET | /validations | Lista validações do EV no tri ativo | EV |
| POST | /validations/:id/approve | Aprovar deal | EV |
| POST | /validations/:id/contest | Contestar deal (body: comment) | EV |
| POST | /validations/:id/resolve | Resolver contestação (body: resolution, accepted) | ADMIN |

#### Finance Dashboard
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET | /finance/dashboard | Saldo devedor, fluxo de caixa, orçado vs realizado | ADMIN, FINANCE |
| GET | /finance/export | Export Excel/CSV/PDF (query: format, filters) | ADMIN, FINANCE |

#### Admin
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET/POST/PUT | /admin/users | CRUD de usuários + atribuição de role | ADMIN |
| GET/POST/PUT | /admin/teams | CRUD de times | ADMIN |
| GET/POST | /admin/commission-table | Ver/atualizar tabela de % (cria nova versão) | ADMIN |
| GET/PUT | /admin/settings | Configurações da plataforma | ADMIN |
| GET | /admin/sync-status | Status do último sync HubSpot | ADMIN |
| GET | /admin/audit-log | Log de auditoria (filtros: table, user, date range) | ADMIN |

#### Notifications
| Método | Path | Descrição | Role |
|--------|------|-----------|------|
| GET | /notifications | Lista notificações do usuário (filtro: read) | autenticado |
| POST | /notifications/:id/read | Marcar como lida | autenticado |
| POST | /notifications/read-all | Marcar todas como lidas | autenticado |

---

## 16. Observabilidade

### Logging

- Formato logfmt estruturado
- Campos obrigatórios: timestamp, level, message, request_id, user_id
- Nunca logar dados sensíveis (tokens, senhas)

### Health Checks

- `GET /health` — liveness (app está rodando)
- `GET /ready` — readiness (DB conectado, dependências ok)

### Monitoramento de Cron Jobs

- Cada execução do `hubspot-sync` loga: início, fim, duração, registros processados, erros
- Se o sync falha 3x consecutivas, dispara alerta no Slack pro RevOps
- `auto-approve-validation` loga quantas validações foram auto-aprovadas

### Backup e Recovery

- RDS com backups automáticos diários (retenção: 7 dias stag, 30 dias prod)
- Point-in-time recovery habilitado em prod
- RDS Single-AZ em stag, Multi-AZ em prod
