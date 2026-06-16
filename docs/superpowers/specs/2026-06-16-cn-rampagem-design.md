# Rampagem no cálculo de comissão do CN

**Data:** 2026-06-16
**Status:** Aprovado (design)

## Problema

Hoje a comissão mensal do CN tem um único cálculo (`simulate_cn`):
`score = pct_sao×0,70 + pct_vidas×0,30` → régua → `comissão = base_nível × multiplicador`.

CNs em **rampagem** (período inicial de rampa) são remunerados por uma régua
de **atividade/cadência**, não por SAO/vidas. Existem duas variantes de
rampagem, e o sistema precisa aplicar o cálculo certo automaticamente quando o
CN está marcado como "em rampagem".

## Regras de negócio

### Régua / Gatilho (idêntica à atual `_regua`)

O **gatilho** é a régua aplicada ao atingimento — é o multiplicador final:

| Atingimento | Gatilho (% do variável) |
|---|---|
| 0–20%   | 0 |
| 21–40%  | 20% |
| 41–100% | o próprio atingimento ("em linha") |
| 101–110%| 120% |
| 111–139%| 180% |
| ≥140%   | 210% |

Isto é exatamente `_regua()` em `backend/app/modules/commissions/simulator.py`
e `calc/regua` em `frontend/src/app/views/cn/calc.cljs`. Reutilizar sem
duplicar a tabela.

**Target CN** = base do nível (CN1 2000 / CN2 2500 / CN3 3000), inalterado.

### Modos de cálculo

O modo é decidido automaticamente por apuração:

| Condição | Modo | Atingimento |
|---|---|---|
| `em_rampagem = false` | `NORMAL` | `pct_sao×0,70 + pct_vidas×0,30` (hoje) |
| `em_rampagem = true` **e** meta SAO do mês `= 0` | `RAMPAGEM_SEM_SAO` | `0,50×min(neg/neg_meta, 1) + 0,50×min(emails/emails_meta, 1)` |
| `em_rampagem = true` **e** meta SAO do mês `> 0` | `RAMPAGEM_COM_SAO` | `0,50×(sao/sao_meta) [SEM teto] + 0,50×min(qualis/qualis_meta, 1)` |

Observações:
- **SEM SAO**: ambos os KPIs são de atividade, ambos com teto de 100%.
- **COM SAO**: o KPI de resultado (SAO) **não tem teto** (pode passar de 100% e
  subir de faixa na régua); o KPI de atividade (Qualis Agendadas) tem teto 100%.
- Vidas **não** participa de nenhum modo de rampagem.

### Comissão final

- `gatilho = regua(atingimento)` (em todos os modos)
- **NORMAL**: `comissão = base × gatilho` (inalterado)
- **RAMPAGEM_SEM_SAO**: `comissão = base × gatilho + bonus_sao × (nº SAO fora da meta)`
- **RAMPAGEM_COM_SAO**: `comissão = base × gatilho` (sem bônus de SAO — o SAO já
  está no atingimento)

`bonus_sao` = **R$ 300**, configurável (não % do Target, valor fixo).

**Validação contra o print (SEM SAO):** neg 103/60 e emails 1133/400 →
atingimento `0,5×1 + 0,5×1 = 100%` → gatilho 100% → `3000×1,0 + 300×1 = 3300`. ✅

## Modelo de dados

### `User`
- `+ em_rampagem BOOLEAN NOT NULL DEFAULT false` — só relevante para role CN.
  Limpo (false) quando o role deixa de ser CN, como já ocorre com nivel/porte.

### `CnMonthlyGoal` (metas, definidas pelo admin)
- `+ negocios_cadencia_meta NUMERIC(12,2) NOT NULL DEFAULT 0`
- `+ emails_meta NUMERIC(12,2) NOT NULL DEFAULT 0`
- `+ qualis_agendadas_meta NUMERIC(12,2) NOT NULL DEFAULT 0`

`sao_target` já existe e é o que decide a variante (com/sem SAO). As metas de
cadência só são usadas quando o CN está em rampagem.

### `CnMonthlyAppraisal`
- `+ calc_mode VARCHAR` — `NORMAL` / `RAMPAGEM_SEM_SAO` / `RAMPAGEM_COM_SAO`
- `+ negocios_cadencia_realizado NUMERIC(12,2) NOT NULL DEFAULT 0`
- `+ emails_realizado NUMERIC(12,2) NOT NULL DEFAULT 0`
- `+ qualis_agendadas_realizado NUMERIC(12,2) NOT NULL DEFAULT 0`
- `+ sao_fora_da_meta INTEGER NOT NULL DEFAULT 0`
- `+ bonus_sao_amount NUMERIC(12,2) NOT NULL DEFAULT 0`

