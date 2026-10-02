# Academia - Cloud en Microsoft 365: Power Apps + SharePoint

Fecha: 2026-10-01. Estado: propuesta para revisar con TI / el administrador de Power Platform.

## 1. Respuesta corta

**La app de Python no se puede ejecutar dentro de Power Apps ni de SharePoint.** Power Apps no corre Python: sus apps se
construyen con pantallas y fórmulas Power Fx, y SharePoint solo muestra páginas, listas y web parts. No existe un
«importar app de Streamlit».

Lo que sí se puede hacer, y lo que este documento prepara:

| Opción | Qué es | Python | Licencias | Cuándo conviene |
|---|---|---|---|---|
| **A. Nativa en Power Platform** (recomendada) | Los datos pasan a listas de SharePoint; la interfaz se reconstruye como app de lienzo de Power Apps; se inserta en una página de SharePoint | No se usa en producción | Conectores estándar: normalmente cubiertos por Microsoft 365 | Entorno enterprise con Office 365, sin suscripción propia de Azure |
| **B. Python hospedado en Azure** | La app actual se publica en Azure App Service con inicio de sesión de Entra ID; SharePoint solo enlaza a ella | Se conserva | Suscripción de Azure + aprobación de TI | Si el equipo tiene Azure y quiere conservar el código tal cual |
| **C. Híbrida** | Power Apps como interfaz y Python como API (Azure Functions) mediante conector personalizado | Parcial | Conector personalizado = Power Apps Premium por usuario | Solo si se necesita lógica que Power Fx no puede hacer |

**Recomendación: opción A.** Es la única que vive por completo dentro de Microsoft 365, usa la identidad y los permisos
que el equipo ya tiene, y no pide infraestructura nueva. La app de Python no se tira: se queda como **taller de
contenido** (escribir, validar y auditar lecciones, importar el reporte de brechas) y **exporta** todo a SharePoint.

> Licencias: los conectores de SharePoint, Office 365 Users y Excel Online son estándar. Dataverse, los conectores
> personalizados y los conectores premium requieren Power Apps Premium. Las condiciones cambian: confírmalo con tu
> administrador antes de comprometer fechas.
> Referencia: https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/connections-list

## 2. Arquitectura de la opción A

```
  Taller de contenido (Python, local)              Microsoft 365 (producción)
  ----------------------------------               ------------------------------------------------
  packs/<tema>/pack.json                           Sitio de SharePoint «Academia Cloud»
  catalog/skills.json            export CSV          ├─ Listas de contenido (solo lectura para aprendices)
  tools/validate_pack.py       ───────────────►      ├─ Listas de actividad (Progreso, EntregasVBD)
  tools/audit_videos.py                              └─ Página con el web part de Power Apps
  tools/export_sharepoint.py                        App de lienzo «Academia Cloud» (Power Fx)
                                                   Power Automate: carga de CSV, aviso al champion
                                                   Identidad: Entra ID (la sesión de Microsoft 365)
```

Tres lentes:

- **Producto/UX.** El aprendiz entra desde SharePoint o Teams ya identificado: desaparece el campo «Tu nombre».
  La primera pantalla pasa a ser «tu siguiente lección y tus brechas», no la línea de rangos.
- **Entrega ágil.** El contenido se versiona como JSON en el repositorio y se publica con una exportación; la app de
  lienzo va en una **solución** de Power Platform con ambientes Dev → Test → Prod.
- **Arquitectura y seguridad.** Sin servidores que mantener. Los permisos son grupos de SharePoint. Los datos se
  quedan en el tenant, bajo las mismas etiquetas de confidencialidad y DLP que el resto de Microsoft 365.

## 3. Modelo de datos: listas de SharePoint

`tools/export_sharepoint.py` genera un CSV por cada lista de contenido en `export/sharepoint/`, con estas columnas.

### Listas de contenido (las escribe el taller; los aprendices solo leen)

| Lista | Columnas | Filas hoy |
|---|---|---|
| **Familias** | Title (nombre), FamilyId, GapVolume (número), RoleImpact (número), Champion (texto; en SharePoint conviene cambiarla a tipo Persona) | 9 |
| **Skills** | Title, SkillId, FamilyId, Severity (High/Medium/Low), TargetLevel (p. ej. «P3 - Advanced»), ImpactedRoles (número) | 34 |
| **Lecciones** | Title, LessonId, PackId, Level, SortOrder, Summary, KeyPoints (varias líneas), PracticeLabel, PracticeUrl, CatalogSkills (ids separados por `;`), VbdDeliverable, VbdDoneWhen (varias líneas), VbdValue, VbdWhereLabel, VbdWhereUrl | 12 |
| **Preguntas** | Title (pregunta), QuestionId (`leccion:n`), LessonId, SortOrder, OptionA…OptionD, AnswerLetter, Why | 36 |
| **Recursos** | Title, ResourceKey, Url, Channel, Lang, Topic, Why, Kind (video/playlist/link), Level | 49 |
| **LeccionRecursos** | Title, LessonId, ResourceKey, SortOrder, Note | 45 |
| **Glosario** | Title (término), Category, Definition | 47 |
| **Rangos** | Title, Points, Emoji, Color | 5 |

