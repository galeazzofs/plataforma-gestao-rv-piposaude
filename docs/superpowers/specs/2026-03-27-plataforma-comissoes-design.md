# Plataforma de Comissões — Design Spec

**Versão**: 1.0
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

#### policies (âncora: ticket de cotação gongado)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| hubspot_ticket_id | VARCHAR UNIQUE | ID do ticket de cotação |
| ev_id | FK → users | EV responsável |
| deal_id | VARCHAR | ID do deal no HubSpot |
| client_name | VARCHAR | Nome da empresa |
| benefit_type | ENUM | SAUDE, ODONTO, VIDA |
| segment | ENUM | STARTUP, P, M, G, ENTERPRISE |
| mrr_projected | DECIMAL | MRR previsto no gongo |
| mrr_post_deploy | DECIMAL | MRR pós-implantação |
| mrr_actual | DECIMAL | MRR real faturado |
| closed_date | DATE | Data do gongo |
| deploy_date | DATE | Data de implantação |
| first_payment_prev | DATE | Previsão 1º pagamento |
| first_payment_real | DATE | 1º recebimento efetivo |
| installments_paid | INTEGER | Faturas pagas (0-12) |
| commission_status | ENUM | PROJECTED, IN_PAYMENT, SETTLED |
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
| import_batch_id | UUID | Lote de importação |
| created_at | TIMESTAMP | |

#### perks
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| client_name | VARCHAR | Empresa |
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
| monthly_estimated | DECIMAL | Comissão mensal estimada |
| monthly_actual | DECIMAL | Comissão mensal real |
| total_estimated | DECIMAL | Total estimado (12x) |
| total_actual | DECIMAL | Total real |
| is_final | BOOLEAN | Apuração fechada? |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

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

#### commission_pct_table (versionada)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| version | INTEGER | Versão da tabela |
| segment | ENUM | STARTUP, P, M, G, ENTERPRISE |
| achievement_min | DECIMAL | Mínimo da faixa (%) |
| achievement_max | DECIMAL | Máximo da faixa (%) |
| commission_pct | DECIMAL | % de comissão |
| valid_from | DATE | Vigência início |
| valid_until | DATE | Vigência fim (null = atual) |
| created_by | FK → users | |

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

- `commission_status`: PROJECTED → IN_PAYMENT → SETTLED
- `appraisal.status`: DRAFT → CALCULATING → VALIDATING → REVIEWING → APPROVED → LOCKED
- `ev_validations.status`: PENDING → APPROVED → CONTESTED → RESOLVED → AUTO_APPROVED
- `benefit_type`: SAUDE, ODONTO, VIDA
- `segment`: STARTUP, P, M, G, ENTERPRISE
- `role`: ADMIN, FINANCE, GERENTE, EV, CN

### Regras de Imutabilidade

- Quando `appraisal.status = LOCKED`, nenhum registro vinculado pode ser alterado
- Toda alteração passa pelo `audit_logs` com old/new values em JSONB
- Tabela de % nunca deleta, cria nova versão. Comissões referenciam a versão vigente

---

## 4. Motor de Cálculo de Comissões

### Tabela de Percentuais

| Porte | 0% a 49,9% | 50% a 99,9% | 100%+ |
|-------|------------|-------------|-------|
| P e PP (até 199) | 7% | 8% | 10% |
| M (200 a 999) | 5% | 6% | 8% |
| G+ (1000 a 10k) | 3% | 4% | 6% |

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
3. **Para cada policy**:
   - Agrupar NFs por empresa: `SUM(nf_valor_liquido)` por `client_name` no tri
   - Subtrair perks: `base = total_liquido_empresa - perks_empresa`
   - `comissao_real = base × commission_pct` (faixa final)
4. **Retroatividade**: % final aplica em TODOS os deals do EV naquele trimestre
5. Marca `is_final = true`

### Regras de Negócio Críticas

| Regra | Descrição |
|-------|-----------|
| Retroatividade | % definido no fechamento do tri aplica retroativamente em todos os deals do tri |
| Imutabilidade | Uma vez LOCKED, % e valores não mudam mais |
| Relógio 12 faturas | Só inicia no recebimento EFETIVO (planilha financeiro), não na previsão |
| Perks por empresa | Abatidos do total líquido da empresa, não da apólice individual |
| 1 EV por empresa | Não existe caso de EVs diferentes na mesma empresa |
| MRR cascata | Projetado → pós-implantação → real faturado (usa o mais recente disponível) |

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
   - Criar/atualizar registro em `policies`
3. Log do sync (timestamp, criados, atualizados, erros)

### Campos Mapeados

| Campo HubSpot | Campo policies | Origem |
|---|---|---|
| solicitante_demanda | ev_id (match por email) | Ticket cotação |
| cotar___segmentacao_pipo | segment | Ticket cotação |
| mrr___receita_mensal | mrr_projected | Ticket cotação |
| closed_date | closed_date | Ticket cotação |
| apolice___beneficio | benefit_type | Ticket cotação |
| cliente___nome_da_empresa | client_name | Ticket cotação |
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
- JWT com refresh token (8h / 7 dias)

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
