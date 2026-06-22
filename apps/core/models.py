from django.db import models
from django.core.exceptions import ValidationError


class Position(models.Model):
    """Должность ППС"""

    # Коды должностей для программной логики
    CODE_DEAN = 'DEAN'
    CODE_HEAD_OF_DEPARTMENT = 'HEAD_OF_DEPARTMENT'
    CODE_PROFESSOR = 'PROFESSOR'
    CODE_ASSOCIATE_PROFESSOR = 'ASSOCIATE_PROFESSOR'
    CODE_SENIOR_TEACHER = 'SENIOR_TEACHER'
    CODE_ASSISTANT = 'ASSISTANT'

    CODE_CHOICES = [
        (CODE_DEAN, 'Декан'),
        (CODE_HEAD_OF_DEPARTMENT, 'Заведующий кафедрой'),
        (CODE_PROFESSOR, 'Профессор'),
        (CODE_ASSOCIATE_PROFESSOR, 'Доцент'),
        (CODE_SENIOR_TEACHER, 'Старший преподаватель'),
        (CODE_ASSISTANT, 'Ассистент'),
    ]

    name = models.CharField(
        max_length=100, unique=True,
        verbose_name='Название должности'
    )
    code = models.CharField(
        max_length=30, unique=True, choices=CODE_CHOICES,
        verbose_name='Код должности'
    )

    class Meta:
        verbose_name = 'Должность'
        verbose_name_plural = 'Должности'
        ordering = ['name']

    def __str__(self):
        return self.name


class AcademicYear(models.Model):
    """Учебный год."""

    name = models.CharField(
        max_length=20, unique=True,
        verbose_name='Название',
        help_text='Например: 2025-2026'
    )
    start_date = models.DateField(verbose_name='Дата начала')
    end_date = models.DateField(verbose_name='Дата окончания')
    is_active = models.BooleanField(
        default=False,
        verbose_name='Активный',
        help_text='Только один учебный год может быть активным'
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name='Архивный'
    )

    class Meta:
        verbose_name = 'Учебный год'
        verbose_name_plural = 'Учебные годы'
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    def clean(self):
        """Валидация: дата окончания должна быть позже даты начала."""
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValidationError({
                    'end_date': 'Дата окончания должна быть позже даты начала.'
                })

    def save(self, *args, **kwargs):
        # Если этот год помечен как активный — снимаем флаг с остальных
        if self.is_active:
            AcademicYear.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class TaskCategory(models.Model):
    """Категория задачи (вид деятельности ППС)."""

    CODE_TEACHING = 'TEACHING'
    CODE_EDUCATIONAL_METHODICAL = 'EDUCATIONAL_METHODICAL'
    CODE_SCIENTIFIC = 'SCIENTIFIC'
    CODE_ORGANIZATIONAL = 'ORGANIZATIONAL'
    CODE_EDUCATIONAL_WORK = 'EDUCATIONAL_WORK'

    CODE_CHOICES = [
        (CODE_TEACHING, 'Учебная работа'),
        (CODE_EDUCATIONAL_METHODICAL, 'Учебно-методическая'),
        (CODE_SCIENTIFIC, 'Научно-исследовательская'),
        (CODE_ORGANIZATIONAL, 'Организационно-методическая'),
        (CODE_EDUCATIONAL_WORK, 'Воспитательная работа'),
    ]

    name = models.CharField(
        max_length=100, unique=True,
        verbose_name='Название категории'
    )
    code = models.CharField(
        max_length=30, unique=True, choices=CODE_CHOICES,
        verbose_name='Код категории'
    )
    description = models.TextField(
        blank=True, default='',
        verbose_name='Описание'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активна'
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name='Архивирована',
        help_text='Если включено — категория не показывается в форме создания новых задач, '
                  'но исторические задачи продолжают отображаться. '
                  'Используется для категории «Учебная работа», которая приходит из 1С.'
    )

    class Meta:
        verbose_name = 'Категория задач'
        verbose_name_plural = 'Категории задач'
        ordering = ['name']

    def __str__(self):
        return self.name


