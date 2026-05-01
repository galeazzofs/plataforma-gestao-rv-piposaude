# Auditoria & Plano de Ataque

> Documento de continuidade — se a sessão Claude for perdida, abrir este arquivo
> em uma nova sessão dá todo o contexto para retomar de onde paramos.
>
> **Última atualização**: 2026-05-01 (auditoria concluída — todos os cycles validados em browser)

---

## Status atual: ✅ AUDITORIA CONCLUÍDA

- ✅ **Cycle 1: Mapeamento + auditoria completa**
- ✅ **Cycle 2: Fixes críticos B1+B2+B3** — validado
- ✅ **Cycle 3: Fixes médios B4, F1, F2, R1 (parcial)** — validado
- ✅ **Cycle 4: B5 fechado, R1 completo, vestígios arquivados, R3 skip** — validado

Working tree tem mudanças não-commitadas. Próximos passos opcionais: revisar diff (`git diff`), commit, abrir PR.

### Resumo do Cycle 4
- **B5**: investigação fechada como FALSO POSITIVO. Backend `cn_commissions.py:41` espera `month`/`year`/`items` no body; frontend envia exatamente isso. Sem bug.
- **R1 completo**: `utils/format.cljs` agora tem 3 funções (`fmt-brl`, `fmt-brl-int`, `int-brl`). Migrados todos os 4 sites restantes preservando contrato visual de cada um. Zero `defn` local de formatadores BRL no codebase.
- **Vestígios arquivados** via `git rm`/`rm`:
  - `backend/migrate_legacy_policies.py`
  - `backend/apolices_legado.csv`
  - `backend/tests/test_migrate_legacy.py` (teste órfão do script)
  - `reset_sync.sql`
  - `smoke_test.py`
- **R3 skip** decisão do user: 3 modelos de `Appraisal` ficam como estão. Sem planos de adicionar 4ª variante. Re-avaliar quando surgir.

### Eventos importantes do Cycle 3
- `git fetch` revelou 5 commits novos no origin (incluindo `35ea268 feat(ds): rebuild every screen on the pipo design system` e `ds/nav.cljs` canônico)
- Pull + stash pop deu conflito em `revops/dashboard.cljs` (B2 já tinha mudado de lugar — sidebar agora vive em `ds/nav.cljs`)
- B2 reaplicado em `ds/nav.cljs` (lugar canônico, não mais inline no dashboard)
- **R2 cancelado** — já resolvido upstream pelo `ds/nav.cljs` (admin/ev/gerente/finance items unificados)
- **F1 invertido** — Cycle 1 propunha padronizar em `:navigate!`, mas o upstream usa `:navigate` (sem !) em 22+ lugares e zero `:navigate!`. Padronizei conforme o time: removido o event-fx `:navigate!` redundante, mantido o fx primitivo
- **R1 parcial** — extraí só `fmt-brl` (3 sites idênticos modulo parseFloat). `fmt-brl-int`/`fmt-int-brl` (3 sites) deixei intocados — têm contratos visuais divergentes (uns incluem prefixo "R$ ", outros não, e os call-sites compensam de jeitos diferentes). Refatorar arrisca regressão visual

---

## Stack & arquitetura (resumo)

- **Frontend**: ClojureScript + Reagent + re-frame + reitit (shadow-cljs)
- **Backend**: Flask + SQLAlchemy + Alembic, prefixo `/api/v1`
- **Auth**: Google SSO (prod) + dev-login picker (dev)

### Arquivos âncora
| Função | Arquivo |
|---|---|
| Entry + dispatch de views | `frontend/src/app/core.cljs` |
| Roteamento (reitit) + fx `:navigate!` | `frontend/src/app/routes.cljs` |
| Estado inicial re-frame | `frontend/src/app/state/db.cljs` |
| Eventos globais (`:initialize-db`, `:ui/*`, `:navigate`) | `frontend/src/app/state/events.cljs` |
| HTTP client (`:http` fx) — prefixa `/api/v1` | `frontend/src/app/api/client.cljs` |
| Catálogo de URLs | `frontend/src/app/api/endpoints.cljs` |
| Design system | `frontend/src/app/ds/*` |
| App factory + blueprints | `backend/app/__init__.py`, `backend/app/api/__init__.py` |

