from django.contrib import admin
from .models import (
    Position,
    AcademicYear,
    TaskCategory,
    PositionWorkload,
    Department,
    WorkType,
    TeachingActivityType,
    CategoryLimit,
)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    """Админка для должностей ППС."""
    list_display = ('name', 'code')
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    """Админка для учебных годов."""
    list_display = ('name', 'start_date', 'end_date', 'is_active', 'is_archived')
    list_filter = ('is_active', 'is_archived')
    search_fields = ('name',)
    ordering = ('-start_date',)
    list_editable = ('is_active',)


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий задач."""
    list_display = ('name', 'code', 'is_active', 'is_archived')
    list_filter = ('is_active', 'is_archived')
    search_fields = ('name',)
    list_editable = ('is_active', 'is_archived')
    ordering = ('name',)


@admin.register(PositionWorkload)
class PositionWorkloadAdmin(admin.ModelAdmin):
    """Админка для норм нагрузки."""
    list_display = ('position', 'academic_year', 'max_teaching_hours', 'max_total_hours')
    list_filter = ('academic_year', 'position')
    ordering = ('academic_year', 'position')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('position', 'academic_year')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Админка для кафедр."""
    list_display = ('name', 'short_name')
    search_fields = ('name', 'short_name')
    ordering = ('name',)


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    """Админка для справочника видов работ."""
    list_display = ('name', 'category', 'max_hours', 'unit_description', 'is_per_unit', 'is_active')
    list_filter = ('category', 'is_per_unit', 'is_active')
    search_fields = ('name',)
    list_editable = ('is_per_unit', 'is_active')
    ordering = ('category', 'name')

    fieldsets = (
        (None, {
            'fields': ('name', 'category', 'is_active'),
        }),
        ('Норматив времени', {
            'fields': ('max_hours', 'unit_description'),
            'description': 'Максимум часов согласно нормативу ВГТУ '
                           'и пояснение единицы измерения.',
        }),
    )


@admin.register(TeachingActivityType)
class TeachingActivityTypeAdmin(admin.ModelAdmin):
    """Админка для справочника видов учебных занятий."""
    list_display = ('name', 'code', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    list_editable = ('sort_order', 'is_active')
    ordering = ('sort_order', 'name')


@admin.register(CategoryLimit)
class CategoryLimitAdmin(admin.ModelAdmin):
    """
    Админка для лимитов по категориям второй половины дня.
    """
    list_display = (
        'category',
        'position_display',
        'min_percent',
        'max_percent',
        'regulation_point',
    )
    list_filter = ('category', 'position')
    search_fields = ('category__name', 'position__name', 'regulation_point')
    ordering = ('category', 'position')
    autocomplete_fields = ('category', 'position')

    fieldsets = (
        (None, {
            'fields': ('category', 'position'),
            'description': 'Если должность не указана, лимит применяется '
                           'ко всем должностям. Запись с конкретной должностью '
                           'переопределяет общую.',
        }),
        ('Лимиты', {
            'fields': ('min_percent', 'max_percent'),
            'description': 'Проценты считаются от объёма второй половины '
                           'рабочего дня: (1550 × ставка − учебные часы из 1С). '
                           'Если в приказе минимум не установлен — указать 0.',
        }),
        ('Юридическое обоснование', {
            'fields': ('regulation_point', 'notes'),
        }),
    )

    @admin.display(description='Должность', ordering='position')
    def position_display(self, obj):
        return obj.position.name if obj.position else '— все должности —'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category', 'position')