"""
Функции работают с TeacherPosition вместо User.
Позиция уже знает свой год, своего пользователя, свою норму и свою
учебную нагрузку.
"""

from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError


def _get_active_position(user, academic_year):
    """
    Вспомогательная функция: получить активную позицию пользователя в году.
    """
    from apps.accounts.models import TeacherPosition

    priority = [
        TeacherPosition.EMPLOYMENT_MAIN,
        TeacherPosition.EMPLOYMENT_INTERNAL_COMBINING,
        TeacherPosition.EMPLOYMENT_EXTERNAL_COMBINING,
        TeacherPosition.EMPLOYMENT_HOURLY,
    ]
    positions = list(TeacherPosition.objects.filter(
        user=user, academic_year=academic_year, is_active=True,
    ).select_related('position'))
    if not positions:
        return None
    positions.sort(key=lambda p: priority.index(p.employment_type)
                   if p.employment_type in priority else 99)
    return positions[0]

def _get_category_limits_for_position(position):
    """
    Получить лимиты по категориям для конкретной должности.
    """
    from apps.core.models import CategoryLimit

    # Сначала забираем все общие лимиты (position=None).
    limits = {}
    general = CategoryLimit.objects.filter(position__isnull=True).select_related('category')
    for limit in general:
        limits[limit.category.code] = (limit.min_percent, limit.max_percent)

    # Затем — персональные для этой должности; они переопределяют общие.
    if position is not None:
        specific = CategoryLimit.objects.filter(position=position).select_related('category')
        for limit in specific:
            limits[limit.category.code] = (limit.min_percent, limit.max_percent)

    return limits