class PositionWorkload(models.Model):
    """Нормы нагрузки по должности на учебный год."""

    position = models.ForeignKey(
        Position, on_delete=models.CASCADE,
        verbose_name='Должность', related_name='workloads'
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE,
        verbose_name='Учебный год', related_name='workloads'
    )
    max_teaching_hours = models.PositiveIntegerField(
        verbose_name='Макс. учебных часов (на полную ставку)',
        help_text='Верхний предел учебной нагрузки для ставки 1.0'
    )
    max_total_hours = models.PositiveIntegerField(
        default=1550,
        verbose_name='Общий объём рабочего времени (часов в год)',
        help_text='По умолчанию 1550 часов'
    )

    class Meta:
        verbose_name = 'Норма нагрузки'
        verbose_name_plural = 'Нормы нагрузки'
        # Одна запись на связку должность + учебный год
        unique_together = ['position', 'academic_year']
        ordering = ['academic_year', 'position']

    def __str__(self):
        return f'{self.position} — {self.academic_year} ({self.max_teaching_hours} ч.)'

    def get_teaching_hours_for_rate(self, rate):
        """
        Формула: max_teaching_hours × rate
        Допустимое отклонение в меньшую сторону:
          - от 0.1 до 0.5 ставки — до 5 часов
          - свыше 0.5 до 1.0 ставки — до 10 часов
        """
        from decimal import Decimal
        rate = Decimal(str(rate))
        base = self.max_teaching_hours * rate

        if rate <= Decimal('0.5'):
            tolerance = 5
        else:
            tolerance = 10

        return {
            'max_hours': int(base),
            'min_hours': max(0, int(base) - tolerance),
            'tolerance': tolerance,
        }

    def get_total_hours_for_rate(self, rate):
        """Рассчитать общий объём рабочего времени для доли ставки."""
        from decimal import Decimal
        rate = Decimal(str(rate))
        return int(self.max_total_hours * rate)


class Department(models.Model):
    """Кафедра (для расширяемости)"""

    name = models.CharField(
        max_length=200, unique=True,
        verbose_name='Название кафедры'
    )
    short_name = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name='Сокращённое название'
    )

    class Meta:
        verbose_name = 'Кафедра'
        verbose_name_plural = 'Кафедры'
        ordering = ['name']

    def __str__(self):
        return self.short_name or self.name

class WorkType(models.Model):
    """
    Вид работы — справочник конкретных видов деятельности с нормативом часов.
    """

    name = models.CharField(
        max_length=500,
        verbose_name='Название вида работы',
        help_text='Например: «Разработка рабочей программы дисциплины»',
    )
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.PROTECT,
        verbose_name='Категория',
        related_name='work_types',
        help_text='Категория, к которой относится этот вид работы',
    )
    max_hours = models.PositiveIntegerField(
        verbose_name='Максимум часов',
        help_text='Верхний предел часов согласно нормативу ВГТУ',
    )
    unit_description = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Единица измерения / уточнение',
        help_text='Например: «на одну дисциплину», «за 1 печатный лист», «в год»',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен',
        help_text='Неактивные виды не показываются при создании задач',
    )
    is_per_unit = models.BooleanField(
        default=False,
        verbose_name='Норматив на единицу',
        help_text='Если включено, норматив max_hours указан «за один объект» '
                  '(работа, статья, программа, мероприятие). Тогда одна задача '
                  'в системе может содержать несколько таких единиц — превышение '
                  'norm в задаче допустимо. Если выключено, норматив указан '
                  '«в год» или «на позицию» — превышение блокируется.',
    )

    class Meta:
        verbose_name = 'Вид работы'
        verbose_name_plural = 'Виды работ (справочник)'
        ordering = ['category', 'name']
        # Один и тот же вид работы не должен дублироваться внутри категории
        unique_together = ['category', 'name']

    def __str__(self):
        return f'{self.name} (до {self.max_hours} ч.)'


class TeachingActivityType(models.Model):
    """
    Справочник видов учебных занятий (первая половина дня).
    """

    name = models.CharField(
        max_length=200, unique=True,
        verbose_name='Название вида занятия',
        help_text='Например: «Лекционные занятия», «Экзамен»'
    )
    code = models.CharField(
        max_length=40, unique=True,
        verbose_name='Код',
        help_text='Короткий ASCII-идентификатор для парсера. '
                  'Например: LECTURE, EXAM, COURSE_WORK'
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок сортировки',
        help_text='Чем меньше число, тем выше в списке'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен'
    )

    class Meta:
        verbose_name = 'Вид учебного занятия'
        verbose_name_plural = 'Виды учебных занятий'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

