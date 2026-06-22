from django import forms
from itertools import groupby
from django.core.exceptions import ValidationError
from decimal import Decimal


from apps.accounts.models import TeacherPosition
from apps.core.models import AcademicYear, TaskCategory
from .models import Task


class GroupedPositionSelect(forms.Select):
    """
    Кастомный виджет для поля assignee в TaskForm.
    Рендерит <select> с группировкой по ФИО пользователя:
    """

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._queryset = queryset

    def optgroups(self, name, value, attrs=None):
        groups = []
        has_selected = False
        index = 0

        # Пустой "Выберите..." вариант — без группы, первой строкой.
        empty_label = self.choices.field.empty_label if hasattr(self.choices, 'field') else '---------'
        subgroup = []
        subgroup.append(self.create_option(
            name=name, value='', label=empty_label or '---------',
            selected=not value or value == [''], index=index, attrs=attrs,
        ))
        groups.append((None, subgroup, index))
        index += 1

        # Группируем queryset по пользователю.
        positions = list(self._queryset)
        for user, items in groupby(positions, key=lambda p: p.user):
            subgroup = []
            group_label = user.full_name or user.username
            for tp in items:
                # Подпись опции — без ФИО (оно уже в названии optgroup).
                parts = [tp.get_employment_type_display()]
                if not tp.is_hourly:
                    parts.append(f'{tp.rate} ст.')
                parts.append(tp.position.name)
                if tp.user.academic_title:
                    parts.append(f'({tp.user.academic_title.lower()})')
                if not tp.academic_year.is_active:
                    parts.append(f'[{tp.academic_year.name}]')
                label = ', '.join(parts)

                str_pk = str(tp.pk)
                is_selected = (
                    str(value) == str_pk
                    or (isinstance(value, (list, tuple)) and str_pk in [str(v) for v in value])
                )
                if is_selected:
                    has_selected = True
                subgroup.append(self.create_option(
                    name=name, value=tp.pk, label=label,
                    selected=is_selected, index=index, attrs=attrs,
                ))
                index += 1
            groups.append((group_label, subgroup, index))

        return groups


class TaskForm(forms.ModelForm):
    """Форма создания/редактирования задачи заведующим."""

    work_type = forms.ModelChoiceField(
        queryset=None,
        label='Вид работы',
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-role': 'work-type-select',
        }),
        empty_label='— выберите вид работы —',
        help_text='Норматив часов подставится автоматически.',
    )
    start_date = forms.DateField(
        label='Дата начала',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    end_date = forms.DateField(
        label='Дата окончания',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )

    class Meta:
        model = Task
        fields = [
            'description', 'category', 'work_type',
            'assignee', 'planned_hours',
            'start_date', 'end_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Постановка задачи, обоснование, заметки (необязательно)',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
                'data-role': 'category-select',
            }),
            'assignee': forms.Select(attrs={'class': 'form-select'}),
            'planned_hours': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0.5', 'step': '0.5',
                'data-role': 'planned-hours-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = TaskCategory.objects.filter(
            is_active=True, is_archived=False,
        )
        assignee_qs = TeacherPosition.objects.filter(
            is_active=True,
            user__is_active=True,
            user__role='teacher',
            academic_year__is_active=True,
        ).select_related('user', 'position', 'academic_year').order_by(
            'user__full_name', 'employment_type'
        )
        self.fields['assignee'].queryset = assignee_qs
        self.fields['assignee'].widget = GroupedPositionSelect(
            attrs={'class': 'form-select', 'data-role': 'assignee-select'},
            queryset=assignee_qs,
        )

        from apps.core.models import WorkType
        self.fields['work_type'].queryset = WorkType.objects.filter(
            is_active=True,
        ).select_related('category').order_by('category', 'name')

        self.fields['description'].label = 'Описание'
        self.fields['description'].help_text = (
            'Постановка задачи, обоснование, заметки. '
            'Видно только в интерфейсе — в итоговый Word-документ не попадает. '
            'В Word идёт отчёт о выполнении, который заполняется при завершении задачи.'
        )
        self.fields['category'].label = 'Категория'
        self.fields['assignee'].label = 'Позиция исполнителя'
        self.fields['planned_hours'].label = 'Плановые часы'

        active_year = AcademicYear.objects.filter(is_active=True).first()
        if active_year is not None:
            min_date = active_year.start_date.isoformat()
            max_date = active_year.end_date.isoformat()
            self.fields['start_date'].widget.attrs['min'] = min_date
            self.fields['start_date'].widget.attrs['max'] = max_date
            self.fields['end_date'].widget.attrs['min'] = min_date
            self.fields['end_date'].widget.attrs['max'] = max_date

            # Предзаполнение start_date только при создании новой задачи.

            is_new_task = not self.instance.pk
            if (is_new_task
                    and not self.initial.get('start_date')
                    and not self.data):
                self.fields['start_date'].initial = active_year.start_date.isoformat()

            from datetime import date
            if (is_new_task
                    and not self.initial.get('end_date')
                    and not self.data):
                default_end = date(active_year.start_date.year + 1, 6, 30)
                if active_year.end_date and default_end > active_year.end_date:
                    default_end = active_year.end_date
                self.fields['end_date'].initial = default_end.isoformat()

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        planned_hours = cleaned_data.get('planned_hours')
        category = cleaned_data.get('category')
        work_type = cleaned_data.get('work_type')

        if start_date and end_date and end_date <= start_date:
            raise ValidationError({'end_date': 'Дата окончания должна быть позже даты начала.'})

        if planned_hours is not None and planned_hours <= 0:
            raise ValidationError({'planned_hours': 'Плановые часы должны быть больше нуля.'})

        if work_type is not None and category is not None:
            if work_type.category_id != category.id:
                raise ValidationError({'work_type': 'Выбранный вид работы не относится к этой категории.'})

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.work_type:
            instance.title = instance.work_type.name
        if commit:
            instance.save()
        return instance

