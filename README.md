# OpenOrganizador

Aplicación local para **recopilar, extraer y organizar facturas que llegan por Gmail**. Todo se ejecuta en tu computadora con Docker: los correos, los archivos y la base de datos no salen a servicios externos.

El sistema descarga los adjuntos (PDF, XML y ZIP), extrae los datos importantes (lugar, fecha, monto, moneda y si es gasto o ganancia), los agrupa por comercio y fecha, y te permite revisar y corregir lo que tenga baja confianza. También puede exportar todo a Excel.

> **Nota:** la integración experimental con IA (Ollama / OpenAI) fue retirada. La clasificación actual funciona con reglas deterministas, parsing de XML DIAN/UBL y CFDI, y extracción de texto/OCR de PDF. No necesitas descargar ningún modelo.

---

## ¿Qué estás viendo?

La interfaz tiene cinco secciones en el menú lateral y una vista de detalle:

| Sección | Qué muestra |
|---|---|
| **Dashboard** | Totales de gastos y ganancias, gráficos por mes y por lugar, y un resumen de documentos pendientes de revisión. |
| **Explorador** | Lista completa de documentos con filtros por cuenta, lugar, flujo, fecha y estado. Desde aquí puedes ver el PDF/XML, editar datos, verificar o eliminar. |
| **Revisión** | Documentos que el sistema no pudo clasificar con suficiente confianza, más los enlaces que requieren descarga manual. |
| **Carpeta local** | Arrastra PDF, XML o ZIP que hayas descargado manualmente y procésalos igual que los del correo. |
| **Configuración** | Conexión con Gmail (IMAP), rango de fechas para sincronizar, carpeta `inbox` y moneda base. |
| **Detalle de lugar** | Al hacer clic en un lugar del dashboard o explorador: todos sus documentos, totales y acciones masivas. |

La moneda base por defecto es **COP** (peso colombiano). Puedes cambiarla a USD en Configuración; los montos en USD se convierten con la tasa `fx_usd_cop` que definas.

### Flujo de trabajo típico

1. Configuras tu correo y contraseña de aplicación de Gmail.
2. Sincronizas un rango de fechas.
3. El sistema descarga y procesa los adjuntos automáticamente.
4. Revisas en **Revisión** los documentos dudosos y confirmas montos.
5. Consultas totales en **Dashboard** y exportas a Excel cuando lo necesites.

---

## Arquitectura

```
Gmail (IMAP)
    │
    ▼
email-service ──► Redis (queue:pdf)
    │
    ▼
pdf-service (PyMuPDF + Tesseract OCR)
    │
    ▼
organizer-service (reglas + parsers XML/PDF)
    │
    ▼
PostgreSQL  ◄──  gateway (API FastAPI)  ◄──  frontend (React + nginx)
```

| Servicio | Función | Puerto |
|---|---|---|
| `frontend` | Interfaz web (React compilado, servido por nginx) | `127.0.0.1:8080` |
| `gateway` | API REST, exportación a Excel y orquestación | `127.0.0.1:8000` |
| `email-service` | Conexión IMAP, descarga de adjuntos y enlaces | interno |
| `pdf-service` | Extracción de texto, OCR y parsing de XML | interno |
| `organizer-service` | Clasificación, montos, lugares y flujo | interno |
| `postgres` | Base de datos | interno |
| `redis` | Colas de trabajo | interno |

Los puertos se publican solo en `127.0.0.1`, así que no quedan accesibles desde otros equipos de la red local. Si cambias el puerto del frontend, actualiza también `CORS_ORIGINS` en `docker-compose.yml`.

---

## Requisitos

- **Windows 10/11**, macOS o Linux con **Docker Desktop** instalado y funcionando.
- Una cuenta de Gmail con **verificación en 2 pasos** activada.
- Una **contraseña de aplicación** de Gmail (no la contraseña normal).
- Alrededor de **2 GB de RAM** libre para los contenedores.

---

## Instalación y arranque

1. Instala y abre **Docker Desktop**. Espera a que el ícono de la ballena esté en verde.
2. Clona el repositorio (o abre la carpeta si ya la descargaste):

   ```powershell
   git clone https://github.com/TU_USUARIO/openorganizador.git
   cd openorganizador
   ```

