from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.info.models import HealthActivity, HealthMeasurement, HealthProfile, HealthReminder, SleepRecord
from apps.users.services import mirror_healthtrack_account


class HealthTrackerTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username='tracker',
			email='tracker@example.com',
			password='secret1234',
		)
		self.health_user = mirror_healthtrack_account(self.user)
		self.client.force_login(self.user)

	def test_all_health_sections_render(self):
		for slug in (
			'profile', 'activities', 'exercises', 'sleep', 'water', 'meals',
			'goals', 'measurements', 'reminders', 'reports',
		):
			with self.subTest(slug=slug):
				response = self.client.get(reverse('info:health_list', kwargs={'slug': slug}))
				self.assertEqual(response.status_code, 200)
				self.assertTemplateUsed(response, 'health/record_list.html')

	def test_activity_creation_updates_dashboard(self):
		today = timezone.localdate()
		response = self.client.post(
			reverse('info:health_create', kwargs={'slug': 'activities'}),
			{
				'activity_date': today.isoformat(),
				'steps': '6400',
				'calories_burned': '180',
				'mood': 'Good',
				'stress_level': 'Low',
				'notes': '',
			},
		)

		self.assertRedirects(response, reverse('info:health_list', kwargs={'slug': 'activities'}))
		self.assertEqual(HealthActivity.objects.get(user=self.health_user).steps, 6400)
		dashboard = self.client.get(reverse('dashboard'))
		self.assertEqual(dashboard.status_code, 200)
		self.assertEqual(dashboard.context['steps_today'], 6400)

	def test_health_profile_updates_personal_details_shown_on_dashboard(self):
		response = self.client.post(
			reverse('info:health_create', kwargs={'slug': 'profile'}),
			{
				'date_of_birth': '1998-04-23',
				'gender': 'Female',
				'contact_number': '09171234567',
				'height_cm': '165',
				'weight_kg': '60',
				'blood_type': 'O+',
				'allergies': '',
				'existing_conditions': '',
				'emergency_contact_name': '',
				'emergency_contact_number': '',
			},
		)

		self.assertRedirects(response, reverse('info:health_list', kwargs={'slug': 'profile'}))
		self.health_user.refresh_from_db()
		self.assertEqual(self.health_user.date_of_birth.isoformat(), '1998-04-23')
		self.assertEqual(self.health_user.gender, 'Female')
		self.assertEqual(self.health_user.contact_number, '09171234567')
		self.assertTrue(HealthProfile.objects.filter(user=self.health_user).exists())

		dashboard = self.client.get(reverse('dashboard'))
		self.assertContains(dashboard, 'Apr 23, 1998')
		self.assertContains(dashboard, 'Female')
		self.assertContains(dashboard, '09171234567')

	def test_sleep_duration_crosses_midnight(self):
		today = timezone.localdate()
		response = self.client.post(
			reverse('info:health_create', kwargs={'slug': 'sleep'}),
			{
				'sleep_date': today.isoformat(),
				'bedtime': '22:30',
				'wake_time': '06:30',
				'sleep_quality': 'Good',
				'notes': '',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(SleepRecord.objects.get(user=self.health_user).total_hours, Decimal('8.00'))

	def test_body_chart_uses_latest_measurements_for_signed_in_user(self):
		now = timezone.now()
		HealthMeasurement.objects.create(
			user=self.health_user,
			measurement_date=now - timedelta(days=2),
			heart_rate=62,
		)
		HealthMeasurement.objects.create(
			user=self.health_user,
			measurement_date=now - timedelta(days=1),
			heart_rate=74,
			weight_kg=Decimal('68.50'),
		)
		other_user = get_user_model().objects.create_user(
			username='another',
			email='another@example.com',
			password='secret1234',
		)
		HealthMeasurement.objects.create(
			user=mirror_healthtrack_account(other_user),
			measurement_date=now,
			heart_rate=145,
		)

		response = self.client.get(reverse('dashboard'))
		metrics = {metric['key']: metric for metric in response.context['body_metrics']}

		self.assertEqual(metrics['heart_rate']['reading'], '74')
		self.assertEqual(metrics['weight_kg']['reading'], '68.50')

	def test_records_cannot_be_edited_or_deleted_by_another_user(self):
		other_user = get_user_model().objects.create_user(
			username='another',
			email='another@example.com',
			password='secret1234',
		)
		other_health_user = mirror_healthtrack_account(other_user)
		activity = HealthActivity.objects.create(
			user=other_health_user,
			activity_date=timezone.localdate(),
			steps=2000,
		)

		edit_response = self.client.get(reverse(
			'info:health_edit', kwargs={'slug': 'activities', 'pk': activity.pk},
		))
		delete_response = self.client.post(reverse(
			'info:health_delete', kwargs={'slug': 'activities', 'pk': activity.pk},
		))

		self.assertEqual(edit_response.status_code, 404)
		self.assertEqual(delete_response.status_code, 404)
		self.assertTrue(HealthActivity.objects.filter(pk=activity.pk).exists())

	def test_reminder_quick_status_buttons_complete_and_cancel(self):
		reminder = HealthReminder.objects.create(
			user=self.health_user,
			reminder_title='Dinner',
			reminder_date=timezone.localdate(),
			reminder_time=timezone.localtime().time(),
			reminder_type='Meal',
		)
		status_url = reverse('info:health_status', kwargs={'slug': 'reminders', 'pk': reminder.pk})

		completed = self.client.post(status_url, {'status': 'Completed'})
		self.assertRedirects(completed, reverse('info:health_list', kwargs={'slug': 'reminders'}))
		reminder.refresh_from_db()
		self.assertEqual(reminder.status, 'Completed')

		cancelled = self.client.post(status_url, {'status': 'Cancelled'})
		self.assertEqual(cancelled.status_code, 302)
		reminder.refresh_from_db()
		self.assertEqual(reminder.status, 'Cancelled')

		self.client.post(status_url, {'status': 'NotAStatus'})
		reminder.refresh_from_db()
		self.assertEqual(reminder.status, 'Cancelled')

		listing = self.client.get(reverse('info:health_list', kwargs={'slug': 'reminders'}))
		self.assertContains(listing, 'Mark as completed')
		self.assertContains(listing, 'Mark as cancelled')
		self.assertContains(listing, 'ht-status-cancel is-active')

	def test_quick_status_is_rejected_for_resources_without_status(self):
		activity = HealthActivity.objects.create(
			user=self.health_user,
			activity_date=timezone.localdate(),
			steps=1500,
		)
		response = self.client.post(
			reverse('info:health_status', kwargs={'slug': 'activities', 'pk': activity.pk}),
			{'status': 'Completed'},
		)
		self.assertRedirects(response, reverse('info:health_list', kwargs={'slug': 'activities'}))

		listing = self.client.get(reverse('info:health_list', kwargs={'slug': 'activities'}))
		self.assertNotContains(listing, 'Mark as completed')
