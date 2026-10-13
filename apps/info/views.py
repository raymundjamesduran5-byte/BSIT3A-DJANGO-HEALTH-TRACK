
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import forms
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.forms import modelform_factory
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.scoping import scoped_info, scoped_infos
from apps.users.models import HealthTrackUser
from .models import (
    Exercise,
    HealthActivity,
    HealthGoal,
    HealthMeasurement,
    HealthProfile,
    HealthReminder,
    HealthReport,
    Info,
    Meal,
    SleepRecord,
    WaterIntake,
)

MIN_AGE = 1
MAX_AGE = 150


class HealthProfileForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
    )
    gender = forms.ChoiceField(
        required=False,
        choices=(('', 'Select gender'), *HealthTrackUser.GENDER_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    contact_number = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'tel'}),
    )

    class Meta:
        model = HealthProfile
        fields = (
            'height_cm', 'weight_kg', 'blood_type', 'allergies',
            'existing_conditions', 'emergency_contact_name', 'emergency_contact_number',
        )

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.fields['date_of_birth'].initial = account.date_of_birth
        self.fields['gender'].initial = account.gender
        self.fields['contact_number'].initial = account.contact_number


def _parse_age(raw_age):
    try:
        return int(raw_age)
    except (TypeError, ValueError):
        return None


@login_required(login_url='login')
def info_list_page(request):
    query = request.GET.get('q', '').strip()
    infos_list = scoped_infos(request.user).order_by('name')
    if query:
        infos_list = infos_list.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(email__icontains=query)
        )
    infos = Paginator(infos_list, 10).get_page(request.GET.get('page', 1))
    return render(request, 'info.html', {'infos': infos, 'query': query})


@login_required(login_url='login')
def info_list_ajax(request):
    query = request.GET.get('q', '').strip()
    infos_list = scoped_infos(request.user).order_by('name')
    if query:
        infos_list = infos_list.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(email__icontains=query)
        )
    infos = Paginator(infos_list, 10).get_page(request.GET.get('page', 1))
    data = list(infos.object_list.values('id', 'name', 'age', 'address', 'email'))
    return JsonResponse({
        'data': data,
        'has_next': infos.has_next(),
        'has_prev': infos.has_previous(),
        'page': infos.number,
        'pages': infos.paginator.num_pages,
        'total': infos.paginator.count,
    })


@login_required(login_url='login')
def info_get_ajax(request, pk):
    info = scoped_info(request.user, pk)
    return JsonResponse({
        'id': info.id,
        'name': info.name,
        'age': info.age,
        'address': info.address,
        'email': info.email,
    })


@login_required(login_url='login')
@require_POST
def info_save_ajax(request):
    info_id = request.POST.get('id')
    if info_id:
        info = scoped_info(request.user, info_id)
        is_update = True
    else:
        info = Info()
        is_update = False

    name = request.POST.get('name', '').strip()
    age = request.POST.get('age', '').strip()
    address = request.POST.get('address', '').strip()
    email = request.POST.get('email', '').strip()
    if not name:
        return JsonResponse({'error': 'Name is required.'}, status=400)
    if not age:
        return JsonResponse({'error': 'Age is required.'}, status=400)
    age_value = _parse_age(age)
    if age_value is None or age_value < MIN_AGE or age_value > MAX_AGE:
        return JsonResponse({'error': f'Age must be a number between {MIN_AGE} and {MAX_AGE}.'}, status=400)
    if not address:
        return JsonResponse({'error': 'Address is required.'}, status=400)
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({'error': 'Enter a valid email address.'}, status=400)

    info.name = name
    info.age = age_value
    info.address = address
    info.email = email
    if not info.pk:
        info.user = request.user
    try:
        info.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save record due to a conflict.'}, status=400)

    messages.success(request, f'Record "{info.name}" has been {"updated" if is_update else "saved"} successfully.')
    return JsonResponse({
        'status': 'success',
        'id': info.id,
        'name': info.name,
        'age': info.age,
        'address': info.address,
        'email': info.email,
    })


