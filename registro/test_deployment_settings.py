from django.conf import settings
from django.test import SimpleTestCase


class DeploymentHostSettingsTests(SimpleTestCase):
    def test_vercel_domains_are_allowed(self):
        self.assertIn("claro-personal.vercel.app", settings.ALLOWED_HOSTS)
        self.assertIn("cuentas-claras-gusman-app.vercel.app", settings.ALLOWED_HOSTS)

    def test_vercel_domains_are_trusted_for_csrf(self):
        self.assertIn("https://claro-personal.vercel.app", settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn(
            "https://cuentas-claras-gusman-app.vercel.app",
            settings.CSRF_TRUSTED_ORIGINS,
        )
