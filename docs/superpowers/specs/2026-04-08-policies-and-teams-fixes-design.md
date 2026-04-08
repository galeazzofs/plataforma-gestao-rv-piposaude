# Design — Fixes em Apólices, Usuários e Times

**Data:** 2026-04-08
**Autor:** Eric Valoz (RevOps) + assistente
**Escopo:** Bug fixes + enriquecimento de dados nas páginas de Apólices, Usuários e Times

## Problemas

1. **Página de Apólices**
   - Coluna EV não existe (deveria mostrar nome do EV; nunca pode ficar vazia)
   - Faltam campos previstos pela spec v2.2 §3.5: `dealstage`, `deploy_date`, `first_payment_prev`, `mrr_post_deploy`
   - `benefit_type` aparece como enum cru (`SAUDE`, `ODONTO`, `VIDA`)

2. **Página de Usuários**
   - Coluna "Time" sempre vazia → `_serialize_user` não retorna `team_name`
   - Lista mostrando usuários soft-deleted (fix já parcialmente aplicado, não commitado)

3. **Página de Times**
   - "Líder" sempre vazio e contador de membros sempre zero → `_serialize_team` não retorna `leader_name` nem `members`
   - Não há fluxo direto para adicionar/remover usuários de um time pela própria página de Times

## Causas-raiz

| Sintoma | Arquivo:linha | Causa |
|---|---|---|
| EV vazio em Apólices | `backend/app/api/v1/policies.py:168-195` | `_serialize_policy` só retorna `ev_id`, não `ev_name`. Demais campos só aparecem com `detail=True` |
| Sem Estágio/Datas/MRR pós-impl. em Apólices | `frontend/src/app/views/revops/policies.cljs:35-51` | Colunas não existem no array `build-columns` |
| Time vazio em Usuários | `backend/app/api/v1/admin.py:538-546` | `_serialize_user` não faz join com Team |
| Líder/Membros vazios em Times | `backend/app/api/v1/admin.py:549-554` | `_serialize_team` não retorna `leader_name` nem `members[]` |
| Lista mostrando inativos | `backend/app/api/v1/admin.py:14-33` | `list_users` sem filtro default por `active=True` (fix pendente, não commitado) |
| Sem gestão de membros pela página Times | `frontend/src/app/views/revops/teams.cljs` | Modal só edita name+leader; não há add/remove member |

## Solução

### Backend

**`backend/app/api/v1/admin.py`**
- `_serialize_user`: adicionar `team_name` (lookup `db.session.get(Team, u.team_id)`)
- `_serialize_team`: adicionar `leader_name` + `members: [{id, name, role, email}]` (query `User.query.filter_by(team_id=t.id, active=True)`)
- Commitar fix de `list_users` (filter `User.active.is_(True)` por default; `?active=all` libera)
- Novos endpoints:
  - `POST /admin/teams/<team_id>/members` body `{user_id}` → seta `user.team_id`
  - `DELETE /admin/teams/<team_id>/members/<user_id>` → seta `user.team_id = None`
  - Ambos com audit log

**`backend/app/api/v1/policies.py`**
- `_serialize_policy`: mover `ev_name`, `deal_stage`, `deploy_date`, `first_payment_prev`, `mrr_post_deploy` para o payload base (não apenas `detail=True`)

### Frontend

**`frontend/src/app/views/revops/policies.cljs`**
- Adicionar colunas: **EV** (ev_name), **Estágio** (deal_stage cru — virá enriquecido do HubSpot), **Implantação** (deploy_date), **Prev. 1º Pag.** (first_payment_prev), **MRR Pós-Impl.** (mrr_post_deploy formatado BRL)
- Helper `fmt-benefit` mapeando `SAUDE`→"Saúde", `ODONTO`→"Odonto", `VIDA`→"Vida"
- Helper `fmt-date` para datas ISO → `dd/mm/yyyy`
- Reduzir/colapsar colunas pouco críticas se necessário (`installments_paid` pode virar tooltip)

**`frontend/src/app/views/revops/teams.cljs`**
- Nova ação "Membros" abre `manage-members-modal`:
  - Lista usuários atuais do time com botão "Remover"
  - Seletor "Adicionar usuário" populado com `users` SEM `team_id` (ou com outro time, mostrando confirmação)
  - Dispatch `:revops/add-team-member` / `:revops/remove-team-member`

**`frontend/src/app/views/revops/events.cljs`**
- `:revops/add-team-member` → POST `/admin/teams/{id}/members`, on-success refetch teams + users
- `:revops/remove-team-member` → DELETE, idem

### Verificação geral

- Grep por handlers re-frame chamados sem definição correspondente
- Grep por endpoints frontend ausentes no backend (e vice-versa)
- Rodar `pytest backend` se existir suite e for rápida

## Não-objetivos

- Não alterar lógica de cálculo de comissão
- Não tocar em sync HubSpot
- Não refatorar paginação ou layout geral

## Riscos

- Se `deal_stage` vier `null` para policies antigas (HubSpot não populou ainda), aparece como "—" — esperado
- Adição de `team_name` em `_serialize_user` faz N+1 queries; aceitável (lista pequena, <500 usuários)
