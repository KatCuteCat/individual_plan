from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):

    list_display = ('username', 'full_name', 'email', 'role', 'academic_title', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'full_name', 'email')
    ordering = ('full_name',)

    fieldsets = BaseUserAdmin.fieldsets + (
        (_('Данные ВГТУ'), {
            'fields': ('full_name', 'role', 'academic_title', 'department'),
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_('Данные ВГТУ'), {
            'fields': ('full_name', 'role', 'academic_title'),
        }),
    )

from .models import TeacherPosition


@admin.register(TeacherPosition)
class TeacherPositionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'academic_year', 'employment_type',
        'position', 'rate', 'teaching_hours', 'is_active',
    )
    list_filter = ('academic_year', 'employment_type', 'position', 'is_active')
    search_fields = ('user__full_name', 'user__username')
    autocomplete_fields = ('user',)
    readonly_fields = ('teaching_load_imported_at',)

    fieldsets = (
        ('Основное', {
            'fields': ('user', 'academic_year', 'employment_type',
                       'position', 'rate', 'is_active'),
        }),
        ('Учебная нагрузка и протокол', {
            'fields': ('teaching_hours', 'teaching_load_imported_at',
                       'protocol_number', 'protocol_date'),
        }),
        ('Заметки', {
            'fields': ('notes',),
        }),
    )


from .models import TeachingLoadItem


@admin.register(TeachingLoadItem)
class TeachingLoadItemAdmin(admin.ModelAdmin):
    #Админка для строк учебной нагрузки (только просмотр)
    list_display = ('position', 'discipline', 'semester', 'activity_type', 'hours')
    list_filter = ('position__academic_year', 'semester', 'activity_type')
    search_fields = ('discipline', 'position__user__full_name')
    autocomplete_fields = ('position',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('position', 'discipline', 'semester',
                       'activity_type', 'hours', 'group_number'),
        }),
        ('Служебная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )