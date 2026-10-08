# Academy Kit

La Academia de AZP Trading Lab convertida en un módulo independiente para **cualquier práctica**: Cloud Security, IT,
onboarding, upskilling de ingenieros… El motor es genérico; el contenido vive en un paquete JSON por tema.

Incluye un ejemplo completo: **Academia de Cloud Security** — 4 niveles, 12 lecciones, 36 preguntas, 12 entregables
de valor (VBD), 47 términos de glosario y 45 videos verificados con YouTube (de 2 a 5 por lección, varias fuentes,
al menos uno en español en cada lección).

## Qué hace

- **Curso**: lección (resumen, puntos clave, práctica) + 3 preguntas con explicación + **panel de video compacto** al lado
  (Mini/Chico/Mediano/Grande; se queda fijo mientras bajas por las preguntas y cambiar de video no borra tus respuestas) + **VBD** con criterios que se marcan y se entregan.
- **Glosario**: quiz término ↔ definición y buscador.
- **Videoteca**: todos los recursos por tema, filtro «solo en español», y en qué lecciones se usa cada uno.
- **Progreso e insignias**: rangos con línea de medallas, insignias, ruta recomendada para tu rol, actividad reciente.
- **Equipo**: progreso de cada persona (puntos, rango, lecciones, VBDs) descargable en CSV.
- Interfaz en español o inglés; tema oscuro tipo terminal fintech (y claro).

## Correrlo (Windows)

