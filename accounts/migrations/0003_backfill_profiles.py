from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    """Создаёт пустые профили пользователям, появившимся до введения модели Profile."""
    User = apps.get_model("accounts", "User")
    Profile = apps.get_model("accounts", "Profile")
    missing = User.objects.filter(profile__isnull=True)
    Profile.objects.bulk_create([Profile(user=user) for user in missing])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_profile"),
    ]

    operations = [
        # Обратная операция пустая: профили удалятся вместе с таблицей при откате 0002.
        migrations.RunPython(create_missing_profiles, migrations.RunPython.noop),
    ]
