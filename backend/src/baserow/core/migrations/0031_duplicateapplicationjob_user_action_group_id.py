# Generated by Django 3.2.13 on 2022-09-02 21:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="duplicateapplicationjob",
            name="user_action_group_id",
            field=models.CharField(
                help_text="The user session uuid needed for undo/redo action group functionality.",
                max_length=36,
                null=True,
            ),
        ),
    ]
