"""Personalized, local wellness plans and daily progress summaries."""

import hashlib
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import DailyRecommendation
from apps.info.models import (
    Exercise,
    HealthActivity,
    HealthGoal,
    HealthMeasurement,
    HealthReminder,
    Meal,
    SleepRecord,
    WaterIntake,
)
from apps.users.models import HealthTrackUser

PLAN_CATEGORIES = (
    'Hydration',
    'Movement',
    'Sleep',
    'Nutrition',
    'Health goals',
    'Health tracking',
    'Reminders',
)

GENERIC_SUGGESTIONS = {
    'Hydration': (
        ('hydration-log', 'Log water as you go', 'If you drink water today, add each amount to your water log.', 'This helps build a record without assuming how much you have had.'),
        ('hydration-routine', 'Choose a comfortable water check-in', 'Consider keeping water accessible and logging intake at a time that suits you.', 'Your records do not establish a personal intake target.'),
        ('hydration-meal', 'Pair a water log with a daily pause', 'At a convenient break, check whether you want water and record it if you do.', 'A check-in can make your record more complete without setting a prescribed amount.'),
        ('hydration-reminder', 'Review your water log later', 'Set aside a moment to review today’s water entries and add any missing ones.', 'Today’s log is the only information available here; no intake is assumed.'),
        ('hydration-choice', 'Keep hydration tracking simple', 'Record water when convenient rather than estimating amounts you cannot recall.', 'Accurate entries are more useful than guessed totals.'),
    ),
    'Movement': (
        ('movement-walk', 'Consider a comfortable short walk', 'If it suits you, take a brief walk at a comfortable pace and record it afterward.', 'No activity entry today does not tell us whether you have moved.'),
        ('movement-stretch', 'Take a gentle movement break', 'If comfortable for you, try a few minutes of easy stretching or light movement.', 'This is an optional general wellness idea, not a prescribed exercise plan.'),
        ('movement-pause', 'Add a movement pause to your day', 'Choose a convenient time for a brief, comfortable movement break.', 'Your activity log does not define what is safe or suitable for you.'),
        ('movement-record', 'Record activity you have already done', 'If you have exercised or walked today, consider adding the activity to HealTrack.', 'The record helps distinguish completed activity from suggested activity.'),
        ('movement-choice', 'Choose movement that feels manageable', 'If appropriate for you, choose a light activity you enjoy and note it in your log.', 'The assistant does not know your physical limitations, so use your own judgement.'),
    ),
    'Sleep': (
        ('sleep-wind-down', 'Make room for a wind-down routine', 'Consider a calm, low-stimulation activity before your usual bedtime.', 'Sleep habits are easier to review when they are recorded consistently.'),
        ('sleep-schedule', 'Keep your usual sleep schedule in mind', 'If possible, plan a bedtime that fits your normal routine and commitments.', 'This is a general habit suggestion, not treatment advice.'),
        ('sleep-screen', 'Create a restful pause before bed', 'Try setting aside a little quiet time before bed, in a way that works for you.', 'Your sleep record can help you notice patterns over time.'),
        ('sleep-log', 'Record last night’s sleep details', 'Add the bedtime, wake time, and sleep quality you recall for last night.', 'A complete record helps make the duration and quality easier to review.'),
        ('sleep-reflect', 'Review how your recent sleep felt', 'If you choose, note how rested you felt and any routine that helped.', 'The assistant cannot infer sleep quality from duration alone.'),
    ),
    'Nutrition': (
        ('nutrition-log', 'Add any meals you have not logged', 'Record meals you have eaten today, including a short description if useful.', 'A missing meal entry does not mean you skipped a meal.'),
        ('nutrition-balance', 'Think about variety at your next meal', 'For a general balanced approach, consider including a mix of food groups that works for you.', 'This is general information, not a personalized diet or medical nutrition plan.'),
        ('nutrition-pause', 'Plan a convenient meal check-in', 'Choose a time to record a meal or snack when it fits your day.', 'Your current meal records may not include everything you have eaten.'),
        ('nutrition-note', 'Add useful notes to a meal entry', 'If relevant, note meal details you want to remember in your own records.', 'Notes can make your own tracking more useful; no meal details are assumed.'),
        ('nutrition-choice', 'Keep meal tracking practical', 'If you have eaten, add a brief meal entry rather than trying to estimate details you do not know.', 'Only information you record will appear in your health history.'),
    ),
    'Health goals': (
        ('goal-review', 'Review one active health goal', 'Check its target, unit, and due date, then choose a small next step that fits your day.', 'Goal values are user-entered and are not a clinical assessment.'),
        ('goal-step', 'Choose a manageable goal-related action', 'If you have an active goal, consider one practical step toward it today.', 'The plan does not assume a goal is appropriate or alter its target.'),
        ('goal-record', 'Update goal progress if it has changed', 'If you have new progress to report, update the goal using the same unit as its target.', 'No progress is inferred until you record it.'),
        ('goal-date', 'Check your goal’s time frame', 'Review the start and target dates on a goal before planning a next step.', 'Dates help put a target in context; they do not determine health outcomes.'),
        ('goal-reflect', 'Reflect on what makes a goal manageable', 'Consider whether a small, realistic action fits your schedule today.', 'This suggestion is optional and does not change any saved goal.'),
    ),
    'Health tracking': (
        ('tracking-steps', 'Complete today’s activity log if useful', 'If you track steps, add today’s count when you have it.', 'No steps are assumed when no activity record is present.'),
        ('tracking-exercise', 'Record exercise if you did any', 'Add an exercise entry with its duration if you completed an activity today.', 'An empty exercise log does not mean you were inactive.'),
        ('tracking-sleep', 'Fill in a missing sleep record', 'If you know last night’s bedtime and wake time, consider adding them to your sleep log.', 'No sleep duration or quality is estimated when it has not been recorded.'),
        ('tracking-meals', 'Review which daily records are useful to you', 'Complete only the health entries you want to keep track of today.', 'Tracking is optional; missing entries are not treated as poor health.'),
        ('tracking-water', 'Check whether any entries need updating', 'Review today’s health log and add only details you can reliably recall.', 'This avoids treating an empty log as a zero measurement.'),
    ),
    'Reminders': (
        ('reminder-review', 'Review a pending reminder', 'Check the reminder and decide how it fits with your plans today.', 'The reminder below is one you already saved in HealTrack.'),
        ('reminder-time', 'Keep a saved reminder in view', 'Consider checking the time of a reminder you scheduled for today.', 'This repeats your saved reminder; it does not create or change one.'),
    ),
}

