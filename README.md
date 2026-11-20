# Cuentas Claras - registro personal de pagos

Aplicacion Django independiente de la gestion comercial del repositorio.
No importa sus modelos, no usa su base ni sus usuarios y no modifica sus calculos.
Nombre e identidad visual provisorios para mostrar el primer MVP.

## Uso en casa y celular

Interfaz reducida a pagos, pendientes, comprobantes y cuentas. Sin textos
promocionales ni paneles de ayuda. Los errores y avisos de revision siguen visibles.
En celular y tablet (hasta 900 px) los movimientos se presentan como tarjetas
sin desplazamiento horizontal y la navegacion queda abajo, con etiquetas.
El resaltado al pasar el mouse solo se aplica con un puntero preciso que admite
hover; en pantallas tactiles no queda pegado despues de tocar un boton.
La seccion activa y el foco de teclado conservan sus indicadores.
Al tocar una seccion de la navegacion, el resaltado cambia inmediatamente y se
muestra un spinner mientras carga otra pagina. Los saltos dentro de la misma
pagina no muestran carga; al volver con el navegador se restaura la seleccion.
Movimientos tiene su propia pantalla en `/movimientos/`: la lista, la busqueda,
los filtros y la exportacion son el contenido principal, sin tarjetas de totales
ni categorias. Resumen conserva los indicadores del periodo.
Al abrir un movimiento se muestra una ficha de consulta compacta con importe,
motivo, fecha, cuenta, categoria y estado. Notas y numero de operacion quedan
plegados en Mas detalles. El boton Editar abre el formulario; guardar o volver
regresa a la ficha. La demo muestra la misma ficha sin acciones de escritura.
Pendientes muestra solo registros por completar o revisar, sin totales de gastos
confirmados. No representa deudas ni pagos pendientes de realizar. La busqueda
y los filtros conservan el estado pendiente; para ver otros estados se usa
Movimientos.
El boton de la barra superior muestra una luna para activar Oscuro y un sol
para activar Claro.
La preferencia se guarda solo en este navegador y se aplica antes de mostrar
la pagina. Sin una eleccion guardada, sigue la apariencia del dispositivo.
Los formularios usan controles de al menos 44 px y texto de 16 px para evitar
el zoom automatico al escribir en iPhone. Filtros, categorias, imagen original,
numero de operacion y notas quedan plegados hasta necesitarlos; los errores de
campos opcionales abren su seccion. La carga de imagen aparece antes del
formulario manual en celular. Los importes conservan centavos y moneda.

## Primer pantallazo

Abrir `http://127.0.0.1:8011/demo/` con el servidor iniciado.
La demo muestra movimientos **ficticios** del mes actual y es de solo lectura.
Permite filtrar, consultar fichas, ver cuentas y descargar un Excel de muestra.
No crea registros ni requiere credenciales.

## Iniciar en Windows

Desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Cambiar SECRET_KEY en .env; no reutilizar la base del negocio.
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8011
```

Ingresar en `/ingresar/`, crear las cuentas en **Mis cuentas** y registrar pagos.
No se incluye un usuario ni una contrasena predeterminados.
SQLite, los comprobantes locales y el entorno virtual estan ignorados por Git.

## Preparar Neon y crear el primer usuario

1. En Neon, abre **Connect**, selecciona la rama `production` y desactiva
   **Connection pooling** para copiar la conexion directa. No la compartas por chat.
2. Desde esta carpeta, en PowerShell, ejecuta:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-neon.ps1
   ```

3. Pega la conexion cuando se solicite; sera visible en la terminal local. El comando aplica
   las migraciones para crear las tablas y luego pide un usuario y contrasena.
   Django no muestra la contrasena mientras se escribe. La URL solo se usa durante
   el proceso y se elimina del entorno al terminar.
4. En Vercel, `PAGOS_DATABASE_URL` debe conservar la conexion **pooled**, solo en
   Production. No reemplaces esa variable con la conexion directa de este paso.

## Incluido

- Registro manual y lectura de imagenes JPG, PNG y WebP, hasta 8 MB.
- OCR en el navegador; las nuevas imagenes no se envian ni se guardan.
- Solo se guardan los campos reconocidos y corregidos; no se conserva el texto OCR completo.
- Campos editables: fecha, importe decimal, moneda, cuenta, contraparte,
  numero de operacion, categoria, motivo y notas.
- Borradores incompletos sin inventar fecha, importe o destinatario.
- Confirmacion explicita; exige datos esenciales y motivo.
- Transferencias entre cuentas propias separadas de gastos e ingresos.
- Resumen y categorias solo de gastos confirmados; ARS y USD no se suman.
- Filtros de mes, texto, cuenta, moneda y estado; Excel aplica los mismos filtros.
- Pendientes sin fecha visibles aun con filtro de mes, para no perderlos.
- Advertencia de posibles duplicados basada en los datos del movimiento.

La moneda inicial es ARS si no puede extraerse: el usuario debe revisarla.
Un comprobante **no demuestra** que la operacion se haya realizado.
La imagen original debe conservarse en la aplicacion del banco o en el celular
si el usuario desea volver a consultarla. Los adjuntos de registros anteriores
al cambio se conservan; las nuevas lecturas no guardan imagen ni texto OCR.

