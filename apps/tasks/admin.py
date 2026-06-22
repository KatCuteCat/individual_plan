from django.contrib import admin
from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Админка для задач (для отладки и начального наполнения)."""

    list_display = (
        'title', 'assignee', 'category', 'status',
        'task_type', 'planned_hours', 'actual_hours',
        'start_date', 'end_date',
    )
    list_filter = ('status', 'category', 'task_type', 'academic_year')
    search_fields = ('title', 'assignee__full_name', 'assignee__username')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    # Группировка полей в форме
    fieldsets = (
        ('Основное', {
            'fields': ('title', 'description', 'category', 'academic_year', 'task_type'),
        }),
        ('Назначение', {
            'fields': ('assignee', 'creator'),
        }),
        ('Часы', {
            'fields': ('planned_hours', 'actual_hours'),
        }),
        ('Сроки', {
            'fields': ('start_date', 'end_date'),
        }),
        ('Статус и результат', {
            'fields': ('status', 'result', 'rejection_reason'),
        }),
        ('Служебные поля', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'assignee', 'creator', 'category', 'academic_year'
        )