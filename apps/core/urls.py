from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Дашборд администратора
    path('dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),

    # Учебные годы
    path('years/', views.YearListView.as_view(), name='year_list'),
    path('years/create/', views.YearCreateView.as_view(), name='year_create'),
    path('years/<int:pk>/edit/', views.YearEditView.as_view(), name='year_edit'),
    path('years/<int:pk>/activate/', views.YearActivateView.as_view(), name='year_activate'),
    path('years/<int:pk>/archive/', views.YearArchiveView.as_view(), name='year_archive'),
    path('years/<int:pk>/delete/', views.YearDeleteView.as_view(), name='year_delete'),

    # Категории задач
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/<int:pk>/toggle/', views.CategoryToggleActiveView.as_view(), name='category_toggle'),

    # Нормы нагрузки
    path('workloads/', views.WorkloadListView.as_view(), name='workload_list'),
    path('workloads/<int:pk>/edit/', views.WorkloadEditView.as_view(), name='workload_edit'),


# Виды работ (справочник)
    path('worktypes/', views.WorkTypeListView.as_view(), name='worktype_list'),
    path('worktypes/create/', views.WorkTypeCreateView.as_view(), name='worktype_create'),
    path('worktypes/<int:pk>/edit/', views.WorkTypeEditView.as_view(), name='worktype_edit'),
    path('worktypes/<int:pk>/toggle/', views.WorkTypeToggleActiveView.as_view(), name='worktype_toggle'),
    path('export-settings/', views.ExportSettingsView.as_view(), name='export_settings'),
]