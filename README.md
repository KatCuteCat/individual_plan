# Модуль контроля индивидуального плана преподавателя

Веб-приложение для автоматизации учёта и контроля выполнения индивидуальных планов преподавателей кафедры ВГТУ.

Система поддерживает три роли: **администратор**, **заведующий кафедрой**, **преподаватель**.

## Стек

- Python 3.10+
- Django 5.2
- PostgreSQL 14+
- Bootstrap 5
- openpyxl (импорт нагрузки из Excel)
- python-docx (выгрузка плана в Word)

## Развёртывание

### 1. Клонировать репозиторий

```bash
git clone https://github.com/KatCuteCat/individual_plan.git
cd individual_plan
```

### 2. Создать виртуальное окружение и установить зависимости

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 3. Создать базу данных PostgreSQL

```sql
CREATE DATABASE individual_plan_db;
CREATE USER individual_plan_user WITH PASSWORD '1234567';
GRANT ALL PRIVILEGES ON DATABASE individual_plan_db TO individual_plan_user;
```

### 4. Применить миграции и загрузить справочники

```bash
python manage.py migrate core 0010
python manage.py loaddata initial_data
python manage.py migrate
python manage.py loaddata category_limits
python manage.py loaddata teaching_activity_types
```

### 5. Создать администратора

```bash
python manage.py createsuperuser
python manage.py shell -c "from apps.accounts.models import User; u = User.objects.last(); u.role = 'admin'; u.save()"
```

### 6. Запустить сервер

```bash
python manage.py runserver
```

Приложение будет доступно по адресу http://127.0.0.1:8000

## Быстрый запуск с демоданными

В комплекте идёт файл `dump.sql` — дамп базы данных с готовыми пользователями, учебной нагрузкой и задачами. Для быстрого запуска с демоданными шаги 4 и 5 заменяются на:

```bash
python manage.py migrate
psql -U individual_plan_user -d individual_plan_db < dump.sql
```

После этого можно зайти в систему под существующими пользователями и посмотреть работу модуля со всеми заполненными данными.
