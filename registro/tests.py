import tempfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from PIL import Image

from .forms import MAX_RECEIPT_BYTES, MovementForm, UploadForm
from .models import Account, Movement
from .ocr import ExtractionError, extract_receipt, parse_receipt


def image_upload():
    stream = BytesIO()
    Image.new("RGB", (80, 120), color="white").save(stream, "PNG")
    return SimpleUploadedFile("pago.png", stream.getvalue(), content_type="image/png")


class PaymentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("personal", password="test-pass-12345")
        cls.other = get_user_model().objects.create_user("other", password="test-pass-12345")
        cls.account = Account.objects.create(owner=cls.user, name="Galicia", bank="galicia")
        cls.destination = Account.objects.create(owner=cls.user, name="Mercado Pago", bank="mp")
        cls.other_account = Account.objects.create(owner=cls.other, name="Ajena", bank="other")

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media.name, OCR_ENABLED=False,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        self.settings_override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.client.force_login(self.user)

    def movement(self, **kwargs):
        data = {
            "owner": self.user, "account": self.account,
            "date": timezone.localdate(), "amount": Decimal("1234.56"),
            "recipient": "Comercio", "description": "Compra semanal",
            "category": "food", "status": "confirmed",
        }
        data.update(kwargs)
        return Movement.objects.create(**data)

    def valid_data(self, **kwargs):
        data = {
            "kind": "expense", "date": timezone.localdate().isoformat(),
            "amount": "1234.56", "currency": "ARS",
            "account": self.account.pk, "recipient": "Comercio",
            "description": "Compra semanal", "category": "food",
            "action": "confirm",
        }
        data.update(kwargs)
        return data

    def test_demo_is_public_and_does_not_create_records(self):
        self.client.logout()
        for url in (
            "/demo/", "/demo/?status=pending", "/demo/?screen=new",
            "/demo/?screen=accounts", "/demo/?detail=2",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "ficticios")
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 3)

    def test_demo_summary_and_excel(self):
        response = self.client.get("/demo/")
        self.assertEqual(response.context["expense_total"], Decimal("177230"))
        self.assertEqual(response.context["pending_count"], 2)
        self.assertEqual(response.context["transfers_count"], 1)
        download = self.client.get("/demo/?download=1")
        workbook = load_workbook(BytesIO(download.content))
        self.assertEqual(workbook.active.max_row, 9)

    def test_demo_rejects_writes(self):
        response = self.client.post("/demo/", self.valid_data())
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Movement.objects.exists())

    def test_anonymous_cannot_access_private_surfaces(self):
        movement = self.movement()
        self.client.logout()
        for url in ("/", "/nuevo/", "/cuentas/", "/exportar/",
                    f"/movimientos/{movement.pk}/", f"/movimientos/{movement.pk}/comprobante/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_login_hides_app_navigation_for_anonymous_users(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<aside class="sidebar">')
        self.assertContains(response, 'class="app app-login"')
        self.assertContains(response, "Ingresar")

    def test_other_user_cannot_read_or_edit_movement(self):
        movement = self.movement(owner=self.other, account=self.other_account)
        self.assertEqual(self.client.get(reverse("edit", args=[movement.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("edit", args=[movement.pk]), self.valid_data()).status_code, 404)
        self.assertEqual(self.client.get(reverse("receipt", args=[movement.pk])).status_code, 404)
        self.assertEqual(self.client.get("/").context["total_count"], 0)
        sheet = load_workbook(BytesIO(self.client.get("/exportar/").content)).active
        self.assertEqual(sheet.max_row, 1)

    def test_confirm_new_movement(self):
        response = self.client.post("/nuevo/", self.valid_data())
        self.assertRedirects(response, "/")
        movement = Movement.objects.get()
        self.assertEqual(movement.owner, self.user)
        self.assertEqual(movement.status, "confirmed")
        self.assertEqual(movement.amount, Decimal("1234.56"))

    def test_confirm_requires_context_and_payment_fields(self):
        response = self.client.post("/nuevo/", self.valid_data(
            description="", recipient="", date="", account="", amount="", category=""
        ))
        self.assertEqual(response.status_code, 200)
        for field in ("description", "recipient", "date", "account", "amount", "category"):
            self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Movement.objects.exists())

    def test_can_save_draft_without_inventing_date_amount_or_recipient(self):
        response = self.client.post("/nuevo/", {
            "action": "pending", "kind": "expense", "currency": "ARS",
        })
        self.assertRedirects(response, "/")
        movement = Movement.objects.get()
        self.assertEqual(movement.status, "pending")
        self.assertIsNone(movement.date)
        self.assertIsNone(movement.amount)
        self.assertEqual(self.client.get("/").context["pending_count"], 1)

    def test_owner_is_not_controlled_by_post(self):
        self.client.post("/nuevo/", self.valid_data(owner=self.other.pk))
        self.assertEqual(Movement.objects.get().owner, self.user)

    def test_cannot_select_another_users_account(self):
        response = self.client.post("/nuevo/", self.valid_data(account=self.other_account.pk))
        self.assertIn("account", response.context["form"].errors)
        self.assertFalse(Movement.objects.exists())

    def test_model_rejects_cross_owner_accounts(self):
        movement = Movement(owner=self.user, account=self.other_account)
        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_transfer_requires_different_own_destination(self):
        form = MovementForm(self.valid_data(
            kind="transfer", destination_account=self.account.pk
        ), user=self.user, confirm=True)
        self.assertFalse(form.is_valid())
        self.assertIn("destination_account", form.errors)
        response = self.client.post("/nuevo/", self.valid_data(
            kind="transfer", destination_account=self.destination.pk, category=""
        ))
        self.assertRedirects(response, "/")
        self.assertEqual(Movement.objects.get().kind, "transfer")
        self.assertEqual(self.client.get("/").context["expense_total"], Decimal("0"))

    def test_transfer_missing_destination_is_invalid(self):
        response = self.client.post("/nuevo/", self.valid_data(kind="transfer"))
        self.assertIn("destination_account", response.context["form"].errors)

    def test_zero_and_negative_amount_are_invalid(self):
        for value in ("0", "-50"):
            with self.subTest(value=value):
                response = self.client.post("/nuevo/", self.valid_data(amount=value))
                self.assertIn("amount", response.context["form"].errors)

    def test_summary_does_not_mix_currency_pending_or_income(self):
        self.movement()
        self.movement(amount=Decimal("100"), currency="USD")
        self.movement(amount=Decimal("9000"), status="pending")
        self.movement(amount=Decimal("50000"), kind="income")
        response = self.client.get("/")
        self.assertEqual(response.context["expense_total"], Decimal("1234.56"))
        self.assertContains(response, "1.234,56")
        self.assertEqual(response.context["pending_count"], 1)
        dollars = self.client.get("/?currency=USD")
        self.assertEqual(dollars.context["expense_total"], Decimal("100"))

    def test_filters_and_export_match(self):
        self.movement(recipient="Carrefour")
        self.movement(recipient="Farmacia")
        self.movement(date=date(2020, 1, 1))
        query = "?q=Carrefour&account=" + str(self.account.pk)
        context = self.client.get("/" + query).context
        self.assertEqual(len(context["rows"]), 1)
        sheet = load_workbook(BytesIO(self.client.get("/exportar/" + query).content)).active
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual(sheet["G2"].value, "Carrefour")
        self.assertAlmostEqual(sheet["B2"].value, 1234.56)

    def test_invalid_filters_have_visible_errors_and_do_not_export(self):
        for query in ("?currency=EUR", "?month=0000-01", "?month=garbage", "?account=999999"):
            with self.subTest(query=query):
                response = self.client.get("/" + query)
                self.assertTrue(response.context["filters"].errors)
                self.assertEqual(response.context["total_count"], 0)
                self.assertEqual(self.client.get("/exportar/" + query).status_code, 400)

    def test_server_ocr_fallback_does_not_save_the_uploaded_image(self):
        with self.assertLogs("registro.views", level="WARNING"):
            response = self.client.post("/comprobantes/subir/", {"receipt": image_upload()})
        movement = Movement.objects.get()
        self.assertRedirects(response, reverse("edit", args=[movement.pk]))
        self.assertEqual(movement.status, "pending")
        self.assertIsNone(movement.amount)
        self.assertIsNone(movement.date)
        self.assertFalse(movement.receipt)
        self.assertEqual(movement.receipt_hash, "")
        self.assertEqual(movement.extracted_text, "")
        self.assertEqual(list(Path(self.media.name).iterdir()), [])
        self.assertEqual(self.client.get(reverse("receipt", args=[movement.pk])).status_code, 404)

    def test_browser_ocr_data_is_saved_without_sending_or_storing_the_image(self):
        text = (
            "Mercado Pago\nComprobante de transferencia\n"
            "16/noviembre/2026 a las 19:56.\n$ 11.400\nOrigen y destino\n"
            "Ana Ejemplo\nMercado Pago\nCVU: 123\nCUIT/CUIL: 20-00000000-1\n"
            "Jorge Alberto Emilio Fenoglio\nBanco ejemplo\nCBU: 456\n"
            "CUIT/CUIL: 20-00000000-2\n"
            "N.° de operación de Mercado Pago\n188952849457"
        )
        response = self.client.post("/comprobantes/subir/", {
            "ocr_text": text,
            "amount": "1", "recipient": "No confiable",
        })
        movement = Movement.objects.get()
        self.assertRedirects(response, reverse("edit", args=[movement.pk]))
        self.assertEqual(movement.amount, Decimal("11400"))
        self.assertEqual(movement.date, date(2026, 11, 16))
        self.assertEqual(movement.recipient, "Jorge Alberto Emilio Fenoglio")
        self.assertEqual(movement.operation_id, "188952849457")
        self.assertEqual(movement.status, "pending")
        self.assertEqual(movement.extracted_data["amount"], "11400")
        self.assertEqual(movement.extracted_text, "")
        self.assertFalse(movement.receipt)
        self.assertEqual(movement.receipt_hash, "")
        self.assertEqual(list(Path(self.media.name).iterdir()), [])

    def test_browser_ocr_text_is_size_limited(self):
        response = self.client.post("/comprobantes/subir/", {
            "ocr_text": "x" * 30_001,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Movement.objects.exists())

    def test_upload_requires_an_image_or_browser_ocr_text(self):
        response = self.client.post("/comprobantes/subir/", {})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Movement.objects.exists())

    @patch("registro.views.extract_receipt")
    def test_extraction_proposes_data_without_confirming(self, extract):
        extract.return_value = ("Monto: $ 1.234,56", {
            "amount": "1234.56", "recipient": "Comercio", "date": "2026-11-12",
        })
        self.client.post("/comprobantes/subir/", {"receipt": image_upload()})
        movement = Movement.objects.get()
        self.assertEqual(movement.amount, Decimal("1234.56"))
        self.assertEqual(movement.extracted_data["amount"], "1234.56")
        self.assertEqual(movement.status, "pending")
        response = self.client.post(reverse("edit", args=[movement.pk]), self.valid_data(amount="1250.00"))
        self.assertRedirects(response, "/")
        movement.refresh_from_db()
        self.assertEqual(movement.amount, Decimal("1250"))
        self.assertEqual(movement.extracted_data["amount"], "1234.56")

    def test_possible_duplicates_are_visible_but_not_removed(self):
        self.movement(operation_id="SAME")
        duplicate = self.movement(operation_id="SAME")
        response = self.client.get(reverse("edit", args=[duplicate.pk]))
        self.assertContains(response, "posibles duplicados")
        self.assertEqual(Movement.objects.count(), 2)

    def test_invalid_image_is_rejected(self):
        form = UploadForm(files={"receipt": SimpleUploadedFile(
            "malicioso.png", b"<script>bad</script>", content_type="image/png"
        )})
        self.assertFalse(form.is_valid())
        self.assertIn("receipt", form.errors)

    def test_image_extension_comes_from_validated_content(self):
        image = image_upload()
        image.name = "fake.html"
        form = UploadForm(files={"receipt": image})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["receipt"].name, "comprobante.png")

    def test_oversize_upload_is_rejected(self):
        file = image_upload()
        file.size = MAX_RECEIPT_BYTES + 1
        form = UploadForm(files={"receipt": file})
        self.assertFalse(form.is_valid())
        self.assertIn("8 MB", str(form.errors))

    def test_excel_strings_are_not_formulas(self):
        self.movement(recipient="=HYPERLINK(\"bad\")", description="+SUM(1,1)")
        sheet = load_workbook(BytesIO(self.client.get("/exportar/").content)).active
        self.assertEqual(sheet["G2"].data_type, "s")
        self.assertEqual(sheet["H2"].data_type, "s")
        self.assertEqual(sheet["G2"].value, '=HYPERLINK("bad")')

    def test_accounts_create_and_reject_duplicate_without_error(self):
        response = self.client.post("/cuentas/", {"name": "Efectivo", "bank": "other"})
        self.assertRedirects(response, "/cuentas/")
        response = self.client.post("/cuentas/", {"name": "Efectivo", "bank": "other"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(Account.objects.filter(owner=self.user, name="Efectivo").count(), 1)

    def test_new_and_existing_forms_render(self):
        self.assertEqual(self.client.get("/nuevo/").status_code, 200)
        movement = self.movement()
        self.assertEqual(self.client.get(reverse("edit", args=[movement.pk])).status_code, 200)

    def test_household_dashboard_keeps_actions_without_marketing_help(self):
        response = self.client.get("/demo/")
        for text in ("Mis pagos", "Leer comprobante", "Cargar a mano", "Filtros", "Excel"):
            self.assertContains(response, text)
        for text in ("Tu yo de fin de mes", "Que cada movimiento tenga una historia", "DEL COMPROBANTE AL REGISTRO"):
            self.assertNotContains(response, text)
        self.assertContains(response, 'class="movement-row"', count=8)

    def test_manual_entry_and_receipt_upload_remain_separate_forms(self):
        response = self.client.get("/nuevo/")
        html = response.content.decode()
        self.assertLess(html.index('class="upload-form"'), html.index('id="manual"'))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "La imagen se lee en este dispositivo y no se guarda.")
        self.assertNotContains(response, 'name="skip_ocr"')
        self.assertContains(response, 'name="action" value="pending"')
        self.assertContains(response, 'name="action" value="confirm"')
        self.assertContains(response, 'aria-label="Cerrar sesión"')

    def test_optional_details_expand_for_validation_errors(self):
        response = self.client.post("/nuevo/", self.valid_data(operation_id="x" * 101))
        self.assertEqual(response.status_code, 200)
        self.assertIn("operation_id", response.context["form"].errors)
        self.assertContains(response, '<details class="optional-fields" open>')
        self.assertFalse(Movement.objects.exists())

    @patch("registro.views.extract_receipt")
    def test_retry_fills_blanks_and_preserves_saved_context(self, extract):
        movement = self.movement(
            status="pending", amount=None, date=None, account=None,
            recipient="Nombre corregido", description="Mi motivo", category="",
            receipt=image_upload(),
        )
        extract.return_value = ("Texto original", {
            "amount": "11400", "date": "2026-11-16", "recipient": "Sugerencia OCR",
            "operation_id": "123456789", "currency": "ARS", "source_bank": "mp",
        })
        response = self.client.post(reverse("retry_extraction", args=[movement.pk]))
        self.assertRedirects(response, reverse("edit", args=[movement.pk]))
        movement.refresh_from_db()
        self.assertEqual(movement.amount, Decimal("11400"))
        self.assertEqual(movement.date, date(2026, 11, 16))
        self.assertEqual(movement.recipient, "Nombre corregido")
        self.assertEqual(movement.description, "Mi motivo")
        self.assertEqual(movement.account, self.destination)
        self.assertEqual(movement.status, "pending")
        self.assertEqual(movement.extracted_text, "")

    @patch("registro.views.extract_receipt")
    def test_retry_preserves_prior_amount_currency_and_extraction(self, extract):
        movement = self.movement(
            status="pending", currency="USD", receipt=image_upload(),
            extracted_text="Primera lectura", extracted_data={"amount": "1200"},
        )
        extract.return_value = ("Otra lectura", {"amount": "500", "currency": "ARS"})
        self.client.post(reverse("retry_extraction", args=[movement.pk]))
        movement.refresh_from_db()
        self.assertEqual(movement.amount, Decimal("1234.56"))
        self.assertEqual(movement.currency, "USD")
        self.assertEqual(movement.extracted_text, "Primera lectura")
        self.assertEqual(movement.extracted_data["amount"], "1200")

    @patch("registro.views.extract_receipt", side_effect=ExtractionError("OCR no disponible"))
    def test_retry_error_is_visible_and_preserves_record(self, extract):
        movement = self.movement(status="pending", receipt=image_upload())
        with self.assertLogs("registro.views", level="WARNING"):
            response = self.client.post(
                reverse("retry_extraction", args=[movement.pk]), follow=True
            )
        self.assertContains(response, "No se pudo leer")
        movement.refresh_from_db()
        self.assertEqual(movement.amount, Decimal("1234.56"))

    @patch("registro.views.extract_receipt")
    def test_retry_requires_owner_post_pending_and_receipt(self, extract):
        movement = self.movement(status="pending", receipt=image_upload())
        url = reverse("retry_extraction", args=[movement.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.user)
        movement.status = "confirmed"
        movement.save()
        self.client.post(url)
        movement.status = "pending"
        movement.receipt = ""
        movement.save()
        self.client.post(url)
        extract.assert_not_called()

    @patch("registro.views.extract_receipt")
    def test_upload_does_not_guess_between_two_accounts_at_same_bank(self, extract):
        Account.objects.create(owner=self.user, name="Otra MP", bank="mp")
        extract.return_value = ("Monto: $ 100", {"amount": "100", "source_bank": "mp"})
        self.client.post("/comprobantes/subir/", {"receipt": image_upload()})
        self.assertIsNone(Movement.objects.get().account_id)


class ExtractionTests(TestCase):
    def test_mercado_pago_layout_with_month_name_and_separate_operation_line(self):
        data = parse_receipt(
            "mercado\npago\nComprobante de transferencia\n"
            "16/noviembre/2026 a las 19:56.\n\n$ 11.400\nMotivo: Varios\n"
            "Origen y destino\n<S Ana Ejemplo\nMercado Pago\n"
            "CVU: 0000000000000000000001\nCUIT/CUIL: 20-00000000-1\n"
            "w Pablo Prueba\nBanco de ejemplo\nCBU: 0000000000000000000002\n"
            "CUIT/CUIL: 20-00000000-2\n"
            "N.? de operación de Mercado Pago\n123456789012\n"
            "Código de identificación\nABCD1234"
        )
        self.assertEqual(data, {
            "amount": "11400", "currency": "ARS", "date": "2026-11-16",
            "recipient": "Pablo Prueba", "operation_id": "123456789012",
            "source_bank": "mp",
        })

    def test_mp_browser_ocr_handles_duplicated_account_letter(self):
        data = parse_receipt(
            "mercado\npago\nComprobante de transferencia\n"
            "16/noviembre/2026 a las 19:56.\n$ 11.400\nMotivo: Varios\n"
            "Origen y destino\nGS Ezequiel Alejandro Gusman\nMercado Pago\n"
            "CVvU: 0000003100046988702732\nCUIT/CUIL: 23-43562306-9\n"
            "= Jorge Alberto Emilio Fenoglio\nNaranja Digital Compañia Financiera S.A.\n"
            "CBU: 4530000800015466618700\nCUIT/CUIL: 20-11619568-3\n"
            "N.* de operación de Mercado Pago\n188952849457\n"
            "Código de identificación\n275819419699AGBA34"
        )
        self.assertEqual(data, {
            "amount": "11400", "currency": "ARS", "date": "2026-11-16",
            "recipient": "Jorge Alberto Emilio Fenoglio",
            "operation_id": "188952849457", "source_bank": "mp",
        })

    def test_mp_does_not_use_sender_when_recipient_block_is_missing(self):
        data = parse_receipt(
            "Mercado Pago\nComprobante de transferencia\n"
            "Origen y destino\nAna Ejemplo\nMercado Pago\nCVU: 123\n"
            "CUIT/CUIL: 20-00000000-1"
        )
        self.assertNotIn("recipient", data)
        self.assertNotIn("description", data)

    def test_argentine_amount_date_and_operation(self):
        data = parse_receipt(
            "Monto: ARS 1.234,56\nFecha: 12/11/2026\n"
            "Destinatario: Ana Perez\nNumero de operacion: 123ABC"
        )
        self.assertEqual(data, {
            "amount": "1234.56", "currency": "ARS", "date": "2026-11-12",
            "recipient": "Ana Perez", "operation_id": "123ABC",
        })

    def test_usd_and_grouped_pesos(self):
        self.assertEqual(parse_receipt("Total: USD 25.50")["currency"], "USD")
        self.assertEqual(parse_receipt("Importe total: $ 35.000")["amount"], "35000")

    def test_unrecognised_values_are_not_invented(self):
        self.assertEqual(parse_receipt("Comprobante sin datos"), {})
        self.assertNotIn("date", parse_receipt("Fecha: 31/02/2026"))
        self.assertNotIn("amount", parse_receipt("Monto: $ 0"))
        self.assertNotIn("amount", parse_receipt("Monto: $ 99999999999999999"))

    @override_settings(OCR_ENABLED=False)
    def test_disabled_ocr_is_an_explicit_error(self):
        with self.assertRaisesMessage(ExtractionError, "no esta habilitada"):
            extract_receipt(image_upload())

    @override_settings(OCR_ENABLED=True)
    @patch("registro.ocr.pytesseract.image_to_string", side_effect=RuntimeError("timeout"))
    def test_ocr_timeout_is_explicit(self, mocked):
        with self.assertRaisesMessage(ExtractionError, "No pudimos leer"):
            extract_receipt(image_upload())
