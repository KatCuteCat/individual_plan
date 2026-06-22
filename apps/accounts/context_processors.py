"""
current_position — кладёт в каждый шаблон:
    user_positions — список активных позиций пользователя в активном году
    current_position — выбранная позиция (TeacherPosition или None)
    show_position_selector — True, если у пользователя ≥ 2 позиций
"""

from apps.core.models import AcademicYear

from .utils import get_current_position, get_user_positions


def current_position(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {
            'user_positions': [],
            'current_position': None,
            'show_position_selector': False,
        }

    active_year = AcademicYear.objects.filter(is_active=True).first()
    positions = get_user_positions(user, active_year)
    selected = get_current_position(request, academic_year=active_year)

    return {
        'user_positions': positions,
        'current_position': selected,
        'show_position_selector': len(positions) >= 2,
    }