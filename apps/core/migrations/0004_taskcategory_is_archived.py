from django.db import migrations, models


def archive_teaching_category(apps, schema_editor):
    """Помечаем категорию TEACHING как архивную — она приходит из 1С."""
    TaskCategory = apps.get_model('core', 'TaskCategory')
    TaskCategory.objects.filter(code='TEACHING').update(is_archived=True)


def unarchive_teaching_category(apps, schema_editor):
    """Откат: снимаем флаг архивности."""
    TaskCategory = apps.get_model('core', 'TaskCategory')
    TaskCategory.objects.filter(code='TEACHING').update(is_archived=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_teachingactivitytype'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskcategory',
            name='is_archived',
            field=models.BooleanField(
                default=False,
                help_text='Если включено — категория не показывается в форме создания новых задач, '
                          'но исторические задачи продолжают отображаться. '
                          'Используется для категории «Учебная работа», которая приходит из 1С.',
                verbose_name='Архивирована',
            ),
        ),
        migrations.RunPython(
            archive_teaching_category,
            reverse_code=unarchive_teaching_category,
        ),
    ]