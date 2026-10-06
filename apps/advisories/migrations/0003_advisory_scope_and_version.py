from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("advisories", "0002_advisory_generation_seconds"),
    ]

    operations = [
        migrations.AddField(
            model_name="advisory",
            name="content_version",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Incremented when a DRAFT is edited; approval must match this version.",
            ),
        ),
        migrations.AddField(
            model_name="advisory",
            name="scope_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Household/plot scope captured when this advisory was drafted (not live DB counts).",
            ),
        ),
        migrations.AddField(
            model_name="advisory",
            name="crop",
            field=models.CharField(default="maize", max_length=40),
        ),
        migrations.AddField(
            model_name="advisory",
            name="season",
            field=models.CharField(default="short_rains", max_length=40),
        ),
        migrations.AddField(
            model_name="advisoryevidence",
            name="source_observed_at",
            field=models.CharField(
                blank=True,
                help_text="Source observation or publication date (ISO or human-readable), not retrieval time.",
                max_length=40,
            ),
        ),
    ]
