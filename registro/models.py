import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


def receipt_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"receipts/{instance.owner_id}/{uuid.uuid4().hex}{extension}"


class Account(models.Model):
    class Bank(models.TextChoices):
        MP = "mp", "Mercado Pago"
        GALICIA = "galicia", "Galicia"
        OTHER = "other", "Otra cuenta"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField("nombre", max_length=80)
    bank = models.CharField("entidad", max_length=16, choices=Bank.choices)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="personal_unique_account")
        ]

    def __str__(self):
        return self.name


class Movement(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Gasto"
        INCOME = "income", "Ingreso"
        TRANSFER = "transfer", "Entre mis cuentas"

    class Status(models.TextChoices):
        PENDING = "pending", "Por identificar"
        CONFIRMED = "confirmed", "Confirmado"

    class Currency(models.TextChoices):
        ARS = "ARS", "Pesos argentinos (ARS)"
        USD = "USD", "Dolares (USD)"

    class Category(models.TextChoices):
        FOOD = "food", "Comida y supermercado"
        HOME = "home", "Hogar y servicios"
        TRANSPORT = "transport", "Transporte"
        HEALTH = "health", "Salud"
        LEISURE = "leisure", "Salidas y ocio"
        SHOPPING = "shopping", "Compras"
        EDUCATION = "education", "Educacion"
        OTHER = "other", "Otros"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(
        Account, verbose_name="cuenta de origen", on_delete=models.PROTECT,
        related_name="movements", null=True, blank=True,
    )
    destination_account = models.ForeignKey(
        Account, verbose_name="cuenta de destino propia", on_delete=models.PROTECT,
        related_name="incoming_transfers", null=True, blank=True,
    )
    kind = models.CharField("tipo", max_length=16, choices=Kind.choices, default=Kind.EXPENSE)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    date = models.DateField("fecha del pago", null=True, blank=True)
    amount = models.DecimalField(
        "importe", max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(
        "moneda", max_length=3, choices=Currency.choices, default=Currency.ARS
    )
    recipient = models.CharField("destinatario / comercio", max_length=180, blank=True)
    operation_id = models.CharField("numero de operacion", max_length=100, blank=True)
    description = models.CharField("para que fue", max_length=250, blank=True)
    category = models.CharField(
        "categoria", max_length=16, choices=Category.choices, blank=True
    )
    notes = models.TextField("notas", blank=True)
    receipt = models.FileField("comprobante", upload_to=receipt_path, blank=True)
    receipt_hash = models.CharField(max_length=64, blank=True)
    extracted_text = models.TextField(blank=True)
    extracted_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "receipt_hash"],
                condition=~Q(receipt_hash=""),
                name="personal_unique_receipt",
            ),
            models.CheckConstraint(
                condition=Q(amount__isnull=True) | Q(amount__gt=0),
                name="personal_positive_amount",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        for field in ("account", "destination_account"):
            account = getattr(self, field)
            if account and account.owner_id != self.owner_id:
                errors[field] = "La cuenta no pertenece a este usuario."
        if self.kind == self.Kind.TRANSFER:
            if self.account_id and self.account_id == self.destination_account_id:
                errors["destination_account"] = "Elegi una cuenta distinta a la de origen."
        elif self.destination_account_id:
            errors["destination_account"] = "Solo corresponde en transferencias propias."
        if self.status == self.Status.CONFIRMED:
            required = ["date", "amount", "account", "description"]
            if self.kind == self.Kind.TRANSFER:
                required.append("destination_account")
            elif self.kind == self.Kind.EXPENSE:
                required.extend(["category", "recipient"])
            for field in required:
                if not getattr(self, field):
                    errors[field] = "Completa este dato para confirmar el movimiento."
        if errors:
            raise ValidationError(errors)