### Listas de actividad (las escribe la app; nacen vacías)

| Lista | Columnas | Reglas |
|---|---|---|
| **Progreso** | Title (`correo|QuestionId`), Learner (Persona), ItemType (quiz/glossary), ItemId, Correct (Sí/No), Points (número), FirstTry (Sí/No) | Un registro por intento. 10 puntos al primer intento, 5 si acierta después de fallar, 0 si ya la había acertado |
| **EntregasVBD** | Title (`correo|LessonId`), Learner (Persona), LessonId, FamilyId, Checks (texto), EvidenceUrl, Status (Enviado/Aprobado/Devuelto), Reviewer (Persona), ReviewNote, Points | 25 puntos cuando Status = Aprobado |

**Privacidad:** en las dos listas de actividad activa «Leer: solo los elementos creados por el usuario» y
«Editar: solo los propios» (Configuración de la lista → Configuración avanzada). Los champions y dueños ven todo por
pertenecer al grupo con control total. Así nadie ve ni altera el progreso de otro.

**Límites a respetar:** las consultas de Power Apps a SharePoint deben ser delegables (filtrar por columnas
indexadas: `LessonId`, `Learner`, `FamilyId`). Indexa esas columnas desde el inicio.

## 4. La app de lienzo: pantallas y su equivalente actual

| Pantalla | Qué muestra | Equivale hoy a |
|---|---|---|
| **Inicio** | Saludo con `User().FullName`, siguiente lección, brechas de su rol, puntos y rango | Encabezado + parte de «Progreso» |
| **Curso** | Niveles y lecciones con estado (✅ / pendiente / ⭐ recomendada) | Pestaña Curso (selectores) |
| **Lección** | Resumen, puntos clave, video, 3 preguntas, VBD | Pestaña Curso (contenido) |
| **Glosario** | Buscador y quiz de términos | Pestaña Glosario |
| **Videoteca** | Recursos por tema, filtro «solo en español» | Pestaña Videoteca |
| **Mapa de skills** | Familias por brecha, champion, cobertura | Pestaña Mapa de skills |
| **Champion** | Entregas pendientes de su familia: aprobar o devolver | Nuevo |
| **Equipo** | Avance por persona y por familia (solo champions y dueños) | Pestaña Equipo |

Fórmulas Power Fx de referencia:

```powerfx
// Al abrir la app: quién soy y qué llevo
Set(varMe, User());
ClearCollect(colMine, Filter(Progreso, Learner.Email = varMe.Email));
Set(varPoints, Sum(colMine, Points) + Sum(Filter(EntregasVBD, Learner.Email = varMe.Email, Status.Value = "Aprobado"), Points));

// Rango actual: el de más puntos que ya alcancé
Set(varRank, First(SortByColumns(Filter(Rangos, Points <= varPoints), "Points", SortOrder.Descending)));

// Al revisar una pregunta (ThisItem = la pregunta; rdoOpciones.Selected.Letter = "A".."D")
With({ok: rdoOpciones.Selected.Letter = ThisItem.AnswerLetter,
      antes: Filter(colMine, ItemId = ThisItem.QuestionId)},
  Patch(Progreso, Defaults(Progreso), {
    Title: varMe.Email & "|" & ThisItem.QuestionId, ItemType: "quiz", ItemId: ThisItem.QuestionId, Correct: ok,
    FirstTry: IsEmpty(antes),
    Points: If(!ok || !IsEmpty(Filter(antes, Correct)), 0, IsEmpty(antes), 10, 5)
  }));

// Lección completada = sus 3 preguntas acertadas al menos una vez
CountRows(Distinct(Filter(colMine, StartsWith(ItemId, varLesson.LessonId & ":"), Correct), ItemId)) = 3
```

Video: usa el control de video con la URL de YouTube o, si el tenant lo bloquea, un botón `Launch(ThisItem.Url)`.

## 5. Flujos de Power Automate

1. **Publicar contenido.** Al subir los CSV a una biblioteca «Cargas», el flujo borra y vuelve a crear los elementos
   de la lista correspondiente. Alternativa manual para empezar: en cada lista, «Editar en vista de cuadrícula» y pegar.