@login_required(login_url='login')
@require_POST
def info_delete_ajax(request, pk):
    info = scoped_info(request.user, pk)
    info_name = info.name
    info.delete()
    messages.success(request, f'Record "{info_name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


HEALTH_RESOURCES = {
    'profile': {
        'model': HealthProfile, 'title': 'Health profile',
        'fields': ('height_cm', 'weight_kg', 'blood_type', 'allergies', 'existing_conditions', 'emergency_contact_name', 'emergency_contact_number'),
        'columns': ('height_cm', 'weight_kg', 'blood_type', 'allergies', 'updated_at'),
        'search': ('blood_type', 'allergies', 'existing_conditions'),
    },
    'activities': {
        'model': HealthActivity, 'title': 'Daily activities',
        'fields': ('activity_date', 'steps', 'calories_burned', 'mood', 'stress_level', 'notes'),
        'columns': ('activity_date', 'steps', 'calories_burned', 'mood', 'stress_level'),
        'search': ('mood', 'stress_level', 'notes'),
    },
    'exercises': {
        'model': Exercise, 'title': 'Exercise',
        'fields': ('exercise_date', 'exercise_type', 'duration_minutes', 'calories_burned', 'intensity', 'notes'),
        'columns': ('exercise_date', 'exercise_type', 'duration_minutes', 'intensity', 'calories_burned'),
        'search': ('exercise_type', 'intensity', 'notes'),
    },
    'sleep': {
        'model': SleepRecord, 'title': 'Sleep',
        'fields': ('sleep_date', 'bedtime', 'wake_time', 'sleep_quality', 'notes'),
        'columns': ('sleep_date', 'bedtime', 'wake_time', 'total_hours', 'sleep_quality'),
        'search': ('sleep_quality', 'notes'),
    },
    'water': {
        'model': WaterIntake, 'title': 'Water intake',
        'fields': ('intake_date', 'intake_time', 'amount_ml'),
        'columns': ('intake_date', 'intake_time', 'amount_ml'), 'search': (),
    },
    'meals': {
        'model': Meal, 'title': 'Meals',
        'fields': ('meal_date', 'meal_type', 'meal_description', 'calories', 'notes'),
        'columns': ('meal_date', 'meal_type', 'meal_description', 'calories'),
        'search': ('meal_type', 'meal_description', 'notes'),
    },
    'goals': {
        'model': HealthGoal, 'title': 'Health goals',
        'fields': ('goal_name', 'description', 'target_value', 'current_value', 'unit', 'start_date', 'target_date', 'status'),
        'columns': ('goal_name', 'current_value', 'target_value', 'unit', 'target_date', 'status'),
        'search': ('goal_name', 'description', 'status'),
    },
    'measurements': {
        'model': HealthMeasurement, 'title': 'Measurements',
        'fields': ('measurement_date', 'systolic_bp', 'diastolic_bp', 'heart_rate', 'temperature', 'blood_sugar', 'weight_kg', 'notes'),
        'columns': ('measurement_date', 'systolic_bp', 'diastolic_bp', 'heart_rate', 'temperature', 'blood_sugar', 'weight_kg'),
        'search': ('notes',),
    },
    'reminders': {
        'model': HealthReminder, 'title': 'Reminders',
        'fields': ('reminder_title', 'description', 'reminder_date', 'reminder_time', 'reminder_type', 'status'),
        'columns': ('reminder_title', 'reminder_date', 'reminder_time', 'reminder_type', 'status'),
        'search': ('reminder_title', 'description', 'reminder_type', 'status'),
    },
    'reports': {
        'model': HealthReport, 'title': 'Health reports',
        'fields': ('report_date', 'report_period', 'summary', 'recommendations'),
        'columns': ('report_date', 'report_period', 'summary', 'created_at'),
        'search': ('report_period', 'summary', 'recommendations'),
    },
}


def _health_account(auth_user):
    if not auth_user.email:
        return None
    return HealthTrackUser.objects.filter(email__iexact=auth_user.email).first()


def _health_resource(slug):
    try:
        return HEALTH_RESOURCES[slug]
    except KeyError as exc:
        raise Http404('Health record type not found.') from exc


def _health_form_class(resource):
    if resource['model'] is HealthProfile:
        return HealthProfileForm

    form_class = modelform_factory(resource['model'], fields=resource['fields'])
    for name, field in form_class.base_fields.items():
        model_field = resource['model']._meta.get_field(name)
        field.widget.attrs['class'] = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
        if model_field.get_internal_type() == 'DateField':
            field.widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'})
        elif model_field.get_internal_type() == 'TimeField':
            field.widget = forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control'})
        elif model_field.get_internal_type() == 'DateTimeField':
            field.widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})
            field.input_formats = ['%Y-%m-%dT%H:%M', *field.input_formats]
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs['rows'] = 3
    return form_class


