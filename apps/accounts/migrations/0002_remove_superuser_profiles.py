from django.db import migrations


def remove_superuser_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")
    superuser_ids = User.objects.filter(is_superuser=True).values_list("id", flat=True)
    UserProfile.objects.filter(user_id__in=superuser_ids).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial_user_profile_and_port_access"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(remove_superuser_profiles, noop_reverse),
    ]
