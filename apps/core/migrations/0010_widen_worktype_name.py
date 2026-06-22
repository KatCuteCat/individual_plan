from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_exportsettings_department_full_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='worktype',
            name='name',
            field=models.CharField(
                max_length=500,
                verbose_name='Название вида работы',
                help_text='Например: «Разработка рабочей программы дисциплины»',
            ),
        ),
    ]