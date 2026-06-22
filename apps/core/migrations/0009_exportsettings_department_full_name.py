# apps/core/migrations/0009_exportsettings_department_full_name.py
# Поместить в: apps/core/migrations/

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_exportsettings_report_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportsettings',
            name='department_full_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Полное название кафедры в родительном падеже, например: '
                          '«Компьютерных интеллектуальных технологий проектирования»',
                max_length=300,
                verbose_name='Полное название кафедры',
            ),
        ),
    ]
