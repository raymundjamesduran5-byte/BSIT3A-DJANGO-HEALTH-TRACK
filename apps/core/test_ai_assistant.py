from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.ai_assistant_service import answer_question
from apps.core.daily_recommendation_service import (
    calculate_sleep_duration,
    get_daily_progress,
    get_daily_wellness_plan,
)
from apps.core.models import DailyRecommendation
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
from apps.users.services import mirror_healthtrack_account


class HealthAssistantServiceTests(TestCase):
    def setUp(self):
        self.today = date(2026, 10, 13)
        self.auth_user = get_user_model().objects.create_user(
            username='assistant-member',
            email='assistant@example.com',
            password='secret1234',
        )
        self.account = mirror_healthtrack_account(self.auth_user)
        self.other_auth_user = get_user_model().objects.create_user(
            username='other-member',
            email='other@example.com',
            password='secret1234',
        )
        self.other_account = mirror_healthtrack_account(self.other_auth_user)

    def ask(self, question):
        return answer_question(self.account, question, today=self.today)

    def test_daily_steps_sum_only_requested_day_and_user(self):
        HealthActivity.objects.create(user=self.account, activity_date=self.today, steps=3200)
        HealthActivity.objects.create(user=self.account, activity_date=self.today, steps=1800)
        HealthActivity.objects.create(user=self.account, activity_date=self.today - timedelta(days=1), steps=900)
        HealthActivity.objects.create(user=self.other_account, activity_date=self.today, steps=9900)

        self.assertIn('5,000 steps', self.ask('How many steps did I record today?'))

    def test_weekly_steps_use_last_seven_days_including_today(self):
        HealthActivity.objects.create(user=self.account, activity_date=self.today - timedelta(days=6), steps=500)
        HealthActivity.objects.create(user=self.account, activity_date=self.today, steps=1200)
        HealthActivity.objects.create(user=self.account, activity_date=self.today - timedelta(days=7), steps=8000)
        HealthActivity.objects.create(user=self.other_account, activity_date=self.today, steps=7000)

        self.assertIn('1,700 steps', self.ask('What are my weekly steps?'))

    def test_water_yesterday_and_missing_records_are_reported(self):
        WaterIntake.objects.create(user=self.account, intake_date=self.today - timedelta(days=1), amount_ml=400)
        WaterIntake.objects.create(user=self.account, intake_date=self.today - timedelta(days=1), amount_ml=350)

        self.assertIn('750 ml', self.ask('How much water yesterday?'))
        self.assertIn('can’t find any recorded water intake', self.ask('How much water did I drink today?'))

    def test_sleep_uses_latest_recorded_quality_without_inventing_it(self):
        SleepRecord.objects.create(
            user=self.account,
            sleep_date=self.today - timedelta(days=1),
            bedtime=time(22, 30),
            wake_time=time(6, 30),
            total_hours=Decimal('8.00'),
            sleep_quality='',
        )

        reply = self.ask('Tell me about my sleep')
        self.assertIn('8 hours', reply)
        self.assertIn('quality not recorded', reply)

    def test_exercise_meals_and_goal_progress_use_recorded_fields(self):
        Exercise.objects.create(
            user=self.account, exercise_date=self.today, exercise_type='Walking', duration_minutes=35,
        )
        Meal.objects.create(
            user=self.account, meal_date=self.today, meal_type=Meal.MealType.LUNCH,
            meal_description='Vegetable soup', calories=Decimal('210.00'),
        )
        HealthGoal.objects.create(
            user=self.account, goal_name='Walking', target_value=Decimal('10000'),
            current_value=Decimal('4200'), unit='steps',
            start_date=self.today - timedelta(days=5), target_date=self.today + timedelta(days=9),
            status=HealthGoal.Status.IN_PROGRESS,
        )

        self.assertIn('Walking, 35 min', self.ask('Show my recent workout history'))
        self.assertIn('Vegetable soup (210 kcal)', self.ask('What meals did I have today?'))
        goals = self.ask('Show my health goal progress')
        self.assertIn('status: In Progress', goals)
        self.assertIn('current: 4200 steps', goals)
        self.assertIn('target: 10000 steps', goals)
        self.assertIn('42% of target', goals)

    def test_invalid_goal_values_and_date_range_do_not_produce_progress(self):
        HealthGoal.objects.create(
            user=self.account, goal_name='Invalid goal', target_value=Decimal('0'),
            current_value=Decimal('12'), unit='km',
            start_date=self.today, target_date=self.today - timedelta(days=1),
        )

        reply = self.ask('What is my goal progress?')
        self.assertIn('missing or invalid', reply)
        self.assertNotIn('% progress', reply)

    def test_lower_is_better_goal_does_not_claim_progress_from_target_ratio(self):
        HealthGoal.objects.create(
            user=self.account, goal_name='Lose weight', target_value=Decimal('55'),
            current_value=Decimal('60'), unit='kg',
            start_date=self.today - timedelta(days=30), target_date=self.today + timedelta(days=30),
            status=HealthGoal.Status.IN_PROGRESS,
        )
        reply = self.ask('Show my goal progress')

        self.assertIn('current: 60 kg', reply)
        self.assertIn('target: 55 kg', reply)
        self.assertIn('starting value is needed to calculate progress', reply)
        self.assertNotIn('% of target', reply)

    def test_goal_progress_is_rounded_and_target_passing_is_explained(self):
        HealthGoal.objects.create(
            user=self.account, goal_name='Daily steps', target_value=Decimal('8'),
            current_value=Decimal('10.666'), unit='steps',
            start_date=self.today - timedelta(days=1), target_date=self.today + timedelta(days=1),
            status=HealthGoal.Status.IN_PROGRESS,
        )
        reply = self.ask('Show my goal progress')

        self.assertIn('target surpassed (133.38% of target)', reply)
        self.assertNotIn('133.325', reply)

    def test_sleep_duration_is_calculated_from_times_and_suspicious_duration_flagged(self):
        overnight = SleepRecord(
            user=self.account,
            sleep_date=self.today - timedelta(days=1),
            bedtime=time(22, 30),
            wake_time=time(6, 30),
            total_hours=Decimal('23.00'),
        )
        duration, issue = calculate_sleep_duration(overnight)
        self.assertEqual(duration, Decimal('8.00'))
        self.assertIsNone(issue)

        suspicious = SleepRecord(
            user=self.account,
            sleep_date=self.today - timedelta(days=1),
            bedtime=time(6, 0),
            wake_time=time(5, 0),
        )
        duration, issue = calculate_sleep_duration(suspicious)
        self.assertIsNone(duration)
        self.assertIn('suspicious duration', issue)

    def test_sleep_answer_uses_calculated_duration_not_stale_stored_hours(self):
        record = SleepRecord.objects.create(
            user=self.account,
            sleep_date=self.today - timedelta(days=1),
            bedtime=time(22, 0),
            wake_time=time(6, 0),
            total_hours=Decimal('8.00'),
        )
        SleepRecord.objects.filter(pk=record.pk).update(total_hours=Decimal('23.00'))

        reply = self.ask('What was my sleep duration?')

        self.assertIn('8 hours', reply)
        self.assertNotIn('23 hours', reply)

    def test_measurements_reminders_and_reports_are_account_scoped(self):
        HealthMeasurement.objects.create(
            user=self.account,
            measurement_date=timezone.make_aware(datetime(2026, 10, 12, 8, 0)),
            heart_rate=72,
            weight_kg=Decimal('68.50'),
        )
        HealthMeasurement.objects.create(
            user=self.other_account,
            measurement_date=timezone.make_aware(datetime(2026, 10, 13, 8, 0)),
            heart_rate=180,
        )
        HealthReminder.objects.create(
            user=self.account, reminder_title='Water break', reminder_date=self.today,
            reminder_time=time(14, 0), status=HealthReminder.Status.PENDING,
        )
        HealthReminder.objects.create(
            user=self.account, reminder_title='Old reminder', reminder_date=self.today - timedelta(days=1),
            reminder_time=time(8, 0), status=HealthReminder.Status.PENDING,
        )
        HealthReminder.objects.create(
            user=self.other_account, reminder_title='Private reminder', reminder_date=self.today,
            reminder_time=time(14, 0), status=HealthReminder.Status.PENDING,
        )
        HealthReport.objects.create(
            user=self.account, report_date=self.today - timedelta(days=1),
            report_period=HealthReport.Period.WEEKLY, summary='Logged activity consistently.',
        )
        HealthReport.objects.create(
            user=self.other_account, report_date=self.today,
            report_period=HealthReport.Period.DAILY, summary='Private summary.',
        )

        measurements = self.ask('Summarize my health measurements')
        self.assertIn('heart rate: 72 bpm', measurements)
        self.assertIn('weight: 68.5 kg', measurements)
        self.assertNotIn('180 bpm', measurements)
        reminders = self.ask('Which reminders are pending?')
        self.assertIn('Water break', reminders)
        self.assertNotIn('Old reminder', reminders)
        self.assertNotIn('Private reminder', reminders)
        reports = self.ask('Summarize my previous health reports')
        self.assertIn('Logged activity consistently.', reports)
        self.assertNotIn('Private summary', reports)

    def test_greeting_unsupported_ambiguous_and_safety_responses(self):
        self.assertIn('rule-based', self.ask('Hello'))
        self.assertIn('can only look up', self.ask('Will it rain tomorrow?'))
        self.assertIn('one topic at a time', self.ask('How many steps and water today?'))
        self.assertIn('can’t diagnose', self.ask('Can you diagnose my symptoms?'))
        self.assertIn('emergency services', self.ask('I have chest pain'))

    def test_no_recorded_data_is_not_reported_as_zero(self):
        self.assertIn('can’t find any recorded daily step totals', self.ask('How many steps today?'))

    def test_water_adequacy_compares_only_with_a_saved_valid_personal_goal(self):
        WaterIntake.objects.create(user=self.account, intake_date=self.today, amount_ml=900)
        no_goal = self.ask('Am I drinking enough water based on my records?')
        self.assertIn('cannot compare this with your own target', no_goal)
        HealthGoal.objects.create(
            user=self.account, goal_name='Water intake', target_value=Decimal('2'),
            current_value=Decimal('1'), unit='L',
            start_date=self.today - timedelta(days=1), target_date=self.today + timedelta(days=1),
        )

        with_goal = self.ask('Am I drinking enough water based on my records?')
        self.assertIn('900 ml', with_goal)
        self.assertIn('2 L', with_goal)
        self.assertIn('below that goal', with_goal)
        self.assertIn('not a medical assessment', with_goal)


class HealthAssistantViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='assistant-view-member',
            email='view-assistant@example.com',
            password='secret1234',
        )
        self.account = mirror_healthtrack_account(self.user)
        self.url = reverse('assistant_chat')

    def test_page_and_chat_endpoint_require_authentication(self):
        self.assertEqual(self.client.get(reverse('assistant')).status_code, 302)
        response = self.client.post(self.url, {'message': 'How many steps today?'})
        self.assertEqual(response.status_code, 302)

    def test_chat_page_renders_suggestions_and_disclaimer(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('assistant'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rule-based helper')
        self.assertContains(response, 'not a substitute for a healthcare professional')
        self.assertContains(response, 'How much water did I drink today?')

    def test_api_rejects_blank_and_overlong_input(self):
        self.client.force_login(self.user)

        blank = self.client.post(self.url, {'message': '   '})
        overlong = self.client.post(self.url, {'message': 'x' * 501})

        self.assertEqual(blank.status_code, 400)
        self.assertEqual(overlong.status_code, 400)
        self.assertIn('error', blank.json())
        self.assertIn('500 characters or fewer', overlong.json()['error'])

    def test_api_uses_authenticated_records_not_frontend_user_id(self):
        other = get_user_model().objects.create_user(
            username='assistant-other-view',
            email='other-view@example.com',
            password='secret1234',
        )
        other_account = mirror_healthtrack_account(other)
        today = timezone.localdate()
        HealthActivity.objects.create(user=self.account, activity_date=today, steps=2100)
        HealthActivity.objects.create(user=other_account, activity_date=today, steps=9999)
        self.client.force_login(self.user)

        response = self.client.post(self.url, {'message': 'How many steps today?', 'user_id': other_account.pk})

        self.assertEqual(response.status_code, 200)
        self.assertIn('2,100 steps', response.json()['reply'])
        self.assertNotIn('9,999', response.json()['reply'])

    def test_chat_endpoint_rejects_get(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_plan_is_stable_for_the_day_and_rotates_on_a_new_day(self):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)

        first = get_daily_wellness_plan(self.account, today=today)
        WaterIntake.objects.create(user=self.account, intake_date=today, amount_ml=700)
        same_day = get_daily_wellness_plan(self.account, today=today)
        next_day = get_daily_wellness_plan(self.account, today=tomorrow)

        self.assertEqual(first, same_day)
        self.assertNotIn('Water recorded today: 700 ml.', same_day['recorded_summary'])
        self.assertEqual(len(first['items']), 4)
        self.assertEqual(len({item['id'] for item in first['items']}), len(first['items']))
        self.assertNotEqual(
            {item['category'] for item in first['items']},
            {item['category'] for item in next_day['items']},
        )
        self.assertEqual(
            DailyRecommendation.objects.filter(user=self.account, recommendation_date=today).count(),
            1,
        )

    def test_plan_avoids_suggestions_from_recent_days_and_is_user_scoped(self):
        today = timezone.localdate()
        previous = get_daily_wellness_plan(self.account, today=today - timedelta(days=1))
        current = get_daily_wellness_plan(self.account, today=today)
        previous_by_category = {item['category']: item['id'] for item in previous['items']}
        current_by_category = {item['category']: item['id'] for item in current['items']}
        repeated_categories = previous_by_category.keys() & current_by_category.keys()

        for category in repeated_categories:
            self.assertNotEqual(previous_by_category[category], current_by_category[category])
        other_user = get_user_model().objects.create_user(
            username='plan-isolation-other',
            email='plan-isolation-other@example.com',
            password='secret1234',
        )
        other_account = mirror_healthtrack_account(other_user)
        other_plan = get_daily_wellness_plan(other_account, today=today)
        self.assertEqual(
            DailyRecommendation.objects.filter(user=other_account, recommendation_date=today).count(),
            1,
        )
        self.assertEqual(other_plan['date'], today.isoformat())

    def test_plan_personalizes_facts_and_reports_missing_entries(self):
        today = timezone.localdate()
        HealthActivity.objects.create(user=self.account, activity_date=today, steps=2400)
        WaterIntake.objects.create(user=self.account, intake_date=today, amount_ml=500)
        HealthGoal.objects.create(
            user=self.account, goal_name='Daily walk', target_value=Decimal('5000'),
            current_value=Decimal('2400'), unit='steps',
            start_date=today - timedelta(days=2), target_date=today + timedelta(days=10),
            status=HealthGoal.Status.IN_PROGRESS,
        )

        plan = get_daily_wellness_plan(self.account, today=today)

        self.assertIn('Steps recorded today: 2,400.', plan['recorded_summary'])
        self.assertIn('Water recorded today: 500 ml.', plan['recorded_summary'])
        self.assertIn('No sleep record is saved for the last 7 days.', plan['missing_data'])
        self.assertTrue(all(item['reason'] for item in plan['items']))

    def test_progress_separates_recorded_data_missing_data_and_suggestions(self):
        today = timezone.localdate()
        HealthActivity.objects.create(user=self.account, activity_date=today, steps=3000)
        HealthActivity.objects.create(
            user=self.account, activity_date=today, steps=9900,
        )
        other = get_user_model().objects.create_user(
            username='progress-other', email='progress-other@example.com', password='secret1234',
        )
        HealthActivity.objects.create(
            user=mirror_healthtrack_account(other), activity_date=today, steps=100000,
        )

        progress = get_daily_progress(self.account, today=today)

        self.assertEqual(progress['type'], 'progress')
        self.assertIn('Steps recorded today: 12,900.', progress['recorded_summary'])
        self.assertFalse(any('100,000' in line for line in progress['recorded_summary']))
        self.assertTrue(progress['missing_data'])
        self.assertTrue(progress['next_steps'])

    def test_plan_view_endpoints_return_structured_results_for_signed_in_user(self):
        self.client.force_login(self.user)

        plan = self.client.post(self.url, {'message': 'Give me my daily health plan.'})
        progress = self.client.post(self.url, {'message': 'Can you check my health progress today?'})

        self.assertEqual(plan.status_code, 200)
        self.assertEqual(plan.json()['type'], 'wellness_plan')
        self.assertEqual(len(plan.json()['items']), 4)
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.json()['type'], 'progress')


class HealthAssistantCsrfTests(TestCase):
    def test_chat_post_requires_csrf_token(self):
        user = get_user_model().objects.create_user(
            username='csrf-assistant',
            email='csrf-assistant@example.com',
            password='secret1234',
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)

        response = client.post(reverse('assistant_chat'), {'message': 'hello'})

        self.assertEqual(response.status_code, 403)