## Lectura automatica local

El paquete Python no incluye el ejecutable Tesseract. Para habilitar OCR:

1. Instalar Tesseract y los datos del idioma espanol (`spa`) en el equipo servidor.
2. Configurar `OCR_ENABLED=True`.
3. Si no esta en PATH, configurar `TESSERACT_CMD` con la ruta del ejecutable.
4. Ajustar `OCR_LANGUAGE` si se utiliza otro idioma instalado.

El OCR se ejecuta localmente, sin enviar imagenes a terceros, con limite de 20 segundos.
Se proponen campos etiquetados reconocibles; no se garantiza compatibilidad con
todos los formatos de Galicia o Mercado Pago. Siempre requiere revision humana.
Si no esta habilitado, falla o no reconoce datos, la interfaz lo informa y permite
cargar los datos a mano mirando el original en el banco o en el celular.

En el entorno local de desarrollo se instalo Tesseract 5.4 y el idioma `spa`,
y se habilito OCR en `.env` (no versionado). Se verifico un comprobante real de
Mercado Pago con importe, fecha con mes en letras, destinatario y operacion.
Esto no certifica precision en otros formatos ni en comprobantes de Galicia.

Para Vercel, el formulario prepara OCR en el navegador con assets propios
versionados de Tesseract.js, Tesseract core y el modelo `spa` compacto.
En la lectura normal del navegador, la imagen permanece en el dispositivo y nunca
se envia al servidor. Para compatibilidad con celulares, se abre con el lector de
imagenes del navegador y se prepara sobre fondo blanco, con un lado maximo de
3200 pixeles, antes del OCR. No se amplia ni se guarda esta copia temporal.
Se admiten hasta 20 megapixeles en el original y 8 MB por archivo.
Solo se transmite temporalmente el texto detectado para
extraer propuestas de campos; el texto completo no se conserva. Las propuestas
completan el formulario y no crean ni guardan un movimiento. El usuario debe
revisarlas y elegir explicitamente **Guardar pendiente** o **Confirmar**. Si la
imagen no se puede leer o no se reconocen datos, la app avisa y permite elegir
otro comprobante sin salir de la pantalla. La alternativa OCR local del servidor puede
recibir temporalmente la imagen, pero no la almacena.
Despues de una lectura exitosa, el comprobante queda bloqueado en ese formulario:
para usar otro, inicia un nuevo pago. Los pagos existentes pueden eliminarse
desde su ficha; la aplicacion pide confirmacion antes del borrado permanente.
El primer uso descarga y almacena en cache del navegador aproximadamente 6 MB de
lector y datos. Si el dispositivo no puede leer la imagen, ofrece completar los
datos a mano. El OCR del servidor queda como alternativa local y tampoco almacena
el archivo recibido.

Prueba de carga de capturas: `node --test scripts/receipt-upload.test.cjs`.

El build instala las dependencias JavaScript bloqueadas en `package-lock.json`,
copia de `node_modules` solo los archivos necesarios y ejecuta `collectstatic`.
Las librerias y los datos OCR no se guardan en Git. Se conserva la atribucion
Apache-2.0 y MIT en los avisos del paquete generado.

La lectura inicial solo completa campos vacios y no confirma el movimiento.
Como la imagen no se almacena, no se puede volver a leer desde Cuentas Claras: si hace falta,
se debe seleccionar otra vez desde la aplicacion del banco o el celular.
La cuenta se sugiere solamente cuando la entidad de origen es reconocible y existe
una unica cuenta propia de esa entidad. Nunca se crean cuentas automaticamente.
El motivo personal y la categoria siempre requieren revision del usuario.

## Vercel: proyecto separado

1. Crear **otro proyecto** Vercel apuntando a este repositorio y configurar
   **Root Directory: `registro_personal`**. No cambiar el proyecto existente.
2. Crear otra base PostgreSQL, por ejemplo en Neon.
3. Configurar `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS` y **`PAGOS_DATABASE_URL`**.
   No se lee `DATABASE_URL`, para evitar usar accidentalmente la base del negocio.
4. Ejecutar `migrate` y `createsuperuser` desde un entorno autorizado apuntando
   a esa nueva base. El build solo recolecta estaticos; no modifica la base.
5. Comprobar login, lectura local de imagenes y guardado de movimientos.

En produccion se exige una base externa; no hace falta almacenamiento de archivos
ni activar R2 o Blob para las nuevas lecturas.
La demo se mantiene publica con datos ficticios; el resto exige login.
Vercel no necesita Tesseract instalado en el servidor: el OCR principal se ejecuta
en el navegador y sus assets se sirven desde el propio despliegue. Mantener
`OCR_ENABLED=False` en produccion; no se requiere enviar imagenes a Vercel.

No se desplego esta version ni se verificaron credenciales, bucket o Neon remotos.
Antes de uso real: backups de base y archivos, limites de intentos de login en el
hosting y comprobacion del acceso privado en produccion.

## Validacion

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test registro
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```
