import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .demo import sample_data
from .forms import AccountForm, MovementForm, UploadForm
from .models import Account, Movement
from .ocr import ExtractionError, extract_receipt, parse_receipt

logger = logging.getLogger(__name__)
MONTHS = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def apply_extraction(movement, extracted):
    allowed = {"amount", "date", "recipient", "operation_id", "currency"}
    amount_was_empty = movement.amount is None
    for field in allowed:
        if field not in extracted:
            continue
        if field == "currency":
            if amount_was_empty:
                movement.currency = extracted[field]
        elif not getattr(movement, field):
            setattr(movement, field, extracted[field])
    if not movement.account_id and extracted.get("source_bank"):
        matches = list(Account.objects.filter(
            owner=movement.owner, bank=extracted["source_bank"]
        )[:2])
        if len(matches) == 1:
            movement.account = matches[0]


class FiltersForm(forms.Form):
    month = forms.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", required=False)
    q = forms.CharField(max_length=180, required=False)
    account = forms.ChoiceField(required=False)
    status = forms.ChoiceField(
        choices=[("", "Todos los estados"), *Movement.Status.choices], required=False
    )
    currency = forms.ChoiceField(choices=Movement.Currency.choices)

    def __init__(self, *args, accounts, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].choices = [
            ("", "Todas las cuentas"), *[(str(a.pk), a.name) for a in accounts]
        ]

    def clean_month(self):
        value = self.cleaned_data["month"]
        if value:
            try:
                date.fromisoformat(value + "-01")
            except ValueError as exc:
                raise forms.ValidationError("El mes no es valido.") from exc
        return value


def filtered_context(request, accounts, rows, is_demo=False):
    today = timezone.localdate()
    params = request.GET.copy()
    if "month" not in params:
        params["month"] = today.strftime("%Y-%m")
    if "currency" not in params:
        params["currency"] = "ARS"
    filters = FiltersForm(params, accounts=accounts)
    visible = []
    if filters.is_valid():
        cleaned = filters.cleaned_data
        for row in rows:
            if cleaned["month"] and row.date and row.date.strftime("%Y-%m") != cleaned["month"]:
                continue
            if row.currency != cleaned["currency"]:
                continue
            if cleaned["account"] and str(row.account_id) != cleaned["account"]:
                continue
            if cleaned["status"] and row.status != cleaned["status"]:
                continue
            query = cleaned["q"].casefold()
            if query and query not in " ".join([
                row.recipient, row.description, row.notes, row.operation_id,
            ]).casefold():
                continue
            visible.append(row)
    expense_total = Decimal("0")
    grouped = defaultdict(Decimal)
    pending_count = sum(row.status == "pending" for row in visible)
    confirmed_count = sum(row.status == "confirmed" for row in visible)
    transfers_count = sum(row.kind == "transfer" for row in visible)
    for row in visible:
        if row.kind == "expense" and row.status == "confirmed" and row.amount is not None:
            expense_total += row.amount
            grouped[row.get_category_display() or "Sin categoria"] += row.amount
    categories = [
        {"name": name, "amount": amount, "percent": round(amount / expense_total * 100)}
        for name, amount in sorted(grouped.items(), key=lambda item: item[1], reverse=True)
    ] if expense_total else []
    month = params.get("month", "")
    label = "Todos los meses"
    if filters.is_valid() and month:
        parsed = date.fromisoformat(month + "-01")
        label = f"{MONTHS[parsed.month]} {parsed.year}"
    base = reverse("demo" if is_demo else "dashboard")
    return {
        "is_demo": is_demo, "rows": visible, "accounts": accounts, "filters": filters,
        "month_label": label, "currency": params.get("currency", "ARS"),
        "expense_total": expense_total, "pending_count": pending_count,
        "confirmed_count": confirmed_count, "transfers_count": transfers_count,
        "categories": categories, "total_count": len(visible),
        "progress": round(confirmed_count / len(visible) * 100) if visible else 0,
        "dashboard_url": base, "pending_url": base + "?status=pending",
        "new_url": base + "?screen=new" if is_demo else reverse("new"),
        "accounts_url": base + "?screen=accounts" if is_demo else reverse("accounts"),
        "export_url": (
            base + "?" + params.urlencode() + "&download=1"
            if is_demo else reverse("export") + "?" + params.urlencode()
        ),
    }