2. **Aviso al champion.** Al crearse un elemento en EntregasVBD con Status = Enviado, busca el Champion de la familia
   en Familias y le manda un mensaje de Teams con el enlace a la pantalla Champion.
3. **Importar el reporte de brechas.** El reporte vive en Excel Online. Para que un flujo lo lea, el bloque
   «Mandatory Gap Remediation» de la pestaña *Upskilling Plan* debe estar con **formato de tabla** (Insertar → Tabla,
   nombre `tblUpskilling`). La acción «Enumerar las filas de una tabla» alimenta las listas Familias y Skills.
   Como el archivo es confidencial, el flujo debe correr con una cuenta de servicio aprobada, y solo guardar el
   **número** de roles afectados, no sus nombres (igual que hace hoy el importador local).

### Avisos automáticos (cuando se integre)
La app offline ya calcula los avisos y sus textos (`academy/notify.py`). En Microsoft 365 el mismo conjunto de reglas
corre en un flujo programado diario:

| Regla | Condición | Asunto |
|---|---|---|
| Curso terminado | Todas las lecciones del curso acertadas | «¡Felicidades! Terminaste …» |
| Simulacro aprobado | Un intento de simulacro con 700 o más | «¡Felicidades! Aprobaste el simulacro de …» |
| Sin actividad | 5 días sin ningún registro en Progreso | «No has tomado cursos en N días» |
| Sin avance | Con actividad, pero 7 días sin ganar puntos | «No has avanzado en tu ruta» |

Flujo: Recurrencia diaria → leer Progreso y SimulacrosExamen → por cada persona que cumple una regla y no tiene ya ese
aviso en la lista **Avisos** → acción «Enviar un correo electrónico (V2)» de Office 365 Outlook con **CC** al Champion
de la familia (columna Persona en Familias) → registrar el aviso en **Avisos** para no repetirlo. Lista **Avisos**:
Title (`correo|regla|referencia`), Learner, Kind, Ref, SentOn. Alternativa a correo: mensaje de Teams con la misma
plantilla.

### Certificaciones (cuando se integre)
Listas adicionales: **Examenes**, **ModulosExamen**, **PreguntasExamen**, **EjerciciosExamen** (contenido) y
**SimulacrosExamen** (Learner, ExamId, Score, Passed, Seconds, DomainsJson). El simulacro en Power Apps toma N preguntas
por dominio con `FirstN(Shuffle(Filter(PreguntasExamen, Domain = …)), cuota)` y un control Temporizador.

### Workday Learning (myLearning)
El portal interno de cursos vive en Workday. Tres niveles de integración, de menor a mayor permiso:

| Nivel | Qué hace | Qué necesita | Estado |
|---|---|---|---|
| 1. Redirección | El family skill lead pega el enlace del curso de Workday como paso de la ruta; la app abre el curso y la persona entra con su propia sesión (SSO). La persona marca el paso como completado. | Nada: solo el enlace del curso | **Disponible offline** («Equipo → Cursos de mi familia») |
| 2. Carga de avances | Un reporte de Workday (inscripciones y cursos terminados) se exporta a Excel/CSV y se carga para marcar los pasos automáticamente | Permiso para correr y exportar el reporte de aprendizaje | Pendiente: definir columnas del reporte |
| 3. Conexión automática | Un flujo de Power Automate lee a diario un reporte de Workday expuesto como servicio web (RaaS: Report as a Service) y actualiza la lista Progreso | Administrador de Workday: reporte personalizado habilitado como servicio web y una cuenta de integración (Integration System User) con permiso solo de lectura sobre datos de aprendizaje. Power Platform: conector de Workday o conector HTTP, ambos premium | Pendiente: autorizaciones |

Notas de diseño:
- La academia nunca guarda credenciales de Workday; en el nivel 3 las guarda la conexión de Power Automate o Azure Key Vault.
- El reporte debe traer solo lo necesario: correo corporativo, identificador y título del curso, estado y fecha de término.
- Para casar un curso de Workday con un paso de la ruta se usa el enlace o el identificador del curso, así que conviene
  que el family skill lead pegue siempre el enlace canónico del curso.
- Qué pedir a TI / al equipo de Workday: (1) si existe ya un reporte de aprendizaje por persona, (2) si puede exponerse
  como RaaS, (3) quién aprueba la cuenta de integración, (4) si los enlaces profundos a cursos son estables.
