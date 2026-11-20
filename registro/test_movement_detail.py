from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Account, Movement


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class MovementDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("detail-user")
        self.account = Account.objects.create(owner=self.user, name="Galicia", bank="galicia")
        self.movement = Movement.objects.create(
            owner=self.user, account=self.account, recipient="Comercio",
            amount=Decimal("1234.56"), date=timezone.localdate(),
            description="Compra semanal", category="food", status="confirmed",
            notes="Nota personal", operation_id="OP-123",
        )
        self.client.force_login(self.user)
        self.url = reverse("movement_detail", args=[self.movement.pk])

    def test_detail_is_read_only_and_list_links_to_it(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for text in ("Compra semanal", "Galicia", "Comida y supermercado",
                     "ARS", "Confirmado", "OP-123", "Nota personal"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("edit", args=[self.movement.pk]))
        self.assertContains(response, '<details class="detail-extra">')
        self.assertNotContains(response, 'id="id_amount"')
        self.assertNotContains(response, "Guardar pendiente")
        listing = self.client.get(reverse("movements"))
        self.assertContains(listing, f'href="{self.url}"', count=2)
        self.assertNotContains(listing, reverse("edit", args=[self.movement.pk]))
        self.assertEqual(self.client.post(self.url, {"amount": "5"}).status_code, 405)
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.amount, Decimal("1234.56"))

    def test_detail_requires_login_and_owner(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        other = get_user_model().objects.create_user("other-detail-user")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_edit_remains_explicit_and_returns_to_detail(self):
        edit_url = reverse("edit", args=[self.movement.pk])
        self.assertContains(self.client.get(edit_url), "Editar pago")
        response = self.client.post(edit_url, {
            "kind": "expense", "date": timezone.localdate().isoformat(),
            "amount": "1234.56", "currency": "ARS", "account": self.account.pk,
            "recipient": "Comercio", "description": "Motivo corregido",
            "category": "food", "action": "confirm",
        })
        self.assertRedirects(response, self.url)
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.description, "Motivo corregido")

    def test_incomplete_and_transfer_details(self):
        self.movement.amount = None
        self.movement.date = None
        self.movement.account = None
        self.movement.description = ""
        self.movement.category = ""
        self.movement.status = "pending"
        self.movement.kind = "transfer"
        self.movement.destination_account = self.account
        self.movement.save()
        response = self.client.get(self.url)
        for text in ("Sin importe", "Sin fecha", "Sin cuenta",
                     "Sin motivo registrado", "Pendiente", "Cuenta de destino"):
            self.assertContains(response, text)

    def test_demo_detail_uses_same_read_only_card(self):
        response = self.client.get("/demo/?detail=1")
        self.assertTemplateUsed(response, "registro/detail.html")
        self.assertContains(response, "Datos ficticios")
        self.assertNotContains(response, ">Editar</a>")
        self.assertNotContains(response, "Eliminar pago")
        self.assertNotContains(response, 'id="id_amount"')
        self.assertEqual(self.client.get("/demo/?detail=999").status_code, 404)
