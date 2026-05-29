import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

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
    if member.guild_permissions.administrator:
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

    try:
        ticket_channel = await guild.create_text_channel(
            name=f"票券-{member.name}",
            category=category,
            overwrites=overwrites,
            reason=f"Ticket created by {member} ({member.id})",
        )
    except discord.Forbidden:
        await i.edit_original_response(
            embed=ErrorEmbed(
                title="無法建立票券",
                description=(
                    "機器人缺少「管理頻道」權限，無法建立票券頻道。\n"
                    "請到伺服器設定中授予機器人「管理頻道」權限後再試一次。"
                ),
            )
        )
        return
    except discord.HTTPException:
        logger.exception(f"Failed to create ticket channel in guild {guild.id}")
        await i.edit_original_response(
            embed=ErrorEmbed(
                title="無法建立票券",
                description=(
                    "建立票券頻道時發生錯誤。\n"
                    "可能是此分類的頻道數已達上限（50 個）或伺服器頻道總數已達上限（500 個），"
                    "請整理後再試一次。"
                ),
            )
        )
        return

    await Ticket.create(channel_id=ticket_channel.id, guild_id=guild.id, creator_id=member.id)

    welcome = DefaultEmbed(
        title="票券已建立",
        description="管理員可使用 `/結單` 來關閉此票券，或使用 `/歸檔` 來歸檔此票券（建立者將無法再檢視此頻道）",
    )
    try:
        await ticket_channel.send(content=member.mention, embed=welcome)
    except discord.HTTPException:
        logger.exception(f"Failed to send welcome message in ticket channel {ticket_channel.id}")

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
        try:
            await i.channel.send(
                embed=embed, view=TicketPanelView(self.button_label.component.value)
            )
        except discord.Forbidden:
            await i.response.send_message(
                embed=ErrorEmbed(
                    title="無法建立面板",
                    description=(
                        "機器人無法在此頻道傳送訊息。\n"
                        "請確認機器人擁有此頻道的「檢視頻道」、「傳送訊息」與「嵌入連結」"
                        "權限後再試一次。"
                    ),
                ),
                ephemeral=True,
            )
            return
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
    @app_commands.default_permissions(administrator=True)
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
        if isinstance(i.channel, discord.TextChannel):
            try:
                await i.channel.delete(reason=f"Ticket closed by {i.user}")
            except discord.Forbidden:
                await i.followup.send(
                    embed=ErrorEmbed(
                        title="無法結單",
                        description=(
                            "機器人缺少「管理頻道」權限，無法刪除此頻道。\n"
                            "請到伺服器設定中授予機器人「管理頻道」權限後再試一次。"
                        ),
                    ),
                    ephemeral=True,
                )
                return
        await ticket.delete()

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
                try:
                    await i.channel.set_permissions(
                        creator, view_channel=False, reason=f"Ticket archived by {i.user}"
                    )
                except discord.Forbidden:
                    await i.response.send_message(
                        embed=ErrorEmbed(
                            title="無法歸檔",
                            description=(
                                "機器人缺少「管理身分組」權限，無法修改此頻道的權限。\n"
                                "請到伺服器設定中授予機器人「管理身分組」權限，並確認其身分組"
                                "順序高於票券建立者後再試一次。"
                            ),
                        ),
                        ephemeral=True,
                    )
                    return

        ticket.archived = True
        await ticket.save()
        await i.response.send_message(
            embed=DefaultEmbed(title="已歸檔", description="此票券已歸檔，建立者已無法檢視此頻道。")
        )


async def setup(bot: DanMaster) -> None:
    await bot.add_cog(TicketsCog(bot))
