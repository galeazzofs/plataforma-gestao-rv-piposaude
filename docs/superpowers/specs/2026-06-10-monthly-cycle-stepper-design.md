# Ciclo Mensal — trilho passo-a-passo (design)

**Data:** 2026-06-10
**Status:** aprovado em brainstorming, aguardando implementação

## Problema

A página do Ciclo Mensal (`/admin/monthly-cycle`) hoje é um dashboard de cards
agrupados por time: para executar a apuração, o RevOps precisa pular entre as
páginas dedicadas (Apuração EV, Apuração CN, bônus) e voltar. Não há senso de
"onde estou / o que falta". O objetivo é uma experiência fluida: entrar na
página e ir executando os passos do ciclo ali mesmo, em sequência.

## Decisões de requisito (Q&A com o usuário)

1. **Apuração EV e Apuração CN são independentes** — podem rodar em paralelo;
   a ordem no trilho é apenas sugestão de leitura, sem dependência de dados.
2. **Orienta, não trava** — os bônus de fechamento de trimestre dependem em
   teoria das apurações fechadas, mas a página apenas avisa; nada é bloqueado.
3. **Orquestração inline + guia vivo** — ações de avanço (rodar cálculo,
   transicionar, finalizar, travar) executam na própria página do ciclo;
   trabalho fino (revisão linha a linha, resolver contestação com nota) abre a
   página dedicada já filtrada, com caminho de volta.
4. **Sem agrupamento por time** — não existe mais líder de G+; tudo cai para o
   Líder de Vendas P/M. O ciclo é global; o payload por time do aggregator sai.
5. **Seletor de ciclo proeminente + histórico detalhado** — navegar entre
   meses é frequente (mês anterior pode ainda estar aberto); ciclos LOCKED
   renderizam o mesmo trilho em modo leitura, servindo de histórico.

## Design — UX

### Estrutura da página

**Cabeçalho**

- Seletor de ciclo: `‹ Maio/2026 ›` com setas mês-a-mês + dropdown com todos
  os ciclos existentes e badge de status (Em andamento / Fechado). Mês
  selecionado sem ciclo → estado vazio com CTA "Abrir ciclo de <Mês/Ano>"
  (mantém a lógica de sugestão `suggest-cycle` atual, agora dirigida pelo
  seletor). Meses futuros podem ser abertos (a API já permite).
- Barra de progresso do ciclo: "N de M passos concluídos" + chip de status.
- Faixa de **próxima ação**: linha computada do estado atual — ex. "Próximo:
  enviar Apuração EV para validação" — com botão que executa a ação ou rola
  até o passo correspondente.

**Trilho vertical**

- Ordem dos passos: `1. Apuração EV` → `2. Apuração CN` → *(somente meses
  3/6/9/12)* divisor visual "Fechamento do Q<n>" → `3. Bônus CN` →
  `4. Bônus EV` → `5. Bônus Liderança`. Meses normais têm trilho de 2 passos.
- Passo atual = primeiro não-LOCKED na sequência → expandido e destacado.
- Passos concluídos → linha colapsada com ✓ e números-chave; clicável para
  reabrir.