def get_position_workload_stats(teacher_position):
    """
    Получить статистику нагрузки позиции преподавателя.
    """
    from apps.tasks.models import Task
    from apps.core.models import PositionWorkload, TaskCategory

    if teacher_position is None:
        return _empty_stats()

    academic_year = teacher_position.academic_year

    tasks = Task.objects.filter(
        assignee=teacher_position,
    ).exclude(
        status=Task.STATUS_DECLINED,
    )

    # Задачи второй половины дня
    task_totals = tasks.aggregate(
        tasks_planned=Sum('planned_hours'),
        tasks_actual=Sum('actual_hours'),
    )
    tasks_planned = task_totals['tasks_planned'] or Decimal('0')
    tasks_actual = task_totals['tasks_actual'] or Decimal('0')

    # Учебная нагрузка (первая половина дня) — из TeachingLoadItem,
    teaching_planned = teacher_position.teaching_hours or Decimal('0')
    teaching_actual = teacher_position.teaching_load.aggregate(
        total=Sum('hours_fact')
    )['total'] or Decimal('0')

    # Суммарные показатели: первая + вторая половина дня
    total_planned = tasks_planned + teaching_planned
    total_actual = tasks_actual + teaching_actual

    # Лимиты — берём из нормы должности на этот год
    max_total_hours = 0
    max_teaching_hours = 0
    min_teaching_hours = 0
    tolerance = 0

    if not teacher_position.is_hourly and teacher_position.rate is not None:
        try:
            workload = PositionWorkload.objects.get(
                position=teacher_position.position,
                academic_year=academic_year,
            )
            max_total_hours = workload.get_total_hours_for_rate(teacher_position.rate)
            teaching_info = workload.get_teaching_hours_for_rate(teacher_position.rate)
            max_teaching_hours = teaching_info['max_hours']
            min_teaching_hours = teaching_info['min_hours']
            tolerance = teaching_info['tolerance']
        except PositionWorkload.DoesNotExist:
            pass

    # Лимиты по категориям второй половины дня.

    second_half_hours = teacher_position.second_half_hours
    # Защита от некорректных данных: если учебка > фонда, считаем 0.
    if second_half_hours is not None and second_half_hours < 0:
        second_half_hours = Decimal('0')

    category_limits = _get_category_limits_for_position(teacher_position.position)

    by_category = []

    categories = TaskCategory.objects.filter(is_active=True, is_archived=False)
    for cat in categories:
        cat_tasks = tasks.filter(category=cat)
        cat_totals = cat_tasks.aggregate(
            planned=Sum('planned_hours'),
            actual=Sum('actual_hours'),
            count=Count('id'),
        )
        cat_planned = cat_totals['planned'] or Decimal('0')

        # Расчёт лимитов по категории
        min_percent = None
        max_percent = None
        min_hours = None
        max_hours = None
        is_below_min = False
        is_above_max = False
        regulation_point = ''

        if (second_half_hours is not None
                and cat.code in category_limits):
            min_percent, max_percent = category_limits[cat.code]
            min_hours = (second_half_hours * min_percent / Decimal('100'))
            max_hours = (second_half_hours * max_percent / Decimal('100'))
            # Округляем до целых часов для отображения,
            # но сравнение делаем по точным значениям.
            is_below_min = min_hours > 0 and cat_planned < min_hours
            is_above_max = max_hours > 0 and cat_planned > max_hours
            from apps.core.models import CategoryLimit
            try:
                # Сначала ищем персональную запись, затем общую
                if teacher_position.position_id:
                    rec = CategoryLimit.objects.filter(
                        category=cat,
                        position=teacher_position.position,
                    ).first()
                else:
                    rec = None
                if rec is None:
                    rec = CategoryLimit.objects.filter(
                        category=cat, position__isnull=True,
                    ).first()
                if rec is not None:
                    regulation_point = rec.regulation_point
            except Exception:
                pass

        by_category.append({
            'category': cat,
            'planned': cat_planned,
            'actual': cat_totals['actual'] or Decimal('0'),
            'count': cat_totals['count'],
            'min_percent': min_percent,
            'max_percent': max_percent,
            'min_hours': min_hours,
            'max_hours': max_hours,
            'is_below_min': is_below_min,
            'is_above_max': is_above_max,
            'regulation_point': regulation_point,
        })

    tasks_count = {
        'total': tasks.count(),
        'assigned': tasks.filter(status=Task.STATUS_ASSIGNED).count(),
        'in_progress': tasks.filter(status=Task.STATUS_IN_PROGRESS).count(),
        'completed': tasks.filter(status=Task.STATUS_COMPLETED).count(),
        'approved': tasks.filter(status=Task.STATUS_APPROVED).count(),
    }

    is_overloaded = (
        (max_total_hours > 0 and total_planned > max_total_hours) or
        (max_teaching_hours > 0 and teaching_planned > max_teaching_hours)
    )

    # Счётчики категорий с нарушением лимитов.
    category_violations_count = sum(
        1 for row in by_category if row['is_above_max']
    )
    category_below_min_count = sum(
        1 for row in by_category if row['is_below_min']
    )

    progress_percent = 0
    if total_planned > 0:
        progress_percent = int((total_actual / total_planned) * 100)


    second_half_planned = tasks_planned

    second_half_overflow = Decimal('0')
    if (second_half_hours is not None
            and second_half_planned > second_half_hours):
        second_half_overflow = second_half_planned - second_half_hours

    return {
        'total_planned': total_planned,
        'total_actual': total_actual,
        'max_total_hours': max_total_hours,
        'max_teaching_hours': max_teaching_hours,
        'min_teaching_hours': min_teaching_hours,
        'tolerance': tolerance,
        'teaching_planned': teaching_planned,
        'teaching_actual': teaching_actual,
        'by_category': by_category,
        'tasks_count': tasks_count,
        'is_overloaded': is_overloaded,
        'progress_percent': min(progress_percent, 100),
        'second_half_hours': second_half_hours,
        'second_half_planned': second_half_planned,
        'second_half_overflow': second_half_overflow,
        'category_violations_count': category_violations_count,
        'category_below_min_count': category_below_min_count,
    }


def _empty_stats():
    """Заглушка статистики для случая, когда у пользователя нет позиции."""
    return {
        'total_planned': Decimal('0'),
        'total_actual': Decimal('0'),
        'max_total_hours': 0,
        'max_teaching_hours': 0,
        'min_teaching_hours': 0,
        'tolerance': 0,
        'teaching_planned': Decimal('0'),
        'teaching_actual': Decimal('0'),
        'by_category': [],
        'tasks_count': {
            'total': 0, 'assigned': 0, 'in_progress': 0,
            'completed': 0, 'approved': 0,
        },
        'is_overloaded': False,
        'progress_percent': 0,
        'second_half_hours': None,
        'second_half_planned': Decimal('0'),
        'second_half_overflow': Decimal('0'),
        'category_violations_count': 0,
        'category_below_min_count': 0,
    }

