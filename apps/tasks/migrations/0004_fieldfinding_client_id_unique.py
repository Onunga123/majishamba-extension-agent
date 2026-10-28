from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0003_fieldfinding_client_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fieldfinding",
            name="client_id",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]