@never_cache
@login_required
def dashboard(request):
    accounts = list(Account.objects.filter(owner=request.user))
    rows = Movement.objects.filter(owner=request.user).select_related("account", "destination_account")
    context = filtered_context(request, accounts, rows)
    context["upload_form"] = UploadForm()
    return render(request, "registro/dashboard.html", context)


@require_GET
def demo(request):
    accounts, rows = sample_data()
    context = filtered_context(request, accounts, rows, is_demo=True)
    if request.GET.get("download") == "1":
        if context["filters"].errors:
            return render(request, "registro/dashboard.html", context, status=400)
        return excel_response(context["rows"], demo=True)
    screen = request.GET.get("screen")
    if screen == "accounts":
        return render(request, "registro/accounts.html", context)
    if screen == "new" or request.GET.get("detail"):
        instance = None
        if request.GET.get("detail"):
            instance = next((row for row in rows if str(row.pk) == request.GET["detail"]), None)
            if instance is None:
                raise Http404
        form = MovementForm(instance=instance, user=None)
        for name in ("account", "destination_account"):
            form.fields[name] = forms.ChoiceField(
                label=form.fields[name].label, required=False,
                choices=[("", "---------"), *[(a.pk, a.name) for a in accounts]],
                initial=getattr(instance, name + "_id", None),
            )
        return render(request, "registro/form.html", {
            **context, "form": form, "movement": instance,
        })
    return render(request, "registro/dashboard.html", context)


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def new_movement(request):
    form = MovementForm(
        request.POST or None, user=request.user,
        confirm=request.POST.get("action") == "confirm",
    )
    if request.method == "POST" and form.is_valid():
        movement = form.save()
        messages.success(request, "Movimiento confirmado." if movement.status == "confirmed" else "Guardado para completar despues.")
        return redirect("dashboard")
    return render(request, "registro/form.html", {
        "form": form, "upload_form": UploadForm(),
    })


@never_cache
@login_required
@require_POST
def upload_receipt(request):
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "registro/form.html", {
            "form": MovementForm(user=request.user), "upload_form": form,
        }, status=400)
    file = form.cleaned_data["receipt"]
    text = form.cleaned_data["ocr_text"].strip()
    extracted = {}
    extraction_failed = False
    if text:
        extracted = parse_receipt(text)
    else:
        try:
            text, extracted = extract_receipt(file)
        except ExtractionError as exc:
            logger.warning("Receipt extraction unavailable: %s", exc)
            messages.warning(request, str(exc))
            extraction_failed = True
    if text and extracted:
        messages.info(
            request,
            "Lectura terminada. Revisa los datos antes de confirmar."
        )
    elif text:
        messages.info(request, "No encontramos datos reconocibles. Completa los campos manualmente.")
    elif not extraction_failed:
        messages.info(request, "La imagen no se guardo. Completa los campos manualmente.")
    movement = Movement(
        owner=request.user, extracted_data=extracted,
    )
    apply_extraction(movement, extracted)
    with transaction.atomic():
        movement.save(force_insert=True)
    return redirect("edit", pk=movement.pk)


