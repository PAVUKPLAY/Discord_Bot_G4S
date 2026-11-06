from config import MODERATOR_ROLE_IDS

def has_moderator_role(member):
    # Fail closed: an empty moderator list must never grant admin actions to everyone.
    if not MODERATOR_ROLE_IDS:
        return False
    if not getattr(member, 'roles', None):
        return False
    member_role_ids = [role.id for role in member.roles]
    return any(role_id in member_role_ids for role_id in MODERATOR_ROLE_IDS)
