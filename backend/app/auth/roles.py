from app.models.user import UserRole

PERMISSIONS = {
    UserRole.ADMIN: ["*"],
    UserRole.FINANCE: [
        "policies:read_all", "commissions:read_all",
        "finance:dashboard", "finance:export",
        "appraisals:approve_payment", "appraisals:return",
    ],
    UserRole.LIDER_VENDAS: ["policies:read_team", "commissions:read_team"],
    UserRole.EV: [
        "policies:read_own", "commissions:read_own",
        "validations:read_own", "validations:approve", "validations:contest",
    ],
    UserRole.CN: [
        "policies:read_own", "commissions:read_own",
        "validations:read_own", "validations:approve", "validations:contest",
    ],
}

def user_has_permission(role, permission):
    if role is None:
        return False
    perms = PERMISSIONS.get(role, [])
    return "*" in perms or permission in perms

def user_has_any_role(role, *allowed_roles):
    if role == UserRole.ADMIN:
        return True
    return role in allowed_roles
