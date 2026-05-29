from typing import TYPE_CHECKING

from discord import app_commands
from discord.ext import commands

from app import ui
from app.core.embeds import DefaultEmbed
from app.db.models import GuildSettings
from app.types import Interaction

if TYPE_CHECKING:
    import discord

    from app.core.bot import DanMaster


class AdminRoleSelect(ui.RoleSelect):
    def __init__(self, default_roles: list[discord.Role]) -> None:
        super().__init__(
            placeholder="選擇可管理票券的管理員身分組",
            min_values=0,
            max_values=25,
            default_values=default_roles,
        )

    async def callback(self, i: Interaction) -> None:
        role_ids = [role.id for role in self.values]
        await GuildSettings.update_or_create(
            guild_id=i.guild_id, defaults={"admin_role_ids": role_ids}
        )

        roles_text = "、".join(role.mention for role in self.values) or "（無）"
        embed = DefaultEmbed(title="設定已更新", description=f"目前的管理員身分組：{roles_text}")
        await i.response.edit_message(embed=embed, view=None)


class SettingsView(ui.View):
    def __init__(self, default_roles: list[discord.Role]) -> None:
        super().__init__(timeout=180)
        self.add_item(AdminRoleSelect(default_roles))


class SettingsCog(commands.Cog):
    def __init__(self, bot: DanMaster) -> None:
        self.bot = bot

    @app_commands.command(name="設定", description="設定此伺服器的票券系統")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def settings(self, i: Interaction) -> None:
        assert i.guild is not None

        gs = await GuildSettings.get_or_none(guild_id=i.guild.id)
        current_ids = gs.admin_role_ids if gs else []
        default_roles = [role for rid in current_ids if (role := i.guild.get_role(rid)) is not None]

        embed = DefaultEmbed(
            title="票券系統設定",
            description="請在下方選擇可以管理票券的管理員身分組。\n管理員可以結單與歸檔由成員建立的票券。",
        )
        await i.response.send_message(embed=embed, view=SettingsView(default_roles), ephemeral=True)


async def setup(bot: DanMaster) -> None:
    await bot.add_cog(SettingsCog(bot))
