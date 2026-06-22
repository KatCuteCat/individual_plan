from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    # Заведующий
    path('head/', views.HeadDashboardView.as_view(), name='head_dashboard'),
    path('list/', views.TaskListView.as_view(), name='task_list'),
    path('create/', views.TaskCreateView.as_view(), name='task_create'),
    path('<int:pk>/edit/', views.TaskEditView.as_view(), name='task_edit'),
    path('<int:pk>/review/', views.TaskReviewView.as_view(), name='task_review'),
    path('teachers/', views.TeacherListView.as_view(), name='teacher_list'),
    path('teachers/<int:pk>/', views.TeacherCardView.as_view(), name='teacher_card'),
    path('analytics/category-limits/', views.CategoryLimitsAnalyticsView.as_view(), name='category_limits_analytics'),
    # Очередь утверждения внеплановых задач
    path('pending-approval/', views.PendingApprovalListView.as_view(), name='pending_approval_list'),
    path('pending-approval/<int:pk>/review/', views.PendingTaskReviewView.as_view(), name='pending_task_review'),
    path('declined/<int:pk>/delete/', views.DeclinedTaskDeleteView.as_view(), name='declined_task_delete'),
    path('<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('close-year/', views.CloseYearView.as_view(), name='close_year'),

    # Преподаватель
    path('my/', views.TeacherDashboardView.as_view(), name='teacher_dashboard'),
    path('my/tasks/', views.MyTasksView.as_view(), name='my_tasks'),
    path('my/tasks/create/', views.TeacherCreateTaskView.as_view(), name='my_task_create'),
    path('my/tasks/<int:pk>/edit/', views.TeacherEditPendingTaskView.as_view(), name='my_task_edit'),
    path('my/workload/', views.MyWorkloadView.as_view(), name='my_workload'),

# Действия преподавателя с задачами
    # Выгрузка Word
    path('export-word/<int:position_id>/', views.ExportWordView.as_view(), name='export_word'),
    path('export-word-all/', views.ExportAllWordView.as_view(), name='export_word_all'),
    # Действия преподавателя с задачами
    path('<int:pk>/start/', views.TaskStartView.as_view(), name='task_start'),
    path('<int:pk>/complete/', views.TaskCompleteView.as_view(), name='task_complete'),
    path('my/<int:pk>/withdraw/', views.TaskWithdrawView.as_view(), name='task_withdraw'),
]