**Reuso decidido:** `score_final` guarda o **atingimento** e `multiplicador`
guarda o **gatilho**. Mesma semântica score→multiplicador da régua; mantém o
serializer, a UI (colunas Score/Mult.) e o bônus trimestral (que lê
`sao_realizado`/`sao_target`, não estes campos) sem alterações. Em rampagem,
`pct_sao`/`pct_vidas` são gravados como 0.

Migration Alembic nova adicionando todas as colunas acima
(`down_revision` = head atual).

### `PlatformSetting`
- key `cn_rampagem_bonus_sao`, value numérico (default 300). Lido pelo calculator
  e editável na tela de Settings.

## Camada de cálculo (pura, sem DB)

`backend/app/modules/commissions/simulator.py` (e espelho em `calc.cljs`):

- `simulate_cn_rampagem_sem_sao(nivel, neg_meta, neg_real, emails_meta, emails_real, sao_fora_da_meta, bonus_sao)`
- `simulate_cn_rampagem_com_sao(nivel, sao_meta, sao_real, qualis_meta, qualis_real)`
- dispatcher `simulate_cn_auto(em_rampagem, nivel, sao_meta, ...)` que escolhe entre
  as 3 (NORMAL via `simulate_cn` existente).

Todas reutilizam `_regua`. Retornam o mesmo shape do `simulate_cn` (chaves como
str) + chaves extras: `calc_mode`, `atingimento`, `gatilho`, `bonus_sao_amount`.
Para compatibilidade, `score_final`=atingimento e `multiplicador`=gatilho no
retorno.

## API

- `cn_calculator.run_cn_monthly_appraisal_with_inputs`: por CN, ramifica pelo
  modo (lê `cn.em_rampagem` e `goal.sao_target`); inputs passam a aceitar
  `negocios_cadencia_realizado`, `emails_realizado`, `qualis_agendadas_realizado`,
  `sao_fora_da_meta`. Persiste os novos campos + `calc_mode`. `run_cn_monthly_appraisal`
  (zero-input) também ramifica.
- `cn_calculator` lê `bonus_sao` de `PlatformSetting.get("cn_rampagem_bonus_sao", 300)`.
- `upsert_cn_goals` / `_serialize_cn_row`: aceitam e devolvem as metas de cadência.
- `_apply_profile_fields` + `_serialize_user`: aceitam/devolvem `em_rampagem`.
- `/commissions/cn/simulate`: aceita os params de rampagem e devolve o breakdown
  do modo aplicado.
- Settings: endpoint para ler/gravar `cn_rampagem_bonus_sao` (ADMIN).
- `_serialize_appraisal`: inclui os novos campos (`calc_mode`, realizados de
  cadência, `sao_fora_da_meta`, `bonus_sao_amount`, e expõe `atingimento`/`gatilho`).

## Frontend (ClojureScript)

- **calc.cljs**: `regua` já existe; adicionar `rampagem-sem-sao` e
  `rampagem-com-sao` espelhando o backend, + um `calculate-auto`.
- **users.cljs**: checkbox "Em rampagem" no modal do CN (ao lado de nivel/porte).
- **cn_goals.cljs**: para CN `em_rampagem`, exibir os campos de meta certos
  (negócios + emails quando SAO=0; qualis quando SAO>0). Persistir via PUT.
- **cn_appraisal.cljs**: trocar as colunas de input conforme o modo do CN; prévia
  ao vivo de Atingimento / Gatilho / Comissão (reusando calc.cljs); coluna/campo
  de "SAO fora da meta" no modo SEM SAO.
- **simulator.cljs**: opção de simular em modo rampagem.
- **settings.cljs**: campo numérico para o bônus de SAO.

## Testes

- Unidade (`test_cn_calculator` / novo `test_simulator`): caso do print (3300),
  caso COM SAO passando de 100% (gatilho sobe de faixa), faixas-limite da régua,
  bônus configurável.
- API: `run_cn_monthly_appraisal_with_inputs` com CN em rampagem (cada variante),
  upsert de metas de cadência, toggle `em_rampagem` no admin.

## Fora de escopo

- Bônus trimestral de SAO do CN (continua lendo `sao_realizado`/`sao_target`).
- Detecção automática de quando a rampagem termina (admin liga/desliga manual).
- Puxar cadência/emails do HubSpot (realizados são digitados na apuração).
