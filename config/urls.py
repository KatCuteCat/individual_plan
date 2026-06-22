from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


def index_redirect(request):
    """Перенаправление с главной страницы на дашборд по роли."""
    user = request.user
    if user.is_admin:
        return redirect('core:admin_dashboard')
    elif user.is_head:
        return redirect('tasks:head_dashboard')
    else:
        return redirect('tasks:teacher_dashboard')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('core/', include('apps.core.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('', login_required(index_redirect), name='index'),
]