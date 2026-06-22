from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Task(models.Model):
    """Задача индивидуального плана преподавателя."""

    # --- Типы задач ---
    TYPE_FIXED = 'fixed'
    TYPE_ADDITIONAL = 'additional'

    TYPE_CHOICES = [
        (TYPE_FIXED, 'Фиксированная'),
        (TYPE_ADDITIONAL, 'Дополнительная'),
    ]

    # --- Статусы задач ---
    STATUS_PENDING_APPROVAL = 'pending_approval'
    STATUS_ASSIGNED = 'assigned'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_APPROVED = 'approved'
    STATUS_DECLINED = 'declined'

    STATUS_CHOICES = [
        (STATUS_PENDING_APPROVAL, 'Ожидает утверждения'),
        (STATUS_ASSIGNED, 'Назначена'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_COMPLETED, 'Выполнена'),
        (STATUS_APPROVED, 'Подтверждена'),
        (STATUS_DECLINED, 'Не утверждена'),
    ]


    STATUS_TRANSITIONS = {
        STATUS_PENDING_APPROVAL: [STATUS_ASSIGNED, STATUS_DECLINED],
        STATUS_ASSIGNED: [STATUS_IN_PROGRESS],
        STATUS_IN_PROGRESS: [STATUS_COMPLETED],
        STATUS_COMPLETED: [STATUS_IN_PROGRESS, STATUS_APPROVED],
        STATUS_APPROVED: [],  # Финальный
        STATUS_DECLINED: [],  # Финальный
    }

    title = models.CharField(
        max_length=300,
        verbose_name='Название задачи'
    )
    description = models.TextField(
        blank=True, default='',
        verbose_name='Описание'
    )
    category = models.ForeignKey(
        'core.TaskCategory', on_delete=models.PROTECT,
        verbose_name='Категория', related_name='tasks'
    )
    academic_year = models.ForeignKey(
        'core.AcademicYear', on_delete=models.PROTECT,
        verbose_name='Учебный год', related_name='tasks'
    )
    assignee = models.ForeignKey(
        'accounts.TeacherPosition', on_delete=models.CASCADE,
        verbose_name='Позиция исполнителя', related_name='assigned_tasks'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        verbose_name='Создатель', related_name='created_tasks'
    )
    task_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default=TYPE_FIXED,
        verbose_name='Тип задачи'
    )
    # FK на вид работы; заменяет текстовый префикс «Вид работы: ...» в description.

    work_type = models.ForeignKey(
        'core.WorkType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Вид работы',
        related_name='tasks',
    )
    planned_hours = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name='Плановые часы'
    )
    actual_hours = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        verbose_name='Фактические часы',
        help_text='Заполняется преподавателем при выполнении'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ASSIGNED,
        verbose_name='Статус'
    )
    result = models.TextField(
        blank=True, default='',
        verbose_name='Результат',
        help_text='Например, название статьи, ссылка на публикацию'
    )
    start_date = models.DateField(
        verbose_name='Дата начала'
    )
    end_date = models.DateField(
        verbose_name='Дата окончания'
    )
    rejection_reason = models.TextField(
        blank=True, default='',
        verbose_name='Причина отклонения'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.assignee}'

    def clean(self):
        """Валидация модели."""
        errors = {}

        # Дата окончания должна быть позже даты начала
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                errors['end_date'] = 'Дата окончания должна быть позже даты начала.'

        # Плановые часы должны быть положительными
        if self.planned_hours is not None and self.planned_hours <= 0:
            errors['planned_hours'] = 'Плановые часы должны быть больше нуля.'

        # Фактические часы (если указаны) должны быть положительными
        if self.actual_hours is not None and self.actual_hours <= 0:
            errors['actual_hours'] = 'Фактические часы должны быть больше нуля.'

        if errors:
            raise ValidationError(errors)

    def can_transition_to(self, new_status):
        """Проверить, допустим ли переход в указанный статус."""
        allowed = self.STATUS_TRANSITIONS.get(self.status, [])
        return new_status in allowed

    def transition_to(self, new_status):
        """
        Выполнить переход в новый статус.
        Возвращает True при успехе, вызывает ValidationError при ошибке.
        """
        if not self.can_transition_to(new_status):
            current_label = self.get_status_display()
            new_label = dict(self.STATUS_CHOICES).get(new_status, new_status)
            raise ValidationError(
                f'Нельзя перейти из статуса «{current_label}» в «{new_label}».'
            )
        self.status = new_status

    @property
    def is_editable(self):
        """Задачу можно редактировать, если она не в финальном статусе и год не архивный."""
        final_statuses = (self.STATUS_APPROVED, self.STATUS_DECLINED)
        return self.status not in final_statuses and not self.academic_year.is_archived

    @property
    def is_completable(self):
        """Преподаватель может отметить выполнение, если задача в работе."""
        return self.status == self.STATUS_IN_PROGRESS

    @property
    def is_reviewable(self):
        """Заведующий может проверить, если задача отмечена как выполненная."""
        return self.status == self.STATUS_COMPLETED

    @property
    def is_pending_approval(self):
        """Задача ожидает утверждения заведующим (создана преподавателем)."""
        return self.status == self.STATUS_PENDING_APPROVAL