@never_cache
@login_required
@require_POST
def retry_extraction(request, pk):
    movement = get_object_or_404(Movement, pk=pk, owner=request.user)
    if movement.status != Movement.Status.PENDING or not movement.receipt:
        messages.error(request, "Solo se pueden leer comprobantes de movimientos pendientes.")
        return redirect("edit", pk=pk)
    try:
        with movement.receipt.open("rb") as file:
            text, extracted = extract_receipt(file)
    except (ExtractionError, FileNotFoundError) as exc:
        logger.warning("Receipt retry failed for movement %s: %s", pk, exc)
        messages.error(request, "No se pudo leer el comprobante. Los datos guardados no cambiaron. " + str(exc))
        return redirect("edit", pk=pk)
    with transaction.atomic():
        movement = get_object_or_404(
            Movement.objects.select_for_update(), pk=pk, owner=request.user
        )
        if movement.status != Movement.Status.PENDING:
            messages.warning(request, "El movimiento ya fue confirmado. No modificamos sus datos.")
            return redirect("edit", pk=pk)
        apply_extraction(movement, extracted)
        movement.extracted_data = {**extracted, **movement.extracted_data}
        movement.save()
    messages.info(
        request,
        "Lectura terminada: completamos los campos vacios sin cambiar tus datos guardados. "
        "Revisa las sugerencias antes de confirmar."
        if extracted else "No encontramos campos reconocibles. Los datos guardados no cambiaron.",
    )
    return redirect("edit", pk=pk)


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def edit_movement(request, pk):
    movement = get_object_or_404(Movement, pk=pk, owner=request.user)
    form = MovementForm(
        request.POST or None, instance=movement, user=request.user,
        confirm=request.POST.get("action") == "confirm",
    )
    if request.method == "POST" and form.is_valid():
        movement = form.save()
        messages.success(request, "Movimiento confirmado." if movement.status == "confirmed" else "Cambios guardados como pendiente.")
        return redirect("dashboard")
    duplicates = Movement.objects.filter(owner=request.user).exclude(pk=pk)
    if movement.operation_id:
        duplicates = duplicates.filter(
            operation_id=movement.operation_id, account=movement.account
        )
    elif movement.amount is not None and movement.date:
        duplicates = duplicates.filter(
            amount=movement.amount, currency=movement.currency,
            date=movement.date, recipient__iexact=movement.recipient,
        )
    else:
        duplicates = duplicates.none()
    return render(request, "registro/form.html", {
        "form": form, "movement": movement, "duplicates": duplicates,
    })


@never_cache
@login_required
def receipt(request, pk):
    movement = get_object_or_404(Movement, pk=pk, owner=request.user)
    if not movement.receipt:
        raise Http404
    try:
        file = movement.receipt.open("rb")
    except FileNotFoundError as exc:
        logger.error("Missing receipt for movement %s", movement.pk)
        raise Http404("No se encontro el comprobante.") from exc
    response = FileResponse(file, filename=f"comprobante-{pk}{Path(movement.receipt.name).suffix}")
    response["Content-Disposition"] = f'inline; filename="comprobante-{pk}"'
    response["Cache-Control"] = "private, no-store"
    return response


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def accounts(request):
    form = AccountForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            if not Account.objects.filter(
                owner=request.user, name=form.cleaned_data["name"]
            ).exists():
                raise
            form.add_error("name", "Ya tenes una cuenta con ese nombre.")
        else:
            messages.success(request, "Cuenta agregada.")
            return redirect("accounts")
    return render(request, "registro/accounts.html", {
        "accounts": Account.objects.filter(owner=request.user), "form": form,
    })


def excel_response(rows, demo=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ejemplos" if demo else "Movimientos"
    sheet.append([
        "Fecha", "Importe", "Moneda", "Tipo", "Cuenta", "Cuenta propia de destino",
        "Destinatario", "Para que fue", "Categoria", "Estado", "Operacion", "Notas",
    ])
    for row in rows:
        values = [
            row.date, row.amount, row.currency, row.get_kind_display(),
            str(row.account) if row.account else "",
            str(row.destination_account) if row.destination_account else "",
            row.recipient, row.description, row.get_category_display(),
            row.get_status_display(), row.operation_id, row.notes,
        ]
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
        sheet.cell(sheet.max_row, 1).number_format = "dd/mm/yyyy"
        sheet.cell(sheet.max_row, 2).number_format = '#,##0.00'
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="173C34")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in "ABCDEFGHIJKL":
        sheet.column_dimensions[column].width = 24
    sheet.column_dimensions["H"].width = 46
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        'attachment; filename="pagos-ejemplo.xlsx"' if demo
        else 'attachment; filename="mis-pagos.xlsx"'
    )
    response["Cache-Control"] = "private, no-store"
    return response


@never_cache
@login_required
def export(request):
    context = filtered_context(
        request, list(Account.objects.filter(owner=request.user)),
        Movement.objects.filter(owner=request.user).select_related("account", "destination_account"),
    )
    if context["filters"].errors:
        return render(request, "registro/dashboard.html", context, status=400)
    return excel_response(context["rows"])