LOWER_IS_BETTER_TERMS = (
    'lose', 'loss', 'lower', 'reduce', 'decrease', 'weight loss', 'lowering',
)


def format_number(value, places=2):
    """Format a number to at most ``places`` decimal places without trailing zeros."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    rendered = f'{number:.{places}f}'
    return rendered.rstrip('0').rstrip('.') if '.' in rendered else rendered


def calculate_sleep_duration(record):
    """Return duration from bedtime/wake-time, flagging implausible intervals."""
    if not record.sleep_date or not record.bedtime or not record.wake_time:
        return None, 'Bedtime or wake time is missing; duration cannot be verified.'
    start = datetime.combine(record.sleep_date, record.bedtime)
    end = datetime.combine(record.sleep_date, record.wake_time)
    if end <= start:
        end += timedelta(days=1)
    hours = Decimal(str((end - start).total_seconds())) / Decimal(3600)
    if hours <= 0 or hours > 16:
        return None, 'The recorded bedtime and wake time imply a suspicious duration; please check the times.'
    return hours.quantize(Decimal('0.01')), None


def _display_date(value):
    return value.strftime('%b %d, %Y').replace(' 0', ' ')


def _today_snapshot(user, today):
    steps = list(HealthActivity.objects.filter(user=user, activity_date=today))
    water = list(WaterIntake.objects.filter(user=user, intake_date=today))
    exercises = list(Exercise.objects.filter(user=user, exercise_date=today))
    meals = list(Meal.objects.filter(user=user, meal_date=today))
    sleep_records = list(SleepRecord.objects.filter(
        user=user,
        sleep_date__range=(today - timedelta(days=6), today),
    )[:7])
    goals = list(HealthGoal.objects.filter(
        user=user,
        status__in=(HealthGoal.Status.NOT_STARTED, HealthGoal.Status.IN_PROGRESS),
    ))
    goals = [
        goal for goal in goals
        if (goal.start_date is None or goal.start_date <= today)
        and (goal.target_date is None or goal.target_date >= today)
    ]
    reminders_today = list(HealthReminder.objects.filter(
        user=user,
        reminder_date=today,
        status=HealthReminder.Status.PENDING,
    ))
    measurement = HealthMeasurement.objects.filter(
        user=user,
        measurement_date__lte=timezone.now(),
    ).order_by('-measurement_date', '-pk').first()

    summary = []
    missing = []
    if steps:
        summary.append(f"Steps recorded today: {sum(record.steps for record in steps):,}.")
    else:
        missing.append('No activity/step record is saved for today.')
    if water:
        summary.append(f"Water recorded today: {sum(record.amount_ml for record in water):,} ml.")
    else:
        missing.append('No water intake is recorded for today (this does not mean none was consumed).')
    if sleep_records:
        latest_sleep = sleep_records[0]
        duration, issue = calculate_sleep_duration(latest_sleep)
        if issue:
            summary.append(f"Latest sleep record ({_display_date(latest_sleep.sleep_date)}): duration not verified. {issue}")
        else:
            summary.append(
                f"Latest sleep record ({_display_date(latest_sleep.sleep_date)}): "
                f'{format_number(duration)} hours from the saved times; quality: '
                f'{latest_sleep.sleep_quality or "not recorded"}.'
            )
    else:
        missing.append('No sleep record is saved for the last 7 days.')
    if exercises:
        summary.append(
            f"Exercise recorded today: {sum(record.duration_minutes for record in exercises)} minutes "
            f'across {len(exercises)} entr{"y" if len(exercises) == 1 else "ies"}.'
        )
    else:
        missing.append('No exercise entry is saved for today (this does not mean no activity occurred).')
    if meals:
        summary.append(f'Meals recorded today: {len(meals)}.')
    else:
        missing.append('No meal entry is saved for today (this does not mean a meal was skipped).')
    if goals:
        for goal in goals[:5]:
            summary.append(_goal_summary(goal, today))
    else:
        summary.append('No active, in-date health goals are recorded.')
    if reminders_today:
        summary.extend(
            f"Pending reminder today: {reminder.reminder_title} at {reminder.reminder_time.strftime('%H:%M')}."
            for reminder in reminders_today[:5]
        )
    else:
        summary.append('No pending reminders are scheduled for today.')
    if measurement:
        summary.append(
            f'Latest health measurement record: {_display_date(timezone.localtime(measurement.measurement_date).date())}.'
        )
    else:
        summary.append('No health measurement record is saved.')

    return {
        'steps': steps,
        'water': water,
        'exercises': exercises,
        'meals': meals,
        'sleep_records': sleep_records,
        'goals': goals,
        'reminders_today': reminders_today,
        'measurement': measurement,
        'summary': summary,
        'missing': missing,
    }


def _goal_summary(goal, today):
    current = format_number(goal.current_value)
    target = format_number(goal.target_value) if goal.target_value is not None else None
    unit = goal.unit.strip()
    current_display = (
        f'{current} {unit}'.strip()
        if current is not None
        else f'{"not recorded" if goal.current_value is None else "invalid"} {unit}'.strip()
    )
    target_display = (
        f'{target} {unit}'.strip()
        if target is not None
        else f'{"not recorded" if goal.target_value is None else "invalid"} {unit}'.strip()
    )
    parts = [f'{goal.goal_name}: {goal.status}; current {current_display}; target {target_display}']
    if goal.target_date:
        parts.append(f'target date {_display_date(goal.target_date)}')
    direction = _goal_direction(goal)
    try:
        current_value = Decimal(str(goal.current_value))
        target_value = Decimal(str(goal.target_value)) if goal.target_value is not None else None
    except (InvalidOperation, TypeError, ValueError):
        current_value = target_value = None
    valid = (
        current_value is not None and current_value.is_finite() and current_value >= 0
        and target_value is not None and target_value.is_finite() and target_value > 0
        and bool(unit)
        and not (goal.start_date and goal.target_date and goal.start_date > goal.target_date)
    )
    if not valid:
        parts.append('progress cannot be calculated because values, unit, or date range are missing or invalid')
    elif direction == 'lower':
        parts.append(
            'target reached' if current_value <= target_value
            else 'target not yet reached; a starting value is needed to calculate progress'
        )
    else:
        percent = (current_value / target_value * 100).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )
        if current_value > target_value:
            parts.append(f'target surpassed ({format_number(percent)}% of target)')
        elif current_value == target_value:
            parts.append(f'target reached (100% of target)')
        else:
            parts.append(f'{format_number(percent)}% of target')
    return 'Active goal: ' + '; '.join(parts) + '.'


def _goal_direction(goal):
    description = f'{goal.goal_name} {goal.description}'.casefold()
    return 'lower' if any(term in description for term in LOWER_IS_BETTER_TERMS) else 'higher'


def _water_goal(user, today=None):
    goals = HealthGoal.objects.filter(
        user=user,
        status__in=(HealthGoal.Status.NOT_STARTED, HealthGoal.Status.IN_PROGRESS),
    )
    today = today or timezone.localdate()
    for goal in goals:
        if (
            (goal.start_date is not None and goal.start_date > today)
            or (goal.target_date is not None and goal.target_date < today)
        ):
            continue
        text = f'{goal.goal_name} {goal.description}'.casefold()
        unit = goal.unit.casefold().strip()
        if any(term in text for term in ('water', 'hydration', 'fluid')) and unit in ('ml', 'l', 'liter', 'liters', 'litre', 'litres'):
            return goal
    return None


def _valid_water_target(goal):
    if goal is None or goal.target_value is None:
        return None
    try:
        target = Decimal(str(goal.target_value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not target.is_finite() or target <= 0:
        return None
    if goal.unit.casefold().strip() in ('l', 'liter', 'liters', 'litre', 'litres'):
        return target * 1000
    return target


def _recent_plan_ids(user, today):
    plans = DailyRecommendation.objects.filter(
        user=user,
        recommendation_date__lt=today,
        recommendation_date__gte=today - timedelta(days=7),
    ).values_list('items', flat=True)
    return {
        item['id']
        for plan in plans
        for item in plan
        if isinstance(item, dict) and isinstance(item.get('id'), str)
    }


def _daily_candidates(user, today, snapshot):
    recorded_water = snapshot['water']
    water_total = sum(item.amount_ml for item in recorded_water) if recorded_water else None
    active_water_goal = _water_goal(user, today)
    water_note = (
        f'The recorded total is {water_total:,} ml today.'
        if water_total is not None
        else 'There is no water entry for today, so no amount is assumed.'
    )
    if active_water_goal:
        target_ml = _valid_water_target(active_water_goal)
        if target_ml is None:
            water_note += ' A saved water goal exists, but its value is invalid, so no comparison is made.'
        else:
            target_text = f'{format_number(active_water_goal.target_value)} {active_water_goal.unit}'
            water_note += f" Your saved goal is {target_text}; compare your log with that personal goal, not a medical hydration standard."
        if water_total is not None and target_ml is not None:
            relation = 'at or above' if Decimal(water_total) >= target_ml else 'below'
            water_note += f' The amount logged so far is {relation} that saved target.'

    sleep_record = snapshot['sleep_records'][0] if snapshot['sleep_records'] else None
    sleep_duration, sleep_issue = calculate_sleep_duration(sleep_record) if sleep_record else (None, None)
    if sleep_issue:
        sleep_note = 'The latest saved sleep times need checking; no duration is treated as reliable.'
    elif sleep_record and (sleep_record.sleep_quality in ('Poor', 'Fair') or (sleep_duration is not None and sleep_duration < 7)):
        sleep_note = (
            f"The latest saved sleep record is from {_display_date(sleep_record.sleep_date)} "
            f"({format_number(sleep_duration)} hours; quality {sleep_record.sleep_quality or 'not recorded'}). "
            'This is a log observation, not a health assessment.'
        )
    elif sleep_record:
        sleep_note = f"The latest saved sleep record is from {_display_date(sleep_record.sleep_date)}; duration is {format_number(sleep_duration)} hours."
    else:
        sleep_note = 'There is no sleep record from the last 7 days.'

    active_goal_note = (
        _goal_summary(snapshot['goals'][0], today)
        if snapshot['goals'] else 'No active, in-date goal is recorded.'
    )
    reminder_note = (
        f"Saved reminder: {snapshot['reminders_today'][0].reminder_title} at "
        f"{snapshot['reminders_today'][0].reminder_time.strftime('%H:%M')}."
        if snapshot['reminders_today'] else 'No reminder is scheduled for today.'
    )

    details = {
        'Hydration': water_note,
        'Movement': (
            f"Today’s activity log contains {sum(row.steps for row in snapshot['steps']):,} steps."
            if snapshot['steps'] else 'No activity entry is saved for today; this does not mean you have been inactive.'
        ),
        'Sleep': sleep_note,
        'Nutrition': (
            f"{len(snapshot['meals'])} meal entr{'y' if len(snapshot['meals']) == 1 else 'ies'} are saved today."
            if snapshot['meals'] else 'No meal entries are saved today; no meals are assumed skipped.'
        ),
        'Health goals': active_goal_note,
        'Health tracking': (
            'Today’s exercise is logged.'
            if snapshot['exercises'] else 'No exercise entry is saved today; no activity is assumed.'
        ),
        'Reminders': reminder_note,
    }

    candidates = {}
    for category, suggestions in GENERIC_SUGGESTIONS.items():
        candidates[category] = [
            {
                'id': f'{category.casefold().replace(" ", "-")}:{key}',
                'category': category,
                'title': title,
                'suggestion': suggestion,
                'reason': details[category],
            }
            for key, title, suggestion, _ in suggestions
        ]

    if snapshot['reminders_today']:
        reminder = snapshot['reminders_today'][0]
        candidates['Reminders'].insert(0, {
            'id': f'reminder:{reminder.pk}',
            'category': 'Reminders',
            'title': f"Review: {reminder.reminder_title}",
            'suggestion': (
                f"Your saved reminder is scheduled for {reminder.reminder_time.strftime('%H:%M')}. "
                'Check it and decide how it fits your plans.'
            ),
            'reason': 'This is an existing pending reminder for today.',
        })
    return candidates


def _choose_items(user, today, snapshot, recent_ids):
    candidates = _daily_candidates(user, today, snapshot)
    start_index = (today.toordinal() + user.pk) % len(PLAN_CATEGORIES)
    rotated_categories = list(PLAN_CATEGORIES[start_index:]) + list(PLAN_CATEGORIES[:start_index])
    if snapshot['reminders_today']:
        rotated_categories.remove('Reminders')
        rotated_categories.insert(0, 'Reminders')
    chosen_categories = rotated_categories[:4]
    selected = []
    used_ids = set()
    for category in chosen_categories:
        options = candidates[category]
        seed = f'{user.pk}:{today.isoformat()}:{category}'.encode()
        offset = int(hashlib.sha256(seed).hexdigest(), 16) % len(options)
        ordered = options[offset:] + options[:offset]
        choice = next(
            (option for option in ordered if option['id'] not in recent_ids and option['id'] not in used_ids),
            None,
        )
        if choice is None:
            choice = next((option for option in ordered if option['id'] not in used_ids), ordered[0])
        selected.append(choice)
        used_ids.add(choice['id'])
    return selected


def get_daily_wellness_plan(user, today=None):
    """Return a stable saved plan; rotate away from recommendation IDs used recently."""
    today = today or timezone.localdate()
    if user is None:
        return {'error': 'Your health-record account is not linked yet, so a personal plan is unavailable.'}

    existing = DailyRecommendation.objects.filter(user=user, recommendation_date=today).first()
    if existing is None:
        snapshot = _today_snapshot(user, today)
        items = _choose_items(user, today, snapshot, _recent_plan_ids(user, today))
        try:
            with transaction.atomic():
                existing, _ = DailyRecommendation.objects.get_or_create(
                    user=user,
                    recommendation_date=today,
                    defaults={
                        'items': items,
                        'recorded_summary': snapshot['summary'],
                        'missing_data': snapshot['missing'],
                    },
                )
        except IntegrityError:
            existing = DailyRecommendation.objects.get(user=user, recommendation_date=today)

    return {
        'type': 'wellness_plan',
        'title': 'Today’s Wellness Plan',
        'date': existing.recommendation_date.isoformat(),
        'items': existing.items,
        'recorded_summary': existing.recorded_summary,
        'missing_data': existing.missing_data,
        'disclaimer': 'Suggestions are optional general wellness ideas, not medical advice. Your saved records are facts; recommendations are not completed activities.',
    }


def get_daily_progress(user, today=None):
    """Summarize today's saved entries and provide clearly separated next steps."""
    today = today or timezone.localdate()
    if user is None:
        return {'error': 'Your health-record account is not linked yet, so I cannot check your records.'}
    snapshot = _today_snapshot(user, today)
    next_steps = []
    if not snapshot['steps']:
        next_steps.append('If you track steps, add today’s count when available; the missing entry does not mean zero steps.')
    if not snapshot['water']:
        next_steps.append('If you drink water today, record the amount. The current log does not establish your hydration status.')
    else:
        water_goal = _water_goal(user, today)
        if water_goal:
            target = _valid_water_target(water_goal)
            total = Decimal(sum(item.amount_ml for item in snapshot['water']))
            if target is not None and total < target:
                next_steps.append('Your logged water is below your own saved goal so far; follow a routine that suits you and update the log if appropriate. This is not a dehydration assessment.')
    if not snapshot['exercises']:
        next_steps.append('If you completed exercise today, add it to your log; no exercise is inferred from the missing entry.')
    if not snapshot['meals']:
        next_steps.append('If useful, record meals eaten today; an empty meal log does not mean you skipped a meal.')
    if snapshot['reminders_today']:
        next_steps.append('Review your pending reminder(s) scheduled for today.')
    if not next_steps:
        next_steps.append('Your daily records are populated. Review any goal or reminder that is relevant to your plans.')
    return {
        'type': 'progress',
        'title': 'Today’s recorded progress',
        'date': today.isoformat(),
        'recorded_summary': snapshot['summary'],
        'missing_data': snapshot['missing'],
        'next_steps': next_steps[:4],
    }


