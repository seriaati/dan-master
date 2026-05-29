from typing import TYPE_CHECKING

import discord
from loguru import logger

from app.core.embeds import ErrorEmbed

if TYPE_CHECKING:
    from app.types import Interaction


async def respond_error(i: Interaction, embed: ErrorEmbed) -> None:
    """Deliver an error embed to the user, regardless of interaction state.

    Sends a followup if the interaction was already responded to (or deferred),
    otherwise an initial response. Never raises, so callers can use it safely
    from within their own error handling.
    """
    try:
        if i.response.is_done():
            await i.followup.send(embed=embed, ephemeral=True)
        else:
            await i.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        logger.warning(f"Failed to deliver error response to interaction {i.id}")


def _error_embed_for(e: Exception) -> ErrorEmbed:
    if isinstance(e, discord.Forbidden):
        logger.warning(f"Missing permissions: {e}")
        return ErrorEmbed(
            title="權限不足",
            description=(
                "機器人缺少執行此操作所需的權限。\n"
                "請到伺服器設定中確認機器人的身分組擁有相關權限（例如「管理頻道」、"
                "「管理身分組」、「傳送訊息」、「嵌入連結」），並確認其身分組順序"
                "高於相關的身分組後再試一次。"
            ),
        )
    if isinstance(e, discord.HTTPException):
        logger.warning(f"Discord API error ({e.status}): {e.text}")
        return ErrorEmbed(
            title="操作失敗",
            description=(
                f"與 Discord 溝通時發生錯誤（錯誤碼 {e.status}）。\n"
                "這可能是因為已達到某些上限（例如頻道數量），或為暫時性的問題，"
                "請稍後再試一次。如果問題持續存在, 請聯繫開發者。"
            ),
        )
    logger.exception("Error occurred", exc_info=e)
    return ErrorEmbed(
        title="發生錯誤了",
        description="發生了一些預期之外的錯誤, 請稍後再試一次\n如果問題持續存在, 請聯繫開發者",
    )


async def handle_error(i: Interaction, error: Exception) -> None:
    original = getattr(error, "original", None)
    e = original or error
    await respond_error(i, _error_embed_for(e))
