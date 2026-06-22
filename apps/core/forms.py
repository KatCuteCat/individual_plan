from django import forms
from django.core.exceptions import ValidationError
from .models import AcademicYear, TaskCategory, PositionWorkload, WorkType, ExportSettings


class AcademicYearForm(forms.ModelForm):
    """Форма создания/редактирования учебного года."""

    start_date = forms.DateField(
        label='Дата начала',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    end_date = forms.DateField(
        label='Дата окончания',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )

    copy_from = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='— не копировать —',
        label='Скопировать позиции из года',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=(
            'Если выбрано, после создания года в него будут '
            'автоматически перенесены все позиции преподавателей '
            'из указанного года (учебная нагрузка не переносится — '
            'она импортируется из 1С отдельно).'
        ),
    )
    copy_include_inactive = forms.BooleanField(
        required=False,
        initial=False,
        label='Включая неактивные позиции (декрет, творческий отпуск)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = AcademicYear
        fields = ['name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: 2026-2027',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop('copy_from', None)
            self.fields.pop('copy_include_inactive', None)
        else:
            self.fields['copy_from'].queryset = AcademicYear.objects.order_by('-start_date')

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({'end_date': 'Дата окончания должна быть позже даты начала.'})
        return cleaned_data


class PositionWorkloadForm(forms.ModelForm):
    """Форма редактирования норм нагрузки по должности."""

    class Meta:
        model = PositionWorkload
        fields = ['max_teaching_hours', 'max_total_hours']
        widgets = {
            'max_teaching_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
            }),
            'max_total_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
            }),
        }
        help_texts = {
            'max_teaching_hours': 'Верхний предел учебных часов для полной ставки (1.0). Для совместителей рассчитывается пропорционально.',
            'max_total_hours': 'Общий объём рабочего времени в год. Стандарт ВГТУ — 1550 ч.',
        }

class WorkTypeForm(forms.ModelForm):
    """Форма создания/редактирования вида работы."""

    class Meta:
        model = WorkType
        fields = ['name', 'category', 'max_hours', 'unit_description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Разработка рабочей программы дисциплины',
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'max_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
            }),
            'unit_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: на одну дисциплину, в год, за 1 печатный лист',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'max_hours': 'Максимум часов согласно нормативу ВГТУ.',
            'unit_description': 'Пояснение к единице измерения (необязательно).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # В выпадающем списке категорий не показываем «Учебную работу» —
        # она приходит из 1С и виды работ к ней не привязываются (см. п. 6.2 требований).
        self.fields['category'].queryset = TaskCategory.objects.exclude(
            code=TaskCategory.CODE_TEACHING
        ).filter(is_active=True)

class ExportSettingsForm(forms.ModelForm):
    """Форма настроек выгрузки индивидуального плана."""

    protocol_date = forms.DateField(
        label='Дата протокола',
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )
    report_protocol_date = forms.DateField(
        label='Дата протокола (отчёт)',
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'class': 'form-control', 'type': 'date'},
        ),
    )

    class Meta:
        model = ExportSettings
        fields = [
            'department_name',
            'department_full_name',
            'faculty_name',
            'approver_title',
            'approver_name',
            'head_name',
            'protocol_number',
            'protocol_date',
            'report_protocol_number',
            'report_protocol_date',
        ]
        widgets = {
            'department_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'КИТП',
            }),
            'department_full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Компьютерных интеллектуальных технологий проектирования',
            }),
            'faculty_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Факультет информационных технологий и компьютерной безопасности',
            }),
            'approver_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Декан факультета ИТ и КБ',
            }),
            'approver_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'И.И. Иванов',
            }),
            'head_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'П.П. Петрова',
            }),
            'protocol_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1',
            }),
            'report_protocol_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Номер протокола (отчёт)',
            }),
        }