```bat
cd academy-kit
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Se abre en http://localhost:8501. El progreso se guarda en `data\academy.db`
(para otra ruta: `set ACADEMY_DB=C:\ruta\academy.db`). Pruebas: `pip install pytest` y `pytest`.

## Abrir con 1 clic
Doble clic en **`Academia Cloud.bat`**. La primera vez prepara el entorno (1 a 3 minutos) y deja el acceso directo
«Academia Cloud» en el Escritorio, con su icono. Cierra la ventana negra para apagar la app.

## Mapa de skills (catálogo, brechas y champions)
La pestaña «Mapa de skills» muestra las familias por brecha, su champion y qué lecciones cubren cada skill. El catálogo
(`catalog/skills.json`) se carga de tres formas, todas en esta computadora:
- **Importar de Excel**: lee solo la pestaña elegida (por omisión *Upskilling Plan*) y busca la tabla con
  `Skill Family` y `Unaligned / Missing Skill`. Guarda cuántos roles tiene cada brecha, no cuáles.
- **Pegar tabla**: copia las celdas en Excel (con encabezados) y pégalas.
- **Editar a mano**: agrega, cambia o borra familias y skills, y asigna champions.

Para probar sin el archivo real: `python tools\make_sample_xlsx.py` crea `catalog\ejemplo_upskilling_plan.xlsx` con roles ficticios.

## Ruta de aprendizaje (formación oficial del proveedor)
Primera pestaña. Por familia de skills, la ruta son los pasos de **Microsoft Learn** (módulos, rutas, cursos) de cada
skill; para skills que no son de Microsoft se usa la ruta de carrera del fabricante (p. ej. Anthropic Academy para
Claude Code). La persona abre el paso, lo completa en el sitio del proveedor y lo marca aquí (+15 pts), con enlace
opcional a su logro. Los pasos salen de `catalog\materials.json`: cuenta como paso lo que tenga `kind` module, path,
course, lab o tutorial; guías, documentos y videos quedan como material de consulta.

Los cursos del portal interno (**Workday Learning / myLearning**) se agregan igual: el family skill lead pega el enlace
en «Equipo → Cursos de mi familia» con proveedor «Workday Learning» y la app redirige al curso; cada persona entra con
su propia sesión. La conexión automática con Workday está descrita en `INTEGRACION_POWERAPPS.md`.

## Certificaciones (ruta de estudio, práctica y simulacro)
La pestaña «Certificaciones» lee `exams\<id>\exam.json`. Incluye **AI-901: Microsoft Azure AI Fundamentals** como modelo:
7 módulos, 35 preguntas originales y 8 ejercicios.
- **Ruta de estudio**: por módulo, puntos clave, material de apoyo (Microsoft Learn) y ejercicios interactivos
  (ordenar pasos, relacionar conceptos, práctica guiada con lista de verificación).
- **Práctica**: una pregunta a la vez con explicación; «Mis puntos débiles» junta los módulos por debajo de 60 %.
- **Simulacro**: 25 preguntas repartidas con los pesos oficiales de los dominios, 45 minutos, resultado sobre 1000
  (se aprueba con 700), desglose por dominio y repaso de lo fallado.
- **Historial**: intentos y evolución.
Las preguntas son de práctica, escritas para la academia; no son preguntas del examen real.
Validar: `python tools\validate_pack.py --all` revisa paquetes, catálogo y exámenes.

## Material de apoyo por skill
`catalog\materials.json` guarda enlaces a material existente (Microsoft Learn u otra fuente) por skill. Se ven en
«Mapa de skills» y se editan en «Editar a mano». Importar un Excel nuevo no los borra.

## Avisos con copia al champion
En «Equipo → Avisos por enviar» la app prepara los mensajes: curso terminado, simulacro aprobado, 5 días sin actividad y
7 días sin avance, cada uno con copia al champion de la familia. Sin conexión se abren en Outlook con un clic o se
descarga la cola en CSV; en Microsoft 365 los enviará un flujo de Power Automate. El aprendiz ve el mismo mensaje al
entrar. Los correos salen de «Tu correo» (barra lateral) y del correo del champion (en «Editar a mano»).

## Vistas: usuario final y owner
- **Usuario final** (por omisión): su curso, glosario, videoteca, su propio progreso, el mapa de skills sin las cifras de
  brecha, y certificaciones. No ve nada de otras personas.
- **Owner** (owners y líderes del equipo de desarrollo de skills): además ve la pestaña «Equipo» (mediciones de todo el
  equipo, avisos por enviar, acceso), las cifras de brecha y la administración del catálogo.
- **Champion** de una familia: la vista de usuario final más la pestaña «Equipo» limitada a quienes cursan **su
  familia** (ruta, lecciones y certificaciones de esa familia), sus avisos y las cifras de brecha de esa familia.
- Con el interruptor de la barra lateral, owners y champions pueden ver la app como usuario final.

La primera vez, quien administra pulsa «Registrarme como owner». Después, en «Equipo → Acceso» se agregan más owners,
un PIN opcional y el nombre del security group. La lista vive en `config\access.json`.
**Sin conexión esto separa vistas, no es un control de seguridad** (la base de datos es un archivo local). El control
real llega con Microsoft 365: la pertenencia al security group sustituye a esta lista.

## Asistente de IA (Amethyst)
El asistente interno de la compañía acompaña el estudio en cuatro puntos:
- **Práctica**: al fallar una pregunta, «Que me lo explique el tutor de IA».
- **Simulacro**: «Plan de estudio de 7 días con IA», armado con tu resultado por dominio y el material oficial.
- **Ruta de aprendizaje**: «Prepárate para tu siguiente paso».
- **Líderes** (owner y champion): borrador de preguntas nuevas por módulo, para revisar antes de agregarlas.

Dos modos, según lo que esté configurado en «Equipo → Asistente de IA» (`config\assistant.json`):
- **Copiar y abrir** (por omisión, funciona sin conexión ni credenciales): la academia escribe el mensaje con el contexto,
  la persona lo copia y lo pega en Amethyst.
- **API**: si la compañía entrega un endpoint para integraciones, se captura ahí y la llave se pone en la variable de
  entorno `AMETHYST_API_KEY` (nunca en archivos). La respuesta aparece dentro de la academia.

Los mensajes solo llevan contenido de estudio y el resultado de la propia persona; nunca datos de otras personas, cifras
de brecha ni nada del reporte confidencial.

## Llevarla a Power Apps + SharePoint
Ver `INTEGRACION_POWERAPPS.md`. `python tools\export_sharepoint.py` genera en `export\sharepoint\` un CSV por lista.

## Crear otra academia

1. Copia `packs\_plantilla` a `packs\<tu-tema>` y llena `pack.json` (formato en `FORMATO_PACK.md`).
2. `python tools\validate_pack.py packs\<tu-tema>` — revisa las reglas de la metodología.
3. `python tools\audit_videos.py packs\<tu-tema>` — confirma cada video con YouTube (`--fix` actualiza títulos/canales).
4. Reinicia la app: el tema aparece en el selector «Academia» de la barra lateral.

O deja que Claude lo haga: usa los prompts de `PROMPT_PROYECTO.md`.

## Archivos

| Archivo | Para qué |
|---|---|
| `app.py` | Punto de entrada de Streamlit (barra lateral: idioma, academia, nombre, rol) |
| `academy/pack.py` | Carga y **valida** paquetes |
| `academy/page.py` | La página completa (pestañas, panel de video, VBD) |
| `academy/progress.py` | Puntos, rangos, insignias, VBDs y vista de equipo (SQLite) |
| `academy/quiz.py`, `videos.py`, `track.py`, `i18n.py` | Quiz, YouTube/oEmbed, línea de rangos, textos ES/EN |
| `packs/cloud-security/` | Ejemplo terminado |
| `packs/_plantilla/` | Esqueleto para un tema nuevo |
| `tools/` | Validador y auditor de videos |
| `METODOLOGIA.md`, `FORMATO_PACK.md`, `PROMPT_PROYECTO.md` | Para el nuevo proyecto de Claude |

## Límites
- El progreso es local (SQLite en la computadora donde corre). Para un equipo distribuido, publícalo en un servidor
  interno con una ruta de base de datos compartida o cambia `progress.py` a una base de datos de red.
- «Tu nombre» no es un inicio de sesión: sirve para separar progreso, no para controlar acceso.
- Los videos son de terceros y pueden desaparecer: corre `audit_videos.py` cada pocos meses.


## Idiomas / Languages

La app abre en inglés; el selector «Language / Idioma» de la barra lateral cambia a español.

- Textos de la interfaz: `academy/i18n.py` (par español / inglés por texto).
- Contenido: cada paquete y examen tiene su versión en inglés junto al original, `packs/<tema>/pack.en.json` y
  `exams/<id>/exam.en.json`. Llevan los mismos ids, el mismo orden de niveles y las mismas respuestas, así que el avance
  se comparte entre idiomas. Si no existe la traducción, se muestra el archivo original.
- Al cambiar una lección o pregunta, cámbiala en los dos archivos; las pruebas (`pytest`) avisan si dejan de coincidir.
- En inglés solo se muestran los videos en inglés (si una lección no tuviera ninguno, se muestran todos).

## Sonidos, animaciones y reportes

- **Sonidos:** tonos cortos generados en el navegador (sin archivos de audio) al responder, completar un paso y terminar una
  lección o un VBD. Se apagan con el interruptor «Sounds / Sonidos» de la barra lateral. Definidos en `academy/ui.py` (`SOUNDS`).
- **Animaciones:** entrada de la tarjeta de siguiente paso, llenado de las barras de avance, puntos clave que aparecen uno a
  uno y confeti al completar. Se desactivan solas si el sistema pide «reducir movimiento».
- **Reportes por familia de skills:** pestaña «Equipo» (vista de owner: todas las familias; vista de champion: solo las suyas).
  Estado por familia y seguimiento por persona, con descarga en Excel y en HTML para imprimir. Lógica en `academy/report.py`.

## Contenido de la academia en un solo archivo (CSV / Excel)

Todo lo que se estudia se edita en **un archivo**, sin tocar código:

    content/academia_contenido.csv

La app lo crea sola la primera vez (con el contenido que ya tiene) y lo mantiene al día cada vez que algo se cambia desde la
propia app (Mapa de skills, cursos de una familia, importaciones).

## Cómo se edita
1. Abre `content/academia_contenido.csv` en Excel.
2. Filtra por la columna **Tabla** para trabajar una tabla a la vez.
3. Edita, guarda (como CSV) y cierra Excel.
4. Vuelve a abrir la app. Revisa el archivo completo: si está bien, lo aplica y guarda un respaldo del contenido anterior en
   `data/content_backups/`; si tiene errores **no cambia nada** y los lista en Equipo → «Contenido de la academia».

También se puede descargar y subir desde la app (pestaña Equipo, vista de owner), como CSV único o como libro de Excel con
una hoja por tabla, o por comando: `python tools/content.py export | check <archivo> | import <archivo>`.

## Estructura: familia → vendor → skill → clases
| Tabla | Qué contiene | Columnas clave |
|---|---|---|
| Familias | Las skill families principales (editables): brecha, roles afectados, champion | FamilyId, Name |
| Skills | Las skills de cada familia, con su tecnología / vendor (Microsoft, AWS, GCP, Cisco, IBM…) y categoría opcional | SkillId, FamilyId, Vendor, Category |
| LearningPaths | La ruta de carrera de cada skill: **Class** 1, 2, 3… y la fuente en **Provider** (Microsoft Learn, el fabricante, Workday Learning…) | SkillId, Class, Title, Url, Kind, Provider |
| Cursos, Niveles, Rangos, Temas, Roles | Datos generales de cada curso, por idioma | PackId, Lang |
| Lecciones, Preguntas, VBD | Lecciones con sus puntos clave, 3 preguntas y el entregable de valor | PackId, Lang, LessonId |
| Recursos, LeccionRecursos | Videos y enlaces (URL, canal, idioma) y en qué lección se muestran | ResourceKey, Url |
| Glosario | Términos y definiciones | Term |

Reglas que revisa la importación:
- En LearningPaths, `Kind` = path, module, course, lab o tutorial cuenta como clase de la ruta; doc, guide y video son material de consulta.
  Las columnas Family, Vendor y Skill de esa tabla son informativas (se toman de Skills).
- Si `Vendor` se deja vacío, la app lo deduce del nombre de la skill o de la fuente de su formación; si no puede, usa «Vendor-neutral».
- Cada lección necesita 3 preguntas con 4 opciones y `AnswerLetter` A–D, al menos 2 videos de 2 canales y un VBD con 3 criterios o más.
- El mismo curso en español e inglés lleva las mismas lecciones, en el mismo orden y con la misma respuesta correcta
  (el avance se comparte entre idiomas).
- Los nombres de los roles del reporte de brechas nunca viajan en el archivo: solo cuántos roles tiene cada brecha.

En la app, la pestaña «Ruta de aprendizaje» sigue esa estructura: se elige la familia, se filtra por tecnología / vendor y cada
skill muestra sus clases en orden. El curso de Cloud Security usa ejemplos, enlaces y videos de Microsoft (Azure, Entra,
Defender, Sentinel).

### Foro, reportes, certificaciones y análisis de demanda

Cuatro módulos que se apoyan en la misma estructura (familia de skills → vendor → skill → clases) y en los mismos roles:
**owner** (todo), **champion** (sus familias), **SME** (experto de una familia) y **aprendiz**.

### Foro (pestaña «Foro»)
- Cada pregunta pertenece a una familia de skills (y opcionalmente a una skill).
- Cualquiera puede responder. La respuesta de un SME, del champion o de un owner lleva insignia, y con ella la pregunta cuenta como contestada.
- Lo administran los owners (todas las familias) y cada champion (las suyas): nombran a los SME de la familia, marcan la respuesta aceptada,
  fijan, cierran o reabren y ocultan lo que no corresponde. Lo oculto no se borra.
- Los expertos ven arriba de la app cuántas preguntas de sus familias esperan respuesta. Exportable a CSV.

### Reportes (pestaña «Reportes», owners y champions)
- **Familias de skills:** estado por familia (champion, brecha, contenido, personas, avance, preguntas del foro sin contestar).
- **Personas y ruta de carrera:** una fila por persona y otra por familia y persona, con estado: No está cumpliendo (7 días o más sin actividad),
  En riesgo (5 a 6 días), Sin iniciar, Al corriente, Cumplido. Incluye a quien está registrado y no ha empezado.
- **Certificaciones:** por familia (quién la tiene, quién la busca), por persona (actuales, deseables, requeridas que faltan) y por vencer en 90 días.
- Descarga todo en Excel o en HTML para imprimir.

### Registro de certificaciones
- Cada persona registra en «Certificaciones → Mis certificaciones» las que tiene (`current`) y las que quiere (`desired`).
- El champion / owner define las que pide cada familia (requerida o deseable) y puede corregir el registro de cualquiera o ponerle deseables.
- Todo entra y sale por CSV:
  - Registro: `Learner, Code, Name, Vendor, Status, Obtained, Expires, CredentialUrl`. Importar reemplaza las certificaciones de las personas del archivo.
  - Requisitos por familia: `FamilyId, Code, Name, Vendor, Level, Url`. Importar reemplaza los de las familias del archivo.

### Análisis de demanda (pestaña «Demanda», owners y champions)
- Lee `content/demanda_roles.csv` (o un Excel subido) con las 35 columnas del reporte de roles; solo son obligatorias
  Role ID, Role Title y Role Primary Skill. `content/demanda_roles_ejemplo.csv` trae 48 roles ficticios para probar.
- Cada skill pedido se compara con la definición de la práctica: de la práctica, otros vendors que manejamos, foco nuevo o fuera de la práctica.
- Muestra los skills, skills primarios y títulos de rol más pedidos, los roles fuera de la práctica y el cruce con los cursos:
  qué skills de la práctica con demanda no tienen lecciones (cursos por crear) y cuáles ni siquiera están en el catálogo.
- Exporta un reporte HTML con gráficos, los skills pedidos en CSV y las skills nuevas como filas listas para pegar en el archivo de contenido.

### La práctica es un dato, no código
La definición de la práctica vive en el archivo de contenido (`content/academia_contenido.csv`):
- `Practica`: nombre y descripción.
- `PracticaSkills`: `Term` (como lo escribe la demanda), `Aliases` (separados por `;`), `SkillId`, `FamilyId`, `Vendor`, `Scope` (core | third-party | emerging).
- `PracticaRoles`: títulos de rol que la práctica puede cubrir, con alias.

Para usar la academia en otra práctica (por ejemplo ServiceNow) se reemplazan esas tablas y las de Familias, Skills y LearningPaths.

### Tendencia de la demanda y PDF
- Cada archivo de roles que se carga se guarda con su fecha en `content/demanda_historial/demanda_AAAA-MM-DD.csv`. La pestaña «Demanda → Tendencia»
  compara las cargas: roles por alcance en cada fecha, skills que más crecen y más bajan frente a la carga anterior, roles nuevos y roles que ya no vienen.
- Si reemplazas `content/demanda_roles.csv` a mano, la app lo registra como una carga más (fecha = el Timestamp más reciente del archivo).
- El reporte se descarga en PDF o en HTML, con la tendencia incluida. El PDF necesita el componente `reportlab`: si el botón sale apagado,
  cierra la app y ejecuta `Instalar componentes.bat` una vez.

## Derechos de autor
© 2026 Alejandro Zavala. Todos los derechos reservados (ver `LICENSE`). El aviso aparece al pie de cada página y en la barra lateral; está fijo en `academy/legal.py`, no hay pantalla ni ajuste que lo cambie, y la app no abre si se altera.