### Convenções
- Views ficam em `views/{revops,finance,gerente,ev,cn,shared}/`
- Cada role tem seu próprio `events.cljs` e `subs.cljs`
- Estado vive todo no `app-db` re-frame, dividido por área (`:auth`, `:ui`, `:policies`, `:commissions`, `:goals`, `:appraisal`, `:validations`, `:finance`, `:admin`, `:notifications`)
- API client adiciona automaticamente `/api/v1` (`config.cljs:3`), então URLs em `endpoints.cljs` começam com `/auth/...`, `/admin/...`, etc.
- Roles: `ADMIN`, `FINANCE`, `GERENTE`, `EV`, `CN`

---

## Bugs e issues priorizados

### 🔴 Críticos (Cycle 2 — ✅ aplicados, faltam testes em browser)

#### B1 — Botão "Entrar com SSO Google" era placeholder
**Arquivo**: `frontend/src/app/auth/views.cljs:167-174`

**Decisão tomada**: Google Identity Services não está carregado no `index.html` e nenhum lugar do código integra o fluxo OAuth real — apenas o backend (`auth.py:122` POST `/auth/google`) está pronto. Como integrar GIS é trabalho separado, o fix mínimo honesto foi tornar o botão visivelmente desabilitado com label "Google SSO — em integração", para o usuário cair direto no dev-login picker em vez de clicar em controle morto.

**Quando GIS for integrado**: remover `:disabled true`, adicionar handler que carrega `https://accounts.google.com/gsi/client`, pega o `code` e dispatcha `[:auth/google-login code]` (evento já funcional em `auth/events.cljs:4-12`).

#### B2 — Sidebar do RevOps escondia 4 telas que existem
**Arquivo**: `frontend/src/app/views/revops/dashboard.cljs:20-23`

Adicionados 4 itens entre "Apuração" e "Contestações":
- `:revops/cn-goals`     → "Metas CN"
- `:revops/cn-appraisal` → "Apuração CN"
- `:revops/ev-bonus`     → "Bônus EV"
- `:revops/leadership`   → "Liderança"

**Nota**: ícones reusam emojis do conjunto SVG do design-system (`ds/layout.cljs:16-25`). Alguns colidem visualmente com itens existentes (🎯 Metas vs Metas CN, 👤 Usuários vs Liderança); aceitável por ora — refinar em Cycle 4 (estética).

#### B3 — Rotas `:home` (`/`) e `:login` caíam em 404 após autenticação
**Arquivo**: `frontend/src/app/routes.cljs:62-83`

**Solução escolhida**: em vez de tratar `:home`/`:login` no `case` de `core.cljs` (que dispatcharia dentro do render — risco de loop), o evento `:route/changed` foi convertido de `reg-event-db` para `reg-event-fx`. Quando rota é `:home` ou `:login` e o usuário está autenticado, ele agrega `:navigate!` ao map de fx para redirecionar ao landing do role.

Helper `role->landing` extraído em `routes.cljs:63-70` — pode ser reusado em `auth/events.cljs:34-40` (que tem a mesma `case` duplicada) num cycle futuro.

**Casos cobertos**:
- ✅ User logado faz F5 em `/` → redireciona ao dashboard do role
- ✅ User logado digita `/login` manualmente → idem
- ✅ User logado dá back no browser para `/` → idem
- ⚠️ User não logado faz F5 em `/` → continua mostrando login page (`core.cljs:71`); ainda precisa de persistência de sessão (fora do escopo)

### 🧪 Testes pendentes (Cycle 2)
Não rodei o frontend porque shadow-cljs não está instalado localmente. Quando quiser validar:
1. `cd frontend && npm install && npx shadow-cljs watch app`
2. Login via dev-picker como ADMIN, FINANCE, GERENTE, EV, CN — verificar que cada role abre seu dashboard
3. Navegar manualmente para `/` e `/login` autenticado — deve redirecionar
4. Sidebar RevOps deve listar 17 itens (era 13)
5. Botão Google SSO deve aparecer disabled com texto "Google SSO — em integração"

---

### 🔴 Crítico mas não no escopo do Cycle 2

#### B4 — Endpoints fantasma em `endpoints.cljs` (dead code)
**Arquivo**: `frontend/src/app/api/endpoints.cljs:26, 28, 44`

Definidos mas nunca chamados pelo frontend, e sem rota Flask correspondente:
- `appraisal-run`              → 0 chamadas, sem `/appraisals/<id>/run` no backend
- `appraisal-approve-payment`  → 0 chamadas, sem `/appraisals/<id>/approve-payment` no backend
- `commission-table-import`    → 0 chamadas, backend só tem `/admin/commission-table` (POST simples)

