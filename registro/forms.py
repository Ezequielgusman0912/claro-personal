from decimal import Decimal

from django import forms

from .models import Account, Movement


class ReceiptTextForm(forms.Form):
    ocr_text = forms.CharField(max_length=30_000)


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
