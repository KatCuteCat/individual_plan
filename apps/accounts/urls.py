from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Аутентификация
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('password-change/', views.PasswordChangeView.as_view(), name='password_change'),
    path('password-change/done/', views.PasswordChangeDoneView.as_view(), name='password_change_done'),

    # CRUD пользователей (администратор)
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/toggle-active/', views.UserToggleActiveView.as_view(), name='user_toggle_active'),
    path('users/<int:pk>/set-password/', views.UserSetPasswordView.as_view(), name='user_set_password'),

    # Позиции преподавателя (привязаны к пользователю)
    path('users/<int:user_pk>/positions/create/', views.PositionCreateView.as_view(), name='position_create'),
    path('positions/<int:pk>/edit/', views.PositionEditView.as_view(), name='position_edit'),
    path('positions/<int:pk>/delete/', views.PositionDeleteView.as_view(), name='position_delete'),
    path('years/<int:target_pk>/copy-positions/', views.CopyPositionsView.as_view(), name='positions_copy'),
    # Загрузка учебной нагрузки на позицию из выгрузки 1С
    path('positions/<int:pk>/load-teaching/',
         views.TeachingLoadImportView.as_view(),
         name='teaching_load_import'),
    # Ввод факта учебной нагрузки
    path('positions/<int:pk>/teaching-fact/',
         views.TeachingLoadFactView.as_view(),
         name='teaching_load_fact'),
    # Переключение текущей позиции преподавателя
    path('set-position/', views.SetCurrentPositionView.as_view(), name='set_current_position'),

]