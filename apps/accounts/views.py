from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, View
from .utils import set_current_position, get_user_positions
from apps.core.models import AcademicYear


from .forms import (
    LoginForm,
    CustomPasswordChangeForm,
    UserCreateForm,
    UserEditForm,
    UserSetPasswordForm,
    TeacherPositionForm,
    CopyPositionsForm,
)
from .mixins import AdminRequiredMixin
from .models import User, TeacherPosition


# Аутентификация

class LoginView(auth_views.LoginView):
    """Страница входа в систему."""
    template_name = 'accounts/login.html'
    form_class = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        """Перенаправление после входа в зависимости от роли."""
        user = self.request.user
        if user.is_admin:
            return reverse_lazy('core:admin_dashboard')
        elif user.is_head:
            return reverse_lazy('tasks:head_dashboard')
        else:
            return reverse_lazy('tasks:teacher_dashboard')


class LogoutView(auth_views.LogoutView):
    """Выход из системы."""
    next_page = reverse_lazy('accounts:login')


class PasswordChangeView(auth_views.PasswordChangeView):
    """Смена пароля пользователем."""
    template_name = 'accounts/password_change.html'
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy('accounts:password_change_done')

    def form_valid(self, form):
        messages.success(self.request, 'Пароль успешно изменён.')
        return super().form_valid(form)


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    """Страница подтверждения смены пароля."""
    template_name = 'accounts/password_change_done.html'


# CRUD пользователей (администратор)

class UserListView(AdminRequiredMixin, ListView):
    """Список всех пользователей."""
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        return User.objects.select_related('department').prefetch_related(
            'teacher_positions__academic_year'
        ).order_by('full_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.models import AcademicYear
        context['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        context['role_choices'] = User.ROLE_CHOICES
        context['current_role'] = self.request.GET.get('role', '')
        context['current_status'] = self.request.GET.get('status', '')
        return context


class UserCreateView(AdminRequiredMixin, CreateView):
    """Создание нового пользователя."""
    model = User
    form_class = UserCreateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Пользователь «{self.object.full_name or self.object.username}» создан. '
            f'Логин: {self.object.username}'
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Создание пользователя'
        context['button_text'] = 'Создать'
        return context


class UserEditView(AdminRequiredMixin, UpdateView):
    """Редактирование пользователя."""
    model = User
    form_class = UserEditForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Пользователь «{self.object.full_name or self.object.username}» обновлён.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Редактирование: {self.object.full_name or self.object.username}'
        context['button_text'] = 'Сохранить'
        context['is_edit'] = True
        return context


class UserToggleActiveView(AdminRequiredMixin, View):
    """Активация / деактивация пользователя."""

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, 'Нельзя деактивировать свою учётную запись.')
            return redirect('accounts:user_list')

        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])

        if user.is_active:
            messages.success(request, f'Пользователь «{user.full_name or user.username}» активирован.')
        else:
            messages.warning(request, f'Пользователь «{user.full_name or user.username}» деактивирован.')

        return redirect('accounts:user_list')


class UserSetPasswordView(AdminRequiredMixin, View):
    """Сброс пароля пользователю администратором."""

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = UserSetPasswordForm()
        return self._render(request, user, form)

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = UserSetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['new_password1'])
            user.save()
            messages.success(
                request,
                f'Пароль пользователя «{user.full_name or user.username}» изменён.'
            )
            return redirect('accounts:user_list')
        return self._render(request, user, form)

    def _render(self, request, user, form):
        from django.shortcuts import render
        return render(request, 'accounts/user_set_password.html', {
            'target_user': user,
            'form': form,
        })


# Карточка пользователя и его позиции (администратор)

