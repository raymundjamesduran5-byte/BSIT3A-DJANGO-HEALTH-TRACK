"""Local rule-based answers grounded in the signed-in user's health records."""

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils import timezone

from apps.core.daily_recommendation_service import (
    answer_water_adequacy,
    calculate_sleep_duration,
    format_number,
    get_daily_progress,
    get_daily_wellness_plan,
)
from apps.info.models import (
    Exercise,
    HealthActivity,
    HealthGoal,
    HealthMeasurement,
    HealthReminder,
    HealthReport,
    Meal,
    SleepRecord,
    WaterIntake,
)
from apps.users.models import HealthTrackUser

MAX_MESSAGE_LENGTH = 500

INTENT_PHRASES = {
    'steps': ('step', 'steps', 'walking', 'walked'),
    'water': ('water', 'hydration', 'drink', 'drank'),
    'sleep': ('sleep', 'slept', 'bedtime'),
    'exercise': ('exercise', 'workout', 'training'),
    'meals': ('meal', 'meals', 'food', 'eat', 'eating', 'ate', 'eaten', 'breakfast', 'lunch', 'dinner', 'snack'),
    'goals': ('goal', 'goals', 'target progress'),
    'measurements': (
        'measurement', 'measurements', 'blood pressure', 'heart rate',
        'temperature', 'blood sugar', 'weight', 'pulse', 'vitals',
    ),
    'reminders': ('reminder', 'reminders'),
    'reports': ('report', 'reports', 'health summary'),
}

GREETING_PHRASES = ('hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening')
URGENT_PHRASES = (
    'chest pain', "can't breathe", 'cannot breathe', 'difficulty breathing',
    'unconscious', 'severe bleeding', 'stroke symptoms',
)
MEDICAL_ADVICE_PHRASES = (
    'diagnose', 'diagnosis', 'prescribe', 'prescription', 'medication dose',
    'change my medication', 'stop taking', 'treatment plan',
)


def _contains_phrase(text, phrase):
    return re.search(rf'(?<!\w){re.escape(phrase)}(?!\w)', text) is not None


def _unavailable(item):
    return f'I can’t find any recorded {item} for your account in the requested period.'


def _account_missing():
    return 'Your health-record account is not linked yet, so I can’t retrieve health records.'


def _display_date(value):
    return value.strftime('%b %d, %Y').replace(' 0', ' ')


def _format_decimal(value):
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def answer_steps(user, question, today):
    if user is None:
        return _account_missing()

    if any(_contains_phrase(question, word) for word in ('week', 'weekly', '7 days', 'seven days')):
        start = today - timedelta(days=6)
        records = HealthActivity.objects.filter(user=user, activity_date__range=(start, today))
        period = f'the last 7 days ({_display_date(start)}–{_display_date(today)})'
    else:
        day = today - timedelta(days=1) if _contains_phrase(question, 'yesterday') else today
        records = HealthActivity.objects.filter(user=user, activity_date=day)
        period = _display_date(day)

    if not records.exists():
        return _unavailable(f'daily step totals for {period}')
    total = sum(record.steps for record in records)
    return f'You recorded {total:,} steps for {period}.'


def answer_water(user, question, today):
    if user is None:
        return _account_missing()
    day = today - timedelta(days=1) if _contains_phrase(question, 'yesterday') else today
    records = WaterIntake.objects.filter(user=user, intake_date=day)
    if not records.exists():
        return _unavailable(f'water intake for {_display_date(day)}')
    total = sum(record.amount_ml for record in records)
    return f'You recorded {total:,} ml of water for {_display_date(day)}.'


def answer_sleep(user, question, today):
    if user is None:
        return _account_missing()
    record = SleepRecord.objects.filter(user=user, sleep_date__lte=today).first()
    if record is None:
        return _unavailable('sleep')
    duration_value, issue = calculate_sleep_duration(record)
    if issue:
        duration = issue
    else:
        duration = f'{format_number(duration_value)} hours, calculated from the saved bedtime and wake time'
    quality = record.sleep_quality or 'quality not recorded'
    response = f'Your latest sleep record ({_display_date(record.sleep_date)}) shows {duration}; recorded quality: {quality}.'
    if any(_contains_phrase(question, phrase) for phrase in ('improve', 'better', 'how can i')):
        response += (
            ' General ideas: keep a routine that fits your schedule, allow a quiet wind-down period, '
            'and record bedtime, wake time, and how rested you feel. These are not treatment advice.'
        )
    return response