class TeacherTaskForm(forms.ModelForm):
    """
    Форма создания внеплановой задачи преподавателем.
"""

    work_type = forms.ModelChoiceField(
        queryset=None,
        label='Вид работы',
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-role': 'work-type-select',
        }),
        empty_label='— выберите вид работы —',
        help_text='Норматив часов подставится автоматически.',
    )
    start_date = forms.DateField(
        label='Дата начала',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    end_date = forms.DateField(
        label='Дата окончания',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )

    class Meta:
        model = Task
        fields = [
            'description', 'category',
            'work_type',
            'planned_hours',
            'start_date', 'end_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Постановка задачи, обоснование, заметки (необязательно)',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
                'data-role': 'category-select',
            }),
            'planned_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.5',
                'step': '0.5',
                'data-role': 'planned-hours-input',
            }),
        }

    def __init__(self, *args, **kwargs):

        self.teacher_position = kwargs.pop('teacher_position', None)
        super().__init__(*args, **kwargs)

        from apps.core.models import WorkType

        self.fields['category'].queryset = TaskCategory.objects.filter(
            is_active=True, is_archived=False,
        )

        self.fields['work_type'].queryset = WorkType.objects.filter(
            is_active=True,
        ).select_related('category').order_by('category', 'name')

        self.fields['description'].label = 'Описание'
        self.fields['description'].help_text = (
            'Постановка задачи, обоснование, заметки. '
            'Видно только в интерфейсе — в итоговый Word-документ не попадает. '
            'В Word идёт отчёт о выполнении, который заполняется при завершении задачи.'
        )
        self.fields['category'].label = 'Категория'
        self.fields['planned_hours'].label = 'Плановые часы'

        # Дефолты дат только при создании новой задачи.
        from datetime import date
        is_new_task = not self.instance.pk
        if (is_new_task
                and not self.data
                and self.teacher_position is not None):
            year = self.teacher_position.academic_year
            if not self.initial.get('start_date'):
                self.fields['start_date'].initial = year.start_date.isoformat()
            if not self.initial.get('end_date'):
                default_end = date(year.start_date.year + 1, 6, 30)
                if year.end_date and default_end > year.end_date:
                    default_end = year.end_date
                self.fields['end_date'].initial = default_end.isoformat()

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        work_type = cleaned_data.get('work_type')
        planned_hours = cleaned_data.get('planned_hours')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')


        if start_date and end_date and end_date <= start_date:
            self.add_error('end_date', 'Дата окончания должна быть позже даты начала.')

        if planned_hours is not None and planned_hours <= 0:
            self.add_error('planned_hours', 'Плановые часы должны быть больше нуля.')

        if category is not None and category.is_archived:
            self.add_error(
                'category',
                'В эту категорию задачи создавать нельзя — '
                'она формируется из 1С.'
            )

        #  Вид работы должен соответствовать выбранной категории.
        if work_type is not None and category is not None:
            if work_type.category_id != category.id:
                self.add_error(
                    'work_type',
                    'Выбранный вид работы не относится к этой категории. '
                    'Выберите другой вид работы или измените категорию.'
                )

        # Плановые часы не должны превышать норматив выбранного вида работы.
        # Исключение: is_per_unit=True — норматив «за единицу», одна задача может
        # охватывать несколько единиц (статей, программ и т.д.).
        if (work_type is not None and not work_type.is_per_unit
                and planned_hours is not None
                and work_type.max_hours is not None
                and planned_hours > work_type.max_hours):
            self.add_error(
                'planned_hours',
                f'Превышен норматив для вида работы «{work_type.name}»: '
                f'максимум {work_type.max_hours} ч.'
            )

        # 5. Позиция должна быть передана и пригодна для приёма задачи.
        if self.teacher_position is None:
            raise ValidationError(
                'Не определена позиция для создания задачи. '
                'Выберите позицию в шапке («Я работаю как:») и попробуйте снова.'
            )

        if self.teacher_position.is_hourly:
            raise ValidationError(
                'У почасовой позиции нет второй половины дня — '
                'внеплановые задачи в неё не создаются.'
            )

        if self.teacher_position.academic_year.is_archived:
            raise ValidationError(
                'Нельзя создавать задачи в архивный учебный год.'
            )

        if not self.teacher_position.is_active:
            raise ValidationError('Текущая позиция неактивна.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.work_type:
            instance.title = instance.work_type.name
        if commit:
            instance.save()
        return instance


# Форма решения заведующего по pending-задаче

class PendingTaskDecisionForm(forms.Form):
    """
    Форма решения заведующего по внеплановой задаче преподавателя
    """

    ACTION_APPROVE = 'approve'
    ACTION_DECLINE = 'decline'
    ACTION_CHOICES = [
        (ACTION_APPROVE, 'Одобрить'),
        (ACTION_DECLINE, 'Отклонить'),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect,
        label='Решение',
    )

    #  Поля ветки «Одобрить»
    target_position = forms.ModelChoiceField(
        queryset=TeacherPosition.objects.none(),
        required=False,
        label='Перенести в позицию',
        help_text='Оставьте пустым, чтобы сохранить текущую позицию задачи.',
        empty_label='— Оставить текущую —',
    )

    planned_hours = forms.DecimalField(
        required=False,
        min_value=Decimal('0.5'),
        max_digits=6,
        decimal_places=2,
        label='Плановые часы',
        widget=forms.NumberInput(attrs={'step': '0.5', 'min': '0.5'}),
    )

    # Поле ветки «Отклонить»
    reason = forms.CharField(
        required=False,
        label='Причина отклонения',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Например: задача дублирует уже назначенную'}),
    )

    def __init__(self, *args, **kwargs):
        self.task = kwargs.pop('task', None)
        super().__init__(*args, **kwargs)

        # Импорт здесь, чтобы избежать циклов
        from apps.tasks.services import get_user_positions_for_year

        if self.task is not None:
            self.fields['target_position'].queryset = get_user_positions_for_year(
                self.task.assignee.user,
                self.task.academic_year,
            )

            if not self.data:
                self.fields['planned_hours'].initial = self.task.planned_hours

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')

        if action == self.ACTION_APPROVE:
            planned_hours = cleaned_data.get('planned_hours')
            if planned_hours is None:
                self.add_error('planned_hours', 'Укажите плановые часы для одобрения.')
            elif planned_hours <= 0:
                self.add_error('planned_hours', 'Плановые часы должны быть больше нуля.')

            if self.task is not None:
                if not self.fields['target_position'].queryset.exists():
                    raise ValidationError(
                        'У преподавателя нет активных не-почасовых позиций — '
                        'одобрить эту задачу невозможно. Её можно только отклонить.'
                    )

            cleaned_data['reason'] = ''

        elif action == self.ACTION_DECLINE:
            reason = cleaned_data.get('reason') or ''
            if not reason.strip():
                self.add_error('reason', 'Укажите причину отклонения.')
            # Очищаем поля ветки «Одобрить» — они в этой ветке не используются.
            cleaned_data['target_position'] = None
            cleaned_data['planned_hours'] = None

        return cleaned_data