# Proyectos Inmobiliarios

**English available:** [README.md](README.md)

Un monorepo para dos plataformas de datos de bienes raíces comerciales (CRE), construidas alrededor de una misma disciplina de ingeniería: **los LLM interpretan, nunca calculan matemática financiera**, y cada resultado de modelo que llega a un usuario es rastreable hasta una versión de modelo, una instantánea de datos y, cuando corresponde, una aprobación humana.

| Proyecto | Estado | Qué hace |
|---|---|---|
| **[TerraSignal](terrasignal/README.md)** | Construido — pipeline de ML principal + interfaz de producto | Pronóstico de renta CRE y puntaje de riesgo de incumplimiento de inquilinos, con explicaciones SHAP, un flujo de anulación auditado y una consola de gobernanza (interruptor de emergencia, registro de modelos, monitor de drift). |
| **LedgerLens** | Solo diseño (ver [documento del proyecto 2](project-2-agentic-lease-abstraction.md)) | Abstracción agéntica de contratos de arrendamiento — extracción de términos estructurados de PDFs de contratos con extracción LLM verificada por citas y un agente de reconciliación CAM. Aún no implementado. |

Para la guía completa de instalación, capturas de pantalla y recorrido de usuario de la aplicación en funcionamiento, consulta **[terrasignal/README.md](terrasignal/README.md)**. Este archivo cubre el monorepo en su conjunto.

---

## Qué hay aquí

```
Proyectos inmobiliarios/
├── CLAUDE.md                          ← convenciones de ingeniería compartidas (ambos proyectos)
├── project-1-cre-rent-risk-platform.md   ← documento de diseño de TerraSignal
├── project-2-agentic-lease-abstraction.md ← documento de diseño de LedgerLens (aún no construido)
├── docker-compose.yml                 ← Postgres 16 (desarrollo local)
├── pyproject.toml / uv.lock           ← workspace de Python (uv), un solo lockfile para el monorepo
├── shared/                            ← código compartido: tipos base, escritor de auditoría, ayudantes de DQ
└── terrasignal/                       ← Proyecto 1: pipeline de ML, backend FastAPI, frontend Next.js
```

`shared/` es el único código que ambos proyectos pueden importar entre sí — `terrasignal/` y un futuro `ledgerlens/` nunca se importan directamente.

## Novedades: modo oscuro e interfaz bilingüe

La aplicación web de TerraSignal ahora incluye:

- **Selector de tema claro/oscuro** — en la barra de navegación superior (ícono de sol/luna). Se guarda por navegador y usa la preferencia del sistema operativo en la primera visita. Está implementado con tokens de Tailwind controlados por variables CSS, de modo que cada página y gráfico cambia de forma consistente sin parpadeos del tema incorrecto al cargar.
- **Selector de idioma inglés/español** — el interruptor `EN` / `ES` junto al selector de tema traduce toda la aplicación (navegación, tarjetas KPI, tablas, formularios, mensajes de error, etiquetas de gráficos). Se guarda por navegador. Las fechas se muestran en el idioma seleccionado; los montos permanecen en USD, ya que los datos son de un mercado de bienes raíces comerciales de EE. UU. sin importar el idioma de la interfaz.

Ambas son preferencias del lado del cliente (no involucran al backend) — ver `terrasignal/frontend/src/lib/theme.tsx` y `terrasignal/frontend/src/lib/i18n.tsx`.

## Directrices principales (aplican a todo este repositorio)

1. **Los LLM nunca calculan dinero.** Toda la matemática financiera vive en funciones puras de Polars/NumPy con pruebas unitarias. Los LLM redactan texto alrededor de números que se les entregan, nunca los números en sí.
2. **Ningún resultado de modelo llega al sistema de registro sin pasar por una validación determinista.** Análisis con Pydantic → verificaciones de consistencia → (donde corresponda) aprobación humana.
3. **Todo es rastreable.** Cada predicción, extracción y cambio de umbral se puede reconstruir: versión del modelo/prompt + instantánea de datos + quién aprobó + cuándo.
4. **Datos sintéticos primero.** Ambos proyectos funcionan de extremo a extremo con datos sintéticos generados. Nunca datos reales de inquilinos.
5. **Demostrable en cada hito.** Sin túneles oscuros de varias semanas — cada fase de construcción termina en algo ejecutable.

Consulta [CLAUDE.md](CLAUDE.md) para las convenciones de ingeniería completas (estándares de Python/TypeScript, pirámide de pruebas, CI/CD, orden de construcción).

## Inicio rápido

TerraSignal es el único proyecto implementado actualmente. Las instrucciones completas paso a paso (Docker, migraciones, generación de datos sintéticos, entrenamiento de modelos, ejecución de la API y el frontend) están en **[terrasignal/README.md](terrasignal/README.md)**.

Versión resumida, desde la raíz del repositorio:

```bash
uv sync                                                      # dependencias de Python
docker compose up -d                                         # Postgres
uv run alembic -c terrasignal/db/alembic.ini upgrade head    # esquema
uv run python -m terrasignal.synth                           # portafolio sintético
uv run python -m terrasignal.ingestion                       # carga validada por DQ
uv run python -m terrasignal.training.risk_scorer
uv run python -m terrasignal.training.rent_forecaster
uv run python -m terrasignal.training.registry               # aprobar modelos
uv run python -m terrasignal.training.batch_score             # evaluar el portafolio
uv run uvicorn terrasignal.backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

En una segunda terminal:

```bash
cd terrasignal/frontend
npm install
npm run dev
```

Abre `http://localhost:3001` e inicia sesión con uno de los usuarios de demostración indicados en la pantalla de acceso.

## Estado de construcción

| Fase | Alcance | Estado |
|---|---|---|
| 0 | Andamiaje del monorepo, tipos/auditoría/DQ compartidos, generadores de datos sintéticos | ✅ Completo |
| 1 | Ciclo de ML de TerraSignal (features → risk scorer → registro → endpoint) | ✅ Completo |
| 2 | Producto TerraSignal (API de scoring + interfaz, pronosticador de renta, workbench de precios) | ✅ Completo |
| 3 | Base de MLOps (drift → reentrenamiento automático, aprobación blue/green, consola de gobernanza v1) | Parcial — la consola de gobernanza (interruptor, registro, drift, auditoría) está en vivo; el pipeline de reentrenamiento automático no |
| 4–6 | LedgerLens (pipeline de documentos, agentes, MLOps) | No iniciado — solo documento de diseño |

Consulta [CLAUDE.md §6](CLAUDE.md#6-cross-repo-implementation-order) para el desglose completo de fases.

## Licencia

Proyecto interno / de portafolio. Sin archivo de licencia — no tratar como código abierto.