3. Levanta los contenedores:

   ```powershell
   docker compose up -d --build
   ```

   En Windows también puedes hacer doble clic en **`start.bat`**, que verifica Docker, levanta los servicios y abre el navegador.

4. Abre **http://localhost:8080**.

5. Ve a **Configuración** y completa:
   - Servidor IMAP: `imap.gmail.com`
   - Tu correo de Gmail
   - Contraseña de aplicación (16 caracteres, sin espacios)
   - Tu nombre y NIT/RFC (opcional)
   - Moneda base y tasa de cambio USD → COP

   Pulsa **Guardar configuración** y luego **Probar conexión**.

6. Elige el rango de fechas y pulsa **Sincronizar**.

Para detener la aplicación:

```powershell
docker compose stop
```

O ejecuta **`stop.bat`**. Tus datos quedan guardados.

---

## Estructura del proyecto

```
OpenOrganizador/
├── docker-compose.yml          # Servicios, red y volúmenes
├── start.bat / stop.bat        # Arranque y parada en Windows
├── .env.example                # Variables de entorno de ejemplo
├── LICENSE                     # Licencia MIT
├── .github/workflows/tests.yml # Pruebas automáticas en GitHub Actions
├── data/                       # Facturas, inbox, archivos locales y clave de cifrado (no se versiona)
├── shared/                     # Código común: BD, colas, parsers y utilidades
│   ├── db.py                   # Modelos SQLAlchemy y migraciones
│   ├── crypto.py               # Cifrado de credenciales (Fernet)
│   ├── queues.py               # Colas Redis
│   └── parsing/                # CFDI, UBL/DIAN, montos, fechas y lugares
├── services/
│   ├── email-service/          # Descarga de correos y adjuntos
│   ├── pdf-service/            # Extracción de texto/OCR y XML
│   ├── organizer-service/      # Clasificación y organización
│   ├── gateway/                # API FastAPI y exportación Excel
│   │   └── app/
│   │       ├── main.py         # Creación de la app, CORS y arranque
│   │       ├── deps.py         # Utilidades compartidas por los routers
│   │       └── routers/        # settings, sync, local_folder, places, documents, dashboard
│   └── frontend/               # React + Vite + nginx
├── tests/                      # Pruebas de parsers y utilidades
└── scripts/                    # Scripts de mantenimiento y corrección de datos
```

---

## Datos, respaldos y limpieza

- Los archivos se guardan en `data/facturas/<Lugar>/<AAAA-MM>/`.
- La carpeta `data/inbox/` es para archivos descargados manualmente.
- La carpeta `data/local-scan/` es la que usa la pantalla **Carpeta local**.
- La base de datos vive en el volumen Docker `pgdata`.
- La clave de cifrado vive en `data/.secret_key`. **Inclúyela en tus respaldos**: sin ella no se pueden descifrar las contraseñas guardadas (si se pierde, basta con volver a escribir la contraseña de Gmail en Configuración).

Si quieres que el botón **Abrir carpeta** funcione y que la interfaz muestre la ruta de tu equipo, copia `.env.example` a `.env` y define la ruta absoluta:

```dotenv
HOST_LOCAL_SCAN_DIR=C:\ruta\a\OpenOrganizador\data\local-scan
```

**Respaldo recomendado:**

```powershell
# Base de datos
docker compose exec postgres pg_dump -U organizador organizador > respaldo.sql

# Archivos
Compress-Archive -Path .\data -DestinationPath .\respaldo-data.zip
```

Para restaurar la base:

```powershell
Get-Content respaldo.sql | docker compose exec -T postgres psql -U organizador -d organizador
```

> No borres `data/` ni el volumen `pgdata` si quieres conservar tu historial.

---

## Pruebas

