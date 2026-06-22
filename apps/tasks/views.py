from django.views.generic import TemplateView, ListView, CreateView, UpdateView, View
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError
from decimal import Decimal


from apps.accounts.mixins import (
    HeadRequiredMixin, TeacherRequiredMixin, AdminRequiredMixin,
)
from apps.accounts.models import User, TeacherPosition
from apps.core.models import AcademicYear, TaskCategory
from apps.tasks.models import Task
from apps.tasks.forms import TaskForm, TeacherTaskForm, PendingTaskDecisionForm
from apps.tasks.services import (
    get_department_summary, get_department_summary_grouped, validate_task_hours,
    approve_task, start_task, complete_task, withdraw_completion,
    get_position_workload_stats, _get_active_position,
    submit_pending_task,
    get_pending_approval_count, get_pending_approval_tasks,
    get_pending_task_position_forecasts,
    approve_pending_task, decline_pending_task,
    delete_declined_task, delete_assigned_task,
)
from apps.accounts.utils import get_current_position, get_user_positions
import json
from django.db.models import Q

def _attach_teaching_load_context(context, position):
    """
    Дописывает в контекст переменные для блока «Учебная работа (первая половина дня)»:
      - teaching_load_grouped: список словарей {semester, items, total}
      - teaching_load_total: общая сумма часов
      - teaching_load_imported_at: дата последнего импорта (или None)

    Если позиция None или у неё нет строк нагрузки —
    teaching_load_grouped будет пустым списком и блок не отрисуется.
    """
    from decimal import Decimal

    context['teaching_load_grouped'] = []
    context['teaching_load_total'] = Decimal('0')
    context['teaching_load_imported_at'] = None

    if position is None:
        return

    items = list(
        position.teaching_load
        .select_related('activity_type')
        .order_by('semester', 'period_label', 'row_num', 'discipline', 'activity_type__sort_order')
    )
    if not items:
        return

    # Группируем по семестру с подытогом
    grouped = []
    current_label = None
    current_bucket = None
    total = Decimal('0')
    for it in items:
        label = it.period_label or f'{it.semester}-й семестр'
        if label != current_label:
            current_bucket = {
                'semester': it.semester,
                'period_label': label,
                'items': [],
                'total': Decimal('0'),
            }
            grouped.append(current_bucket)
            current_label = label
        current_bucket['items'].append(it)
        current_bucket['total'] += it.hours
        total += it.hours

    context['teaching_load_grouped'] = grouped
    context['teaching_load_total'] = total
    context['teaching_load_imported_at'] = position.teaching_load_imported_at

def _build_work_types_dict():
    """Словарь видов работ {category_id_str: [{id, name, max_hours, unit}]} для JS."""
    from apps.core.models import WorkType
    result = {}
    for wt in WorkType.objects.filter(is_active=True).select_related('category'):
        key = str(wt.category_id)
        result.setdefault(key, []).append({
            'id': wt.pk,
            'name': wt.name,
            'max_hours': wt.max_hours,
            'unit': wt.unit_description,
            'is_per_unit': wt.is_per_unit,
        })
    for items in result.values():
        items.sort(key=lambda x: x['name'].lower())
    return result


def _build_categories_code_map_json():
    """JSON-строка {category_id: category_code} для JS — нужна для data-code на <option>."""
    from apps.core.models import TaskCategory
    cats = TaskCategory.objects.filter(is_active=True, is_archived=False).only('id', 'code')
    return json.dumps({str(cat.pk): cat.code for cat in cats}, ensure_ascii=False)


def _build_workload_data(position, editing_task=None):
    """
    Построить словарь workload_data для JS live-подсказок.
    editing_task передаётся при редактировании — JS вычитает его часы
    из текущих сумм, чтобы не было двойного счёта.
    """
    stats = get_position_workload_stats(position)
    data = {
        'max_total_hours': stats['max_total_hours'],
        'teaching_planned': float(stats['teaching_planned']),
        'tasks_planned': float(stats['total_planned'] - stats['teaching_planned']),
        'total_planned': float(stats['total_planned']),
        'second_half_hours': (
            float(stats['second_half_hours'])
            if stats['second_half_hours'] is not None else None
        ),
        'by_category': {
            row['category'].code: {
                'planned': float(row['planned']),
                'min_hours': (float(row['min_hours'])
                              if row['min_hours'] is not None else None),
                'max_hours': (float(row['max_hours'])
                              if row['max_hours'] is not None else None),
                'min_percent': (float(row['min_percent'])
                                if row['min_percent'] is not None else None),
                'max_percent': (float(row['max_percent'])
                                if row['max_percent'] is not None else None),
            }
            for row in stats['by_category']
        },
        'editing_task': None,
    }
    if editing_task is not None:
        data['editing_task'] = {
            'planned_hours': float(editing_task.planned_hours),
            'category_code': editing_task.category.code if editing_task.category else None,
        }
    return data


def _build_workload_by_position_json():
    """
    JSON-строка {position_id: workload_data} для всех не-почасовых позиций
    активного года. Используется в форме заведующего (TaskCreateView/TaskEditView).
    """
    from apps.accounts.models import TeacherPosition
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if active_year is None:
        return json.dumps({}, ensure_ascii=False)
    positions = TeacherPosition.objects.filter(
        academic_year=active_year,
        is_active=True,
        user__is_active=True,
        user__role='teacher',
    ).exclude(
        employment_type='HOURLY',
    ).select_related('user', 'position', 'academic_year')
    result = {str(pos.pk): _build_workload_data(pos) for pos in positions}
    return json.dumps(result, ensure_ascii=False)


# === Views заведующего ===

