from django.views.generic import TemplateView, ListView, CreateView, UpdateView, View
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.mixins import AdminRequiredMixin
from apps.accounts.models import User
from .models import AcademicYear, TaskCategory, Position, PositionWorkload, WorkType, ExportSettings
from .forms import AcademicYearForm, PositionWorkloadForm, WorkTypeForm, ExportSettingsForm

class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """Главная страница администратора — здоровье системы, обзор, быстрые действия."""
    template_name = 'core/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        users = User.objects.all()
        active_year = AcademicYear.objects.filter(is_active=True).first()

        # === Обзор данных (карточки-счётчики) ===
        context['users_active'] = users.filter(is_active=True).count()
        context['users_total'] = users.count()
        context['active_year'] = active_year
        context['categories_active'] = TaskCategory.objects.filter(is_active=True).count()
        context['categories_total'] = TaskCategory.objects.count()
        context['positions_total'] = Position.objects.count()
        context['worktypes_active'] = WorkType.objects.filter(is_active=True).count()
        context['worktypes_total'] = WorkType.objects.count()

        if active_year:
            context['workloads_current'] = PositionWorkload.objects.filter(
                academic_year=active_year
            ).count()
        else:
            context['workloads_current'] = 0

        # Здоровье системы
        checks = []

        # 1. Активный учебный год
        if active_year:
            checks.append({
                'status': 'ok',
                'title': 'Учебный год',
                'text': f'Активный год: {active_year.name}',
            })
        else:
            checks.append({
                'status': 'danger',
                'title': 'Учебный год',
                'text': 'Нет активного учебного года',
                'hint': 'Создайте или активируйте учебный год',
                'url': 'core:year_list',
            })

        # 2. Заведующий кафедрой
        heads_count = users.filter(role=User.ROLE_HEAD, is_active=True).count()
        if heads_count > 0:
            checks.append({
                'status': 'ok',
                'title': 'Заведующий',
                'text': f'Заведующих кафедрой: {heads_count}',
            })
        else:
            checks.append({
                'status': 'danger',
                'title': 'Заведующий',
                'text': 'Нет ни одного заведующего',
                'hint': 'Создайте пользователя с ролью «Заведующий кафедрой»',
                'url': 'accounts:user_list',
            })

        # 3. Преподаватели
        teachers_count = users.filter(role=User.ROLE_TEACHER, is_active=True).count()
        if teachers_count > 0:
            checks.append({
                'status': 'ok',
                'title': 'Преподаватели',
                'text': f'Активных преподавателей: {teachers_count}',
            })
        else:
            checks.append({
                'status': 'danger',
                'title': 'Преподаватели',
                'text': 'Нет ни одного преподавателя',
                'hint': 'Создайте пользователей с ролью «Преподаватель»',
                'url': 'accounts:user_list',
            })

        # 4. Нормы нагрузки
        if active_year:
            positions_count = Position.objects.count()
            workloads_count = context['workloads_current']
            if positions_count > 0 and workloads_count >= positions_count:
                checks.append({
                    'status': 'ok',
                    'title': 'Нормы нагрузки',
                    'text': f'Настроены для всех должностей ({workloads_count}/{positions_count})',
                })
            elif workloads_count > 0:
                checks.append({
                    'status': 'warning',
                    'title': 'Нормы нагрузки',
                    'text': f'Настроены не для всех должностей ({workloads_count}/{positions_count})',
                    'hint': 'Добавьте нормы для оставшихся должностей',
                    'url': 'core:workload_list',
                })
            else:
                checks.append({
                    'status': 'danger',
                    'title': 'Нормы нагрузки',
                    'text': 'Нормы нагрузки не настроены',
                    'hint': 'Добавьте нормы нагрузки для каждой должности',
                    'url': 'core:workload_list',
                })

        # 5. Категории задач
        categories_active = context['categories_active']
        if categories_active >= 5:
            checks.append({
                'status': 'ok',
                'title': 'Категории задач',
                'text': f'Активных категорий: {categories_active}',
            })
        elif categories_active > 0:
            checks.append({
                'status': 'warning',
                'title': 'Категории задач',
                'text': f'Активных категорий: {categories_active} (рекомендуется 5)',
                'hint': 'Проверьте, все ли виды деятельности ППС добавлены',
                'url': 'core:category_list',
            })
        else:
            checks.append({
                'status': 'danger',
                'title': 'Категории задач',
                'text': 'Нет активных категорий задач',
                'hint': 'Добавьте категории задач',
                'url': 'core:category_list',
            })

            # 6. Преподаватели без позиций в активном учебном году
            if active_year:
                from apps.accounts.models import TeacherPosition
                teachers_qs = users.filter(
                    role=User.ROLE_TEACHER,
                    is_active=True,
                )
                teachers_with_positions = TeacherPosition.objects.filter(
                    academic_year=active_year,
                    is_active=True,
                    user__in=teachers_qs,
                ).values_list('user_id', flat=True).distinct()
                teachers_no_positions = teachers_qs.exclude(
                    pk__in=teachers_with_positions
                ).count()
                if teachers_no_positions == 0:
                    checks.append({
                        'status': 'ok',
                        'title': 'Позиции преподавателей',
                        'text': 'У всех преподавателей назначены позиции в активном году',
                    })
                else:
                    checks.append({
                        'status': 'warning',
                        'title': 'Позиции преподавателей',
                        'text': f'Без позиций в активном году: {teachers_no_positions}',
                        'hint': 'Откройте карточку пользователя и добавьте позицию',
                        'url': 'accounts:user_list',
                    })
            else:
                checks.append({
                    'status': 'warning',
                    'title': 'Позиции преподавателей',
                    'text': 'Нельзя проверить — нет активного учебного года',
                })
        context['checks'] = checks
        # Общий статус: ok / warning / danger
        statuses = [c['status'] for c in checks]
        if 'danger' in statuses:
            context['system_status'] = 'danger'
        elif 'warning' in statuses:
            context['system_status'] = 'warning'
        else:
            context['system_status'] = 'ok'

        return context


