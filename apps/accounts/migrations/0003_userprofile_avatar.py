from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_remove_superuser_profiles"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="avatar",
            field=models.ImageField(
                blank=True,
                help_text="Profile photo thumbnail (single image).",
                null=True,
                upload_to="users/avatars/",
            ),
        ),
    ]
