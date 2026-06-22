from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0005_migrate_rejected_to_in_progress'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending_approval', 'Ожидает утверждения'),
                    ('assigned', 'Назначена'),
                    ('in_progress', 'В работе'),
                    ('completed', 'Выполнена'),
                    ('approved', 'Подтверждена'),
                    ('declined', 'Не утверждена'),
                ],
                default='assigned',
                max_length=20,
                verbose_name='Статус',
            ),
        ),
    ]