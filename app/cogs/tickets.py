import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from app import ui
from app.core.embeds import DefaultEmbed, ErrorEmbed
from app.db.models import GuildSettings, Ticket
from app.types import Interaction

if TYPE_CHECKING:
    from app.core.bot import DanMaster

CREATE_TICKET_BUTTON_ID = "ticket:create"


async def get_admin_role_ids(guild_id: int) -> list[int]:
    gs = await GuildSettings.get_or_none(guild_id=guild_id)
    return gs.admin_role_ids if gs else []


def member_is_admin(member: discord.Member, admin_role_ids: list[int]) -> bool:
    if member.guild_permissions.manage_guild:
        return True
    return any(role.id in admin_role_ids for role in member.roles)


async def create_ticket(i: Interaction) -> None:
    assert i.guild is not None
    assert isinstance(i.user, discord.Member)

    await i.response.send_message(
        embed=DefaultEmbed(title="建立中", description="正在為你建立票券，請稍候..."),
        ephemeral=True,
    )

    guild = i.guild
    member = i.user
    category = i.channel.category if isinstance(i.channel, discord.TextChannel) else None

    admin_role_ids = await get_admin_role_ids(guild.id)
    overwrites: dict[
        discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
    ] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    for rid in admin_role_ids:
        role = guild.get_role(rid)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    ticket_channel = await guild.create_text_channel(
        name=f"票券-{member.name}",
        category=category,
        overwrites=overwrites,
        reason=f"Ticket created by {member} ({member.id})",
    )
    await Ticket.create(channel_id=ticket_channel.id, guild_id=guild.id, creator_id=member.id)

    welcome = DefaultEmbed(
        title="票券已建立",
        description="管理員可使用 `/結單` 來關閉此票券，或使用 `/歸檔` 來歸檔此票券（建立者將無法再檢視此頻道）",
    )
    await ticket_channel.send(content=member.mention, embed=welcome)
    await i.edit_original_response(
        embed=DefaultEmbed(title="完成", description=f"已為你建立票券：{ticket_channel.mention}")
    )


class CreateTicketButton(ui.Button):
    def __init__(self, label: str = "建立票券") -> None:
        super().__init__(
            label=label, style=discord.ButtonStyle.green, custom_id=CREATE_TICKET_BUTTON_ID
        )

    async def callback(self, i: Interaction) -> None:
        await create_ticket(i)


class TicketPanelView(ui.View):
    def __init__(self, button_label: str = "建立票券") -> None:
        super().__init__(timeout=None)
        self.add_item(CreateTicketButton(button_label))


class PanelSetupModal(ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="設定票券面板")
        self.panel_title: ui.Label[ui.TextInput] = ui.Label(
            text="標題",
            component=ui.TextInput(placeholder="建立票券", max_length=256, required=True),
        )
        self.panel_description: ui.Label[ui.TextInput] = ui.Label(
            text="說明",
            component=ui.TextInput(
                style=discord.TextStyle.paragraph,
                placeholder="點擊下方的按鈕來建立一張票券。",
                max_length=2000,
                required=True,
            ),
        )
        self.button_label: ui.Label[ui.TextInput] = ui.Label(
            text="按鈕文字",
            component=ui.TextInput(placeholder="建立票券", max_length=80, required=True),
        )
        self.add_item(self.panel_title)
        self.add_item(self.panel_description)
        self.add_item(self.button_label)

    async def on_submit(self, i: Interaction) -> None:
        if not isinstance(i.channel, discord.TextChannel):
            await i.response.send_message(
                embed=ErrorEmbed(title="無法建立面板", description="此指令只能在文字頻道中使用。"),
                ephemeral=True,
            )
            return

        embed = DefaultEmbed(
            title=self.panel_title.component.value,
            description=self.panel_description.component.value,
        )
        await i.channel.send(embed=embed, view=TicketPanelView(self.button_label.component.value))
        await i.response.send_message(
            embed=DefaultEmbed(title="完成", description="票券面板已建立。"), ephemeral=True
        )


class TicketsCog(commands.Cog):
    def __init__(self, bot: DanMaster) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(TicketPanelView())

    async def _resolve_ticket(self, i: Interaction) -> Ticket | None:
        return await Ticket.get_or_none(channel_id=i.channel_id)

    async def _require_admin(self, i: Interaction) -> bool:
        assert i.guild is not None
        admin_role_ids = await get_admin_role_ids(i.guild.id)
        if isinstance(i.user, discord.Member) and member_is_admin(i.user, admin_role_ids):
            return True
        await i.response.send_message(
            embed=ErrorEmbed(title="權限不足", description="只有管理員才能執行此操作。"),
            ephemeral=True,
        )
        return False

    @app_commands.command(name="界面", description="建立一個用於開立票券的面板")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, i: Interaction) -> None:
        await i.response.send_modal(PanelSetupModal())

    @app_commands.command(name="結單", description="關閉此票券（刪除此頻道）")
    @app_commands.guild_only()
    async def close(self, i: Interaction) -> None:
        ticket = await self._resolve_ticket(i)
        if ticket is None:
            await i.response.send_message(
                embed=ErrorEmbed(title="無法結單", description="此指令只能在票券頻道中使用。"),
                ephemeral=True,
            )
            return

        if not await self._require_admin(i):
            return

        await i.response.send_message(
            embed=DefaultEmbed(title="結單", description="此票券即將關閉。")
        )
        await asyncio.sleep(3)
        await ticket.delete()
        if isinstance(i.channel, discord.TextChannel):
            await i.channel.delete(reason=f"Ticket closed by {i.user}")

    @app_commands.command(name="歸檔", description="歸檔此票券（建立者將無法再檢視此頻道）")
    @app_commands.guild_only()
    async def archive(self, i: Interaction) -> None:
        assert i.guild is not None

        ticket = await self._resolve_ticket(i)
        if ticket is None:
            await i.response.send_message(
                embed=ErrorEmbed(title="無法歸檔", description="此指令只能在票券頻道中使用。"),
                ephemeral=True,
            )
            return

        if not await self._require_admin(i):
            return

        if isinstance(i.channel, discord.TextChannel):
            creator = i.guild.get_member(ticket.creator_id)
            if creator is not None:
                await i.channel.set_permissions(
                    creator, view_channel=False, reason=f"Ticket archived by {i.user}"
                )

        ticket.archived = True
        await ticket.save()
        await i.response.send_message(
            embed=DefaultEmbed(title="已歸檔", description="此票券已歸檔，建立者已無法檢視此頻道。")
        )


async def setup(bot: DanMaster) -> None:
    await bot.add_cog(TicketsCog(bot))
