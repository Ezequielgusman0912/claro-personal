import warnings
from decimal import Decimal

from django import forms
from PIL import Image, UnidentifiedImageError

from .models import Account, Movement

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_RECEIPT_PIXELS = 20_000_000


class UploadForm(forms.Form):
    receipt = forms.FileField(
        required=False,
        label="Comprobante",
        widget=forms.ClearableFileInput(attrs={
            "accept": "image/jpeg,image/png,image/webp", "required": True,
        }),
    )
    ocr_text = forms.CharField(required=False, max_length=30_000, widget=forms.HiddenInput)

    def clean_receipt(self):
        receipt = self.cleaned_data.get("receipt")
        if not receipt:
            return receipt
        if receipt.size > MAX_RECEIPT_BYTES:
            raise forms.ValidationError("La imagen no puede superar los 8 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(receipt)
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise forms.ValidationError("Usa una imagen JPG, PNG o WebP.")
                if image.width * image.height > MAX_RECEIPT_PIXELS:
                    raise forms.ValidationError("La imagen es demasiado grande. Reducila a menos de 20 megapixeles.")
                extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image.format]
                image.verify()
        except (
            UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise forms.ValidationError("El archivo no es una imagen valida o es demasiado grande.") from exc
        finally:
            receipt.seek(0)
        receipt.name = f"comprobante.{extension}"
        return receipt

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("receipt") and not cleaned_data.get("ocr_text", "").strip():
            raise forms.ValidationError("Selecciona una imagen para leer o completa los datos a mano.")
        return cleaned_data


class MovementForm(forms.ModelForm):
    amount = forms.DecimalField(
        label="Importe", required=False, max_digits=14, decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )

    class Meta:
        model = Movement
        fields = [
            "kind", "date", "amount", "currency", "account", "destination_account",
            "recipient", "operation_id", "description", "category", "notes",
        ]
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "description": forms.TextInput(attrs={"placeholder": "Ej: mi parte de la cena del viernes"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, confirm=False, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(owner=user)
        self.fields["account"].queryset = accounts
        self.fields["destination_account"].queryset = accounts
        self.instance.owner = user
        self.instance.status = (
            Movement.Status.CONFIRMED if confirm else Movement.Status.PENDING
        )


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "bank"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.owner = user

    def clean_name(self):
        name = self.cleaned_data["name"]
        if Account.objects.filter(owner=self.instance.owner, name=name).exists():
            raise forms.ValidationError("Ya tenes una cuenta con ese nombre.")
        return name