def _save_health_profile(form, account):
    with transaction.atomic():
        profile = form.save(commit=False)
        profile.user = account
        profile.save()

        account.date_of_birth = form.cleaned_data['date_of_birth']
        account.gender = form.cleaned_data['gender']
        account.contact_number = form.cleaned_data['contact_number']
        account.save(update_fields=['date_of_birth', 'gender', 'contact_number'])
    return profile


def _health_columns(record, resource):
    columns = []
    for name in resource['columns']:
        model_field = resource['model']._meta.get_field(name)
        value = getattr(record, name)
        if model_field.choices:
            value = getattr(record, f'get_{name}_display')()
        elif value is None or value == '':
            value = '—'
        elif hasattr(value, 'strftime'):
            if name in ('measurement_date', 'updated_at', 'created_at'):
                value = timezone.localtime(value).strftime('%b %d, %Y %H:%M')
            elif name.endswith('_date'):
                value = value.strftime('%b %d, %Y')
            else:
                value = value.strftime('%H:%M')
        columns.append({'label': model_field.verbose_name.title(), 'value': value})
    return columns


@login_required(login_url='login')
def health_list(request, slug):
    resource = _health_resource(slug)
    query = request.GET.get('q', '').strip()
    records = resource['model'].objects.filter(user=_health_account(request.user))
    if query and resource['search']:
        search_filter = Q()
        for field in resource['search']:
            search_filter |= Q(**{f'{field}__icontains': query})
        records = records.filter(search_filter)
    page = Paginator(records, 12).get_page(request.GET.get('page', 1))
    rows = [
        {
            'record': record,
            'columns': _health_columns(record, resource),
            'status': getattr(record, 'status', None),
        }
        for record in page.object_list
    ]
    column_headers = [
        {'label': resource['model']._meta.get_field(name).verbose_name.title()}
        for name in resource['columns']
    ]
    return render(request, 'health/record_list.html', {
        'resource': resource,
        'slug': slug,
        'query': query,
        'records': page,
        'rows': rows,
        'column_headers': column_headers,
    })


