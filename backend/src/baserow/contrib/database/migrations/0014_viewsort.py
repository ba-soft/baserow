# Generated by Django 2.2.11 on 2020-09-28 09:27

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("database", "0013_urlfield"),
    ]

    operations = [
        migrations.CreateModel(
            name="ViewSort",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "order",
                    models.CharField(
                        choices=[("ASC", "Ascending"), ("DESC", "Descending")],
                        default="ASC",
                        help_text="Indicates the sort order direction. ASC (Ascending) is "
                        "from A to Z and DESC (Descending) is from Z to A.",
                        max_length=4,
                    ),
                ),
                (
                    "field",
                    models.ForeignKey(
                        help_text="The field that must be sorted on.",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="database.Field",
                    ),
                ),
                (
                    "view",
                    models.ForeignKey(
                        help_text="The view to which the sort applies. Each view can have "
                        "his own sortings.",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="database.View",
                    ),
                ),
            ],
            options={
                "ordering": ("id",),
            },
        ),
    ]
