from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_teachingloaditem_cycle_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='teachingloaditem',
            name='period_label',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Исходный текст из col5 плана: «Третий семестр», «11 сессия (зимняя)» и т.д.',
                max_length=100,
                verbose_name='Период контроля',
            ),
        ),
        migrations.AddField(
            model_name='teachingloaditem',
            name='row_num',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text='Значение col1 из выгрузки 1С. Используется для сортировки в исходном порядке.',
                verbose_name='Порядковый номер строки',
            ),
        ),
    ]
