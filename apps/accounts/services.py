

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from django.db import transaction

from .models import TeacherPosition



ON_CONFLICT_SKIP = 'skip'
ON_CONFLICT_OVERWRITE = 'overwrite'

ON_CONFLICT_CHOICES = (ON_CONFLICT_SKIP, ON_CONFLICT_OVERWRITE)



@dataclass
class CopyPositionEntry:
    """Одна строка в отчёте по копированию: что произошло с одной позицией."""
    source_position: TeacherPosition
    action: str  # 'create' | 'update' | 'skip_duplicate' | 'skip_inactive'
    target_position: Optional[TeacherPosition] = None  # None для skip_*
    note: str = ''


@dataclass
class CopyPositionsResult:
    """Итоговый отчёт по операции копирования"""
    source_year_id: int
    target_year_id: int
    entries: List[CopyPositionEntry] = field(default_factory=list)

    @property
    def created_count(self):
        return sum(1 for e in self.entries if e.action == 'create')

    @property
    def updated_count(self):
        return sum(1 for e in self.entries if e.action == 'update')

    @property
    def skipped_duplicates_count(self):
        return sum(1 for e in self.entries if e.action == 'skip_duplicate')

    @property
    def skipped_inactive_count(self):
        return sum(1 for e in self.entries if e.action == 'skip_inactive')

    @property
    def total_processed(self):
        return len(self.entries)

    @property
    def total_changed(self):
        return self.created_count + self.updated_count



def _build_source_qs(source_year, include_inactive: bool):
    qs = TeacherPosition.objects.filter(
        academic_year=source_year,
    ).select_related('user', 'position', 'academic_year').order_by(
        'user__full_name', 'employment_type', 'position__name'
    )
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return qs


def _make_copy_kwargs(source: TeacherPosition, target_year):

    return dict(
        user=source.user,
        academic_year=target_year,
        employment_type=source.employment_type,
        position=source.position,
        rate=source.rate,
        teaching_hours=Decimal('0'),
        protocol_number='',
        protocol_date=None,
        is_active=source.is_active,
        notes=source.notes,
    )


def _find_duplicate(source: TeacherPosition, target_year):

    return TeacherPosition.objects.filter(
        user_id=source.user_id,
        academic_year=target_year,
        employment_type=source.employment_type,
        position_id=source.position_id,
    ).first()



def preview_copy_positions(
    source_year,
    target_year,
    include_inactive: bool = False,
    on_conflict: str = ON_CONFLICT_SKIP,
) -> CopyPositionsResult:

    if on_conflict not in ON_CONFLICT_CHOICES:
        raise ValueError(f'Неизвестная стратегия конфликта: {on_conflict!r}')

    result = CopyPositionsResult(
        source_year_id=source_year.pk,
        target_year_id=target_year.pk,
    )

    # Позиции-источники, активные (а если include_inactive — то и неактивные)
    sources = list(_build_source_qs(source_year, include_inactive=True))

    for src in sources:
        # Неактивные обрабатываем отдельно: либо пропускаем сразу,
        # либо обрабатываем как обычно
        if not src.is_active and not include_inactive:
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='skip_inactive',
                note='Позиция неактивна, пропуск (галочка не включена).',
            ))
            continue

        duplicate = _find_duplicate(src, target_year)

        if duplicate is None:
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='create',
                note='Будет создана.',
            ))
            continue

        if on_conflict == ON_CONFLICT_SKIP:
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='skip_duplicate',
                target_position=duplicate,
                note='Такая позиция уже есть в новом году — пропуск.',
            ))
        else:  # ON_CONFLICT_OVERWRITE
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='update',
                target_position=duplicate,
                note='Существующая позиция будет обновлена (rate, notes, is_active).',
            ))

    return result


@transaction.atomic
def copy_positions(
    source_year,
    target_year,
    include_inactive: bool = False,
    on_conflict: str = ON_CONFLICT_SKIP,
) -> CopyPositionsResult:

    if on_conflict not in ON_CONFLICT_CHOICES:
        raise ValueError(f'Неизвестная стратегия конфликта: {on_conflict!r}')
    if source_year.pk == target_year.pk:
        raise ValueError('source_year и target_year должны быть разными.')
    if getattr(target_year, 'is_archived', False):
        raise ValueError('Нельзя копировать позиции в архивный год.')

    result = CopyPositionsResult(
        source_year_id=source_year.pk,
        target_year_id=target_year.pk,
    )

    sources = list(_build_source_qs(source_year, include_inactive=True))

    for src in sources:
        if not src.is_active and not include_inactive:
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='skip_inactive',
                note='Позиция неактивна, пропуск.',
            ))
            continue

        duplicate = _find_duplicate(src, target_year)

        if duplicate is None:
            # Создаём новую
            new_pos = TeacherPosition(**_make_copy_kwargs(src, target_year))

            new_pos.full_clean()
            new_pos.save()
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='create',
                target_position=new_pos,
                note='Создана.',
            ))
            continue

        # Есть дубликат
        if on_conflict == ON_CONFLICT_SKIP:
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='skip_duplicate',
                target_position=duplicate,
                note='Уже существует — пропуск.',
            ))
        else:
            duplicate.rate = src.rate
            duplicate.notes = src.notes
            duplicate.is_active = src.is_active
            duplicate.full_clean()
            duplicate.save(update_fields=['rate', 'notes', 'is_active', 'updated_at'])
            result.entries.append(CopyPositionEntry(
                source_position=src,
                action='update',
                target_position=duplicate,
                note='Обновлены rate, notes, is_active.',
            ))

    return result