def answer_water_adequacy(user, today=None):
    today = today or timezone.localdate()
    if user is None:
        return 'Your health-record account is not linked yet, so I cannot check your water records.'
    records = list(WaterIntake.objects.filter(user=user, intake_date=today))
    if not records:
        return (
            f'No water intake is recorded for {_display_date(today)}, so I cannot tell how much you drank '
            'or whether it met a personal target. An empty log does not mean you drank none.'
        )
    total = sum(record.amount_ml for record in records)
    goal = _water_goal(user, today)
    reply = f'You have recorded {total:,} ml for {_display_date(today)}.'
    if goal is None or goal.target_value is None or not goal.unit:
        return (
            reply + ' I do not find a saved water goal with a usable unit, so I cannot compare this with '
            'your own target. This log is not a medical assessment of hydration.'
        )
    target = _valid_water_target(goal)
    if target is None:
        return reply + ' Your saved water goal is invalid, so no comparison can be calculated.'
    relation = 'at or above' if Decimal(total) >= target else 'below'
    return (
        f'{reply} Your saved goal is {format_number(goal.target_value)} {goal.unit}; today’s recorded amount is '
        f'{relation} that goal. This compares your log with your own saved target only and is not a '
        'medical assessment or a recommendation to force additional intake.'
    )
