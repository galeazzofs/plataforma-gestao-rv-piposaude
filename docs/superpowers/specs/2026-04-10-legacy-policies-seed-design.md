# Design: Seed de Apólices Legado

**Data:** 2026-04-10
**Status:** Aprovado

---

## Contexto

Antes da plataforma existir, diversas apólices já estavam em vigência e com pagamentos realizados. Essas apólices já estão no banco (via HubSpot sync), mas sem os campos `initial_installments_paid` e `first_payment_real` preenchidos. O CSV `apolices_legado.csv` contém o baseline dessas apólices.

Para apólices que **não estão no CSV** (fechadas depois da plataforma ser criada), a primeira vez que aparecerem numa apuração deve ser contada como o primeiro pagamento.

---

## Escopo

Duas mudanças independentes:

1. **Script de migração one-time** — popula `initial_installments_paid` e `first_payment_real` nas policies legadas
2. **Mudança no calculator** — auto-seta `first_payment_real` na primeira NF que bater numa policy sem data de vigência

---

## Parte 1: Script de Migração

### Arquivo

`backend/migrate_legacy_policies.py`

### Uso

```bash
python migrate_legacy_policies.py --dry-run   # imprime o que seria alterado, sem salvar
python migrate_legacy_policies.py             # executa e persiste no banco
```

### Campos do CSV

| Campo CSV        | Campo DB                          |
|-----------------|-----------------------------------|
| Cliente          | Client.name (lookup por nome normalizado) |
| Executivo_Vendas | (informativo, não usado no update) |
| Operadora        | Policy.partner_operator (normalizado) |
| Produto          | Policy.benefit_type (SAUDE/ODONTO/VIDA) |
| Inicio_Vigencia  | Policy.first_payment_real         |
| Meses_Pagos      | Policy.initial_installments_paid  |

### Lógica por linha

1. **Skip**: `Meses_Pagos = 0` E `Inicio_Vigencia` vazio → nada a atualizar, log `[SKIP]`
2. **Calcular `first_payment_real`**:
   - Se `Inicio_Vigencia` preenchido → usa essa data (formato `dd/mm/yyyy`)
   - Se `Inicio_Vigencia` vazio mas `Meses_Pagos > 0` → inferir pela última apuração (Dez/2025):
     - `first_payment_real = 2025-12-01 - (Meses_Pagos - 1) meses`
     - Exemplos: 1 mês → 2025-12-01, 2 meses → 2025-11-01, 3 meses → 2025-10-01
3. **Matching**: busca Policy por (client_id, benefit_type, partner_operator) com normalização de nomes (lowercase, sem acentos, strip)
4. **Update**: seta `initial_installments_paid` e `first_payment_real` na policy encontrada, log `[MATCH]` ou `[INFER]`
5. **Não encontrado**: log `[MISS]` com detalhes para resolução manual

### Normalização de nomes

- Lowercase
- Remove acentos (unicodedata NFKD)
- Strip whitespace

### Output esperado (dry-run)

```
[MATCH]  Celcoin | Sulamérica | Saúde → initial_installments_paid=11, first_payment_real=2026-04-25
[INFER]  BEYOUNG | Porto Seguro | Saúde → initial_installments_paid=2, first_payment_real=2025-11-01
[SKIP]   Arvo | Bradesco | Saúde → Meses_Pagos=0, sem data
[MISS]   Indigo → cliente não encontrado no banco
---
Summary: 48 updated, 32 skipped, 3 not found
```

### O que NÃO é feito

- Não cria policies novas (apenas atualiza existentes)
- Não altera outros campos da policy (segment, mrr, is_locked, etc.)
- Não afeta policies com `is_locked=True` (respeita o lock)

---

## Parte 2: Mudança no Calculator

### Arquivo

`backend/app/modules/commissions/calculator.py`

### Comportamento atual

Se `Policy.first_payment_real = null`, nenhuma NF bate (janela de vigência inexistente → UNMATCHED ou PRE_VIGENCIA).

### Novo comportamento

No **Pass 1 do NF matching** (`run_quarterly_appraisal`), ao encontrar uma policy candidata com `first_payment_real = null`:

1. Seta `policy.first_payment_real = nf.data` (data da NF)
2. Conta essa NF como mês 1 (match válido)
3. Persiste o `first_payment_real` no banco

### Regras

- **Uma vez só**: após setar `first_payment_real`, o fluxo normal de janela de 12 meses vale
- **Persistência**: a data fica no banco mesmo se a apuração for deletada depois — intencional, representa "vimos o primeiro pagamento nessa data"
- **Policies legadas**: já terão `first_payment_real` setado pelo script de migração, nunca caem nesse fluxo
- **Apurações LOCKED**: NFs de comissões finalizadas não re-trigam esse comportamento (a policy já tem `first_payment_real`)

### Pseudo-código

```python
# Pass 1 - ao avaliar candidato
if policy.first_payment_real is None:
    # Auto-detect: primeira aparição na apuração
    policy.first_payment_real = nf_date
    # segue para incrementar installments_paid normalmente

# Lógica de vigência existente continua igual para os demais casos
```

---

## Campos de Modelo Relevantes

| Campo                        | Tipo    | Uso                                                        |
|------------------------------|---------|-------------------------------------------------------------|
| `Policy.initial_installments_paid` | int | Baseline de meses pagos antes do sistema (setado pela migração) |
| `Policy.first_payment_real`  | Date    | Início da janela de 12 meses de vigência                   |
| `Policy.installments_paid`   | int     | Calculado a cada apuração: `initial_installments_paid + NFs matched` |

---

## Sequência de Deploy

1. Rodar `python migrate_legacy_policies.py --dry-run` e revisar output
2. Se ok, rodar `python migrate_legacy_policies.py`
3. Deploy da mudança no calculator (Parte 2) junto ou depois
