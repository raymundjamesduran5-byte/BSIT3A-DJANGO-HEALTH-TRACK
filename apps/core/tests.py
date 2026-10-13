from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)

    @override_settings(TIME_ZONE='Asia/Manila')
    @patch(
        'django.utils.timezone.now',
        return_value=datetime(2026, 10, 13, 14, 20, tzinfo=datetime_timezone.utc),
    )
    def test_dashboard_displays_manila_local_date_time_and_greeting(self, _mock_now):
        user = get_user_model().objects.create_user(username='local-time-member', password='secret1234')
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['today'].isoformat(), '2026-10-13')
        self.assertEqual(response.context['current_time'], '10:20 PM')
        self.assertEqual(response.context['greeting'], 'evening')
        self.assertContains(response, 'October 13, 2026')
        self.assertContains(response, '10:20 PM')
        self.assertContains(response, 'Good evening')


class EmailLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='healthtrack-user',
            email='member@example.com',
            password='secret1234',
        )

    def test_email_login_is_case_insensitive_and_remembered(self):
        response = self.client.post(reverse('login'), {
            'email': 'MEMBER@example.com',
            'password': 'secret1234',
            'remember_me': 'on',
        })

        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session.get_expiry_age()), 60 * 60 * 24 * 14)

    def test_email_login_expires_when_browser_closes_if_unchecked(self):
        response = self.client.post(reverse('login'), {
            'email': 'member@example.com',
            'password': 'secret1234',
        })

        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_sends_reset_link(self):
        response = self.client.post(reverse('password_reset'), {'email': self.user.email})

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/reset/', mail.outbox[0].body)
