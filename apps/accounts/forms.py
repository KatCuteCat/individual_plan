from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from .models import User, TeacherPosition


class LoginForm(AuthenticationForm):
    #Форма входа в систему

    username = forms.CharField(
        label='Имя пользователя',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите логин',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль',
        })
    )


class CustomPasswordChangeForm(PasswordChangeForm):
    """Форма смены пароля с Bootstrap-стилями."""

    old_password = forms.CharField(
        label='Текущий пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )
    new_password1 = forms.CharField(
        label='Новый пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )
    new_password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )


class UserCreateForm(forms.ModelForm):
    """Форма создания пользователя администратором."""

    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'role', 'academic_title']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'academic_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: кандидат наук, доцент',
            }),
        }

    def clean_password2(self):
        """Проверка совпадения паролей."""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Пароли не совпадают.')
        return password2

    def clean_username(self):
        """Проверка уникальности логина."""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Пользователь с таким логином уже существует.')
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """Форма редактирования пользователя (без смены пароля)."""

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'role', 'academic_title', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'academic_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: кандидат наук, доцент',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_username(self):
        """Проверка уникальности логина (исключая текущего пользователя)."""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Пользователь с таким логином уже существует.')
        return username


class UserSetPasswordForm(forms.Form):
    """Форма сброса пароля пользователю администратором."""

    new_password1 = forms.CharField(
        label='Новый пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )
    new_password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
        })
    )

    def clean_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Пароли не совпадают.')
        return password2


class TeacherPositionForm(forms.ModelForm):


    class Meta:
        model = TeacherPosition
        fields = [
            'employment_type',
            'position',
            'rate',
            'is_active',
            'notes',
        ]
        widgets = {
            'employment_type': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.Select(attrs={'class': 'form-select'}),
            'rate': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Например: декретный отпуск',
            }),
        }

    def __init__(self, *args, user=None, academic_year=None, **kwargs):

        super().__init__(*args, **kwargs)
        self._user = user
        self._academic_year = academic_year
        # Поле rate не обязательно на уровне формы — обязательность зависит
        # от employment_type и проверяется в clean() модели.
        self.fields['rate'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned = super().clean()
        # Подставляем user и academic_year на инстанс, чтобы model.clean()
        # мог проверить правило «одна MAIN на год».
        if self._user is not None:
            self.instance.user = self._user
        if self._academic_year is not None:
            self.instance.academic_year = self._academic_year
        try:
            self.instance.clean()
        except forms.ValidationError as exc:
            if hasattr(exc, 'error_dict'):
                for field, errors in exc.error_dict.items():
                    for error in errors:
                        self.add_error(field if field in self.fields else None, error)
            else:
                self.add_error(None, exc)
        return cleaned


class CopyPositionsForm(forms.Form):
    """
    Форма массового копирования позиций из одного учебного года в другой.
    """

    source_year = forms.ModelChoiceField(
        label='Год-источник',
        queryset=None,  # заполняется в __init__
        empty_label='— выберите год —',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Из какого года копировать позиции.',
    )
    include_inactive = forms.BooleanField(
        label='Копировать также неактивные позиции (декрет, творческий отпуск)',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='По умолчанию неактивные позиции пропускаются.',
    )
    overwrite_existing = forms.BooleanField(
        label='Перезаписывать существующие позиции',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text=(
            'Если в новом году уже есть позиция с тем же преподавателем, '
            'видом занятости и должностью — у неё обновятся ставка, заметки и '
            'флаг «Активна». По умолчанию такие позиции пропускаются.'
        ),
    )

    def __init__(self, *args, target_year=None, **kwargs):
        """
        target_year — учебный год-приёмник. Передаётся из view.
        Используется, чтобы исключить его самого из выпадающего списка
        и отрезать архивные годы.
        """
        super().__init__(*args, **kwargs)
        self._target_year = target_year

        # Импорт здесь, чтобы избежать циркулярного импорта между приложениями.
        from apps.core.models import AcademicYear

        qs = AcademicYear.objects.all().order_by('-start_date')
        if target_year is not None:
            qs = qs.exclude(pk=target_year.pk)

        self.fields['source_year'].queryset = qs

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get('source_year')
        target = self._target_year

        if target is None:
            raise forms.ValidationError('Не указан год-приёмник.')

        if getattr(target, 'is_archived', False):
            raise forms.ValidationError(
                'Нельзя копировать позиции в архивный учебный год.'
            )

        if source is not None and source.pk == target.pk:
            self.add_error(
                'source_year',
                'Год-источник и год-приёмник должны быть разными.',
            )

        return cleaned

    @property
    def on_conflict(self):

        from .services import ON_CONFLICT_OVERWRITE, ON_CONFLICT_SKIP
        return (
            ON_CONFLICT_OVERWRITE
            if self.cleaned_data.get('overwrite_existing')
            else ON_CONFLICT_SKIP
        )


class TeachingLoadImportForm(forms.Form):
    """
    Форма загрузки Excel-выгрузки учебной нагрузки из 1С на одну позицию.
    """

    file = forms.FileField(
        label='Файл выгрузки из 1С (.xlsx)',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx',
        }),
        help_text='Excel-файл с шапкой «Отчет о выполнении учебной нагрузки преподавателя».',
    )
    replace_existing = forms.BooleanField(
        label='Заменить существующие данные',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Если включено, все ранее загруженные строки учебной нагрузки этой '
                  'позиции будут удалены и заменены данными из нового файла. '
                  'Если выключено и нагрузка уже загружена — импорт будет отменён.',
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        name = (f.name or '').lower()
        if not name.endswith('.xlsx'):
            raise forms.ValidationError(
                'Поддерживается только формат .xlsx (Excel 2007+). '
                'Если у вас файл .xls — пересохраните его в Excel как .xlsx.'
            )
        # Лимит размера на всякий случай — 5 МБ
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Файл слишком большой. Максимум — 5 МБ.')
        return f