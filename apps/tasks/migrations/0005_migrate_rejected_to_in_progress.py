from django.db import migrations


def migrate_rejected_to_in_progress(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    Task.objects.filter(status='rejected').update(status='in_progress')


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_task_work_type'),
    ]

    operations = [
        migrations.RunPython(
            migrate_rejected_to_in_progress,
            reverse_code=migrations.RunPython.noop,
        ),
    ]