def get_teacher_workload_stats(user, academic_year):

    teacher_position = _get_active_position(user, academic_year)
    return get_position_workload_stats(teacher_position)


def validate_task_hours(task):
    """
    Проверить, не превысит ли назначение задачи лимит нагрузки позиции.
    """
    from apps.tasks.models import Task
    from apps.core.models import PositionWorkload

    warnings = {}
    teacher_position = task.assignee

    if teacher_position is None:
        return warnings

    if teacher_position.is_hourly or teacher_position.rate is None:
        return warnings

    try:
        workload = PositionWorkload.objects.get(
            position=teacher_position.position,
            academic_year=teacher_position.academic_year,
        )
    except PositionWorkload.DoesNotExist:
        return warnings

    # Существующие задачи: все статусы кроме окончательно отклонённых.
    existing_tasks = Task.objects.filter(
        assignee=teacher_position,
    ).exclude(
        status=Task.STATUS_DECLINED,
    )
    if task.pk:
        existing_tasks = existing_tasks.exclude(pk=task.pk)

    current_tasks_total = existing_tasks.aggregate(
        total=Sum('planned_hours')
    )['total'] or Decimal('0')

    # Учебная нагрузка (первая половина) — из 1С, не в Task.
    teaching_hours = teacher_position.teaching_hours or Decimal('0')

    # Проверка общего годового лимита

    max_total = workload.get_total_hours_for_rate(teacher_position.rate)

    current_total_with_teaching = current_tasks_total + teaching_hours
    new_total = current_total_with_teaching + task.planned_hours

    already_overloaded = (
        max_total > 0 and current_total_with_teaching > max_total
    )
    will_overload = max_total > 0 and new_total > max_total

    if will_overload:
        if already_overloaded:
            # Позиция уже перегружена ДО добавления задачи.
            existing_overload = current_total_with_teaching - max_total
            new_overload = new_total - max_total
            warnings['total_warning'] = (
                f'Позиция уже перегружена: '
                f'{current_total_with_teaching:.1f} ч. при лимите '
                f'{max_total} ч. (превышение {existing_overload:.1f} ч.). '
                f'Добавление задачи увеличит перевес до '
                f'{new_overload:.1f} ч.'
            )
        else:
            # Перегрузка случится из-за новой задачи.
            warnings['total_warning'] = (
                f'Общая нагрузка ({new_total:.1f} ч.: учебная '
                f'{teaching_hours:.1f} ч. + задачи '
                f'{current_tasks_total + task.planned_hours:.1f} ч.) '
                f'превысит лимит {max_total} ч. для ставки '
                f'{teacher_position.rate}.'
            )

    #Лимиты по категориям второй половины дня

    second_half = teacher_position.second_half_hours
    if second_half is not None and second_half > 0:
        category_limits = _get_category_limits_for_position(
            teacher_position.position
        )
        cat_code = task.category.code
        if cat_code in category_limits:
            min_percent, max_percent = category_limits[cat_code]
            max_cat_hours = second_half * max_percent / Decimal('100')

            current_cat = existing_tasks.filter(
                category=task.category,
            ).aggregate(total=Sum('planned_hours'))['total'] or Decimal('0')
            new_cat = current_cat + task.planned_hours

            if max_cat_hours > 0 and new_cat > max_cat_hours:
                warnings['category_warning'] = (
                    f'Нагрузка по категории «{task.category.name}» '
                    f'({new_cat} ч.) превысит лимит {max_cat_hours:.0f} ч. '
                    f'({max_percent:g} % от объёма второй половины дня '
                    f'{second_half} ч.).'
                )

    return warnings


def get_department_summary(academic_year, department=None):
    """
    Сводка по всем позициям преподавателей кафедры за учебный год.
    Каждая строка — одна позиция (не пользователь).

    """
    from apps.accounts.models import TeacherPosition

    positions = TeacherPosition.objects.filter(
        academic_year=academic_year,
        is_active=True,
        user__is_active=True,
        user__role='teacher',
    ).select_related('user', 'position', 'academic_year')

    if department:
        positions = positions.filter(user__department=department)

    summary = []
    for tp in positions:
        stats = get_position_workload_stats(tp)
        summary.append({
            'user': tp.user,
            'teacher_position': tp,
            'total_planned': stats['total_planned'],
            'total_actual': stats['total_actual'],
            'max_total_hours': stats['max_total_hours'],
            'tasks_count': stats['tasks_count']['total'],
            'approved_count': stats['tasks_count']['approved'],
            'is_overloaded': stats['is_overloaded'],
            'progress_percent': stats['progress_percent'],
            'category_violations_count': stats['category_violations_count'],
            'category_below_min_count': stats['category_below_min_count'],
        })

    return summary

