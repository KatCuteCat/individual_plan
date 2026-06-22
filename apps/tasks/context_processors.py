
from apps.tasks.services import get_pending_approval_count


def head_badges(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    if not getattr(user, 'is_head', False):
        return {}

    return {
        'head_pending_approval_count': get_pending_approval_count(),
    }

def teacher_badges(request):
    """
    Кладёт в шаблоны счётчики для преподавателя
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    if not getattr(user, 'is_teacher', False):
        return {}

    return {
        'teacher_pending_approval_count': get_pending_approval_count(user=user),
    }