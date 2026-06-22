from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_taskcategory_is_archived'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoryLimit',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('min_percent', models.DecimalField(
                    decimal_places=2, default=0, max_digits=5,
                    help_text='Минимальный процент от объёма второй половины дня. '
                              '0 — если в приказе минимум не установлен.',
                    verbose_name='Минимум, %',
                )),
                ('max_percent', models.DecimalField(
                    decimal_places=2, max_digits=5,
                    help_text='Максимальный процент от объёма второй половины дня.',
                    verbose_name='Максимум, %',
                )),
                ('regulation_point', models.CharField(
                    blank=True, default='', max_length=50,
                    help_text='Ссылка на пункт приказа ВГТУ, например «4.1, абз. 1».',
                    verbose_name='Пункт приказа',
                )),
                ('notes', models.TextField(
                    blank=True, default='',
                    verbose_name='Примечания',
                )),
                ('category', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='limits',
                    to='core.taskcategory',
                    verbose_name='Категория',
                )),
                ('position', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=models.deletion.CASCADE,
                    related_name='category_limits',
                    to='core.position',
                    help_text='Если не указана — лимит применяется ко всем должностям.',
                    verbose_name='Должность',
                )),
            ],
            options={
                'verbose_name': 'Лимит по категории',
                'verbose_name_plural': 'Лимиты по категориям',
                'ordering': ['category', 'position'],
                'unique_together': {('category', 'position')},
            },
        ),
    ]