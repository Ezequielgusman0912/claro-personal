from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Movement


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PendingScreenTests(TestCase):
    def test_pending_screen_excludes_confirmed_and_preserves_status(self):
        user = get_user_model().objects.create_user("pending-screen")
        self.client.force_login(user)
        pending = Movement.objects.create(owner=user, recipient="Por revisar")
        Movement.objects.create(owner=user, recipient="Ya confirmado", status="confirmed")
        for url in (reverse("dashboard"), reverse("movements")):
            with self.subTest(url=url):
                response = self.client.get(url, {"status": "pending", "q": "Por"})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<h1>Pendientes</h1>")
                self.assertContains(response, "No son deudas")
                self.assertContains(response, 'name="status" value="pending"')
                self.assertNotContains(response, "<select name=\"status\"")
                self.assertNotContains(response, 'aria-label="Resumen del período"')
                self.assertNotContains(response, "Ya confirmado")
                self.assertEqual(response.context["rows"], [pending])
        empty = self.client.get(reverse("dashboard"), {"status": "pending", "q": "nada"})
        self.assertContains(empty, "No hay movimientos por completar")

    def test_demo_pending_screen_has_no_summary_or_confirmed_movements(self):
        response = self.client.get("/demo/?status=pending")
        self.assertContains(response, "<h1>Pendientes</h1>")
        self.assertNotContains(response, "Gastos confirmados")
        self.assertNotContains(response, "Gastos por categoría")
        self.assertTrue(all(row.status == "pending" for row in response.context["rows"]))
