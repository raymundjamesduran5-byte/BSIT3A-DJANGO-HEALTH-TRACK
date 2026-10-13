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