**Ação**: deletar as 3 linhas. Sem efeito funcional.

#### B5 — `:revops/save-cn-goals` faz PUT sem query string
**Arquivo**: `frontend/src/app/views/revops/cn_goals.cljs:40` (PUT) vs `:21` (GET com `?month=&year=`)

**Suspeita não confirmada**. Precisa abrir `backend/app/api/v1/cn_commissions.py:41` e ver se o handler PUT espera `month/year` no body ou na query.

---

### 🟡 Inconsistências frágeis (Cycle 3)

#### F1 — `:navigate` vs `:navigate!` coexistem
- `:navigate!` é fx em `routes.cljs:80-88` E também event-fx em `routes.cljs:91-94`
- `:naviget` (sem `!`) é event-fx redundante em `state/events.cljs:35-39` que só repassa para `:navigate!`

**Dispatches `[:navigate ...]`** (sem `!`):
- `frontend/src/app/views/revops/dashboard.cljs:116, 122, 138, 143, 153`
- `frontend/src/app/ds/layout.cljs:135` (sidebar — afeta TODAS as páginas)
- `frontend/src/app/views/shared/not_found.cljs:35`

**Dispatches `[:navigate! ...]`**: 10+ outros lugares.

**Fix proposto**: padronizar em `:navigate!` (semântica `!` = side-effect), migrar os 7 dispatches acima e remover o evento `:navigate` redundante de `state/events.cljs:35-39`.

#### F2 — URLs hard-coded em vez de `endpoints.cljs`
| Arquivo:linha | URL hard-coded | Tem em endpoints? |
|---|---|---|
| `auth/events.cljs:9`  | `/auth/google` | sim (`auth-google`) |
| `auth/events.cljs:19` | `/auth/dev-login` | não |
| `auth/events.cljs:55` | `/auth/refresh` | sim (`auth-refresh`) |
| `auth/views.cljs:22`  | `/api/v1/auth/dev-users` (`js/fetch` direto) | não |
| `revops/events.cljs:537` | `/validations/<id>/resolve` | não |
| `revops/events.cljs:577` | `/admin/sync-trigger` | sim (`sync-trigger`) — não usado |
| `finance/events.cljs:51,60` + `revops/events.cljs:333,374,391` | `/appraisals/<id>/transition` (5x) | não |
| `finance/events.cljs:78` | `/api/v1/finance/export?...` (duplica base URL) | não |

---

### 🔄 Redundância (Cycle 3)

#### R1 — `fmt-brl` reimplementado em 12 arquivos
Mesma função (`js/parseFloat` → `toLocaleString("pt-BR")`):
- `views/ev/dashboard.cljs:15`
- `views/ev/deals_table.cljs:7`
- `views/ev/validation.cljs:19`
- `views/finance/approval.cljs:16`
- `views/finance/dashboard.cljs:19`
- `views/finance/saldo_devedor.cljs:5`
- `views/gerente/dashboard.cljs:14`
- `views/gerente/ev_detail.cljs:13`
- `views/revops/achievements.cljs:13`
- `views/revops/appraisal_review.cljs:15`
- `views/revops/goals.cljs:14`
- `views/revops/policies.cljs:15`

**Fix proposto**: criar `frontend/src/app/utils/format.cljs` com `fmt-brl`, migrar os 12 sites.

#### R2 — `sidebar-items` definido 5x (uma por role)
- `revops-shell/sidebar-items` em `revops/dashboard.cljs:10` — bem (compartilhado por 13 telas via alias)
- `cn-shell/sidebar-items` em `cn/dashboard.cljs:10` — bem
- **`ev/...`**: 3 cópias separadas (`dashboard.cljs:10`, `history.cljs:12`, `validation.cljs:14`)
- **`gerente/...`**: 2 cópias (`dashboard.cljs:11`, `ev_detail.cljs:10`)
- **`finance/...`**: 2 cópias (`dashboard.cljs:15`, `approval.cljs:12`)

**Fix proposto**: criar `views/{ev,gerente,finance}/shell.cljs` com a lista única, importar nas views por alias (mesmo padrão do `revops-shell`).

---

### 🟢 Refactor opcional (Cycle 4)

