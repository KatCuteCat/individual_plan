import json
from pathlib import Path

from django.db import migrations


def forward(apps, schema_editor):
    WorkType = apps.get_model('core', 'WorkType')
    TaskCategory = apps.get_model('core', 'TaskCategory')
    Task = apps.get_model('tasks', 'Task')

    data_path = Path(__file__).parent.parent / 'fixtures' / 'work_types_canonical.json'
    data = json.loads(data_path.read_text(encoding='utf-8'))

    bound_tasks = Task.objects.filter(work_type__isnull=False).count()
    if bound_tasks > 0:
        print(f'  Обнуляем work_type у {bound_tasks} задач...')
        Task.objects.filter(work_type__isnull=False).update(work_type=None)

    WorkType.objects.all().delete()

    categories = {c.code: c for c in TaskCategory.objects.all()}
    for wt in data['work_types']:
        WorkType.objects.create(
            name=wt['name'],
            category=categories[wt['category_code']],
            max_hours=wt['max_hours'],
            unit_description=wt['unit_description'],
            is_active=True,
        )
    print(f'  Загружено {len(data["work_types"])} видов работ.')


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_widen_worktype_name'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]