def get_department_summary_grouped(academic_year, department=None):
    """
    Сводка по позициям, сгруппированная по пользователю.

    Сортировка — по ФИО пользователя. Внутри пользователя позиции
    отсортированы по приоритету занятости
    """
    from apps.accounts.models import TeacherPosition

    rows = get_department_summary(academic_year, department=department)

    employment_order = {
        TeacherPosition.EMPLOYMENT_MAIN: 0,
        TeacherPosition.EMPLOYMENT_INTERNAL_COMBINING: 1,
        TeacherPosition.EMPLOYMENT_EXTERNAL_COMBINING: 2,
        TeacherPosition.EMPLOYMENT_HOURLY: 3,
    }

    grouped = {}
    for row in rows:
        user = row['user']
        bucket = grouped.setdefault(user.pk, {
            'user': user,
            'positions': [],
            'total_planned': 0,
            'total_max_hours': 0,
            'total_tasks': 0,
            'has_overload': False,
            'has_category_violations': False,
            'has_category_below_min': False,
        })
        bucket['positions'].append(row)
        bucket['total_planned'] += row['total_planned'] or 0
        bucket['total_max_hours'] += row['max_total_hours'] or 0
        bucket['total_tasks'] += row['tasks_count'] or 0
        if row['is_overloaded']:
            bucket['has_overload'] = True
        if row['category_violations_count'] > 0:
            bucket['has_category_violations'] = True
        if row['category_below_min_count'] > 0:
            bucket['has_category_below_min'] = True

    for bucket in grouped.values():
        bucket['positions'].sort(
            key=lambda r: employment_order.get(
                r['teacher_position'].employment_type, 99
            )
        )

    result = list(grouped.values())
    result.sort(key=lambda b: (b['user'].full_name or b['user'].username).lower())
    return result

# Действия с задачами

def complete_task(task, actual_hours, result=''):
    if actual_hours is not None and actual_hours <= 0:
        raise ValidationError('Фактические часы должны быть больше нуля.')
    if not result or not result.strip():
        raise ValidationError(
            'Поле «Результат» обязательно — этот текст войдёт '
            'в итоговый отчёт Word.'
        )
    task.transition_to(task.STATUS_COMPLETED)
    task.actual_hours = actual_hours
    task.result = result.strip()
    task.full_clean()
    task.save()
    return task


def approve_task(task):
    task.transition_to(task.STATUS_APPROVED)
    task.save()
    return task


def start_task(task):
    task.transition_to(task.STATUS_IN_PROGRESS)
    task.save()
    return task


def withdraw_completion(task):
    from apps.tasks.models import Task
    if task.status != Task.STATUS_COMPLETED:
        raise ValidationError('Отозвать можно только задачу в статусе "На проверке".')
    task.status = Task.STATUS_IN_PROGRESS
    task.save(update_fields=['status', 'updated_at'])
    return task

# Внеплановые задачи преподавател

def submit_pending_task(task):
    """
    Перевести задачу в статус «Ожидает утверждения».

    """
    from apps.tasks.models import Task

    task.status = Task.STATUS_PENDING_APPROVAL
    task.task_type = Task.TYPE_ADDITIONAL
    task.full_clean()
    task.save()
    return task


def approve_pending_task(task, target_position=None, planned_hours=None):
    """
    Одобрить задачу преподавателя.

    """
    from apps.tasks.models import Task

    if task.status != Task.STATUS_PENDING_APPROVAL:
        raise ValidationError(
            'Одобрить можно только задачу в статусе «Ожидает утверждения».'
        )

    # Проверка целевой позиции (если указана)
    if target_position is not None:
        current_position = task.assignee
        if target_position.user_id != current_position.user_id:
            raise ValidationError(
                'Целевая позиция должна принадлежать тому же преподавателю.'
            )
        if target_position.academic_year_id != current_position.academic_year_id:
            raise ValidationError(
                'Целевая позиция должна быть в том же учебном году.'
            )
        if not target_position.is_active:
            raise ValidationError('Целевая позиция должна быть активной.')
        if target_position.is_hourly:
            raise ValidationError(
                'Нельзя перенести задачу на почасовую позицию — '
                'у неё нет второй половины дня.'
            )
        task.assignee = target_position

    # Изменение плановых часов (если указаны)
    if planned_hours is not None:
        if planned_hours <= 0:
            raise ValidationError('Плановые часы должны быть больше нуля.')
        task.planned_hours = planned_hours

    # Переход статуса
    task.transition_to(Task.STATUS_ASSIGNED)
    task.full_clean()
    task.save()
    return task