#### R3 — 3 modelos de Appraisal sobrepostos
- `backend/app/models/appraisal.py` — `Appraisal` (genérica trimestral)
- `backend/app/models/cn_monthly_appraisal.py` — `CnMonthlyAppraisal`
- `backend/app/models/gerente_quarter_appraisal.py` — `GerenteQuarterAppraisal`

Schemas similares (`user_id`, período, score, valor, `is_final`, timestamps). Candidato a `BaseAppraisal` abstrato com discriminator. **Só vale a pena se forem adicionar mais variantes.**

---

### ⚠️ Vestígios — confirmar com user

| Arquivo | Status |
|---|---|
| `backend/migrate_legacy_policies.py` | One-shot. Hardcoded `_LAST_APPRAISAL = date(2025, 12, 1)` (passada — hoje é 2026-05-01). Provavelmente já rodado. |
| `backend/apolices_legado.csv` | Existe, só referenciado pelo script acima. Provável vestígio. |
| `backend/reset_sync.sql` | 1 linha SQL para resetar `hubspot_sync_status`. Operação manual, sem CLI. |
| `backend/smoke_test.py` | Não está em CI (`.gitlab-ci.yml`). |

---

## Falsos positivos (não re-investigar)

Coisas que os subagentes me reportaram mas verifiquei e **não são bugs**:

- ❌ `:navigate` event não registrado → **falso**, está em `state/events.cljs:36`
- ❌ `app.views.ev.events` órfão → **falso**, importado em `core.cljs:21`
- ❌ `deals_table.cljs`, `policy_edit_modal.cljs`, `fluxo_caixa`, `orcado_realizado`, `saldo_devedor` órfãos → **falso**, todos importados pelos respectivos dashboards
- ❌ `compat.py` shim suspeito → **falso**, são `TypeDecorator`s reais para SQLite/PG
- ❌ `/finance/export` inexistente no backend → **falso**, existe em `finance_dashboard.py:116`

---

## Estrutura de diretórios sugerida (mínima)

A organização atual está OK. Adições:

```
frontend/src/app/
  utils/
    format.cljs       ← NOVO (R1): fmt-brl, fmt-date, helpers genéricos
  views/{ev,gerente,finance}/
    shell.cljs        ← NOVO (R2): sidebar-items único por role
```

Backend não precisa de mudanças estruturais.

---

## Como retomar em uma nova sessão

1. Abrir este arquivo (`AUDIT.md`) — dá o contexto completo.
2. Verificar onde paramos no `Status atual` (topo).
3. Para qualquer fix, **conferir as linhas atuais** dos arquivos referenciados aqui (linhas mudam à medida que código é editado).
4. Antes de aceitar qualquer recomendação como verdade, validar com grep — vide a seção de "Falsos positivos" como lembrete de que os subagentes podem errar.

---

## Plano de ataque (ordenado)

| # | Severidade | Item | Esforço | Status |
|---|---|---|---|---|
| 1 | 🔴 | B1 — Google SSO botão honestamente disabled | ~5 min | ✅ aplicado |
| 2 | 🔴 | B2 — sidebar revops 4 itens adicionados | ~5 min | ✅ aplicado |
| 3 | 🔴 | B3 — `:home`/`:login` redirect ao dashboard do role | ~15 min | ✅ aplicado |
| 4 | 🟡 | B4 — remover 3 endpoints fantasma | ~5 min | ✅ aplicado |
| 5 | 🟡 | F1 — padronizar `:navigate` (remover event-fx `:navigate!` órfão) | ~10 min | ✅ aplicado (invertido vs Cycle 1) |
| 6 | 🟡 | R1 — `app/utils/format.cljs` + migrar **7** sites (`fmt-brl` + `fmt-brl-int` + `int-brl`) | ~40 min | ✅ aplicado (completo) |
| 7 | 🟡 | R2 — `shell.cljs` por role | — | ✅ resolvido upstream (`ds/nav.cljs`) |
| 8 | 🟡 | F2 — substituir 5 URLs hard-coded por `ep/*` | ~15 min | ✅ aplicado |
| 9 | 🟢 | B5 — confirmar contrato PUT cn-goals | ~10 min | ✅ falso positivo, sem bug |
| 10 | 🟢 | Vestígios — arquivar 4 (+1 teste órfão) | ~5 min | ✅ aplicado |
| 11 | 🟢 | R3 — base `Appraisal` abstrato | — | ⏭️ skip (sem 4ª variante prevista) |