- Passos futuros → esmaecidos mas clicáveis. Expandir um bônus com apurações
  ainda abertas mostra aviso amarelo ("Recomendado concluir as apurações
  antes") — sem bloqueio.

### Anatomia de um passo expandido

- **Topo**: número + nome + badge de status + mini-stepper do estado do
  componente (EV: Draft → Calculating → Validating → Líder Review → RevOps
  Review → Locked; CN idem; bônus têm versões curtas Pendente → Calculando →
  Final).
- **Corpo**: agregados-chave — EV: "x/y validações · R$ total apurado";
  CN: "n CNs apurados, m finais"; bônus: "rows/finais". Contestação aberta
  vira badge de alerta.
- **Rodapé**: botão de **ação primária do estado atual** inline + link
  "Ver detalhes →" para a página dedicada filtrada no mês/trimestre do ciclo.

Mapeamento da ação primária (componente + status → ação):

| Componente | Estado | Ação inline |
|---|---|---|
| Apuração EV | sem apuração | Criar apuração (DRAFT) |
| Apuração EV | DRAFT | Rodar cálculo |
| Apuração EV | CALCULATING | Enviar para validação |
| Apuração EV | VALIDATING | mostra progresso x/y; "Enviar p/ revisão do líder" habilita quando x = y |
| Apuração EV | LIDER_REVIEW / REVOPS_REVIEW | Avançar / Travar |
| Apuração CN | PENDING | Rodar apuração CN (mês) |
| Apuração CN | estados intermediários | Avançar todos (em lote) |
| Apuração CN | REVOPS_REVIEW | Finalizar todos (em lote) |
| Bônus CN | PENDING | Rodar bônus | 
| Bônus CN | CALCULATING | Finalizar |
| Bônus EV | PENDING | Rodar bônus |
| Bônus Liderança | PENDING | Rodar apuração |
| Bônus Liderança | intermediário | Avançar / Finalizar |

As regras de transição continuam validadas no backend (state machine); o
frontend apenas deriva o rótulo/dispatch da ação por uma função pura.

### Fim do ciclo e histórico

- Auto-lock existente (`maybe_lock_cycle`) inalterado: todos os componentes
  LOCKED → ciclo fecha. A página mostra estado "Ciclo fechado" com resumo dos
  totais e CTA "Abrir <próximo mês>".
- Ciclos LOCKED renderizam o trilho em modo leitura: passos colapsados com
  resumos, sem botões de ação. Esse é o histórico detalhado.

## Design — Backend

### Aggregator global (sem times)

`build_cycle_payload` deixa de retornar `teams: [...]` e retorna
`components: {...}` no nível do ciclo, com os mesmos agregados de hoje
(status, validações, rows/finais, contestação) calculados globalmente:

```json
{
  "id": "...", "month": 6, "year": 2026, "quarter": 2,
  "is_quarter_end": true, "sequence": ["ev_apuracao", "cn_apuracao",
  "cn_bonus", "ev_bonus", "leadership_bonus"],
  "status": "OPEN", "created_at": "...", "locked_at": null,
  "components": {
    "ev_apuracao": {"status": "VALIDATING", "appraisal_id": "...",
                     "validations_total": 15, "validations_done": 12},
    "cn_apuracao": {"status": "DRAFT", "rows": 8, "final": 0, "month": 6},
    "cn_bonus":    {"status": "PENDING", "rows": 0, "final": 0},
    "ev_bonus":    {"status": "PENDING", "rows": 0, "final": 0},
    "leadership_bonus": {"status": "PENDING", "has_contestation": false}
  }
}
```

- Cada componente inclui os ids que a ação inline precisa (ex.:
  `appraisal_id` da Apuração EV).
- Liderança agrega todas as `LiderVendasQuarterAppraisal` do (trimestre, ano)
  — na prática 1 (Líder P/M) — sem depender de `team.leader_id`.
- EVs/CNs elegíveis seguem as regras atuais (role + active/left_company),
  apenas sem particionar por `team_id`. CNs sem time deixam de ser caso
  especial.
- `all_components_locked` / `maybe_lock_cycle` inalterados na semântica
  (PENDING continua contando como não-LOCKED).

### Endpoints novos — ações em lote da Apuração CN

Rodar a apuração CN já é mês-level; `transition`/`finalize` hoje são por CN.
Para o botão do passo ser um clique:

- `POST /api/v1/cn-commissions/appraisal/transition-month`
  body `{month, year, to_status}` — aplica a transição a todas as
  `CnMonthlyAppraisal` do mês que estão no estado de origem válido.
- `POST /api/v1/cn-commissions/appraisal/finalize-month`
  body `{month, year}` — finaliza todas as elegíveis.

Comportamento comum: **pular** linhas com contestação aberta (a state machine
já bloqueia) e retornar `{advanced: n, skipped: [{cn_id, reason}]}`;
o card mostra "5 avançaram, 1 pulado por contestação". Ambos com
`require_role(ADMIN)` + `log_audit`, como os endpoints existentes.

Bônus CN (`/quarterly-bonus` + `/quarterly-bonus/finalize`), Bônus EV
(`/bonus`) e Liderança (`/appraisal`, `/finalize`) já são mês/trimestre-level
— sem mudanças.

### O que não muda

Model `MonthlyCycle`, migration `b9c0d1e2f3a4`, rotas das páginas dedicadas,
state machines (EV e CN), Slack DMs, lógica de contestação.

## Erros e casos de borda

- **Contestação aberta**: transições bloqueadas pela state machine; a ação
  inline mostra o erro no card com link "Resolver na página de detalhe →".
- **Refetch após ação**: toda ação inline bem-sucedida refaz o GET do payload
  do ciclo; sem estado otimista.
- **Componente sem dados** (mês sem EVs ativos, etc.): PENDING, card mostra
  "—", ciclo não auto-fecha (igual hoje).
- **Erro de ação em lote parcial**: o retorno advanced/skipped é exibido no
  card; nada é retentado automaticamente.
- **Exclusão de ciclo**: como hoje — só não-LOCKED, com confirmação.

## Testes

**Backend**

- Reescrever testes do aggregator para o payload global (sem `teams`).
- Endpoints em lote CN: caminho feliz, pula contestação aberta, mês sem
  apurações (404/no-op), idempotência (segunda chamada → `advanced: 0`),
  exigência de role ADMIN.
- Liderança agregada sem times.
- Auto-lock: comportamento preservado com payload novo.

**Frontend (cljs)**

- Função pura `next-action` (componente + status → ação/label).
- Ordem do trilho: mês normal (2 passos) vs fechamento (5 passos + divisor).
- Seletor: navegação mês-a-mês, sugestão de abertura, mês sem ciclo.
- Ciclo LOCKED → render read-only (sem botões de ação).

## Fora de escopo

- Mudanças nas páginas dedicadas além de aceitar filtro de mês/trimestre via
  query params (e link de volta ao ciclo).
- Notificações novas (Slack) disparadas pela página do ciclo.
- Qualquer mudança nas regras de cálculo das apurações/bônus.
