"""
Добавление FK work_type в Task + перенос данных из description.

Шаг 1 (схема): FK work_type → core.WorkType (null=True, blank=True, PROTECT).
Шаг 2 (данные): парсим строки «Вид работы: <name> (до <N> ч.)» из начала
    description → находим WorkType по имени → ставим FK → чистим description.
"""

import django.db.models.deletion
from django.db import migrations, models


def _migrate_work_type_forward(apps, schema_editor):
    """
    Переносим «Вид работы» из текстового префикса description в FK work_type.

    Формат префикса (создавался в TeacherCreateTaskView.post):
        Вид работы: {name} (до {max_hours} ч.)\\n\\n{описание}
    или, если описания не было:
        Вид работы: {name} (до {max_hours} ч.)

    Алгоритм:
        1. Берём первую строку до \\n.
        2. Извлекаем имя между «Вид работы: » и последним « (до ».
        3. Ищем WorkType по точному совпадению имени.
        4. Если нашли — ставим FK, очищаем description от префикса.
        5. Если НЕ нашли — оставляем task нетронутым (данные не теряются).
    """
    Task = apps.get_model('tasks', 'Task')
    WorkType = apps.get_model('core', 'WorkType')

    work_types_by_name = {wt.name: wt for wt in WorkType.objects.all()}

    PREFIX = 'Вид работы: '
    HOURS_MARKER = ' (до '

    updated = 0
    for task in Task.objects.filter(description__startswith=PREFIX):
        desc = task.description

        # Первая строка: «Вид работы: Разработка ПО (до 80 ч.)»
        newline_pos = desc.find('\n')
        if newline_pos == -1:
            first_line = desc
            rest = ''
        else:
            first_line = desc[:newline_pos]
            rest = desc[newline_pos + 1:]

        # Имя вида работы: между «Вид работы: » и последним « (до ».
        after_prefix = first_line[len(PREFIX):]
        paren_pos = after_prefix.rfind(HOURS_MARKER)
        if paren_pos != -1:
            wt_name = after_prefix[:paren_pos]
        else:
            wt_name = after_prefix.strip()

        wt = work_types_by_name.get(wt_name)
        if wt is None:
            continue

        # Убираем пустую строку-разделитель (\n после первого \n).
        rest = rest.lstrip('\n')

        task.work_type_id = wt.pk
        task.description = rest
        task.save(update_fields=['work_type_id', 'description'])
        updated += 1

    if updated:
        print(f'  → Перенесено work_type из description в FK: {updated} задач')


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0003_alter_task_status'),
        ('core', '0005_categorylimit'),  # WorkType живёт в core
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='work_type',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='tasks',
                to='core.worktype',
                verbose_name='Вид работы',
            ),
        ),
        migrations.RunPython(
            _migrate_work_type_forward,
            migrations.RunPython.noop,
        ),
    ]