def answer_exercise(user, question, today):
    if user is None:
        return _account_missing()
    start = today - timedelta(days=6)
    records = list(Exercise.objects.filter(
        user=user,
        exercise_date__range=(start, today),
    )[:5])
    if not records:
        return _unavailable(f'exercise for the last 7 days ({_display_date(start)}–{_display_date(today)})')
    entries = [
        f'{_display_date(record.exercise_date)}: {record.exercise_type}, {record.duration_minutes} min'
        for record in records
    ]
    return 'Your recent exercise records: ' + '; '.join(entries) + '.'


def answer_meals(user, question, today):
    if user is None:
        return _account_missing()
    day = today - timedelta(days=1) if _contains_phrase(question, 'yesterday') else today
    records = list(Meal.objects.filter(user=user, meal_date=day)[:10])
    if not records:
        return _unavailable(f'meals for {_display_date(day)}')
    entries = []
    for record in records:
        description = record.meal_description.strip() or 'description not recorded'
        calories = (
            f' ({_format_decimal(record.calories)} kcal)'
            if record.calories is not None
            else ''
        )
        entries.append(f'{record.meal_type}: {description}{calories}')
    return f'Meals recorded for {_display_date(day)}: ' + '; '.join(entries) + '.'


def answer_goals(user, question, today):
    if user is None:
        return _account_missing()
    goals = list(HealthGoal.objects.filter(user=user))
    if not goals:
        return _unavailable('health goals')

    results = []
    for goal in goals:
        current = goal.current_value
        target = goal.target_value
        details = [f'status: {goal.status}']
        unit = goal.unit.strip()
        current_text = format_number(current) if current is not None else None
        target_text = format_number(target) if target is not None else None
        details.append(
            f'current: {current_text} {unit}'.strip()
            if current_text is not None
            else f'current value {"not recorded" if current is None else "invalid"} {unit}'.strip()
        )
        details.append(
            f'target: {target_text} {unit}'.strip()
            if target_text is not None
            else f'target {"not recorded" if target is None else "invalid"} {unit}'.strip()
        )

        if goal.start_date:
            details.append(f'started {_display_date(goal.start_date)}')
        else:
            details.append('start date not recorded')
        if goal.target_date:
            details.append(f'target date {_display_date(goal.target_date)}')
        else:
            details.append('target date not recorded')

        valid_dates = not (goal.start_date and goal.target_date and goal.start_date > goal.target_date)
        try:
            current_decimal = Decimal(str(current)) if current is not None else None
            target_decimal = Decimal(str(target)) if target is not None else None
        except (InvalidOperation, TypeError, ValueError):
            current_decimal = None
            target_decimal = None

        valid_values = (
            current_decimal is not None
            and target_decimal is not None
            and current_decimal.is_finite()
            and target_decimal.is_finite()
            and current_decimal >= 0
            and target_decimal > 0
            and bool(unit)
        )
        goal_text = f'{goal.goal_name} {goal.description}'.casefold()
        lower_is_better = any(
            term in goal_text
            for term in ('lose', 'loss', 'lower', 'reduce', 'decrease', 'weight loss', 'lowering')
        )
        if valid_values and valid_dates and lower_is_better:
            if current_decimal <= target_decimal:
                details.append('target reached')
            else:
                details.append('target not yet reached; starting value is needed to calculate progress')
        elif valid_values and valid_dates:
            percentage = (current_decimal / target_decimal * 100).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
            if current_decimal > target_decimal:
                details.append(f'target surpassed ({format_number(percentage)}% of target)')
            elif current_decimal == target_decimal:
                details.append('target reached (100% of target)')
            else:
                details.append(f'{format_number(percentage)}% of target')
        else:
            details.append('progress cannot be calculated because goal values, unit, or date range are missing or invalid')

        if goal.target_date and goal.target_date < today and goal.status not in (
            HealthGoal.Status.COMPLETED,
            HealthGoal.Status.CANCELLED,
        ):
            details.append('target date has passed')
        results.append(f'{goal.goal_name} — ' + '; '.join(details))
    return 'Your recorded goals: ' + ' | '.join(results)