class UserDetailView(AdminRequiredMixin, View):
    """
    Карточка пользователя с разделом «Позиции в учебном году».
    """

    def get(self, request, pk):
        from django.shortcuts import render
        from apps.core.models import AcademicYear

        target_user = get_object_or_404(User, pk=pk)

        year_id = request.GET.get('year')
        all_years = AcademicYear.objects.order_by('-start_date')
        active_year = AcademicYear.objects.filter(is_active=True).first()

        if year_id:
            current_year = all_years.filter(pk=year_id).first() or active_year
        else:
            current_year = active_year

        positions_current = TeacherPosition.objects.none()
        if current_year:
            positions_current = (
                target_user.teacher_positions
                .filter(academic_year=current_year)
                .select_related('position', 'academic_year')
                .order_by('employment_type')
            )

        positions_other = (
            target_user.teacher_positions
            .exclude(academic_year=current_year) if current_year
            else target_user.teacher_positions.all()
        )
        positions_other = positions_other.select_related(
            'position', 'academic_year'
        ).order_by('-academic_year__start_date', 'employment_type')

        return render(request, 'accounts/user_detail.html', {
            'target_user': target_user,
            'current_year': current_year,
            'active_year': active_year,
            'all_years': all_years,
            'positions_current': positions_current,
            'positions_other': positions_other,
        })


class PositionCreateView(AdminRequiredMixin, View):
    """Создание новой позиции для конкретного пользователя в выбранном году."""

    def get(self, request, user_pk):
        return self._render(request, user_pk, form=None)

    def post(self, request, user_pk):
        from apps.core.models import AcademicYear

        target_user = get_object_or_404(User, pk=user_pk)
        year_id = request.POST.get('academic_year') or request.GET.get('year')
        academic_year = get_object_or_404(AcademicYear, pk=year_id) if year_id else None
        if academic_year is None:
            messages.error(request, 'Не указан учебный год для позиции.')
            return redirect('accounts:user_detail', pk=target_user.pk)

        form = TeacherPositionForm(
            request.POST,
            user=target_user,
            academic_year=academic_year,
        )
        if form.is_valid():
            position = form.save(commit=False)
            position.user = target_user
            position.academic_year = academic_year
            position.save()
            messages.success(
                request,
                f'Позиция «{position.display_label}» добавлена для '
                f'{target_user.full_name or target_user.username} '
                f'в учебном году {academic_year.name}.'
            )
            return redirect(
                f"{reverse_lazy('accounts:user_detail', kwargs={'pk': target_user.pk})}"
                f"?year={academic_year.pk}"
            )
        return self._render(request, user_pk, form=form, year_id=year_id)

    def _render(self, request, user_pk, form=None, year_id=None):
        from django.shortcuts import render
        from apps.core.models import AcademicYear

        target_user = get_object_or_404(User, pk=user_pk)
        year_id = year_id or request.GET.get('year')
        active_year = AcademicYear.objects.filter(is_active=True).first()
        all_years = AcademicYear.objects.filter(is_archived=False).order_by('-start_date')

        if year_id:
            academic_year = AcademicYear.objects.filter(pk=year_id).first() or active_year
        else:
            academic_year = active_year

        if form is None:
            form = TeacherPositionForm(
                user=target_user,
                academic_year=academic_year,
                initial={'is_active': True},
            )

        return render(request, 'accounts/position_form.html', {
            'target_user': target_user,
            'academic_year': academic_year,
            'all_years': all_years,
            'form': form,
            'page_title': 'Новая позиция',
            'button_text': 'Создать позицию',
            'is_edit': False,
        })


