"""
Утилиты для работы с TeacherPosition.
Логика:
1. Если у пользователя нет ни одной активной позиции в активном году — None.
2. Если в сессии лежит id позиции и она всё ещё валидна (принадлежит
   пользователю, активна, активный год) — возвращаем её.
3. Иначе — выбираем приоритетную,
   записываем в сессию.
"""

from django.contrib import messages

from apps.accounts.models import TeacherPosition
from apps.core.models import AcademicYear


SESSION_KEY = 'current_position_id'


def _priority_index(employment_type):
    order = [
        TeacherPosition.EMPLOYMENT_MAIN,
        TeacherPosition.EMPLOYMENT_INTERNAL_COMBINING,
        TeacherPosition.EMPLOYMENT_EXTERNAL_COMBINING,
        TeacherPosition.EMPLOYMENT_HOURLY,
    ]
    try:
        return order.index(employment_type)
    except ValueError:
        return 99


def get_user_positions(user, academic_year):

    if user is None or not user.is_authenticated or academic_year is None:
        return []
    positions = list(
        TeacherPosition.objects.filter(
            user=user,
            academic_year=academic_year,
            is_active=True,
        ).select_related('position', 'academic_year')
    )
    positions.sort(key=lambda p: _priority_index(p.employment_type))
    return positions


def get_current_position(request, academic_year=None, notify=True):
    """
    Получить текущую позицию преподавателя из сессии.
    """
    user = request.user
    if not user.is_authenticated:
        return None

    if academic_year is None:
        academic_year = AcademicYear.objects.filter(is_active=True).first()
    if academic_year is None:
        return None

    positions = get_user_positions(user, academic_year)
    if not positions:
        request.session.pop(SESSION_KEY, None)
        return None

    saved_id = request.session.get(SESSION_KEY)
    saved_position = None
    if saved_id is not None:
        for p in positions:
            if p.pk == saved_id:
                saved_position = p
                break

    if saved_position is not None:
        return saved_position

    fallback = positions[0]
    if saved_id is not None and saved_position is None and notify:
        messages.warning(
            request,
            f'Прежняя выбранная позиция больше недоступна. '
            f'Переключено на «{fallback.display_label}».'
        )
    request.session[SESSION_KEY] = fallback.pk
    return fallback


def set_current_position(request, position):
    """Сохранить выбранную позицию в сессии """
    request.session[SESSION_KEY] = position.pk