def decline_pending_task(task, reason):
    """
    Отклонить задачу преподавателя на этапе утверждения.
    """
    from apps.tasks.models import Task

    if task.status != Task.STATUS_PENDING_APPROVAL:
        raise ValidationError(
            'Отклонить на утверждении можно только задачу '
            'в статусе «Ожидает утверждения».'
        )
    if not reason or not reason.strip():
        raise ValidationError('Укажите причину отклонения.')

    task.transition_to(Task.STATUS_DECLINED)
    task.rejection_reason = reason.strip()
    task.save()
    return task


def delete_assigned_task(task):
    """
    Удалить задачу в статусе «Назначена»
    """
    from apps.tasks.models import Task

    if task.status != Task.STATUS_ASSIGNED:
        raise ValidationError(
            'Удалить можно только задачу в статусе «Назначена». '
            'Если преподаватель уже начал работу — отредактируйте задачу.'
        )
    if task.academic_year.is_archived:
        raise ValidationError(
            'Нельзя удалять задачи архивного учебного года.'
        )
    task.delete()


def delete_declined_task(task):
    """
    Окончательно удалить отклонённую задачу из БД.
    """
    from apps.tasks.models import Task

    if task.status != Task.STATUS_DECLINED:
        raise ValidationError(
            'Окончательно удалить можно только задачу '
            'в статусе «Не утверждена».'
        )
    task.delete()


def get_user_positions_for_year(user, academic_year):

    from apps.accounts.models import TeacherPosition

    return TeacherPosition.objects.filter(
        user=user,
        academic_year=academic_year,
        is_active=True,
    ).exclude(
        employment_type=TeacherPosition.EMPLOYMENT_HOURLY,
    ).select_related('position', 'academic_year').order_by(
        'employment_type'  # MAIN, INTERNAL, EXTERNAL по алфавиту кодов
    )

# Оередь утверждения у заведующего

def get_pending_approval_count(academic_year=None, department=None, user=None):

    from apps.tasks.models import Task
    from apps.core.models import AcademicYear

    if academic_year is None:
        academic_year = AcademicYear.objects.filter(is_active=True).first()
        if academic_year is None:
            return 0

    qs = Task.objects.filter(
        status=Task.STATUS_PENDING_APPROVAL,
        academic_year=academic_year,
    )
    if department is not None:
        qs = qs.filter(assignee__user__department=department)
    if user is not None:
        qs = qs.filter(assignee__user=user)
    return qs.count()


def get_pending_approval_tasks(academic_year=None, department=None, limit=None):

    from apps.tasks.models import Task
    from apps.core.models import AcademicYear

    if academic_year is None:
        academic_year = AcademicYear.objects.filter(is_active=True).first()
        if academic_year is None:
            return Task.objects.none()

    qs = Task.objects.filter(
        status=Task.STATUS_PENDING_APPROVAL,
        academic_year=academic_year,
    ).select_related(
        'assignee__user',
        'assignee__position',
        'category',
        'academic_year',
        'creator',
    ).order_by('-created_at')

    if department is not None:
        qs = qs.filter(assignee__user__department=department)

    if limit is not None:
        qs = qs[:limit]

    return qs