@login_required(login_url='login')
def health_create(request, slug):
    resource = _health_resource(slug)
    health_user = _health_account(request.user)
    if resource['model'] is HealthProfile:
        profile = HealthProfile.objects.filter(user=health_user).first()
        if profile:
            return redirect('info:health_edit', slug=slug, pk=profile.pk)
    form_class = _health_form_class(resource)
    if resource['model'] is HealthProfile:
        form = form_class(request.POST or None, account=health_user)
    else:
        form = form_class(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if resource['model'] is HealthProfile:
            _save_health_profile(form, health_user)
        else:
            record = form.save(commit=False)
            record.user = health_user
            record.save()
        messages.success(request, f'{resource["title"]} saved.')
        return redirect('info:health_list', slug=slug)
    return render(request, 'health/record_form.html', {
        'resource': resource, 'slug': slug, 'form': form, 'is_edit': False,
    })


@login_required(login_url='login')
def health_edit(request, slug, pk):
    resource = _health_resource(slug)
    health_user = _health_account(request.user)
    record = get_object_or_404(resource['model'], pk=pk, user=health_user)
    form_class = _health_form_class(resource)
    if resource['model'] is HealthProfile:
        form = form_class(request.POST or None, instance=record, account=health_user)
    else:
        form = form_class(request.POST or None, instance=record)
    if request.method == 'POST' and form.is_valid():
        if resource['model'] is HealthProfile:
            _save_health_profile(form, health_user)
        else:
            form.save()
        messages.success(request, f'{resource["title"]} updated.')
        return redirect('info:health_list', slug=slug)
    return render(request, 'health/record_form.html', {
        'resource': resource, 'slug': slug, 'form': form, 'is_edit': True,
    })


@login_required(login_url='login')
@require_POST
def health_delete(request, slug, pk):
    resource = _health_resource(slug)
    record = get_object_or_404(resource['model'], pk=pk, user=_health_account(request.user))
    record.delete()
    messages.success(request, f'{resource["title"]} deleted.')
    return redirect('info:health_list', slug=slug)


@login_required(login_url='login')
@require_POST
def health_status(request, slug, pk):
    """Quick status change (e.g. mark a reminder completed or cancelled)."""
    resource = _health_resource(slug)
    model = resource['model']
    try:
        status_field = model._meta.get_field('status')
    except FieldDoesNotExist:
        messages.error(request, f'{resource["title"]} do not have a status.')
        return redirect('info:health_list', slug=slug)

    record = get_object_or_404(model, pk=pk, user=_health_account(request.user))
    new_status = request.POST.get('status', '').strip()
    allowed = {value for value, _label in status_field.choices}
    if new_status not in allowed:
        messages.error(request, 'Unknown status value.')
        return redirect('info:health_list', slug=slug)

    record.status = new_status
    record.save(update_fields=['status'])
    messages.success(request, f'{resource["title"]} marked as {new_status.lower()}.')
    return redirect('info:health_list', slug=slug)


@login_required(login_url='login')
def health_dashboard(request):
    today = timezone.localdate()
    user = _health_account(request.user)
    display_user = user or request.user
    current_hour = timezone.localtime().hour
    greeting = 'morning' if current_hour < 12 else 'afternoon' if current_hour < 18 else 'evening'
    activities = HealthActivity.objects.filter(user=user, activity_date=today)
    steps_today = activities.aggregate(total=Sum('steps'))['total'] or 0
    water_today = WaterIntake.objects.filter(user=user, intake_date=today).aggregate(total=Sum('amount_ml'))['total'] or 0
    exercise_today = Exercise.objects.filter(user=user, exercise_date=today).aggregate(total=Sum('duration_minutes'))['total'] or 0
    activity_calories = activities.aggregate(total=Sum('calories_burned'))['total'] or 0
    exercise_calories = Exercise.objects.filter(user=user, exercise_date=today).aggregate(total=Sum('calories_burned'))['total'] or 0
    calories_today = activity_calories + exercise_calories
    latest_sleep = SleepRecord.objects.filter(user=user).first()
    sleep_hours = latest_sleep.total_hours if latest_sleep else 0
    goals = list(HealthGoal.objects.filter(
        user=user,
        status__in=[HealthGoal.Status.NOT_STARTED, HealthGoal.Status.IN_PROGRESS],
    ).order_by('target_date', 'goal_name')[:4])
    for goal in goals:
        goal.progress = min(round(float(goal.current_value / goal.target_value * 100)), 100) if goal.target_value else 0

    reminders_query = HealthReminder.objects.filter(
        user=user,
        reminder_date__gte=today,
        status=HealthReminder.Status.PENDING,
    )
    upcoming_reminders = reminders_query[:4]

    measurement_specs = [
        {'key': 'heart_rate', 'label': 'Heart rate', 'unit': 'bpm', 'icon': 'fa-heart-pulse', 'color': 'coral'},
        {'key': 'blood_pressure', 'label': 'Blood pressure', 'unit': 'mmHg', 'icon': 'fa-gauge-high', 'color': 'blue'},
        {'key': 'temperature', 'label': 'Temperature', 'unit': '°C', 'icon': 'fa-temperature-half', 'color': 'gold'},
        {'key': 'blood_sugar', 'label': 'Blood sugar', 'unit': 'mg/dL', 'icon': 'fa-droplet', 'color': 'green'},
        {'key': 'weight_kg', 'label': 'Weight', 'unit': 'kg', 'icon': 'fa-weight-scale', 'color': 'mint'},
    ]
    body_metrics = []
    for spec in measurement_specs:
        measurements = HealthMeasurement.objects.filter(user=user)
        if spec['key'] == 'blood_pressure':
            measurements = measurements.filter(
                Q(systolic_bp__isnull=False) | Q(diastolic_bp__isnull=False)
            )
        else:
            measurements = measurements.exclude(**{f"{spec['key']}__isnull": True})
        measurement = measurements.first()
        if measurement is None:
            reading = 'No reading'
            recorded_at = 'Log a measurement to see it here'
        elif spec['key'] == 'blood_pressure':
            systolic = measurement.systolic_bp or '—'
            diastolic = measurement.diastolic_bp or '—'
            reading = f'{systolic}/{diastolic}'
            recorded_at = timezone.localtime(measurement.measurement_date).strftime('Recorded %b %d, %Y')
        else:
            reading = str(getattr(measurement, spec['key']))
            recorded_at = timezone.localtime(measurement.measurement_date).strftime('Recorded %b %d, %Y')
        body_metrics.append({**spec, 'reading': reading, 'recorded_at': recorded_at})

    body_regions = [
        {'label': 'Head', 'key': 'head', 'metric': 'temperature', 'front_x': 29, 'front_y': 12, 'back_x': 72, 'back_y': 12, 'color': 'gold'},
        {'label': 'Neck', 'key': 'neck', 'metric': 'heart_rate', 'front_x': 29, 'front_y': 21, 'back_x': 72, 'back_y': 21, 'color': 'coral'},
        {'label': 'Chest', 'key': 'chest', 'metric': 'blood_pressure', 'front_x': 29, 'front_y': 35, 'back_x': 72, 'back_y': 35, 'color': 'blue'},
        {'label': 'Abdomen', 'key': 'abdomen', 'metric': 'blood_sugar', 'front_x': 29, 'front_y': 49, 'back_x': 72, 'back_y': 49, 'color': 'green'},
        {'label': 'Back', 'key': 'back', 'metric': 'blood_pressure', 'front_x': 29, 'front_y': 43, 'back_x': 72, 'back_y': 43, 'color': 'blue'},
        {'label': 'Left arm', 'key': 'left_arm', 'metric': 'blood_pressure', 'front_x': 41, 'front_y': 40, 'back_x': 59, 'back_y': 40, 'color': 'blue'},
        {'label': 'Right arm', 'key': 'right_arm', 'metric': 'heart_rate', 'front_x': 17, 'front_y': 40, 'back_x': 85, 'back_y': 40, 'color': 'coral'},
        {'label': 'Left hand', 'key': 'left_hand', 'metric': 'blood_sugar', 'front_x': 46, 'front_y': 54, 'back_x': 54, 'back_y': 54, 'color': 'green'},
        {'label': 'Right hand', 'key': 'right_hand', 'metric': 'blood_sugar', 'front_x': 12, 'front_y': 54, 'back_x': 90, 'back_y': 54, 'color': 'green'},
        {'label': 'Left leg', 'key': 'left_leg', 'metric': 'weight_kg', 'front_x': 34, 'front_y': 73, 'back_x': 77, 'back_y': 73, 'color': 'mint'},
        {'label': 'Right leg', 'key': 'right_leg', 'metric': 'weight_kg', 'front_x': 24, 'front_y': 73, 'back_x': 67, 'back_y': 73, 'color': 'mint'},
        {'label': 'Left foot', 'key': 'left_foot', 'metric': 'weight_kg', 'front_x': 34, 'front_y': 94, 'back_x': 77, 'back_y': 94, 'color': 'gold'},
        {'label': 'Right foot', 'key': 'right_foot', 'metric': 'weight_kg', 'front_x': 24, 'front_y': 94, 'back_x': 67, 'back_y': 94, 'color': 'gold'},
    ]

    recent_records = []
    record_sources = [
        (HealthActivity, 'activity_date', 'Activity', lambda record: f'{record.steps:,} steps'),
        (Exercise, 'exercise_date', 'Exercise', lambda record: f'{record.exercise_type} · {record.duration_minutes} min'),
        (SleepRecord, 'sleep_date', 'Sleep', lambda record: f'{record.total_hours} hours · {record.sleep_quality or "Quality not set"}'),
        (WaterIntake, 'intake_date', 'Water', lambda record: f'{record.amount_ml:,} ml'),
        (Meal, 'meal_date', 'Meal', lambda record: f'{record.meal_type} · {record.meal_description or "Meal logged"}'),
        (HealthMeasurement, 'measurement_date', 'Measurement', lambda record: ', '.join(
            f'{label} {getattr(record, field)}{unit}'
            for field, label, unit in (
                ('systolic_bp', 'BP', ''), ('heart_rate', 'HR', ' bpm'),
                ('temperature', 'Temp', '°C'), ('weight_kg', 'Weight', ' kg'),
            ) if getattr(record, field) is not None
        ) or 'Health reading'),
    ]
    for model, date_field, category, summary in record_sources:
        for record in model.objects.filter(user=user).order_by(f'-{date_field}')[:5]:
            record_date = getattr(record, date_field)
            recent_records.append({
                'date': record_date,
                'date_label': timezone.localtime(record_date).strftime('%b %d, %Y') if hasattr(record_date, 'hour') else record_date.strftime('%b %d, %Y'),
                'category': category,
                'details': summary(record),
            })
    recent_records.sort(key=lambda record: record['date'].isoformat(), reverse=True)

    return render(request, 'home.html', {
        'today': today,
        'current_hour': current_hour,
        'current_time': timezone.localtime().strftime('%I:%M %p').lstrip('0'),
        'greeting': greeting,
        'steps_today': steps_today,
        'steps_progress': min(round(steps_today / 8000 * 100), 100),
        'water_today': water_today,
        'water_progress': min(round(water_today / 2000 * 100), 100),
        'exercise_today': exercise_today,
        'calories_today': calories_today,
        'calories_progress': min(round(float(calories_today) / 500 * 100), 100),
        'latest_sleep': latest_sleep,
        'sleep_hours': sleep_hours,
        'sleep_progress': min(round(float(sleep_hours) / 8 * 100), 100),
        'health_user': display_user,
        'health_age': (today.year - display_user.date_of_birth.year - ((today.month, today.day) < (display_user.date_of_birth.month, display_user.date_of_birth.day))) if getattr(display_user, 'date_of_birth', None) else None,
        'health_profile': HealthProfile.objects.filter(user=user).first(),
        'goals': goals,
        'reminder_count': reminders_query.count(),
        'body_metrics': body_metrics,
        'body_regions': body_regions,
        'upcoming_reminders': upcoming_reminders,
        'recent_records': recent_records[:5],
        'activity_count': HealthActivity.objects.filter(user=user).count(),
        'goal_count': len(goals),
    })