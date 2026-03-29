from app.models import AppraisalStatus

# Valid transitions: from_status → [to_statuses]
VALID_TRANSITIONS = {
    AppraisalStatus.DRAFT: [AppraisalStatus.CALCULATING],
    AppraisalStatus.CALCULATING: [AppraisalStatus.VALIDATING],
    AppraisalStatus.VALIDATING: [AppraisalStatus.REVIEWING],
    AppraisalStatus.REVIEWING: [
        AppraisalStatus.APPROVED,
        AppraisalStatus.CALCULATING,  # Recalculate if needed
    ],
    AppraisalStatus.APPROVED: [
        AppraisalStatus.LOCKED,
        AppraisalStatus.REVIEWING,  # Finance returns to RevOps
    ],
    AppraisalStatus.LOCKED: [],  # Terminal state
}