class PositionEditView(AdminRequiredMixin, View):
    """Редактирование существующей позиции."""

    def get(self, request, pk):
        position = get_object_or_404(
            TeacherPosition.objects.select_related('user', 'academic_year', 'position'),
            pk=pk,
        )
        form = TeacherPositionForm(
            instance=position,
            user=position.user,
            academic_year=position.academic_year,
        )
        return self._render(request, position, form)

    def post(self, request, pk):
        position = get_object_or_404(
            TeacherPosition.objects.select_related('user', 'academic_year', 'position'),
            pk=pk,
        )
        form = TeacherPositionForm(
            request.POST,
            instance=position,
            user=position.user,
            academic_year=position.academic_year,
        )
        if form.is_valid():
            updated = form.save()
            messages.success(
                request,
                f'Позиция «{updated.display_label}» обновлена.'
            )
            return redirect(
                f"{reverse_lazy('accounts:user_detail', kwargs={'pk': position.user.pk})}"
                f"?year={position.academic_year.pk}"
            )
        return self._render(request, position, form)

    def _render(self, request, position, form):
        from django.shortcuts import render
        return render(request, 'accounts/position_form.html', {
            'target_user': position.user,
            'academic_year': position.academic_year,
            'all_years': None,
            'form': form,
            'position_obj': position,
            'page_title': 'Редактирование позиции',
            'button_text': 'Сохранить',
            'is_edit': True,
        })


class PositionDeleteView(AdminRequiredMixin, View):

    def post(self, request, pk):
        position = get_object_or_404(
            TeacherPosition.objects.select_related('user', 'academic_year'),
            pk=pk,
        )
        if position.assigned_tasks.exists():
            messages.error(
                request,
                f'Нельзя удалить позицию «{position.display_label}»: '
                f'на ней есть задачи. Сначала переназначьте или удалите задачи.'
            )
            return redirect(
                f"{reverse_lazy('accounts:user_detail', kwargs={'pk': position.user.pk})}"
                f"?year={position.academic_year.pk}"
            )

        user_pk = position.user.pk
        year_pk = position.academic_year.pk
        label = position.display_label
        position.delete()
        messages.warning(request, f'Позиция «{label}» удалена.')
        return redirect(
            f"{reverse_lazy('accounts:user_detail', kwargs={'pk': user_pk})}"
            f"?year={year_pk}"
        )


class CopyPositionsView(AdminRequiredMixin, View):

    template_name = 'accounts/positions_copy.html'

    def get(self, request, target_pk):
        target_year = self._get_target_year(target_pk)
        form = CopyPositionsForm(target_year=target_year)
        return self._render(request, target_year, form, preview=None)

    def post(self, request, target_pk):
        target_year = self._get_target_year(target_pk)
        action = request.POST.get('action', 'preview')

        form = CopyPositionsForm(request.POST, target_year=target_year)
        if not form.is_valid():
            return self._render(request, target_year, form, preview=None)

        source_year = form.cleaned_data['source_year']
        include_inactive = form.cleaned_data['include_inactive']
        on_conflict = form.on_conflict

        if action == 'confirm':
            return self._do_copy(
                request, target_year, source_year, include_inactive, on_conflict, form,
            )

        return self._do_preview(
            request, target_year, source_year, include_inactive, on_conflict, form,
        )



    def _get_target_year(self, target_pk):
        from apps.core.models import AcademicYear
        return get_object_or_404(AcademicYear, pk=target_pk)

    def _render(self, request, target_year, form, preview):
        from django.shortcuts import render
        return render(request, self.template_name, {
            'target_year': target_year,
            'form': form,
            'preview': preview,
            'page_title': f'Копирование позиций в год «{target_year.name}»',
        })

    def _do_preview(self, request, target_year, source_year,
                    include_inactive, on_conflict, form):
        from .services import preview_copy_positions
        preview = preview_copy_positions(
            source_year=source_year,
            target_year=target_year,
            include_inactive=include_inactive,
            on_conflict=on_conflict,
        )
        return self._render(request, target_year, form, preview=preview)

    def _do_copy(self, request, target_year, source_year,
                 include_inactive, on_conflict, form):
        from .services import copy_positions
        from django.core.exceptions import ValidationError as DjangoValidationError

        if getattr(target_year, 'is_archived', False):
            messages.error(request, 'Нельзя копировать позиции в архивный год.')
            return redirect('core:year_list')

        try:
            result = copy_positions(
                source_year=source_year,
                target_year=target_year,
                include_inactive=include_inactive,
                on_conflict=on_conflict,
            )
        except DjangoValidationError as exc:
            messages.error(
                request,
                'Копирование прервано: одна из позиций-источников '
                'не проходит валидацию. ' + '; '.join(exc.messages),
            )
            return self._render(request, target_year, form, preview=None)
        except ValueError as exc:
            messages.error(request, f'Копирование прервано: {exc}')
            return self._render(request, target_year, form, preview=None)

        parts = []
        if result.created_count:
            parts.append(f'создано: {result.created_count}')
        if result.updated_count:
            parts.append(f'обновлено: {result.updated_count}')
        if result.skipped_duplicates_count:
            parts.append(f'пропущено дубликатов: {result.skipped_duplicates_count}')
        if result.skipped_inactive_count:
            parts.append(f'пропущено неактивных: {result.skipped_inactive_count}')

        summary = ', '.join(parts) if parts else 'ничего не сделано'
        msg = (
            f'Копирование позиций из «{source_year.name}» в «{target_year.name}» '
            f'завершено: {summary}.'
        )

        if result.total_changed > 0:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)

        return redirect('core:year_list')


