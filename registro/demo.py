from datetime import date
from decimal import Decimal

from django.utils import timezone

from .models import Account, Movement


def sample_data():
    today = timezone.localdate()
    accounts = [
        Account(pk=1, name="Mercado Pago", bank="mp"),
        Account(pk=2, name="Galicia", bank="galicia"),
    ]
    samples = [
        ("Martina López", "Mi parte de la cena del sábado", "18500", "leisure", 1, "confirmed", "expense", 15),
        ("Diego Fernández", "", "35000", "", 0, "pending", "expense", 14),
        ("Carrefour", "Compra semanal del súper", "62480", "food", 0, "confirmed", "expense", 12),
        ("Mis cuentas", "Pasé plata a Mercado Pago", "100000", "", 1, "confirmed", "transfer", 11),
        ("Personal Flow", "Internet de casa · noviembre", "28900", "home", 1, "confirmed", "expense", 10),
        ("Lucía García", "", "12800", "", 0, "pending", "expense", 9),
        ("YPF", "Nafta para el viaje del finde", "45000", "transport", 1, "confirmed", "expense", 8),
        ("Farmacity", "Medicamentos y protector solar", "22350", "health", 0, "confirmed", "expense", 6),
    ]
    rows = []
    for pk, (recipient, description, amount, category, account, status, kind, day) in enumerate(samples, 1):
        rows.append(Movement(
            pk=pk, recipient=recipient, description=description,
            amount=Decimal(amount), category=category, account=accounts[account],
            date=date(today.year, today.month, min(day, today.day)),
            status=status, kind=kind, currency="ARS",
            destination_account=accounts[0] if kind == "transfer" else None,
            operation_id=f"DEMO-{pk:06}",
        ))
    return accounts, rows
