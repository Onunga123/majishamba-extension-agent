# Generated manually for UX remediation
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("clusters", "0002_farmercluster_coordinates_verified_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("advisories", "0003_advisory_scope_and_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdvisoryRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(
                    choices=[
                        ("queued", "Queued"),
                        ("running", "Running"),
                        ("waiting_for_model", "Waiting for model"),
                        ("validating", "Validating"),
                        ("completed", "Completed"),
                        ("completed_with_fallback", "Completed with template fallback"),
                        ("failed", "Failed"),
                    ],
                    default="queued",
                    max_length=40,
                )),
                ("current_stage", models.CharField(blank=True, max_length=80)),
                ("current_message", models.CharField(blank=True, max_length=240)),
                ("completed_stages", models.JSONField(blank=True, default=list)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("generation_mode", models.CharField(blank=True, max_length=40)),
                ("pipeline_request_id", models.CharField(blank=True, max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "cluster",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="advisory_runs", to="clusters.farmercluster"),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="advisory_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "result_advisory",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_runs",
                        to="advisories.advisory",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="advisoryrun",
            index=models.Index(fields=["requested_by", "status", "created_at"], name="agents_advi_request_6a0b0d_idx"),
        ),
        migrations.AddIndex(
            model_name="advisoryrun",
            index=models.Index(fields=["cluster", "status"], name="agents_advi_cluster_8c2f1a_idx"),
        ),
    ]
