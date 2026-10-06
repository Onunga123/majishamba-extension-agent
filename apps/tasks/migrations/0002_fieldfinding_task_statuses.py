from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="followuptask",
            name="status",
            field=models.CharField(
                choices=[
                    ("assigned", "Assigned"),
                    ("in_progress", "In progress"),
                    ("completed", "Completed"),
                    ("verified", "Verified by supervisor"),
                    ("closed", "Closed"),
                    ("cancelled", "Cancelled"),
                ],
                default="assigned",
                max_length=40,
            ),
        ),
        migrations.CreateModel(
            name="FieldFinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visit_date", models.DateField()),
                ("checklist", models.JSONField(blank=True, default=dict)),
                ("observations", models.TextField(blank=True)),
                ("missing_information", models.TextField(blank=True)),
                ("follow_up_notes", models.TextField(blank=True)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "submitted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="field_findings_submitted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="field_findings", to="tasks.followuptask"),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="field_findings_verified",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-submitted_at",)},
        ),
    ]