class HeadDashboardView(HeadRequiredMixin, TemplateView):
    template_name = 'tasks/head_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        active_year = AcademicYear.objects.filter(is_active=True).first()
        context['active_year'] = active_year

        if not active_year:
            return context

        all_tasks = Task.objects.filter(academic_year=active_year)

        context['count_total'] = all_tasks.count()
        context['count_pending'] = all_tasks.filter(status=Task.STATUS_COMPLETED).count()
        context['count_in_progress'] = all_tasks.filter(status=Task.STATUS_IN_PROGRESS).count()
        context['count_approved'] = all_tasks.filter(status=Task.STATUS_APPROVED).count()

        today = timezone.now().date()
        context['count_overdue'] = all_tasks.filter(
            end_date__lt=today
        ).exclude(
            status__in=[Task.STATUS_APPROVED]
        ).count()

        context['tasks_pending'] = (
            all_tasks
            .filter(status=Task.STATUS_COMPLETED)
            .select_related('assignee__user', 'assignee__position', 'category')
            .order_by('updated_at')[:10]
        )

        # --- Внеплановые задачи на утверждение ---
        context['count_pending_approval'] = get_pending_approval_count(
            academic_year=active_year
        )
        context['tasks_pending_approval'] = get_pending_approval_tasks(
            academic_year=active_year, limit=10
        )

        context['teachers_summary'] = get_department_summary(active_year)

        return context


