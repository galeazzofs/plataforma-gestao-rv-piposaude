from app.models import AppraisalStatus

# Valid transitions: from_status → [to_statuses]
#
# Sequência: DRAFT → CALCULATING → VALIDATING → LIDER_REVIEW → REVOPS_REVIEW → LOCKED.
# REVOPS_REVIEW pode voltar para CALCULATING; LIDER_REVIEW também.
# Finance aprova movendo direto para LOCKED. Reabrir após LOCKED volta para
# REVOPS_REVIEW (a nota obrigatória é validada na camada de API).
VALID_TRANSITIONS = {
    AppraisalStatus.DRAFT: [AppraisalStatus.CALCULATING],
    AppraisalStatus.CALCULATING: [AppraisalStatus.VALIDATING],
    AppraisalStatus.VALIDATING: [
        AppraisalStatus.LIDER_REVIEW,
        # Abort validation to recalculate — values only change in
        # CALCULATING; entering it voids the EvValidations attested
        # against the old numbers (reset in the state machine).
        AppraisalStatus.CALCULATING,
    ],
    AppraisalStatus.LIDER_REVIEW: [
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.CALCULATING,  # Recalculate if needed
    ],
    AppraisalStatus.REVOPS_REVIEW: [
        AppraisalStatus.LOCKED,
        AppraisalStatus.CALCULATING,  # Recalculate if needed
    ],
    AppraisalStatus.LOCKED: [AppraisalStatus.REVOPS_REVIEW],  # Reopen
}