Las pruebas se ejecutan fuera de Docker, con las dependencias de Python instaladas:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r services/gateway/requirements.txt pytest httpx
python -m pytest
```

Las pruebas cubren parsers de CFDI, UBL/DIAN, montos, fechas, lugares, archivos comprimidos y cifrado de credenciales. También se ejecutan automáticamente en **GitHub Actions** en cada push o pull request.

---

## Solución de problemas

| Problema | Solución |
|---|---|
| `docker` no se reconoce en PowerShell | Abre Docker Desktop o usa `start.bat`, que busca Docker en `C:\Program Files\Docker\Docker\resources\bin`. También puedes agregar esa ruta al `PATH`. |
| Docker no está corriendo | Abre Docker Desktop y espera a que la ballena esté en verde. |
| El puerto 8080 está ocupado | Cambia `"127.0.0.1:8080:80"` por otro puerto en `docker-compose.yml`, actualiza `CORS_ORIGINS` del gateway y vuelve a levantar. |
| Error de autenticación con Gmail | Debes usar una **contraseña de aplicación**, no tu contraseña normal. Requiere verificación en 2 pasos. |
| Perdí `data/.secret_key` | Las contraseñas guardadas ya no se pueden descifrar. Vuelve a escribir la contraseña de Gmail en **Configuración**; se guardará con una clave nueva. |
| Un PDF no se lee | El OCR usa Tesseract en español. Si el PDF es una imagen de muy baja calidad, el documento quedará en **Revisión** para que lo corrijas manualmente. |
| Los cambios no aparecen | Reconstruye las imágenes: `docker compose up -d --build`. |
| Quiero ver errores | `docker compose logs -f gateway organizer-service` |

---

## Seguridad

Esta aplicación está pensada para **uso personal y local**:

- No tiene autenticación de usuarios: cualquiera con acceso a tu equipo puede abrirla.
- La contraseña de Gmail se guarda **cifrada** (Fernet/AES) en la base de datos local. La clave está en `data/.secret_key`; si alguien copia la base de datos pero no ese archivo, no puede descifrarla.
- Las contraseñas guardadas por versiones anteriores en texto plano se cifran automáticamente al arrancar el gateway.
- El CORS solo acepta peticiones desde `http://localhost:8080` y `http://127.0.0.1:8080` (configurable con `CORS_ORIGINS`).
- Los puertos `8000` y `8080` se publican únicamente en `127.0.0.1`, no en toda la red.

No la expongas directamente a Internet. Si necesitas acceder desde otro equipo, usa una VPN o un proxy con autenticación, y ajusta `CORS_ORIGINS` y los puertos de `docker-compose.yml`.

---

## Si vienes de la versión con IA

El código ya no usa IA. En una base de datos creada con la versión anterior pueden quedar ajustes `ai_*`, la columna `ai_analyzed` y la cola `queue:ai`; son inofensivos, pero puedes limpiarlos así:

```powershell
docker compose exec postgres psql -U organizador -d organizador -c `
  "DELETE FROM settings WHERE key IN ('ai_provider','ai_model','ai_url','ai_api_key');"

docker compose exec postgres psql -U organizador -d organizador -c `
  "DELETE FROM jobs WHERE kind = 'ai';"

docker compose exec postgres psql -U organizador -d organizador -c `
  "ALTER TABLE documents DROP COLUMN IF EXISTS ai_analyzed;"

docker compose exec redis redis-cli DEL queue:ai
```

Si instalaste Ollama solo para este proyecto, puedes borrar el modelo con `ollama rm qwen2.5:7b-instruct` o desinstalar Ollama desde Windows.

---

## Licencia

Este proyecto se distribuye bajo la licencia **MIT**. Consulta [LICENSE](LICENSE) para más detalles.

---

## Estado del proyecto

Funcional y estable para el flujo principal: sincronización de Gmail, extracción de PDF/XML, organización por lugar y fecha, revisión manual, dashboard y exportación a Excel.

Ya implementado:

- Moneda base **COP** por defecto.
- Credenciales de Gmail cifradas en reposo y migración automática de valores antiguos.
- CORS restringido a localhost y puertos publicados solo en `127.0.0.1`.
- Gateway dividido en routers (`settings`, `sync`, `local_folder`, `places`, `documents`, `dashboard`).
- Control de versiones con Git y `.gitignore`.

Mejoras pendientes recomendadas:

- Autenticación básica para la interfaz.
- División de `Config.jsx` en componentes más pequeños.
- Respaldos automáticos y pruebas del worker de organización.
