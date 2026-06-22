from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Доступ только для администратора."""

    def test_func(self):
        return self.request.user.is_admin

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return redirect('accounts:login')
        return super().handle_no_permission()


class HeadRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Доступ только для заведующего кафедрой."""

    def test_func(self):
        return self.request.user.is_head

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return redirect('accounts:login')
        return super().handle_no_permission()


class TeacherRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Доступ только для преподавателя."""

    def test_func(self):
        return self.request.user.is_teacher

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return redirect('accounts:login')
        return super().handle_no_permission()


class HeadOrAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Доступ для заведующего или администратора."""

    def test_func(self):
        return self.request.user.is_head or self.request.user.is_admin

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return redirect('accounts:login')
        return super().handle_no_permission()