# === Импорт учебной нагрузки из 1С ===

class TeachingLoadImportView(AdminRequiredMixin, View):
    """
    Загрузка выгрузки учебной нагрузки 1С на конкретную позицию.
    """

    PREVIEW_SESSION_KEY_TEMPLATE = 'teaching_load_preview_{}'
    PREVIEW_TTL_SECONDS = 60 * 60  # один час

    def _session_key(self, position):
        return self.PREVIEW_SESSION_KEY_TEMPLATE.format(position.pk)

    def _clear_preview(self, request, position):
        request.session.pop(self._session_key(position), None)

    def _back_url(self, request, position):
        """URL карточки пользователя с тем же выбранным учебным годом."""
        from django.urls import reverse
        url = reverse('accounts:user_detail', args=[position.user.pk])
        return f'{url}?year={position.academic_year.pk}'


    def get(self, request, pk):
        from django.shortcuts import render, get_object_or_404
        from .models import TeacherPosition
        from .forms import TeachingLoadImportForm

        position = get_object_or_404(
            TeacherPosition.objects.select_related('user', 'position', 'academic_year'),
            pk=pk,
        )

        if position.academic_year.is_archived:
            messages.error(
                request,
                'Учебный год архивирован. Загрузка учебной нагрузки недоступна.'
            )
            return redirect(self._back_url(request, position))

        self._clear_preview(request, position)

        form = TeachingLoadImportForm()
        return render(request, 'accounts/teaching_load_import.html', {
            'position': position,
            'target_user': position.user,
            'form': form,
            'preview_items': None,
            'back_url': self._back_url(request, position),
        })


    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        from .models import TeacherPosition

        position = get_object_or_404(
            TeacherPosition.objects.select_related('user', 'position', 'academic_year'),
            pk=pk,
        )

        if position.academic_year.is_archived:
            messages.error(request, 'Учебный год архивирован. Загрузка недоступна.')
            return redirect(self._back_url(request, position))

        action = request.POST.get('action')

        if action == 'preview':
            return self._handle_preview(request, position)
        elif action == 'confirm':
            return self._handle_confirm(request, position)
        elif action == 'cancel':
            self._clear_preview(request, position)
            messages.info(request, 'Загрузка отменена.')
            return redirect('accounts:teaching_load_import', pk=position.pk)
        else:
            messages.error(request, 'Неизвестное действие.')
            return redirect('accounts:teaching_load_import', pk=position.pk)

    # предосмотр

    def _handle_preview(self, request, position):
        from django.shortcuts import render
        from decimal import Decimal
        from django.utils import timezone
        from .forms import TeachingLoadImportForm
        from .teaching_load_import import parse_teaching_load_xlsx

        form = TeachingLoadImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, 'accounts/teaching_load_import.html', {
                'position': position,
                'target_user': position.user,
                'form': form,
                'preview_items': None,
                'back_url': self._back_url(request, position),
            })

        replace_existing = form.cleaned_data['replace_existing']
        file = form.cleaned_data['file']

        # Парсим файл
        items, errors, warnings = parse_teaching_load_xlsx(file)

        # Бизнес-проверка: нагрузка уже загружена, а галка «Заменить» снята
        existing_count = position.teaching_load.count()
        if existing_count > 0 and not replace_existing:
            errors.insert(
                0,
                f'У позиции уже загружено строк нагрузки: {existing_count}. '
                f'Включите галку «Заменить существующие данные», чтобы перезаписать их.'
            )


        if replace_existing and position.teaching_load.filter(hours_fact__gt=0).exists():
            warnings.insert(
                0,
                'У некоторых строк текущей нагрузки заполнено поле «Факт». '
                'При замене фактические часы будут сброшены в 0.'
            )

        # Если ошибок нет — кладём предпросмотр в сессию
        preview_payload = None
        if not errors and items:
            preview_payload = {
                'position_id': position.pk,
                'replace_existing': replace_existing,
                'created_at': timezone.now().isoformat(),
                'items': [
                    {
                        'row': it.row,
                        'discipline': it.discipline,
                        'semester': it.semester,
                        'activity_type_id': it.activity_type.pk,
                        'activity_type_name': it.activity_type.name,
                        'hours': str(it.hours),
                        'group_number': it.group_number,
                        'cycle': it.cycle,
                        'students_count': it.students_count,
                        'period_label': it.period_label,
                        'row_num': it.row_num,
                    }
                    for it in items
                ],
            }
            request.session[self._session_key(position)] = preview_payload

        total_hours = sum((it.hours for it in items), Decimal('0'))

        return render(request, 'accounts/teaching_load_import.html', {
            'position': position,
            'target_user': position.user,
            'form': form,
            'preview_items': items,
            'preview_total_hours': total_hours,
            'preview_count': len(items),
            'parse_errors': errors,
            'parse_warnings': warnings,
            'replace_existing': replace_existing,
            'has_preview': preview_payload is not None,
            'existing_count': existing_count,
            'back_url': self._back_url(request, position),
        })



    def _handle_confirm(self, request, position):
        from datetime import datetime
        from decimal import Decimal
        from django.db import transaction
        from django.utils import timezone
        from .models import TeachingLoadItem
        from apps.core.models import TeachingActivityType

        key = self._session_key(position)
        payload = request.session.get(key)

        if not payload:
            messages.error(
                request,
                'Не нашли данные предпросмотра. Возможно, сессия истекла — загрузите файл заново.'
            )
            return redirect('accounts:teaching_load_import', pk=position.pk)

        try:
            created_at = datetime.fromisoformat(payload['created_at'])
        except (KeyError, ValueError):
            created_at = None
        if created_at is None or (timezone.now() - created_at).total_seconds() > self.PREVIEW_TTL_SECONDS:
            self._clear_preview(request, position)
            messages.error(
                request,
                'Предпросмотр устарел (прошло больше часа). Загрузите файл заново.'
            )
            return redirect('accounts:teaching_load_import', pk=position.pk)

        # Проверка соответствия позиции
        if payload.get('position_id') != position.pk:
            self._clear_preview(request, position)
            messages.error(request, 'Внутренняя ошибка: данные предпросмотра не от этой позиции.')
            return redirect('accounts:teaching_load_import', pk=position.pk)

        items_data = payload.get('items', [])
        if not items_data:
            self._clear_preview(request, position)
            messages.error(request, 'В предпросмотре нет ни одной строки. Загрузите файл заново.')
            return redirect('accounts:teaching_load_import', pk=position.pk)

        activity_types_by_id = {
            at.pk: at for at in TeachingActivityType.objects.all()
        }

        new_items = []
        total_hours = Decimal('0')
        for d in items_data:
            at = activity_types_by_id.get(d['activity_type_id'])
            if at is None:
                self._clear_preview(request, position)
                messages.error(
                    request,
                    f'Вид нагрузки с id={d["activity_type_id"]} не найден в справочнике. '
                    f'Загрузите файл заново.'
                )
                return redirect('accounts:teaching_load_import', pk=position.pk)
            hours = Decimal(d['hours'])
            total_hours += hours
            new_items.append(TeachingLoadItem(
                position=position,
                discipline=d['discipline'],
                semester=d['semester'],
                activity_type=at,
                hours=hours,
                group_number=d.get('group_number', ''),
                cycle=d.get('cycle', ''),
                students_count=d.get('students_count'),
                period_label=d.get('period_label', ''),
                row_num=d.get('row_num'),
            ))

        # Транзакция: удалить старые, создать новые, обновить позицию
        try:
            with transaction.atomic():
                position.teaching_load.all().delete()
                TeachingLoadItem.objects.bulk_create(new_items)
                position.teaching_hours = total_hours
                position.teaching_load_imported_at = timezone.now()
                position.save(update_fields=['teaching_hours', 'teaching_load_imported_at', 'updated_at'])
        except Exception as e:
            self._clear_preview(request, position)
            messages.error(request, f'Ошибка при сохранении: {e}')
            return redirect('accounts:teaching_load_import', pk=position.pk)

        self._clear_preview(request, position)
        messages.success(
            request,
            f'Учебная нагрузка загружена: {len(new_items)} строк, '
            f'итого {total_hours} ч.'
        )
        return redirect(self._back_url(request, position))


