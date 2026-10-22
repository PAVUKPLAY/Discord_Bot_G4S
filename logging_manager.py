import discord
import logging
import asyncio
from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

async def get_channel(bot):
    if not LOG_CHANNEL_ID: return None
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        try: channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except Exception: return None
    return channel

async def get_audit_executor(guild: discord.Guild, action_type, target_id: int):
    try:
        async for entry in guild.audit_logs(limit=5, action=action_type):
            if entry.target.id == target_id: return entry.user
    except discord.Forbidden:
        return None
    except discord.HTTPException as e:
        logger.warning(f"Rate limit or HTTP error fetching audit logs: {e}")
        await asyncio.sleep(1)
        return None
    return None

async def on_member_ban(guild: discord.Guild, user: discord.User, bot):
    channel = await get_channel(bot)
    if not channel: return
    executor = await get_audit_executor(guild, discord.AuditLogAction.ban, user.id)
    mod_text = f"Модератор: {executor.mention}" if executor else "Модератор: Неизвестен"
    embed = discord.Embed(title="🔨 Пользователь забанен", description=f"**Нарушитель:** {user.mention} ({user.name})\n{mod_text}", color=discord.Color.red())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Code by PAVUK")
    await channel.send(embed=embed)

async def on_member_remove(member: discord.Member, bot):
    channel = await get_channel(bot)
    if not channel: return
    executor = await get_audit_executor(member.guild, discord.AuditLogAction.kick, member.id)
    if executor:
        embed = discord.Embed(title="👢 Пользователь выгнан (Кик)", description=f"**Нарушитель:** {member.mention} ({member.name})\n**Модератор:** {executor.mention}", color=discord.Color.orange())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)
    else:
        embed = discord.Embed(title="🚪 Пользователь вышел", description=f"**Участник:** {member.mention} ({member.name})", color=discord.Color.dark_grey())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)

async def on_member_update(before: discord.Member, after: discord.Member, bot):
    channel = await get_channel(bot)
    if not channel: return
    if before.nick != after.nick:
        executor = await get_audit_executor(before.guild, discord.AuditLogAction.member_update, before.id)
        mod_text = f"\n**Модератор:** {executor.mention}" if executor else ""
        embed = discord.Embed(title="📝 Изменён никнейм", description=f"**Пользователь:** {after.mention}{mod_text}", color=discord.Color.blue())
        embed.add_field(name="Было", value=f"`{before.nick or before.name}`", inline=True)
        embed.add_field(name="Стало", value=f"`{after.nick or after.name}`", inline=True)
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)
    if before.roles != after.roles:
        added_roles = [role.mention for role in after.roles if role not in before.roles]
        removed_roles = [role.mention for role in before.roles if role not in after.roles]
        if added_roles or removed_roles:
            executor = await get_audit_executor(before.guild, discord.AuditLogAction.member_role_update, before.id)
            mod_text = f"\n**Модератор:** {executor.mention}" if executor else ""
            embed = discord.Embed(title="🛡️ Изменены роли", description=f"**Пользователь:** {after.mention}{mod_text}", color=discord.Color.green() if added_roles else discord.Color.red())
            if added_roles: embed.add_field(name="✅ Выданы", value="\n".join(added_roles), inline=False)
            if removed_roles: embed.add_field(name="❌ Сняты", value="\n".join(removed_roles), inline=False)
            embed.set_footer(text="Code by PAVUK")
            await channel.send(embed=embed)

async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState, bot):
    channel = await get_channel(bot)
    if not channel or member.bot: return
    if before.mute != after.mute:
        executor = await get_audit_executor(member.guild, discord.AuditLogAction.member_update, member.id)
        mod_text = f"\n**Модератор:** {executor.mention}" if executor else ""
        status = "🔇 Микрофон отключён" if after.mute else "🎙️ Микрофон включён"
        embed = discord.Embed(title=status, description=f"**Пользователь:** {member.mention}{mod_text}", color=discord.Color.red() if after.mute else discord.Color.green())
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)
    elif before.deaf != after.deaf:
        executor = await get_audit_executor(member.guild, discord.AuditLogAction.member_update, member.id)
        mod_text = f"\n**Модератор:** {executor.mention}" if executor else ""
        status = "🔕 Звук отключён" if after.deaf else "🔊 Звук включён"
        embed = discord.Embed(title=status, description=f"**Пользователь:** {member.mention}{mod_text}", color=discord.Color.red() if after.deaf else discord.Color.green())
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)
