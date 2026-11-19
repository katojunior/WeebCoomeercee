import datetime

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.admin.views.main import PAGE_VAR
from django.db import models
from django.utils import timezone


class DateRangeFilter(admin.FieldListFilter):
    """
    Filtro reutilizável de intervalo de datas (De / Até) com atalhos rápidos
    para uso no `list_filter` do Django Admin em campos DateField e DateTimeField.
    """

    template = 'admin/cadastro/filters/date_range_filter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_kwarg_start = f'{field_path}__range_start'
        self.lookup_kwarg_end = f'{field_path}__range_end'
        self.lookup_kwarg_isnull = f'{field_path}__isnull'

        self.field_generic = f'{field_path}__'
        self.start_value = ''
        self.end_value = ''
        self.isnull_value = None

        super().__init__(field, request, params, model, model_admin, field_path)

        self.start_value = self._extract_single_param(self.used_parameters.get(self.lookup_kwarg_start))
        self.end_value = self._extract_single_param(self.used_parameters.get(self.lookup_kwarg_end))
        raw_isnull = self.used_parameters.get(self.lookup_kwarg_isnull)
        if raw_isnull is not None:
            val = raw_isnull[-1] if isinstance(raw_isnull, list) else raw_isnull
            self.isnull_value = bool(val)

        today = timezone.localdate() if timezone.is_aware(timezone.now()) else datetime.date.today()
        first_day_month = today.replace(day=1)
        if today.month == 12:
            last_day_month = today.replace(year=today.year + 1, month=1, day=1) - datetime.timedelta(days=1)
        else:
            last_day_month = today.replace(month=today.month + 1, day=1) - datetime.timedelta(days=1)

        last_day_prev_month = first_day_month - datetime.timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)

        self.links = [
            ('Qualquer data', {}),
            (
                'Hoje',
                {
                    self.lookup_kwarg_start: today.isoformat(),
                    self.lookup_kwarg_end: today.isoformat(),
                },
            ),
            (
                'Últimos 7 dias',
                {
                    self.lookup_kwarg_start: (today - datetime.timedelta(days=6)).isoformat(),
                    self.lookup_kwarg_end: today.isoformat(),
                },
            ),
            (
                'Este mês',
                {
                    self.lookup_kwarg_start: first_day_month.isoformat(),
                    self.lookup_kwarg_end: last_day_month.isoformat(),
                },
            ),
            (
                'Mês passado',
                {
                    self.lookup_kwarg_start: first_day_prev_month.isoformat(),
                    self.lookup_kwarg_end: last_day_prev_month.isoformat(),
                },
            ),
        ]

        if field.null:
            self.links.extend([
                ('Sem data', {self.lookup_kwarg_isnull: 'True'}),
                ('Com data', {self.lookup_kwarg_isnull: 'False'}),
            ])

        self.preserved_params = []
        self.clear_query_string = ''

    @staticmethod
    def _extract_single_param(value):
        if value is None:
            return ''
        if isinstance(value, list):
            value = value[-1] if value else ''
        return str(value).strip()

    @staticmethod
    def _parse_date(value_str):
        if not value_str:
            return None
        try:
            return datetime.date.fromisoformat(value_str)
        except ValueError as exc:
            raise IncorrectLookupParameters(f'Data inválida informada no filtro: {value_str}') from exc

    def _make_aware_if_needed(self, dt):
        if settings.USE_TZ and timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    def _build_lookup_kwargs(self, start_str=None, end_str=None, isnull_val=None):
        lookups = {}
        if isnull_val is not None:
            lookups[self.lookup_kwarg_isnull] = isnull_val
            return lookups

        start_date = self._parse_date(start_str)
        end_date = self._parse_date(end_str)

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        if isinstance(self.field, models.DateTimeField):
            if start_date:
                start_dt = self._make_aware_if_needed(datetime.datetime.combine(start_date, datetime.time.min))
                lookups[f'{self.field_path}__gte'] = start_dt
            if end_date:
                next_day = end_date + datetime.timedelta(days=1)
                end_dt = self._make_aware_if_needed(datetime.datetime.combine(next_day, datetime.time.min))
                lookups[f'{self.field_path}__lt'] = end_dt
        else:
            if start_date:
                lookups[f'{self.field_path}__gte'] = start_date
            if end_date:
                lookups[f'{self.field_path}__lte'] = end_date

        return lookups

    def expected_parameters(self):
        params = [self.lookup_kwarg_start, self.lookup_kwarg_end]
        if self.field.null:
            params.append(self.lookup_kwarg_isnull)
        return params

    def has_output(self):
        return True

    @property
    def is_active(self):
        return bool(self.start_value or self.end_value or self.isnull_value is not None)

    def queryset(self, request, queryset):
        if not self.is_active:
            return queryset
        lookups = self._build_lookup_kwargs(
            start_str=self.start_value,
            end_str=self.end_value,
            isnull_val=self.isnull_value,
        )
        if not lookups:
            return queryset
        return queryset.filter(**lookups)

    def get_facet_counts(self, pk_attname, filtered_qs):
        counts = {}
        for i, (_, param_dict) in enumerate(self.links):
            if not param_dict:
                counts[f'{i}__c'] = models.Count(pk_attname)
                continue
            isnull_val = None
            if self.lookup_kwarg_isnull in param_dict:
                isnull_val = param_dict[self.lookup_kwarg_isnull] == 'True'
            lookups = self._build_lookup_kwargs(
                start_str=param_dict.get(self.lookup_kwarg_start),
                end_str=param_dict.get(self.lookup_kwarg_end),
                isnull_val=isnull_val,
            )
            counts[f'{i}__c'] = models.Count(pk_attname, filter=models.Q(**lookups))
        return counts

    def choices(self, changelist):
        excluded = set(self.expected_parameters()) | {PAGE_VAR}
        self.preserved_params = [
            (k, v)
            for k, vals in self.request.GET.lists()
            if k not in excluded
            for v in vals
        ]
        self.clear_query_string = changelist.get_query_string(
            remove=self.expected_parameters() + [PAGE_VAR]
        )

        active_params = {}
        if self.start_value:
            active_params[self.lookup_kwarg_start] = self.start_value
        if self.end_value:
            active_params[self.lookup_kwarg_end] = self.end_value
        if self.isnull_value is not None:
            active_params[self.lookup_kwarg_isnull] = 'True' if self.isnull_value else 'False'

        add_facets = changelist.add_facets
        facet_counts = self.get_facet_queryset(changelist) if add_facets else None

        for i, (title, param_dict) in enumerate(self.links):
            if add_facets:
                count = facet_counts[f'{i}__c']
                title = f'{title} ({count})'
            yield {
                'selected': active_params == param_dict,
                'query_string': changelist.get_query_string(
                    param_dict, self.expected_parameters() + [PAGE_VAR]
                ),
                'display': title,
            }
