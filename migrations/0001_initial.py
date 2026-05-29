from tortoise import migrations
from tortoise.migrations import operations as ops
from orjson import loads
from tortoise.fields.data import JSON_DUMPS
from tortoise import fields

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='GuildSettings',
            fields=[
                ('guild_id', fields.BigIntField(primary_key=True, unique=True, db_index=True)),
                ('admin_role_ids', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
            ],
            options={'table': 'guild_settings', 'app': 'models', 'pk_attr': 'guild_id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='Ticket',
            fields=[
                ('channel_id', fields.BigIntField(primary_key=True, unique=True, db_index=True)),
                ('guild_id', fields.BigIntField()),
                ('creator_id', fields.BigIntField()),
                ('archived', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'tickets', 'app': 'models', 'pk_attr': 'channel_id'},
            bases=['Model'],
        ),
    ]
