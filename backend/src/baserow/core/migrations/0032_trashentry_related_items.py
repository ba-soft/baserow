# Generated by Django 3.2.13 on 2022-09-02 20:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_duplicateapplicationjob_user_action_group_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="trashentry",
            name="related_items",
            field=models.JSONField(default=dict, null=True),
        ),
    ]