# Учебные годы

class YearListView(AdminRequiredMixin, ListView):
    """Список учебных годов."""
    model = AcademicYear
    template_name = 'core/year_list.html'
    context_object_name = 'years'
    ordering = ['-start_date']


class YearCreateView(AdminRequiredMixin, CreateView):
    """Создание учебного года."""
    model = AcademicYear
    form_class = AcademicYearForm
    template_name = 'core/year_form.html'
    success_url = reverse_lazy('core:year_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Учебный год «{self.object.name}» создан.')

        copy_from = form.cleaned_data.get('copy_from')
        if copy_from:
            from apps.accounts.services import copy_positions
            try:
                result = copy_positions(
                    source_year=copy_from,
                    target_year=self.object,
                    include_inactive=form.cleaned_data.get('copy_include_inactive', False),
                    on_conflict='skip',
                )
                skipped = result.skipped_duplicates_count + result.skipped_inactive_count
                msg = f'Из года «{copy_from.name}» скопировано позиций: {result.created_count}.'
                if skipped:
                    msg += f' Пропущено: {skipped}.'
                messages.success(self.request, msg)
            except Exception as e:
                messages.error(
                    self.request,
                    f'Год создан, но копирование позиций не удалось: {e}'
                )

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Новый учебный год'
        context['button_text'] = 'Создать'
        return context


