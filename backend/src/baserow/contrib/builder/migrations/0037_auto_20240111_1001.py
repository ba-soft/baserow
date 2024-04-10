# Generated by Django 3.2.21 on 2024-01-11 10:01

from django.db import migrations, models

import baserow.core.formula.field


class Migration(migrations.Migration):
    dependencies = [
        ("builder", "0036_checkboxelement"),
    ]

    operations = [
        migrations.AddField(
            model_name="inputtextelement",
            name="is_multiline",
            field=models.BooleanField(
                default=False, help_text="Whether this text input is multiline."
            ),
        ),
        migrations.AddField(
            model_name="inputtextelement",
            name="rows",
            field=models.PositiveIntegerField(
                default=3,
                help_text="Number of rows displayed by the rendered input element",
            ),
        ),
        migrations.AlterField(
            model_name="inputtextelement",
            name="placeholder",
            field=baserow.core.formula.field.FormulaField(
                default="",
                help_text="The placeholder text which should be applied to the element.",
            ),
        ),
    ]