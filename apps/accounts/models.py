from django.contrib.auth.models import AbstractUser
from django.db import models
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError


class User(AbstractUser):
    """
    Кастомная модель пользователя.
    """

    # --- Константы ролей ---
    ROLE_ADMIN = 'admin'
    ROLE_HEAD = 'head'
    ROLE_TEACHER = 'teacher'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Администратор'),
        (ROLE_HEAD, 'Заведующий кафедрой'),
        (ROLE_TEACHER, 'Преподаватель'),
    ]

    # --- Дополнительные поля ---

    full_name = models.CharField(
        max_length=255,
        verbose_name='ФИО',
        blank=True,
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_TEACHER,
        verbose_name='Роль',
    )

    # Учёное звание и степень
    academic_title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Учёное звание и степень',
        help_text='Например: «кандидат наук, доцент». Используется в шапке выгрузки плана.',
    )

    # Поле для расширяемости — кафедра. Сейчас не используется в логике,
    # на случай многокафедрального варианта.
    department = models.ForeignKey(
        'core.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Кафедра',
        related_name='users',
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['full_name']

    def __str__(self):
        return self.full_name or self.username


    @property
    def is_admin(self):
        """Является ли пользователь администратором системы."""
        return self.role == self.ROLE_ADMIN

    @property
    def is_head(self):
        """Является ли пользователь заведующим кафедрой."""
        return self.role == self.ROLE_HEAD

    @property
    def is_teacher(self):
        """Является ли пользователь преподавателем."""
        return self.role == self.ROLE_TEACHER




class TeacherPosition(models.Model):
    """
    Позиция преподавателя в учебном году.
    Один пользователь может иметь несколько позиций одновременно в одном году.
    """

    # --- Виды занятости ---
    EMPLOYMENT_MAIN = 'MAIN'
    EMPLOYMENT_INTERNAL_COMBINING = 'INTERNAL_COMBINING'
    EMPLOYMENT_EXTERNAL_COMBINING = 'EXTERNAL_COMBINING'
    EMPLOYMENT_HOURLY = 'HOURLY'

    EMPLOYMENT_CHOICES = [
        (EMPLOYMENT_MAIN, 'Основное место работы'),
        (EMPLOYMENT_INTERNAL_COMBINING, 'Внутреннее совместительство'),
        (EMPLOYMENT_EXTERNAL_COMBINING, 'Внешнее совместительство'),
        (EMPLOYMENT_HOURLY, 'На условиях почасовой оплаты труда'),
    ]

    EMPLOYMENT_TYPES_WITH_RATE = [
        EMPLOYMENT_MAIN,
        EMPLOYMENT_INTERNAL_COMBINING,
        EMPLOYMENT_EXTERNAL_COMBINING,
    ]

    # --- Доли ставки ---
    RATE_FULL = Decimal('1.00')
    RATE_THREE_QUARTERS = Decimal('0.75')
    RATE_HALF = Decimal('0.50')
    RATE_QUARTER = Decimal('0.25')

    RATE_CHOICES = [
        (RATE_FULL, '1.0 (полная ставка)'),
        (RATE_THREE_QUARTERS, '0.75'),
        (RATE_HALF, '0.5'),
        (RATE_QUARTER, '0.25'),
    ]


    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teacher_positions',
        verbose_name='Преподаватель',
    )
    academic_year = models.ForeignKey(
        'core.AcademicYear',
        on_delete=models.PROTECT,
        related_name='teacher_positions',
        verbose_name='Учебный год',
    )
    employment_type = models.CharField(
        max_length=30,
        choices=EMPLOYMENT_CHOICES,
        verbose_name='Вид занятости',
    )
    position = models.ForeignKey(
        'core.Position',
        on_delete=models.PROTECT,
        related_name='teacher_positions',
        verbose_name='Должность',
    )
    rate = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        choices=RATE_CHOICES,
        null=True,
        blank=True,
        verbose_name='Доля ставки',
        help_text='Заполняется для всех видов занятости, кроме почасовой',
    )
    teaching_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Учебная нагрузка (часов из 1С)',
        help_text='Заполняется по выгрузке из 1С.',
    )
    teaching_load_imported_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Учебная нагрузка загружена',
        help_text='Дата и время последнего импорта выгрузки 1С для этой позиции',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активна',
        help_text='Если позиция закрыта (декрет, увольнение и т.п.) — снимите флаг',
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name='Заметки',
        help_text='Например: «декретный отпуск», «творческий отпуск»',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Позиция преподавателя'
        verbose_name_plural = 'Позиции преподавателей'
        ordering = ['user__full_name', 'academic_year', 'employment_type']

    def __str__(self):
        return f'{self.user} — {self.display_label} ({self.academic_year})'


    @property
    def is_hourly(self):
        """Это позиция с почасовой оплатой?"""
        return self.employment_type == self.EMPLOYMENT_HOURLY

    @property
    def has_second_half(self):
        """Есть ли у этой позиции вторая половина дня."""
        return not self.is_hourly

    @property
    def total_hours_limit(self):
        """
        Годовой фонд рабочего времени для этой позиции.
        Для почасовой — None (фонд не применяется).
        Для остальных — 1550 × rate.
        """
        if self.is_hourly or self.rate is None:
            return None
        # Берём max_total_hours из нормы должности на этот год, если есть;
        # иначе используем стандартные 1550 ч.
        try:
            workload = self.position.workloads.get(academic_year=self.academic_year)
            base = workload.max_total_hours
        except Exception:
            base = 1550
        return int(Decimal(base) * self.rate)

    @property
    def second_half_hours(self):
        """
        Объём второй половины дня = годовой фонд − учебная нагрузка.
        Для почасовой — None.
        """
        if not self.has_second_half:
            return None
        limit = self.total_hours_limit
        if limit is None:
            return None
        return Decimal(limit) - (self.teaching_hours or Decimal('0'))

    @property
    def teaching_load_total(self):
        """
        Суммарные часы из загруженной учебной нагрузки
        """
        from django.db.models import Sum
        result = self.teaching_load.aggregate(total=Sum('hours'))
        return result['total'] or Decimal('0')

    @property
    def display_label(self):
        """Текстовое представление для: «Доцент, основная 1.0 ст.»"""
        position_name = self.position.name if self.position_id else '—'
        type_label = dict(self.EMPLOYMENT_CHOICES).get(self.employment_type, '—')
        if self.is_hourly:
            return f'{position_name}, почасовая'
        rate_str = f'{self.rate:.2f}'.rstrip('0').rstrip('.') if self.rate else '—'

        type_short = {
            self.EMPLOYMENT_MAIN: 'основная',
            self.EMPLOYMENT_INTERNAL_COMBINING: 'внутр. совмест.',
            self.EMPLOYMENT_EXTERNAL_COMBINING: 'внеш. совмест.',
        }.get(self.employment_type, type_label.lower())
        return f'{position_name}, {type_short} {rate_str} ст.'


    def clean(self):
        errors = {}

        # Правило 1: у MAIN/INTERNAL/EXTERNAL поле rate обязательно
        if self.employment_type in self.EMPLOYMENT_TYPES_WITH_RATE:
            if self.rate is None:
                errors['rate'] = (
                    'Для этого вида занятости нужно указать долю ставки.'
                )

        # Правило 2: у HOURLY поле rate должно быть пустым
        if self.employment_type == self.EMPLOYMENT_HOURLY:
            if self.rate is not None:
                errors['rate'] = (
                    'У почасовой позиции доля ставки не указывается.'
                )

        # Правило 3: только одна позиция MAIN на пользователя в одном году
        if (
            self.employment_type == self.EMPLOYMENT_MAIN
            and self.user_id
            and self.academic_year_id
        ):
            qs = TeacherPosition.objects.filter(
                user_id=self.user_id,
                academic_year_id=self.academic_year_id,
                employment_type=self.EMPLOYMENT_MAIN,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                errors['employment_type'] = (
                    'У этого преподавателя уже есть позиция с типом '
                    '«Основное место работы» в этом учебном году.'
                )

        if errors:
            raise ValidationError(errors)

class TeachingLoadItem(models.Model):

    position = models.ForeignKey(
        'TeacherPosition',
        on_delete=models.CASCADE,
        related_name='teaching_load',
        verbose_name='Позиция преподавателя',
    )
    discipline = models.CharField(
        max_length=300,
        verbose_name='Дисциплина',
        help_text='Название дисциплины из выгрузки 1С',
    )
    semester = models.PositiveSmallIntegerField(
        verbose_name='Семестр',
        help_text='Номер семестра (1–8)',
    )
    activity_type = models.ForeignKey(
        'core.TeachingActivityType',
        on_delete=models.PROTECT,
        related_name='teaching_load_items',
        verbose_name='Вид занятия',
    )
    hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        verbose_name='Часы (план)',
        help_text='Плановое количество часов из выгрузки 1С',
    )
    group_number = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Факультет, курс, группа',
        help_text='Из колонки 11 полного плана или колонки 5 legacy-выгрузки (для информации)',
    )

    cycle = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Цикл дисциплины',
        help_text='Например: «Б1.О.23». Из полного плана (col9).',
    )
    students_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Число студентов',
        help_text='Из полного плана (col13).',
    )
    hours_fact = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Часы (факт)',
        help_text='Фактически выполненные часы. По умолчанию 0.',
    )

    period_label = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Период контроля',
        help_text='Исходный текст из col5 плана: «Третий семестр», «11 сессия (зимняя)» и т.д.',
    )
    row_num = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Порядковый номер строки',
        help_text='Значение col1 из выгрузки 1С. Используется для сортировки в исходном порядке.',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Строка учебной нагрузки'
        verbose_name_plural = 'Строки учебной нагрузки'
        ordering = ['position', 'semester', 'discipline', 'activity_type__sort_order']

    def __str__(self):
        return f'{self.discipline} — {self.activity_type} ({self.hours} ч.)'