# Переключение текущей позиции

class SetCurrentPositionView(View):
    """
    Обработчик запроса от селектора «Я работаю как
    """

    def post(self, request):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        position_id = request.POST.get('position_id')
        if not position_id:
            return redirect(request.META.get('HTTP_REFERER', '/'))

        try:
            position_id = int(position_id)
        except (TypeError, ValueError):
            messages.error(request, 'Некорректный идентификатор позиции.')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        active_year = AcademicYear.objects.filter(is_active=True).first()
        allowed = get_user_positions(request.user, active_year)
        match = next((p for p in allowed if p.pk == position_id), None)

        if match is None:
            messages.error(
                request,
                'Эта позиция вам недоступна или больше не активна.'
            )
            return redirect(request.META.get('HTTP_REFERER', '/'))

        set_current_position(request, match)
        messages.success(
            request,
            f'Текущая позиция: {match.display_label}.'
        )
        return redirect(request.META.get('HTTP_REFERER', '/'))

# Ввод факта учебной нагрузки

class TeachingLoadFactView(AdminRequiredMixin, View):
    """
    Страница ввода фактических часов учебной нагрузки по позиции.
    """

    def _back_url(self, position):
        from django.urls import reverse
        url = reverse('accounts:user_detail', args=[position.user.pk])
        return f'{url}?year={position.academic_year.pk}'

    def _get_position(self, pk):
        return get_object_or_404(
            TeacherPosition.objects.select_related(
                'user', 'position', 'academic_year',
            ),
            pk=pk,
        )

    def get(self, request, pk):
        from django.shortcuts import render

        position = self._get_position(pk)
        items = position.teaching_load.select_related('activity_type').order_by(
            'semester', 'discipline', 'activity_type__sort_order',
        )
        from apps.core.models import TeachingActivityType
        activity_types = TeachingActivityType.objects.order_by('sort_order')
        return render(request, 'accounts/teaching_load_fact.html', {
            'position': position,
            'target_user': position.user,
            'items': items,
            'activity_types': activity_types,
            'back_url': self._back_url(position),
        })

    def post(self, request, pk):
        from django.db.models import F
        from decimal import Decimal, InvalidOperation

        position = self._get_position(pk)

        if position.academic_year.is_archived:
            messages.error(request, 'Учебный год архивирован. Редактирование недоступно.')
            return redirect(self._back_url(position))

        action = request.POST.get('action')

        if action == 'copy_plan':
            updated = position.teaching_load.update(hours_fact=F('hours'))
            messages.success(request, f'Факт скопирован из плана ({updated} строк).')
            return redirect('accounts:teaching_load_fact', pk=position.pk)

        if action == 'reset':
            updated = position.teaching_load.update(hours_fact=Decimal('0'))
            messages.success(request, f'Факт обнулён ({updated} строк).')
            return redirect('accounts:teaching_load_fact', pk=position.pk)

        if action == 'save':
            items = {
                str(item.pk): item
                for item in position.teaching_load.all()
            }
            errors = []
            to_update = []
            for key, value in request.POST.items():
                if not key.startswith('fact_'):
                    continue
                item_pk = key[5:]  # после 'fact_'
                item = items.get(item_pk)
                if item is None:
                    continue
                try:
                    new_val = Decimal(value.replace(',', '.').strip())
                    if new_val < 0:
                        raise ValueError
                except (InvalidOperation, ValueError):
                    errors.append(f'Строка «{item.discipline}»: некорректное значение «{value}»')
                    continue
                if new_val != item.hours_fact:
                    item.hours_fact = new_val
                    to_update.append(item)

            if errors:
                messages.error(request, ' '.join(errors))
            elif to_update:
                from django.db import transaction
                with transaction.atomic():
                    for item in to_update:
                        item.save(update_fields=['hours_fact', 'updated_at'])
                messages.success(request, f'Сохранено ({len(to_update)} строк обновлено).')
            else:
                messages.info(request, 'Изменений нет.')

            return redirect('accounts:teaching_load_fact', pk=position.pk)

        if action == 'add':
            from apps.core.models import TeachingActivityType
            from decimal import Decimal, InvalidOperation
            from .models import TeachingLoadItem

            discipline = request.POST.get('new_discipline', '').strip()
            semester = request.POST.get('new_semester', '').strip()
            at_id = request.POST.get('new_activity_type', '').strip()
            hours_str = request.POST.get('new_hours', '').strip()
            fact_str = request.POST.get('new_hours_fact', '').strip()
            group = request.POST.get('new_group', '').strip()

            if not discipline:
                messages.error(request, 'Укажите название дисциплины.')
                return redirect('accounts:teaching_load_fact', pk=position.pk)

            try:
                semester_val = int(semester)
                if semester_val < 1 or semester_val > 12:
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, 'Семестр — целое число от 1 до 12.')
                return redirect('accounts:teaching_load_fact', pk=position.pk)

            try:
                activity_type = TeachingActivityType.objects.get(pk=at_id)
            except TeachingActivityType.DoesNotExist:
                messages.error(request, 'Выберите вид занятия.')
                return redirect('accounts:teaching_load_fact', pk=position.pk)

            try:
                hours_val = Decimal(hours_str.replace(',', '.'))
                if hours_val < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                messages.error(request, 'Часы (план) — число ≥ 0.')
                return redirect('accounts:teaching_load_fact', pk=position.pk)

            try:
                fact_val = Decimal(fact_str.replace(',', '.')) if fact_str else hours_val
                if fact_val < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                messages.error(request, 'Часы (факт) — число ≥ 0.')
                return redirect('accounts:teaching_load_fact', pk=position.pk)

            TeachingLoadItem.objects.create(
                position=position,
                discipline=discipline,
                semester=semester_val,
                activity_type=activity_type,
                hours=hours_val,
                hours_fact=fact_val,
                group_number=group,
            )
            messages.success(request, f'Строка «{discipline} — {activity_type.name}» добавлена.')
            return redirect('accounts:teaching_load_fact', pk=position.pk)

        messages.error(request, 'Неизвестное действие.')
        return redirect('accounts:teaching_load_fact', pk=position.pk)