class TaskListView(HeadRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 25

    def get_queryset(self):
        queryset = Task.objects.select_related(
            'assignee__user', 'assignee__position', 'category', 'academic_year',
            'work_type',
        ).order_by('-created_at')

        year_id = self.request.GET.get('year')
        if year_id:
            queryset = queryset.filter(academic_year_id=year_id)
        else:
            active_year = AcademicYear.objects.filter(is_active=True).first()
            if active_year:
                queryset = queryset.filter(academic_year=active_year)

        assignee_user_id = self.request.GET.get('assignee')
        if assignee_user_id:
            queryset = queryset.filter(assignee__user_id=assignee_user_id)

        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        status = self.request.GET.get('status')
        if status and status in dict(Task.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        else:
            # По умолчанию declined-задачи скрываются из общего списка.
            # Они доступны в разделе «Утверждение задач → Не утверждены»
            # либо явно через фильтр status=declined.
            queryset = queryset.exclude(status=Task.STATUS_DECLINED)

        task_type = self.request.GET.get('task_type')
        if task_type and task_type in dict(Task.TYPE_CHOICES):
            queryset = queryset.filter(task_type=task_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['all_years'] = AcademicYear.objects.order_by('-start_date')
        context['all_teachers'] = User.objects.filter(
            role=User.ROLE_TEACHER, is_active=True
        ).order_by('full_name')
        context['all_categories'] = TaskCategory.objects.filter(is_active=True).order_by('name')
        context['status_choices'] = [
            (code, 'На проверке' if code == Task.STATUS_COMPLETED else label)
            for code, label in Task.STATUS_CHOICES
        ]
        context['type_choices'] = Task.TYPE_CHOICES
        context['current_year'] = self.request.GET.get('year', '')
        context['current_assignee'] = self.request.GET.get('assignee', '')
        context['current_category'] = self.request.GET.get('category', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_task_type'] = self.request.GET.get('task_type', '')
        context['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        context['today'] = timezone.now().date()

        year_id = self.request.GET.get('year')
        if year_id:
            selected_year = AcademicYear.objects.filter(pk=year_id).first()
            context['is_archive_view'] = selected_year.is_archived if selected_year else False
        else:
            context['is_archive_view'] = False

        return context

class PendingApprovalListView(HeadRequiredMixin, ListView):
    """
    Список внеплановых задач для заведующего.
    Архивные годы исключены — внеплановые задачи не должны висеть в архиве.
    Доступны фильтры: преподаватель, категория.
    """
    model = Task
    template_name = 'tasks/pending_approval_list.html'
    context_object_name = 'tasks'
    paginate_by = 25

    VIEW_PENDING = 'pending'
    VIEW_DECLINED = 'declined'

    def _get_view_mode(self):
        """Возвращает 'pending' (по умолчанию) или 'declined'."""
        mode = self.request.GET.get('view', self.VIEW_PENDING)
        if mode == self.VIEW_DECLINED:
            return self.VIEW_DECLINED
        return self.VIEW_PENDING

    def _get_status_for_mode(self, mode):
        if mode == self.VIEW_DECLINED:
            return Task.STATUS_DECLINED
        return Task.STATUS_PENDING_APPROVAL

    def get_queryset(self):
        active_year = AcademicYear.objects.filter(is_active=True).first()
        if active_year is None:
            return Task.objects.none()

        mode = self._get_view_mode()
        target_status = self._get_status_for_mode(mode)

        queryset = Task.objects.filter(
            status=target_status,
            academic_year=active_year,
        ).select_related(
            'assignee__user', 'assignee__position',
            'category', 'academic_year', 'creator',
        )

        # Для declined сортируем по дате обновления (когда отклонили),
        # для pending — по дате создания (как раньше).
        if mode == self.VIEW_DECLINED:
            queryset = queryset.order_by('-updated_at')
        else:
            queryset = queryset.order_by('-created_at')

        # Фильтр по преподавателю
        assignee_user_id = self.request.GET.get('assignee')
        if assignee_user_id:
            queryset = queryset.filter(assignee__user_id=assignee_user_id)

        # Фильтр по категории
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_year = AcademicYear.objects.filter(is_active=True).first()
        context['active_year'] = active_year

        mode = self._get_view_mode()
        context['view_mode'] = mode
        context['is_pending_view'] = (mode == self.VIEW_PENDING)
        context['is_declined_view'] = (mode == self.VIEW_DECLINED)

        # Счётчики для переключателя — сколько задач в каждом режиме
        if active_year:
            context['count_pending_total'] = Task.objects.filter(
                status=Task.STATUS_PENDING_APPROVAL,
                academic_year=active_year,
            ).count()
            context['count_declined_total'] = Task.objects.filter(
                status=Task.STATUS_DECLINED,
                academic_year=active_year,
            ).count()
        else:
            context['count_pending_total'] = 0
            context['count_declined_total'] = 0

        # Списки для фильтров (только преподаватели, у которых есть задачи
        # в текущем режиме отображения)
        if active_year:
            target_status = self._get_status_for_mode(mode)
            teacher_ids = Task.objects.filter(
                status=target_status,
                academic_year=active_year,
            ).values_list('assignee__user_id', flat=True).distinct()
            context['all_teachers'] = User.objects.filter(
                pk__in=teacher_ids
            ).order_by('full_name', 'username')
        else:
            context['all_teachers'] = User.objects.none()

        # Все категории, кроме архивных
        context['all_categories'] = TaskCategory.objects.filter(
            is_archived=False
        ).order_by('name')

        # Текущие значения фильтров — для восстановления выбора
        context['current_assignee'] = self.request.GET.get('assignee', '')
        context['current_category'] = self.request.GET.get('category', '')

        return context

class DeclinedTaskDeleteView(HeadRequiredMixin, View):
    """
    Окончательное удаление declined-задачи из БД.
    """

    http_method_names = ['post']

    def post(self, request, pk):
        task = get_object_or_404(
            Task.objects.select_related('assignee__user', 'category'),
            pk=pk,
        )

        if task.status != Task.STATUS_DECLINED:
            messages.error(
                request,
                'Окончательно удалить можно только задачу '
                'в статусе «Не утверждена».'
            )
            return redirect('tasks:pending_approval_list')


        task_title = task.title
        teacher_name = task.assignee.user.full_name or task.assignee.user.username

        try:
            delete_declined_task(task)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return redirect('tasks:pending_approval_list')

        messages.success(
            request,
            f'Задача «{task_title}» преподавателя {teacher_name} '
            f'удалена окончательно.'
        )
        # Возвращаем на ту же страницу declined-задач
        return redirect(
            f"{reverse_lazy('tasks:pending_approval_list')}?view=declined"
        )

class TaskDeleteView(HeadRequiredMixin, View):
    """Удаление задачи в статусе «Назначена» (assigned). Только POST."""

    http_method_names = ['post']

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        try:
            title = task.title
            delete_assigned_task(task)
            messages.success(request, f'Задача «{title}» удалена.')
        except Exception as e:
            messages.error(request, str(e))
        return redirect('tasks:task_list')


class PendingTaskReviewView(HeadRequiredMixin, View):
    """
    Страница ревью внеплановой задачи (GET — просмотр, POST — решение).
    """

    template_name = 'tasks/pending_task_review.html'

    def _get_pending_task(self, pk):
        task = get_object_or_404(
            Task.objects.select_related(
                'assignee__user', 'assignee__position',
                'category', 'academic_year', 'creator',
            ),
            pk=pk,
        )
        if task.status != Task.STATUS_PENDING_APPROVAL:
            raise Http404('Задача не находится на утверждении.')
        return task

    def _render(self, request, task, form):
        forecasts = get_pending_task_position_forecasts(task)
        # Прогноз сохранённой текущей позиции (для подтверждения превышений)
        current_warnings = {}
        for f in forecasts:
            if f['is_current']:
                current_warnings = f['warnings']
                break
        has_any_position = len(forecasts) > 0
        return render(request, self.template_name, {
            'task': task,
            'forecasts': forecasts,
            'multiple_positions': len(forecasts) > 1,
            'has_any_position': has_any_position,
            'form': form,
            'current_warnings': current_warnings,
        })

    def get(self, request, pk):
        task = self._get_pending_task(pk)
        form = PendingTaskDecisionForm(task=task)
        return self._render(request, task, form)

    def post(self, request, pk):
        task = self._get_pending_task(pk)
        form = PendingTaskDecisionForm(request.POST, task=task)

        if not form.is_valid():
            return self._render(request, task, form)

        action = form.cleaned_data['action']

        if action == PendingTaskDecisionForm.ACTION_APPROVE:
            target_position = form.cleaned_data.get('target_position')
            planned_hours = form.cleaned_data.get('planned_hours')


            preview_task = Task.objects.select_related(
                'assignee', 'category', 'academic_year'
            ).get(pk=task.pk)
            if target_position is not None:
                preview_task.assignee = target_position
            if planned_hours is not None:
                preview_task.planned_hours = planned_hours

            warnings = validate_task_hours(preview_task)
            if warnings and not request.POST.get('confirm_overload'):
                # Возвращаем форму с предупреждениями — пользователь должен
                # явно подтвердить чекбокс «Подтвердить превышение лимитов».
                forecasts = get_pending_task_position_forecasts(task)
                return render(request, self.template_name, {
                    'task': task,
                    'forecasts': forecasts,
                    'multiple_positions': len(forecasts) > 1,
                    'has_any_position': len(forecasts) > 0,
                    'form': form,
                    'current_warnings': warnings,
                    'workload_warnings': warnings,
                })

            try:
                approve_pending_task(
                    task,
                    target_position=target_position,
                    planned_hours=planned_hours,
                )
            except ValidationError as exc:
                # На случай  некорректных данных — выводим как ошибки формы.
                for msg in exc.messages:
                    form.add_error(None, msg)
                return self._render(request, task, form)

            messages.success(
                request,
                f'Задача «{task.title}» одобрена и назначена позиции '
                f'«{task.assignee.display_label}».'
            )
            return redirect('tasks:pending_approval_list')


        reason = form.cleaned_data['reason']
        try:
            decline_pending_task(task, reason)
        except ValidationError as exc:
            for msg in exc.messages:
                form.add_error(None, msg)
            return self._render(request, task, form)

        messages.success(
            request,
            f'Задача «{task.title}» отклонена. '
            f'Преподаватель увидит её в статусе «Не утверждена».'
        )
        return redirect('tasks:pending_approval_list')

class TaskCreateView(HeadRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('tasks:task_list')

    def get_initial(self):
        initial = super().get_initial()
        assignee_id = self.request.GET.get('assignee')
        if assignee_id:
            initial['assignee'] = assignee_id
        return initial

    def post(self, request, *args, **kwargs):
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.creator = request.user
            active_year = AcademicYear.objects.filter(is_active=True).first()
            if active_year is None:
                messages.error(request, 'Нет активного учебного года. Обратитесь к администратору.')
                return redirect('tasks:task_list')
            task.academic_year = active_year
            warnings = validate_task_hours(task)
            if warnings and not request.POST.get('confirm_overload'):
                return render(request, self.template_name, {
                    'form': form,
                    'page_title': 'Новая задача',
                    'button_text': 'Создать',
                    'workload_warnings': warnings,
                    'active_year': active_year,
                    'workload_by_position_json': _build_workload_by_position_json(),
                    'categories_code_map_json': _build_categories_code_map_json(),
                    'work_types_by_category_json': json.dumps(
                        _build_work_types_dict(), ensure_ascii=False,
                    ),
                })
            task.save()
            messages.success(
                request,
                f'Задача «{task.title}» создана и назначена позиции '
                f'«{task.assignee.display_label}» преподавателя '
                f'{task.assignee.user.full_name or task.assignee.user.username}.'
            )
            return redirect(self.success_url)
        return render(request, self.template_name, {
            'form': form,
            'page_title': 'Новая задача',
            'button_text': 'Создать',
            'workload_warnings': {},
            'active_year': AcademicYear.objects.filter(is_active=True).first(),
            'workload_by_position_json': _build_workload_by_position_json(),
            'categories_code_map_json': _build_categories_code_map_json(),
            'work_types_by_category_json': json.dumps(
                _build_work_types_dict(), ensure_ascii=False,
            ),
        })

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Новая задача'
        context['button_text'] = 'Создать'
        context['workload_warnings'] = {}
        context['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        context['workload_by_position_json'] = _build_workload_by_position_json()
        context['categories_code_map_json'] = _build_categories_code_map_json()
        context['work_types_by_category_json'] = json.dumps(
            _build_work_types_dict(), ensure_ascii=False,
        )
        return context


class TaskEditView(HeadRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('tasks:task_list')

    def get_object(self, queryset=None):
        return get_object_or_404(Task, pk=self.kwargs['pk'])

    def dispatch(self, request, *args, **kwargs):
        task = get_object_or_404(Task, pk=self.kwargs['pk'])
        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя редактировать задачи архивного учебного года.')
            return redirect('tasks:task_list')
        if not task.is_editable:
            messages.error(
                request,
                f'Задача в статусе «{task.get_status_display()}» не может быть отредактирована.'
            )
            return redirect('tasks:task_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        task = form.save(commit=False)
        warnings = validate_task_hours(task)
        if warnings and not self.request.POST.get('confirm_overload'):
            return render(self.request, self.template_name, {
                'form': form,
                'page_title': f'Редактирование: {task.title}',
                'button_text': 'Сохранить',
                'workload_warnings': warnings,
                'object': task,
                'active_year': task.academic_year,
                'is_edit': True,
                'workload_by_position_json': _build_workload_by_position_json(),
                'categories_code_map_json': _build_categories_code_map_json(),
                'work_types_by_category_json': json.dumps(
                    _build_work_types_dict(), ensure_ascii=False,
                ),
                'editing_task_json': json.dumps(
                    {'planned_hours': float(self.object.planned_hours),
                     'category_code': self.object.category.code if self.object.category else None,
                     'assignee_id': str(self.object.assignee_id)},
                    ensure_ascii=False,
                ),
            })
        task.save()
        messages.success(self.request, f'Задача «{task.title}» обновлена.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Редактирование: {self.object.title}'
        context['button_text'] = 'Сохранить'
        context['workload_warnings'] = {}
        context['is_edit'] = True
        context['active_year'] = self.object.academic_year
        context['workload_by_position_json'] = _build_workload_by_position_json()
        context['categories_code_map_json'] = _build_categories_code_map_json()
        context['work_types_by_category_json'] = json.dumps(
            _build_work_types_dict(), ensure_ascii=False,
        )
        context['editing_task_json'] = json.dumps(
            {'planned_hours': float(self.object.planned_hours),
             'category_code': self.object.category.code if self.object.category else None,
             'assignee_id': str(self.object.assignee_id)},
            ensure_ascii=False,
        )
        return context


class TaskReviewView(HeadRequiredMixin, View):

    def get(self, request, pk):
        task = get_object_or_404(
            Task.objects.select_related(
                'assignee__user', 'assignee__position', 'category', 'academic_year'
            ),
            pk=pk,
        )
        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя проверять задачи архивного учебного года.')
            return redirect('tasks:task_list')
        if task.status != Task.STATUS_COMPLETED:
            messages.error(request, 'Эту задачу нельзя проверить — она не в статусе «Выполнена».')
            return redirect('tasks:task_list')
        return render(request, 'tasks/task_review.html', {'task': task})

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)

        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя проверять задачи архивного учебного года.')
            return redirect('tasks:task_list')

        action = request.POST.get('action')

        if action == 'approve':
            try:
                approve_task(task)
                messages.success(request, f'Задача «{task.title}» подтверждена.')
            except Exception as e:
                messages.error(request, str(e))

        return redirect('tasks:task_list')


class TeacherCardView(HeadRequiredMixin, TemplateView):
    template_name = 'tasks/teacher_card.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        teacher = get_object_or_404(
            User.objects.select_related('department'),
            pk=self.kwargs['pk'],
            role=User.ROLE_TEACHER,
        )
        context['teacher'] = teacher

        year_id = self.request.GET.get('year')
        if year_id:
            academic_year = get_object_or_404(AcademicYear, pk=year_id)
        else:
            academic_year = AcademicYear.objects.filter(is_active=True).first()

        context['academic_year'] = academic_year
        context['all_years'] = AcademicYear.objects.order_by('-start_date')
        context['is_archive_view'] = academic_year.is_archived if academic_year else False

        if academic_year:
            positions = TeacherPosition.objects.filter(
                user=teacher, academic_year=academic_year, is_active=True,
            ).select_related('position').order_by('employment_type')
            context['positions'] = positions

            status_filter = self.request.GET.get('status')

            position_blocks = []
            for pos in positions:
                pos_stats = get_position_workload_stats(pos)

                tl_ctx = {}
                _attach_teaching_load_context(tl_ctx, pos)

                pos_tasks = Task.objects.filter(
                    assignee=pos, academic_year=academic_year
                ).select_related(
                    'category', 'assignee__position', 'assignee__user', 'work_type'
                ).order_by('-created_at')
                if status_filter and status_filter in dict(Task.STATUS_CHOICES):
                    pos_tasks = pos_tasks.filter(status=status_filter)
                else:

                    pos_tasks = pos_tasks.exclude(status=Task.STATUS_DECLINED)

                position_blocks.append({
                    'position': pos,
                    'stats': pos_stats,
                    'teaching_load_grouped': tl_ctx.get('teaching_load_grouped'),
                    'teaching_load_total': tl_ctx.get('teaching_load_total'),
                    'teaching_load_imported_at': tl_ctx.get('teaching_load_imported_at'),
                    'tasks': pos_tasks,
                    'tab_id': f'pos-{pos.pk}',
                })

            context['position_blocks'] = position_blocks
            context['has_multiple_positions'] = len(position_blocks) > 1

            context['status_choices'] = [
                (code, 'На проверке' if code == Task.STATUS_COMPLETED else label)
                for code, label in Task.STATUS_CHOICES
            ]
            context['current_status'] = self.request.GET.get('status', '')

        return context


class TeacherListView(HeadRequiredMixin, ListView):
    model = User
    template_name = 'tasks/teacher_list.html'
    context_object_name = 'teachers'

    def get_queryset(self):
        # Список нужен только как заглушка для ListView;
        # реальные данные собирает get_department_summary_grouped().
        return User.objects.filter(
            role=User.ROLE_TEACHER,
            is_active=True,
        ).select_related('department').order_by('full_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        year_id = self.request.GET.get('year')
        if year_id:
            academic_year = AcademicYear.objects.filter(pk=year_id).first()
        else:
            academic_year = AcademicYear.objects.filter(is_active=True).first()

        context['academic_year'] = academic_year
        context['active_year'] = academic_year
        context['all_years'] = AcademicYear.objects.order_by('-start_date')
        context['is_archive_view'] = academic_year.is_archived if academic_year else False

        if academic_year:
            context['teachers_grouped'] = get_department_summary_grouped(academic_year)
        else:
            context['teachers_grouped'] = []
        return context


class CategoryLimitsAnalyticsView(HeadRequiredMixin, TemplateView):
    template_name = 'tasks/category_limits_analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        year_id = self.request.GET.get('year')
        if year_id:
            academic_year = get_object_or_404(AcademicYear, pk=year_id)
        else:
            academic_year = AcademicYear.objects.filter(is_active=True).first()

        context['academic_year'] = academic_year
        context['all_years'] = AcademicYear.objects.order_by('-start_date')
        context['is_archive_view'] = academic_year.is_archived if academic_year else False

        if not academic_year:
            return context

        from apps.accounts.models import TeacherPosition
        from .services import get_position_workload_stats

        positions = TeacherPosition.objects.filter(
            academic_year=academic_year,
            is_active=True,
        ).exclude(
            employment_type='HOURLY',
        ).select_related('user', 'position').order_by('user__full_name', 'position__name')

        show_below_min = self.request.GET.get('show_below_min') == '1'

        teachers_data = []
        total_violations = 0
        total_below_min = 0
        total_overloads = 0

        for tp in positions:
            stats = get_position_workload_stats(tp)
            violations = []
            below_min_list = []
            overload_items = []

            for cat_row in stats['by_category']:
                if cat_row['is_above_max']:
                    violations.append({
                        'category': cat_row['category'].name,
                        'planned': cat_row['planned'],
                        'max_hours': cat_row['max_hours'],
                        'max_percent': cat_row['max_percent'],
                        'regulation_point': cat_row['regulation_point'],
                    })
                if cat_row['is_below_min']:
                    below_min_list.append({
                        'category': cat_row['category'].name,
                        'planned': cat_row['planned'],
                        'min_hours': cat_row['min_hours'],
                        'min_percent': cat_row['min_percent'],
                        'regulation_point': cat_row['regulation_point'],
                    })

            # Превышение общего годового лимита (1550 × ставка)
            if stats['max_total_hours'] and stats['total_planned'] > stats['max_total_hours']:
                overload_items.append({
                    'kind': 'total',
                    'label': 'Общая нагрузка',
                    'planned': stats['total_planned'],
                    'limit': stats['max_total_hours'],
                    'excess': stats['total_planned'] - stats['max_total_hours'],
                })
            # Превышение учебной нагрузки (max_teaching_hours)
            if stats['max_teaching_hours'] and stats['teaching_planned'] > stats['max_teaching_hours']:
                overload_items.append({
                    'kind': 'teaching',
                    'label': 'Учебная нагрузка',
                    'planned': stats['teaching_planned'],
                    'limit': stats['max_teaching_hours'],
                    'excess': stats['teaching_planned'] - stats['max_teaching_hours'],
                })

            total_violations += len(violations)
            total_below_min += len(below_min_list)
            if overload_items:
                total_overloads += 1

            include_in_table = (
                bool(violations)
                or bool(overload_items)
                or (show_below_min and bool(below_min_list))
            )

            if include_in_table:
                teachers_data.append({
                    'position': tp,
                    'second_half_hours': stats['second_half_hours'],
                    'violations': violations,
                    'overloads': overload_items,
                    'below_min': below_min_list if show_below_min else [],
                    'stats': stats,
                })

        context['show_below_min'] = show_below_min
        context['teachers_data'] = teachers_data
        context['total_violations'] = total_violations
        context['total_below_min'] = total_below_min
        context['total_overloads'] = total_overloads
        context['total_positions'] = positions.count()
        context['positions_with_issues'] = len(teachers_data)

        return context


class CloseYearView(AdminRequiredMixin, View):

    def get(self, request):
        academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not academic_year:
            messages.error(request, 'Нет активного учебного года для закрытия.')
            return redirect('core:year_list')
        return render(request, 'tasks/close_year.html', self._build_context(academic_year))

    def post(self, request):
        academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not academic_year:
            messages.error(request, 'Нет активного учебного года для закрытия.')
            return redirect('core:year_list')

        academic_year.is_active = False
        academic_year.is_archived = True
        academic_year.save()

        messages.success(
            request,
            f'Учебный год «{academic_year.name}» закрыт и перемещён в архив.'
        )
        return redirect('core:year_list')

    def _build_context(self, academic_year):
        all_tasks = Task.objects.filter(academic_year=academic_year)

        total_tasks = all_tasks.count()
        approved_tasks = all_tasks.filter(status=Task.STATUS_APPROVED).count()
        completed_tasks = all_tasks.filter(status=Task.STATUS_COMPLETED).count()
        incomplete_tasks = all_tasks.exclude(status=Task.STATUS_APPROVED).count()

        incomplete_task_list = (
            all_tasks
            .exclude(status=Task.STATUS_APPROVED)
            .select_related('assignee__user', 'category')
            .order_by('assignee__user__full_name', 'title')[:10]
        )

        approved_percent = 0
        if total_tasks > 0:
            approved_percent = int(approved_tasks / total_tasks * 100)

        return {
            'academic_year': academic_year,
            'total_tasks': total_tasks,
            'approved_tasks': approved_tasks,
            'completed_tasks': completed_tasks,
            'incomplete_tasks': incomplete_tasks,
            'incomplete_task_list': incomplete_task_list,
            'approved_percent': approved_percent,
        }


#Views преподавателя

class TeacherDashboardView(TeacherRequiredMixin, TemplateView):
    template_name = 'tasks/teacher_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        active_year = AcademicYear.objects.filter(is_active=True).first()
        context['active_year'] = active_year

        if not active_year:
            return context

        # Берём текущую позицию из сессии
        primary_position = get_current_position(self.request, academic_year=active_year)
        context['primary_position'] = primary_position

        stats = get_position_workload_stats(primary_position)
        context['stats'] = stats

        if primary_position is None:
            context['count_total'] = 0
            context['count_assigned'] = 0
            context['count_in_progress'] = 0
            context['count_completed'] = 0
            context['count_approved'] = 0
            context['count_pending_approval'] = 0
            context['count_overdue'] = 0
            context['pending_approval_tasks'] = []
            context['upcoming_tasks'] = []
            context['today'] = timezone.now().date()
            return context

        all_tasks = Task.objects.filter(
            assignee=primary_position,
        ).select_related('category')

        context['count_total'] = all_tasks.count()
        context['count_assigned'] = all_tasks.filter(status=Task.STATUS_ASSIGNED).count()
        context['count_in_progress'] = all_tasks.filter(status=Task.STATUS_IN_PROGRESS).count()
        context['count_completed'] = all_tasks.filter(status=Task.STATUS_COMPLETED).count()
        context['count_approved'] = all_tasks.filter(status=Task.STATUS_APPROVED).count()
        context['count_pending_approval'] = all_tasks.filter(
            status=Task.STATUS_PENDING_APPROVAL
        ).count()

        context['pending_approval_tasks'] = (
            all_tasks
            .filter(status=Task.STATUS_PENDING_APPROVAL)
            .order_by('-created_at')[:5]
        )

        today = timezone.now().date()
        context['upcoming_tasks'] = (
            all_tasks
            .filter(status__in=[Task.STATUS_ASSIGNED, Task.STATUS_IN_PROGRESS])
            .order_by('end_date')[:5]
        )

        context['count_overdue'] = all_tasks.filter(
            end_date__lt=today,
        ).exclude(
            status__in=[Task.STATUS_APPROVED],
        ).count()

        context['today'] = today

        return context


class MyTasksView(TeacherRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/my_tasks.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        user = self.request.user

        academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not academic_year:
            self._academic_year = None
            self._current_position = None
            return Task.objects.none()

        self._academic_year = academic_year

        current = get_current_position(self.request, academic_year=academic_year)
        self._current_position = current
        if current is None:
            return Task.objects.none()

        queryset = Task.objects.filter(
            assignee=current,
        ).select_related('category', 'assignee__position', 'work_type').order_by('-created_at')

        status = self.request.GET.get('status')
        if status and status in dict(Task.STATUS_CHOICES):
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        academic_year = getattr(self, '_academic_year', None)
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_active=True).first()

        context['active_year'] = academic_year
        context['status_choices'] = Task.STATUS_CHOICES
        context['current_status'] = self.request.GET.get('status', '')
        context['today'] = timezone.now().date()
        context['filter_position'] = getattr(self, '_current_position', None)

        return context


class TaskStartView(TeacherRequiredMixin, View):

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, assignee__user=request.user)

        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя изменять задачи архивного учебного года.')
            return redirect('tasks:my_tasks')

        try:
            start_task(task)
            messages.success(request, f'Задача «{task.title}» взята в работу.')
        except Exception as e:
            messages.error(request, str(e))
        return redirect('tasks:my_tasks')


class TaskCompleteView(TeacherRequiredMixin, View):

    def get(self, request, pk):
        task = get_object_or_404(
            Task.objects.select_related('category', 'academic_year'),
            pk=pk, assignee__user=request.user,
        )
        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя изменять задачи архивного учебного года.')
            return redirect('tasks:my_tasks')
        if task.status != Task.STATUS_IN_PROGRESS:
            messages.error(request, 'Эту задачу нельзя завершить — она не в статусе «В работе».')
            return redirect('tasks:my_tasks')
        return render(request, 'tasks/task_complete.html', {'task': task})

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, assignee__user=request.user)

        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя изменять задачи архивного учебного года.')
            return redirect('tasks:my_tasks')

        actual_hours_str = request.POST.get('actual_hours', '').strip()
        result = request.POST.get('result', '').strip()

        if not actual_hours_str:
            messages.error(request, 'Укажите фактические часы.')
            return render(request, 'tasks/task_complete.html', {
                'task': task,
                'entered_hours': actual_hours_str,
                'entered_result': result,
            })

        if not result:
            messages.error(
                request,
                'Заполните поле «Результат» — этот текст войдёт в '
                'итоговый отчёт Word.'
            )
            return render(request, 'tasks/task_complete.html', {
                'task': task,
                'entered_hours': actual_hours_str,
                'entered_result': result,
            })

        try:
            actual_hours = Decimal(actual_hours_str)
        except Exception:
            messages.error(request, 'Некорректное значение фактических часов.')
            return render(request, 'tasks/task_complete.html', {
                'task': task,
                'entered_hours': actual_hours_str,
                'entered_result': result,
            })

        try:
            complete_task(task, actual_hours, result)
            messages.success(request, f'Задача «{task.title}» отправлена на проверку.')
        except Exception as e:
            messages.error(request, str(e))
            return render(request, 'tasks/task_complete.html', {
                'task': task,
                'entered_hours': actual_hours_str,
                'entered_result': result,
            })

        return redirect('tasks:my_tasks')


class TaskWithdrawView(TeacherRequiredMixin, View):

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)

        if task.assignee.user != request.user or task.status != Task.STATUS_COMPLETED:
            messages.error(request, 'Отозвать можно только свою задачу в статусе «На проверке».')
            return redirect('tasks:my_tasks')

        try:
            withdraw_completion(task)
            messages.success(
                request,
                f'Задача «{task.title}» отозвана на редактирование.'
            )
        except Exception as e:
            messages.error(request, str(e))
        return redirect('tasks:my_tasks')


class MyWorkloadView(TeacherRequiredMixin, TemplateView):
    template_name = 'tasks/my_workload.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        academic_year = AcademicYear.objects.filter(is_active=True).first()
        context['active_year'] = academic_year

        if not academic_year:
            return context

        primary_position = get_current_position(self.request, academic_year=academic_year)

        context['primary_position'] = primary_position
        context['stats'] = get_position_workload_stats(primary_position)
        _attach_teaching_load_context(context, primary_position)
        context['teacher'] = user

        return context

# --- Создание внеплановой задачи преподавателем ---

class TeacherCreateTaskView(TeacherRequiredMixin, View):
    """
    Создание внеплановой задачи преподавателем.

    """

    template_name = 'tasks/teacher_task_create.html'

    def _get_position_or_redirect(self, request):

        active_year = AcademicYear.objects.filter(is_active=True).first()
        if not active_year:
            messages.error(request, 'Нет активного учебного года. Обратитесь к администратору.')
            return None, redirect('tasks:teacher_dashboard')

        position = get_current_position(request, academic_year=active_year)
        if position is None:
            messages.error(
                request,
                'У вас нет активной позиции в текущем году. '
                'Обратитесь к администратору.'
            )
            return None, redirect('tasks:teacher_dashboard')

        if position.is_hourly:
            messages.error(
                request,
                'У почасовой позиции нет второй половины дня — '
                'внеплановые задачи в неё не создаются. '
                'Переключитесь на другую позицию в шапке («Я работаю как:»).'
            )
            return None, redirect('tasks:teacher_dashboard')

        if position.academic_year.is_archived:
            messages.error(
                request,
                'Нельзя создавать задачи в архивный учебный год.'
            )
            return None, redirect('tasks:teacher_dashboard')

        return position, None

    def _build_context(self, request, position, form, editing_task=None):
        """Собрать контекст для шаблона."""
        active_year = position.academic_year
        positions_count = len(get_user_positions(request.user, active_year))
        return {
            'form': form,
            'teacher_position': position,
            'has_multiple_positions': positions_count > 1,
            'work_types_by_category_json': json.dumps(
                _build_work_types_dict(),
                ensure_ascii=False,
            ),
            'active_year': active_year,
            'workload_data_json': json.dumps(
                _build_workload_data(position, editing_task=editing_task),
                ensure_ascii=False,
            ),
            'categories_code_map_json': _build_categories_code_map_json(),
        }

    def get(self, request):
        position, redirect_response = self._get_position_or_redirect(request)
        if redirect_response is not None:
            return redirect_response

        form = TeacherTaskForm(teacher_position=position)
        return render(request, self.template_name, self._build_context(request, position, form))

    def post(self, request):
        position, redirect_response = self._get_position_or_redirect(request)
        if redirect_response is not None:
            return redirect_response

        form = TeacherTaskForm(request.POST, teacher_position=position)
        if not form.is_valid():
            return render(request, self.template_name, self._build_context(request, position, form))

        # Собираем объект задачи, но не сохраняем — сначала проставим
        # обязательные поля, которые отсутствуют в форме.
        task = form.save(commit=False)
        task.assignee = position
        task.academic_year = position.academic_year
        task.creator = request.user
        task.task_type = Task.TYPE_ADDITIONAL

        # work_type сохраняется автоматически через form.save(commit=False) — FK в модели (14.7).

        try:
            submit_pending_task(task)
        except Exception as e:
            messages.error(request, f'Не удалось создать задачу: {e}')
            return render(request, self.template_name, self._build_context(request, position, form))

        messages.success(
            request,
            f'Задача «{task.title}» отправлена заведующему на утверждение. '
            f'Вы увидите её в списке после одобрения.'
        )
        return redirect('tasks:my_tasks')

class TeacherEditPendingTaskView(TeacherRequiredMixin, View):
    """
    Редактирование внеплановой задачи преподавателем.
    """

    template_name = 'tasks/teacher_task_create.html'

    def _get_task_or_redirect(self, request, pk):
        """
        Загрузить задачу с проверками доступа.

        """
        task = get_object_or_404(
            Task.objects.select_related(
                'assignee__user', 'assignee__position', 'assignee__academic_year',
                'category', 'academic_year',
            ),
            pk=pk,
        )
        # Это должна быть моя задача.
        if task.assignee.user_id != request.user.id:
            messages.error(request, 'Эту задачу редактировать нельзя.')
            return None, redirect('tasks:my_tasks')

        if task.status != Task.STATUS_PENDING_APPROVAL:
            messages.error(
                request,
                'Редактировать можно только задачу, '
                'ожидающую утверждения. Эта уже обработана заведующим.'
            )
            return None, redirect('tasks:my_tasks')

        if task.academic_year.is_archived:
            messages.error(request, 'Нельзя редактировать задачи архивного года.')
            return None, redirect('tasks:my_tasks')

        return task, None

    def _build_context(self, request, task, form):
        active_year = task.assignee.academic_year
        positions_count = len(get_user_positions(request.user, active_year))
        return {
            'form': form,
            'teacher_position': task.assignee,
            'has_multiple_positions': positions_count > 1,
            'work_types_by_category_json': json.dumps(
                _build_work_types_dict(),
                ensure_ascii=False,
            ),
            'active_year': active_year,
            'is_edit': True,
            'task': task,
            'workload_data_json': json.dumps(
                _build_workload_data(task.assignee, editing_task=task),
                ensure_ascii=False,
            ),
            'categories_code_map_json': _build_categories_code_map_json(),
        }

    def get(self, request, pk):
        task, redirect_response = self._get_task_or_redirect(request, pk)
        if redirect_response is not None:
            return redirect_response

        form = TeacherTaskForm(instance=task, teacher_position=task.assignee)
        return render(request, self.template_name, self._build_context(request, task, form))

    def post(self, request, pk):
        task, redirect_response = self._get_task_or_redirect(request, pk)
        if redirect_response is not None:
            return redirect_response

        form = TeacherTaskForm(request.POST, instance=task, teacher_position=task.assignee)
        if not form.is_valid():
            return render(request, self.template_name, self._build_context(request, task, form))

        task = form.save(commit=False)
        # work_type обновлён через form.save(commit=False) — FK в модели (14.7).
        # Статус не меняем — задача остаётся в pending_approval.
        task.save()
        messages.success(request, f'Задача «{task.title}» обновлена.')
        return redirect('tasks:my_tasks')

# === Выгрузка Word ===

class ExportWordView(View):
    """
    Скачивание индивидуального плана в формате .docx.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, position_id):
        position = get_object_or_404(
            TeacherPosition.objects.select_related(
                'user', 'position', 'academic_year',
            ),
            pk=position_id,
        )

        # Проверка доступа: владелец ИЛИ завкаф ИЛИ админ
        user = request.user
        is_owner = (user.pk == position.user_id)
        is_head = (user.role == User.ROLE_HEAD)
        is_admin = (user.role == User.ROLE_ADMIN)

        if not (is_owner or is_head or is_admin):
            messages.error(request, 'У вас нет доступа к этому документу.')
            return redirect('accounts:login')

        from apps.tasks.word_export import generate_individual_plan

        buf = generate_individual_plan(position)

        last_name = (position.user.full_name or position.user.username).split()[0]
        if position.is_hourly:
            rate_str = 'почасовая'
        else:
            rate_map = {'1.00': 'ст.1', '0.75': 'ст.0,75', '0.50': 'ст.0,5', '0.25': 'ст.0,25'}
            rate_str = rate_map.get(str(position.rate), f'ст.{position.rate}')
        filename = f'{last_name}_{rate_str}.docx'

        from django.http import HttpResponse
        from urllib.parse import quote
        response = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        # ASCII-фоллбэк для старых браузеров + UTF-8 имя для новых (RFC 5987)
        encoded = quote(filename)
        response['Content-Disposition'] = (
            f"attachment; filename=\"plan.docx\"; "
            f"filename*=UTF-8''{encoded}"
        )
        return response

class ExportAllWordView(View):
    """
    Скачивание ZIP-архива индивидуальных планов всех позиций активного года.
    Доступ: администратор.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != User.ROLE_ADMIN:
            messages.error(request, 'У вас нет доступа к этой функции.')
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        active_year = AcademicYear.objects.filter(is_active=True).first()
        if not active_year:
            messages.error(request, 'Нет активного учебного года.')
            return redirect('accounts:user_list')

        positions = TeacherPosition.objects.filter(
            academic_year=active_year,
            is_active=True,
        ).select_related('user', 'position', 'academic_year').order_by(
            'user__full_name', 'employment_type',
        )

        if not positions.exists():
            messages.warning(request, 'Нет активных позиций для выгрузки.')
            return redirect('accounts:user_list')

        from apps.tasks.word_export import generate_individual_plan
        from django.http import HttpResponse
        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for pos in positions:
                buf = generate_individual_plan(pos)
                last_name = (pos.user.full_name or pos.user.username).split()[0]
                if pos.is_hourly:
                    rate_str = 'почасовая'
                else:
                    rate_map = {'1.00': 'ст.1', '0.75': 'ст.0,75', '0.50': 'ст.0,5', '0.25': 'ст.0,25'}
                    rate_str = rate_map.get(str(pos.rate), f'ст.{pos.rate}')
                doc_name = f'{last_name}_{rate_str}.docx'
                zf.writestr(doc_name, buf.getvalue())

        zip_buffer.seek(0)
        safe_year = active_year.name.replace(' ', '_').replace('–', '-').replace('/', '-')
        filename = f'Индивидуальные_планы_{safe_year}.zip'

        response = HttpResponse(
            zip_buffer.getvalue(),
            content_type='application/zip',
        )
        from urllib.parse import quote
        encoded = quote(filename)
        response['Content-Disposition'] = (
            f"attachment; filename=\"plans.zip\"; "
            f"filename*=UTF-8''{encoded}"
        )
        return response