def get_pending_task_position_forecasts(task):
    """
    Для pending-задачи: для каждой не-почасовой позиции преподавателя
    в том же учебном году посчитать прогноз — что будет, если задачу
    повесить на эту позицию.

    """
    from apps.accounts.models import TeacherPosition

    teacher = task.assignee.user
    academic_year = task.academic_year
    current_position_pk = task.assignee_id

    positions = TeacherPosition.objects.filter(
        user=teacher,
        academic_year=academic_year,
        is_active=True,
    ).exclude(
        employment_type=TeacherPosition.EMPLOYMENT_HOURLY,
    ).select_related('position').order_by('employment_type')

    forecasts = []
    original_assignee = task.assignee
    try:
        for position in positions:
            # Временно подменяем позицию задачи — чтобы validate_task_hours
            # посчитала прогноз для возможной целевой позиции.
            task.assignee = position

            stats = get_position_workload_stats(position)
            warnings = validate_task_hours(task)

            forecasts.append({
                'position': position,
                'stats': stats,
                'warnings': warnings,
                'has_warnings': bool(warnings),
                'is_current': position.pk == current_position_pk,
            })
    finally:
        # Гарантированно возвращаем исходную позицию.
        task.assignee = original_assignee

    # Текущая позиция — наверх
    forecasts.sort(key=lambda f: (not f['is_current'], f['position'].employment_type))
    return forecasts


def _detect_education_form(group_number):

    if not group_number:
        return 'очная'
    text = group_number.lower()
    if 'очно-заочн' in text:
        return 'очно-заочная'
    if 'заочн' in text:
        return 'заочная'
    return 'очная'


def _consultation_percent(form):
    """
    Процент для расчёта консультаций к лекциям по приказу

    - Очная: 5%
    - Очно-заочная: 10%
    - Заочная: 15%
    """
    return {
        'заочная': Decimal('0.15'),
        'очно-заочная': Decimal('0.10'),
    }.get(form, Decimal('0.05'))


def calculate_teaching_summary(position, use_fact=False):
    """
    Вычисляет сводку по видам учебной нагрузки для раздела 1.1
    индивидуального плана.


    """
    if position is None:
        return {'rows': [], 'total': Decimal('0')}

    items = list(
        position.teaching_load
        .select_related('activity_type')
        .all()
    )
    if not items:
        return {'rows': [], 'total': Decimal('0')}

    hours_attr = 'hours_fact' if use_fact else 'hours'

    CONTROL_CODES = frozenset({'CREDIT', 'EXAM', 'GRADED_CREDIT'})
    LECTURE_CODE = 'LECTURE'
    CONSULTATION_CODE = 'CONSULTATION'
    CONSULT_LECTURE_NAME = 'Консультации к лекционным занятиям, экзаменам'
    CONSULT_PRACTICE_NAME = 'Консультации к практикам'


    control_counts = {}
    for item in items:
        if item.activity_type.code in CONTROL_CODES:
            key = (item.discipline, item.semester)
            control_counts[key] = control_counts.get(key, 0) + 1


    summary = {}
    sort_orders = {}

    for item in items:
        code = item.activity_type.code
        h = getattr(item, hours_attr) or Decimal('0')

        if code == LECTURE_CODE:
            # расщепление по п. 3.2.1
            form = _detect_education_form(item.group_number)
            pct = _consultation_percent(form)

            if form == 'заочная':
                multiplier = 1
            else:
                multiplier = control_counts.get(
                    (item.discipline, item.semester), 1,
                )

            divisor = 1 + pct * multiplier
            clean = h / divisor
            consult = h - clean

            lec_name = item.activity_type.name   # «Лекционные занятия»
            summary[lec_name] = summary.get(lec_name, Decimal('0')) + clean
            sort_orders.setdefault(lec_name, item.activity_type.sort_order)

            summary[CONSULT_LECTURE_NAME] = (
                summary.get(CONSULT_LECTURE_NAME, Decimal('0')) + consult
            )
            sort_orders.setdefault(CONSULT_LECTURE_NAME, 40)

        elif code == CONSULTATION_CODE:
            if 'практик' in item.discipline.lower():
                name = CONSULT_PRACTICE_NAME
                sort_orders.setdefault(name, 41)
            else:
                name = CONSULT_LECTURE_NAME
                sort_orders.setdefault(name, 40)
            summary[name] = summary.get(name, Decimal('0')) + h

        else:
            name = item.activity_type.name
            summary[name] = summary.get(name, Decimal('0')) + h
            sort_orders.setdefault(name, item.activity_type.sort_order)

    # ---- шаг 3: формируем отсортированный список строк ----
    rows = []
    for name, hours in summary.items():
        if hours:   # пропускаем нулевые
            rows.append({
                'name': name,
                'hours': hours.quantize(Decimal('0.01')),
                'sort_order': sort_orders.get(name, 999),
            })

    rows.sort(key=lambda r: r['sort_order'])
    total = sum(r['hours'] for r in rows)

    return {'rows': rows, 'total': total}
