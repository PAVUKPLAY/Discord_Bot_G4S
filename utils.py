from config import MODERATOR_ROLE_IDS

def has_moderator_role(member):
    if not MODERATOR_ROLE_IDS:
        return True  # если роли не заданы – доступ всем
    member_role_ids = [role.id for role in member.roles]
    return any(role_id in member_role_ids for role_id in MODERATOR_ROLE_IDS)
