from decimal import Decimal
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_teacherposition_teaching_load_imported_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='teachingloaditem',
            name='cycle',
            field=models.CharField(
                blank=True, default='', max_length=50,
                verbose_name='Цикл дисциплины',
            ),
        ),
        migrations.AddField(
            model_name='teachingloaditem',
            name='students_count',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name='Число студентов',
            ),
        ),
        migrations.AddField(
            model_name='teachingloaditem',
            name='hours_fact',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'),
                max_digits=7, verbose_name='Часы (факт)',
            ),
        ),
    ]