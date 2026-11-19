import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pytesseract
from django.conf import settings
from PIL import Image
from pytesseract import TesseractError, TesseractNotFoundError


class ExtractionError(Exception):
    pass


MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def parse_receipt(text):
    """Only propose explicit, labelled values; all proposals need user review."""
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    is_mp_transfer = (
        "comprobante de transferencia" in normalized.lower()
        and re.search(r"mercado\s+pago", normalized, re.IGNORECASE)
    )
    data = {}
    amount = re.search(
        r"(?:importe(?:\s+total)?|monto(?:\s+total)?|total)\s*:?\s*"
        r"(?:(ARS|USD|US\$|\$)\s*)?([\d.,]+)",
        text, re.IGNORECASE,
    )
    if not amount and is_mp_transfer:
        amount = re.search(
            r"^\s*(ARS|USD|US\$|\$)\s*([\d.,]+)\s*$",
            text, re.MULTILINE | re.IGNORECASE,
        )
    if amount:
        raw = amount[2]
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif raw.count(".") > 1 or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
            raw = raw.replace(".", "")
        try:
            value = Decimal(raw)
            if value > 0 and value <= Decimal("999999999999.99") and value.as_tuple().exponent >= -2:
                data["amount"] = str(value)
                if amount[1]:
                    data["currency"] = "USD" if amount[1].upper() in {"USD", "US$"} else "ARS"
        except InvalidOperation:
            pass
    date = re.search(
        r"(?:fecha(?:\s+(?:de\s+)?(?:pago|operacion|transferencia))?)\s*:?\s*"
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        text, re.IGNORECASE,
    )
    if date:
        try:
            data["date"] = datetime.strptime(date[1].replace("-", "/"), "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    if "date" not in data and is_mp_transfer:
        date = re.search(
            r"\b(\d{1,2})/(" + "|".join(MONTHS) + r")/(\d{4})\b",
            normalized, re.IGNORECASE,
        )
        if date:
            try:
                data["date"] = datetime(
                    int(date[3]), MONTHS.index(date[2].lower()) + 1, int(date[1])
                ).date().isoformat()
            except ValueError:
                pass
    for field, pattern in {
        "recipient": r"(?:destinatario|para|beneficiario)\s*:\s*([^\n]+)",
        "operation_id": r"(?:n[uú]mero\s+de\s+operaci[oó]n|operaci[oó]n|id\s+de\s+operaci[oó]n)\s*[:#]\s*([\w\-]+)",
    }.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[field] = match[1].strip()[:100 if field == "operation_id" else 180]
    if is_mp_transfer:
        operation = re.search(
            r"^[^\n]*\bde operacion de Mercado Pago\s*:?\s*\n\s*(\d{6,100})\b",
            normalized, re.MULTILINE | re.IGNORECASE,
        )
        if operation:
            data["operation_id"] = operation[1]
        parties = re.split(r"origen y destino", text, flags=re.IGNORECASE)
        if len(parties) == 2:
            block = re.split(
                r"(?:N\.\s*[^\n]*operaci[oó]n|c[oó]digo de identificaci[oó]n)",
                parties[1], maxsplit=1, flags=re.IGNORECASE,
            )[0]
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            account_lines = [
                i for i, line in enumerate(lines)
                if re.match(r"C(?:B|Vv?)U\s*:", line, re.IGNORECASE)
            ]
            # Only use the second named party when both account blocks are present.
            if len(account_lines) == 2 and account_lines[1] >= 2:
                recipient = lines[account_lines[1] - 2]
                recipient = re.sub(r"^[^\w]+", "", recipient)
                recipient = re.sub(r"^[a-z]{1,2}\s+(?=[A-Z])", "", recipient)
                if re.fullmatch(r"[^\W\d_][^\d:\n]{3,179}", recipient):
                    data["recipient"] = recipient
            if account_lines and account_lines[0] >= 1:
                source = lines[account_lines[0] - 1].casefold()
                if source == "mercado pago":
                    data["source_bank"] = "mp"
    return data


def extract_receipt(file):
    if not settings.OCR_ENABLED:
        raise ExtractionError(
            "La lectura automatica no esta habilitada. La imagen no se guardo; "
            "completa los datos manualmente."
        )
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        file.seek(0)
        with Image.open(file) as image:
            text = pytesseract.image_to_string(
                image, lang=settings.OCR_LANGUAGE, timeout=20
            )
    except (TesseractError, TesseractNotFoundError, RuntimeError, OSError) as exc:
        raise ExtractionError(
            "No pudimos leer automaticamente la imagen. No la guardamos; "
            "completa sus datos manualmente."
        ) from exc
    return text, parse_receipt(text)
