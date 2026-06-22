"""
Миграция: добавление полей report_protocol_number и report_protocol_date
в ExportSettings для даты рассмотрения отчёта (отдельно от даты плана).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_exportsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportsettings',
            name='report_protocol_number',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Номер протокола (отчёт)',
                help_text='Номер протокола заседания кафедры для рассмотрения отчёта',
            ),
        ),
        migrations.AddField(
            model_name='exportsettings',
            name='report_protocol_date',
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name='Дата протокола (отчёт)',
                help_text='Дата заседания кафедры для рассмотрения отчёта',
            ),
        ),
    ]