class YearEditView(AdminRequiredMixin, UpdateView):
    """Редактирование учебного года."""
    model = AcademicYear
    form_class = AcademicYearForm
    template_name = 'core/year_form.html'
    success_url = reverse_lazy('core:year_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Учебный год «{self.object.name}» обновлён.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Редактирование: {self.object.name}'
        context['button_text'] = 'Сохранить'
        return context


class YearActivateView(AdminRequiredMixin, View):
    """Активация учебного года (снимает активность с остальных)."""

    def post(self, request, pk):
        year = get_object_or_404(AcademicYear, pk=pk)
        if year.is_archived:
            messages.error(request, 'Нельзя активировать архивный учебный год.')
            return redirect('core:year_list')
        # Метод save() в модели сам снимет флаг с остальных годов
        year.is_active = True
        year.save()
        messages.success(request, f'Учебный год «{year.name}» установлен как активный.')
        return redirect('core:year_list')


class YearArchiveView(AdminRequiredMixin, View):
    """Архивирование учебного года."""

    def post(self, request, pk):
        year = get_object_or_404(AcademicYear, pk=pk)
        if year.is_active:
            messages.error(request, 'Нельзя архивировать активный учебный год. Сначала активируйте другой год.')
            return redirect('core:year_list')
        year.is_archived = True
        year.save()
        messages.success(request, f'Учебный год «{year.name}» перемещён в архив.')
        return redirect('core:year_list')


class YearDeleteView(AdminRequiredMixin, View):
    """Удаление учебного года (только если нет задач)."""

    def post(self, request, pk):
        year = get_object_or_404(AcademicYear, pk=pk)
        # Проверяем, есть ли задачи привязанные к году
        if year.tasks.exists():
            messages.error(
                request,
                f'Нельзя удалить учебный год «{year.name}»: к нему привязаны задачи.'
            )
            return redirect('core:year_list')
        if year.is_active:
            messages.error(request, 'Нельзя удалить активный учебный год.')
            return redirect('core:year_list')
        name = year.name
        year.delete()
        messages.success(request, f'Учебный год «{name}» удалён.')
        return redirect('core:year_list')


#Категории задач

class CategoryListView(AdminRequiredMixin, ListView):
    """Список категорий задач."""
    model = TaskCategory
    template_name = 'core/category_list.html'
    context_object_name = 'categories'
    ordering = ['name']


class CategoryToggleActiveView(AdminRequiredMixin, View):
    """Активация/деактивация категории задач."""

    def post(self, request, pk):
        category = get_object_or_404(TaskCategory, pk=pk)
        category.is_active = not category.is_active
        category.save(update_fields=['is_active'])
        status = 'активирована' if category.is_active else 'деактивирована'
        messages.success(request, f'Категория «{category.name}» {status}.')
        return redirect('core:category_list')


# Нормы нагрузки

class WorkloadListView(AdminRequiredMixin, ListView):
    """Список норм нагрузки."""
    model = PositionWorkload
    template_name = 'core/workload_list.html'
    context_object_name = 'workloads'

    def get_queryset(self):
        # Фильтр по учебному году (по умолчанию — активный)
        queryset = PositionWorkload.objects.select_related('position', 'academic_year')
        year_id = self.request.GET.get('year')
        if year_id:
            queryset = queryset.filter(academic_year_id=year_id)
        else:
            # Показываем активный год по умолчанию
            active_year = AcademicYear.objects.filter(is_active=True).first()
            if active_year:
                queryset = queryset.filter(academic_year=active_year)
        return queryset.order_by('position__name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['all_years'] = AcademicYear.objects.order_by('-start_date')
        context['current_year_id'] = self.request.GET.get('year', '')
        context['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        return context


class WorkloadEditView(AdminRequiredMixin, View):
    """Редактирование нормы нагрузки для должности."""

    def get(self, request, pk):
        workload = get_object_or_404(PositionWorkload.objects.select_related('position', 'academic_year'), pk=pk)
        from .forms import PositionWorkloadForm
        form = PositionWorkloadForm(instance=workload)
        return self._render(request, workload, form)

    def post(self, request, pk):
        workload = get_object_or_404(PositionWorkload.objects.select_related('position', 'academic_year'), pk=pk)
        from .forms import PositionWorkloadForm
        form = PositionWorkloadForm(request.POST, instance=workload)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Нормы для должности «{workload.position}» ({workload.academic_year}) обновлены.'
            )
            return redirect('core:workload_list')
        return self._render(request, workload, form)

    def _render(self, request, workload, form):
        from django.shortcuts import render
        return render(request, 'core/workload_form.html', {
            'workload': workload,
            'form': form,
        })

# СПРАВОЧНИК ВИДОВ РАБОТ

class WorkTypeListView(AdminRequiredMixin, ListView):
    """Список всех видов работ, сгруппированных по категориям."""
    model = WorkType
    template_name = 'core/worktype_list.html'
    context_object_name = 'work_types'

    def get_queryset(self):
        return WorkType.objects.select_related('category').order_by(
            'category__name', 'name'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Группируем по категориям для удобного отображения
        grouped = {}
        for wt in context['work_types']:
            grouped.setdefault(wt.category, []).append(wt)
        context['grouped_work_types'] = grouped
        context['total_count'] = WorkType.objects.count()
        context['active_count'] = WorkType.objects.filter(is_active=True).count()
        return context


class WorkTypeCreateView(AdminRequiredMixin, CreateView):
    """Создание нового вида работы."""
    model = WorkType
    form_class = WorkTypeForm
    template_name = 'core/worktype_form.html'
    success_url = reverse_lazy('core:worktype_list')

    def form_valid(self, form):
        messages.success(
            self.request,
            f'Вид работы «{form.instance.name}» добавлен в справочник.'
        )
        return super().form_valid(form)


class WorkTypeEditView(AdminRequiredMixin, UpdateView):
    """Редактирование вида работы."""
    model = WorkType
    form_class = WorkTypeForm
    template_name = 'core/worktype_form.html'
    success_url = reverse_lazy('core:worktype_list')

    def form_valid(self, form):
        messages.success(
            self.request,
            f'Вид работы «{form.instance.name}» обновлён.'
        )
        return super().form_valid(form)


class WorkTypeToggleActiveView(AdminRequiredMixin, View):
    """Активация / деактивация вида работы."""

    def post(self, request, pk):
        wt = get_object_or_404(WorkType, pk=pk)
        wt.is_active = not wt.is_active
        wt.save()
        if wt.is_active:
            messages.success(request, f'Вид работы «{wt.name}» активирован.')
        else:
            messages.warning(request, f'Вид работы «{wt.name}» деактивирован.')
        return redirect('core:worktype_list')

# НАСТРОЙКИ ВЫГРУЗКИ

class ExportSettingsView(AdminRequiredMixin, View):
            """
            Страница настроек выгрузки индивидуального плана в Word.
            """

            def get(self, request):
                active_year = AcademicYear.objects.filter(is_active=True).first()
                if not active_year:
                    messages.warning(request, 'Нет активного учебного года. Сначала активируйте год.')
                    return redirect('core:year_list')
                settings_obj, _ = ExportSettings.objects.get_or_create(academic_year=active_year)
                form = ExportSettingsForm(instance=settings_obj)
                return render(request, 'core/export_settings.html', {
                    'form': form,
                    'active_year': active_year,
                    'settings_obj': settings_obj,
                })

            def post(self, request):
                active_year = AcademicYear.objects.filter(is_active=True).first()
                if not active_year:
                    messages.warning(request, 'Нет активного учебного года.')
                    return redirect('core:year_list')
                settings_obj, _ = ExportSettings.objects.get_or_create(academic_year=active_year)
                form = ExportSettingsForm(request.POST, instance=settings_obj)
                if form.is_valid():
                    form.save()
                    messages.success(request, 'Настройки выгрузки сохранены.')
                    return redirect('core:export_settings')
                return render(request, 'core/export_settings.html', {
                    'form': form,
                    'active_year': active_year,
                    'settings_obj': settings_obj,
                })