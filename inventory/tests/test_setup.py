from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="keeper", password="a-long-local-password"
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_user_can_log_in_and_reach_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "keeper", "password": "a-long-local-password"},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertContains(self.client.get(reverse("dashboard")), "NetMap")

    def test_logout_is_post_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