- Referencias: [Workday HCM connector](https://learn.microsoft.com/en-us/connectors/workdayhcm/) y
  [crear un reporte RaaS en Workday](https://learn.microsoft.com/en-us/viva/learning/workday-create-raas-report).

### Asistente de IA (Amethyst)
En la app offline el asistente funciona en modo «copiar y abrir» o, con endpoint y llave, en modo API (`academy/assistant.py`).
En Power Apps hay dos caminos equivalentes: (a) botón que copia el mensaje con `Copy()` y abre Amethyst con `Launch()`;
(b) un flujo de Power Automate con la acción HTTP (premium) o un conector personalizado hacia el endpoint de Amethyst,
con la llave guardada en la conexión o en Azure Key Vault. Los mensajes siguen la misma regla: solo contenido de estudio
y el resultado de la propia persona.

## 6. Seguridad y permisos

| Grupo de SharePoint | Quiénes | Listas de contenido | Progreso / EntregasVBD |
|---|---|---|---|
| Academia - Aprendices | Todo el equipo | Leer | Crear y editar lo propio |
| Academia - Champions | Un champion por familia | Leer | Leer todo; editar EntregasVBD |
| Academia - Dueños | Tú y quien administre | Control total | Control total |

- La app se comparte con los mismos grupos (como grupos de seguridad de Entra ID).
- **Dos vistas, igual que en la app offline** (`academy/access.py`): usuario final y owner. La vista de owner (pantallas
  Equipo y Champion, cifras de brecha, avisos, administración del catálogo) se decide por pertenencia al security group
  de owners, cuyo nombre se registra hoy en «Equipo → Acceso». En Power Apps: al iniciar,
  `Set(varIsOwner, !IsEmpty(Filter(Office365Groups.ListGroupMembers("<id del grupo>").value, mail = User().Email)))`
  y `Visible = varIsOwner` en esas pantallas. La visibilidad es solo comodidad: lo que impide leer los datos de otros
  son los permisos de las listas Progreso, EntregasVBD, SimulacrosExamen y Avisos.
- En la app, las pantallas Champion y Equipo se muestran solo si el usuario es champion o dueño; el permiso real lo
  da SharePoint, no la visibilidad del botón.
- No guardes en estas listas datos de clientes, IDs de roles ni nombres de contactos del reporte.

## 7. Insertarla en SharePoint y Teams

1. En Power Apps: **Detalles** de la app → copia el **vínculo web** o el Id. de aplicación.
2. En la página de SharePoint: **Editar** → agregar web part **Microsoft Power Apps** → pega el vínculo.
3. En Teams: agrega la app como pestaña del canal del equipo (misma app, sin trabajo extra).

## 8. Plan de migración

| Sprint | Entregable | Listo cuando |
|---|---|---|
| 0 | Sitio, grupos, listas y columnas; contenido cargado desde los CSV | Las 8 listas de contenido tienen las mismas cantidades que la tabla de la sección 3 |
| 1 | Inicio + Curso + Lección con preguntas y puntos | Un aprendiz completa una lección y ve sus puntos; otro aprendiz no ve ese progreso |
| 2 | VBD con revisión del champion + aviso en Teams | Un VBD pasa por Enviado → Aprobado y suma 25 puntos |
| 3 | Mapa de skills + Equipo + carga del reporte de brechas | El mapa coincide con la pestaña *Upskilling Plan* |
| 4 | Glosario, Videoteca, pulido de UX, paso a Prod como solución | Piloto con 5 personas sin incidencias abiertas |

## 9. Qué se conserva y qué cambia

| Se conserva | Cambia |
|---|---|
| Metodología (leer → ver → comprobar → practicar → entregar valor) | Interfaz: de Streamlit a app de lienzo |
| Todo el contenido y el catálogo de skills | Datos: de SQLite local a listas de SharePoint |
| Reglas de puntos, rangos e insignias | Identidad: de «Tu nombre» a la sesión de Microsoft 365 |
| Validador y auditor de videos (en el taller) | VBD: de autodeclarado a aprobado por el champion |
| Paleta naranja de marca | El taller de Python deja de ser lo que usa el aprendiz |

## 10. Antes de empezar, confirma con TI

- ¿Puedes crear apps de lienzo y flujos en el ambiente de la empresa, o hay que pedir un ambiente?
- ¿La política DLP permite juntar los conectores SharePoint, Office 365 Users, Teams y Excel Online?
- ¿Se pueden insertar videos de YouTube en apps internas?
- ¿Quién puede crear el sitio de SharePoint y los grupos?

## Anexo: opción B (conservar Python en Azure)

Azure App Service (contenedor Linux) + autenticación integrada con Entra ID + Azure Database for PostgreSQL en lugar
de SQLite + despliegue con GitHub Actions o Azure DevOps. En SharePoint se enlaza desde la navegación del sitio; no se
recomienda incrustarla en un marco, porque la pantalla de inicio de sesión de Microsoft no carga dentro de marcos.
Cambios de código necesarios: leer la identidad de la cabecera de autenticación en lugar de «Tu nombre», cambiar
`progress.py` a PostgreSQL y quitar la restricción de `127.0.0.1`.