def answer_measurements(user, question, today):
    if user is None:
        return _account_missing()
    record = HealthMeasurement.objects.filter(
        user=user,
        measurement_date__lte=timezone.now(),
    ).first()
    if record is None:
        return _unavailable('health measurements')
    fields = (
        ('systolic_bp', 'systolic blood pressure', 'mmHg'),
        ('diastolic_bp', 'diastolic blood pressure', 'mmHg'),
        ('heart_rate', 'heart rate', 'bpm'),
        ('temperature', 'temperature', '°C'),
        ('blood_sugar', 'blood sugar', 'mg/dL'),
        ('weight_kg', 'weight', 'kg'),
    )
    recorded = [
        f'{label}: {_format_decimal(value) if isinstance(value, Decimal) else value} {unit}'
        for field, label, unit in fields
        if (value := getattr(record, field)) is not None
    ]
    if not recorded:
        return _unavailable('health measurements')
    measurement_date = timezone.localtime(record.measurement_date).strftime('%b %d, %Y')
    return (
        f'Your latest measurement record ({measurement_date}) contains '
        + '; '.join(recorded)
        + '. These are recorded values only, not a diagnosis or interpretation; ask a healthcare '
        'professional about results or symptoms that concern you.'
    )


def answer_reminders(user, question, today):
    if user is None:
        return _account_missing()
    records = list(HealthReminder.objects.filter(
        user=user,
        reminder_date__gte=today,
        status=HealthReminder.Status.PENDING,
    )[:10])
    if not records:
        return 'You have no pending reminders scheduled for today or later.'
    entries = [
        f'{_display_date(record.reminder_date)} at {record.reminder_time.strftime("%H:%M")}: {record.reminder_title}'
        for record in records
    ]
    return 'Your pending reminders: ' + '; '.join(entries) + '.'


def answer_reports(user, question, today):
    if user is None:
        return _account_missing()
    records = list(HealthReport.objects.filter(user=user, report_date__lte=today)[:5])
    if not records:
        return _unavailable('health reports')
    entries = [
        f'{_display_date(record.report_date)} ({record.report_period}): {record.summary.strip() or "summary not recorded"}'
        for record in records
    ]
    return 'Your recent health reports: ' + ' | '.join(entries)


INTENT_HANDLERS = {
    'steps': answer_steps,
    'water': answer_water,
    'sleep': answer_sleep,
    'exercise': answer_exercise,
    'meals': answer_meals,
    'goals': answer_goals,
    'measurements': answer_measurements,
    'reminders': answer_reminders,
    'reports': answer_reports,
}


def answer_question(user, message, today=None):
    """Route a validated question to one read-only, account-scoped health intent."""
    question = message.casefold()
    today = today or timezone.localdate()

    if any(_contains_phrase(question, phrase) for phrase in URGENT_PHRASES):
        return (
            'I can’t assess emergencies. Please contact your local emergency services or seek urgent '
            'medical care now for severe or sudden symptoms.'
        )
    if any(_contains_phrase(question, phrase) for phrase in MEDICAL_ADVICE_PHRASES):
        return (
            'I can share recorded health information and general wellness information, but I can’t diagnose, '
            'prescribe, or advise changes to treatment. Please discuss medical decisions with a healthcare professional.'
        )
    if any(_contains_phrase(question, phrase) for phrase in (
        'what should i do today', 'daily health plan', 'daily wellness plan',
        'wellness plan', 'health activities should i focus', 'what should i improve today',
        'today health plan', 'today’s wellness plan', "today's wellness plan",
    )):
        return get_daily_wellness_plan(user, today=today)
    if any(_contains_phrase(question, phrase) for phrase in (
        'check my health progress', 'check my progress today', 'health progress today',
        'how am i doing today', 'daily progress', 'today progress',
    )):
        return get_daily_progress(user, today=today)
    if (
        'water' in question
        and any(_contains_phrase(question, phrase) for phrase in ('enough', 'sufficient', 'adequate'))
    ):
        return answer_water_adequacy(user, today=today)
    if any(_contains_phrase(question, phrase) for phrase in GREETING_PHRASES):
        if not any(_contains_phrase(question, phrase) for phrases in INTENT_PHRASES.values() for phrase in phrases):
            return (
                'Hello! I’m HealTrack’s rule-based Health Assistant. I can look up your recorded steps, water, '
                'sleep, exercise, meals, goals, measurements, reminders, and reports. What would you like to check?'
            )

    intents = [
        intent
        for intent, phrases in INTENT_PHRASES.items()
        if any(_contains_phrase(question, phrase) for phrase in phrases)
    ]
    if len(intents) > 1:
        return 'Which would you like to check? I can answer one topic at a time: steps, water, sleep, exercise, meals, goals, measurements, reminders, or reports.'
    if not intents:
        return (
            'I can only look up and summarize your recorded health data: daily or weekly steps, daily water, '
            'sleep, exercise, meals, goals, measurements, pending reminders, and health reports. '
            'I can’t diagnose or provide treatment advice.'
        )
    return INTENT_HANDLERS[intents[0]](user, question, today)
