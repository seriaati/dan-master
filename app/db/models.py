# pyright: reportAssignmentType=false
from tortoise import fields, models


class GuildSettings(models.Model):
    guild_id = fields.BigIntField(primary_key=True, generated=False)
    admin_role_ids: list[int] = fields.JSONField(default=list)

    class Meta:
        table = "guild_settings"


class Ticket(models.Model):
    channel_id = fields.BigIntField(primary_key=True, generated=False)
    guild_id = fields.BigIntField()
    creator_id = fields.BigIntField()
    archived = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tickets"