class CategoryLimit(models.Model):
    """
    Лимит часов на категорию второй половины дня.
    Хранит минимальный и максимальный процент от объёма второй половины
    рабочего дня (1550 × rate − teaching_hours) для одной категории
    задач.
    """

    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.CASCADE,
        verbose_name='Категория',
        related_name='limits',
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Должность',
        related_name='category_limits',
        help_text='Если не указана — лимит применяется ко всем должностям.',
    )
    min_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Минимум, %',
        help_text='Минимальный процент от объёма второй половины дня. '
                  '0 — если в приказе минимум не установлен.',
    )
    max_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='Максимум, %',
        help_text='Максимальный процент от объёма второй половины дня.',
    )
    regulation_point = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Пункт приказа',
        help_text='Ссылка на пункт приказа ВГТУ, '
                  'например «4.1, абз. 1».',
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name='Примечания',
    )

    class Meta:
        verbose_name = 'Лимит по категории'
        verbose_name_plural = 'Лимиты по категориям'
        # Одна запись на пару категория + должность.
        # Запись с position=NULL — общая для всех должностей.
        unique_together = ['category', 'position']
        ordering = ['category', 'position']

    def __str__(self):
        scope = self.position.name if self.position else 'все должности'
        return f'{self.category.name} ({scope}): {self.min_percent}–{self.max_percent} %'

    @property
    def applies_to_all_positions(self):
        """True, если лимит применяется ко всем должностям."""
        return self.position is None

    @property
    def display_label(self):
        """Человекочитаемое представление для шаблонов и админки."""
        scope = self.position.name if self.position else 'все должности'
        # Decimal('10.00') → «10», Decimal('10.50') → «10.5»
        min_str = f'{self.min_percent:g}'
        max_str = f'{self.max_percent:g}'
        return f'{self.category.name} ({scope}): {min_str}–{max_str} %'

    def clean(self):
        errors = {}

        if self.min_percent is not None and self.min_percent < 0:
            errors['min_percent'] = 'Минимум не может быть отрицательным.'
        if self.max_percent is not None and self.max_percent > 100:
            errors['max_percent'] = 'Максимум не может превышать 100 %.'
        if (self.min_percent is not None and self.max_percent is not None
                and self.min_percent > self.max_percent):
            errors['min_percent'] = 'Минимум не может быть больше максимума.'

        if self.category_id and self.category.is_archived:
            errors['category'] = (
                f'Категория «{self.category.name}» архивирована и не имеет лимитов '
                'второй половины дня (например, «Учебная работа» приходит из 1С).'
            )

        if errors:
            raise ValidationError(errors)

class ExportSettings(models.Model):
    """
    Настройки выгрузки индивидуального плана в Word.
    """

    academic_year = models.OneToOneField(
        'AcademicYear',
        on_delete=models.CASCADE,
        verbose_name='Учебный год',
        related_name='export_settings',
    )
    department_name = models.CharField(
        max_length=300,
        blank=True,
        default='',
        verbose_name='Название кафедры',
        help_text='Аббревиатура, например: «КИТП»',
    )
    department_full_name = models.CharField(
        max_length=300,
        blank=True,
        default='',
        verbose_name='Полное название кафедры',
        help_text='В родительном падеже, например: '
                  '«Компьютерных интеллектуальных технологий проектирования»',
    )
    faculty_name = models.CharField(
        max_length=300,
        blank=True,
        default='',
        verbose_name='Название факультета',
        help_text='Например: «Факультет информационных технологий и компьютерной безопасности»',
    )
    approver_title = models.CharField(
        max_length=300,
        blank=True,
        default='',
        verbose_name='Должность утверждающего',
        help_text='Например: «Декан»',
    )
    approver_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='ФИО утверждающего',
        help_text='Например: «И.И.Иванов »',
    )
    head_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='ФИО заведующего кафедрой',
        help_text='Для подписи в документе',
    )
    protocol_number = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Номер протокола(план)',
        help_text='Если не заполнено — в документе будет плейсхолдер',
    )
    protocol_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Дата протокола(план)',
        help_text='Если не заполнено — в документе будет плейсхолдер',
    )
    report_protocol_number = models.CharField(
        max_length=50, blank=True,
        verbose_name='Номер протокола (отчёт)',
        help_text='Номер протокола заседания кафедры для рассмотрения отчёта',
    )
    report_protocol_date = models.DateField(
        null=True, blank=True,
        verbose_name='Дата протокола (отчёт)',
        help_text='Дата заседания кафедры для рассмотрения отчёта',
    )

    class Meta:
        verbose_name = 'Настройки выгрузки'
        verbose_name_plural = 'Настройки выгрузки'

    def __str__(self):
        return f'Настройки выгрузки — {self.academic_year}'