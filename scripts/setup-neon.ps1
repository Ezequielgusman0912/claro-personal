$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontro el entorno Python del proyecto. Sigue primero los pasos de instalacion local del README."
}

$secureUrl = Read-Host "Pega la conexion DIRECTA de Neon (no la pooled); no se mostrara" -AsSecureString
$credential = New-Object System.Net.NetworkCredential("", $secureUrl)
$databaseUrl = $credential.Password

if ($databaseUrl -notmatch "^postgres(ql)?://") {
    $secureUrl.Dispose()
    throw "La URL no parece una conexion PostgreSQL valida. No se hicieron cambios."
}

if ($databaseUrl -match "-pooler\.") {
    $secureUrl.Dispose()
    throw "Usa la conexion directa: desactiva Connection pooling en Neon. No se hicieron cambios."
}

Push-Location $projectRoot
try {
    $env:PAGOS_DATABASE_URL = $databaseUrl
    $env:DEBUG = "False"
    $env:SECRET_KEY = & $python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo preparar Django. No se aplicaron migraciones."
    }

    Write-Host "Creando las tablas en Neon..."
    & $python manage.py migrate
    if ($LASTEXITCODE -ne 0) {
        throw "Fallaron las migraciones. Revisa la conexion y vuelve a intentar."
    }

    Write-Host "Ahora crea tu usuario y contraseña para iniciar sesion en Claro."
    & $python manage.py createsuperuser
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo completar la creacion del usuario."
    }
}
finally {
    Remove-Item Env:PAGOS_DATABASE_URL, Env:DEBUG, Env:SECRET_KEY -ErrorAction SilentlyContinue
    Pop-Location
    $credential = $null
    $databaseUrl = $null
    $secureUrl.Dispose()
}
