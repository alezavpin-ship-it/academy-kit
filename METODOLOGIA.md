# Metodología Academy — aprender, comprobar y entregar valor

Extraída de la Academia de AZP Trading Lab y generalizada para cualquier práctica (Cloud Security, IT, onboarding,
upskilling de ingenieros…). El motor es el mismo; solo cambia el **paquete de contenido** (`packs/<tema>/pack.json`).

## 1. La idea

Cada lección termina en algo **útil para el trabajo**, no solo en una calificación:

```
Leer (puntos clave) → Ver (videos chicos al lado) → Comprobar (3 preguntas) → Practicar → Entregar valor (VBD)
```

## 2. Anatomía de una lección

| Parte | Regla | Por qué |
|---|---|---|
| **Título + resumen** | 1–2 frases con la idea central | Saber en 10 segundos de qué trata |
| **Puntos clave** | 3–5, concretos y verificables | Lo que hay que recordar, sin relleno |
| **Practica** | Un laboratorio, documento oficial o ejercicio | Pasar de leer a hacer |
| **Quiz** | Exactamente 3 preguntas, 4 opciones, 1 correcta, con explicación | Comprobar comprensión, no memoria |
| **Videos** | 2–5 por lección, de **al menos 2 fuentes distintas**, cada uno con «Por qué aquí» | Otra explicación, otra voz |
| **VBD** | Entregable + ≥ 3 criterios «listo cuando» + valor + dónde hacerlo | Que el aprendizaje produzca algo |

### Cómo escribir buenas preguntas
- De **situación** («Subiste una llave a GitHub y la borraste. ¿Qué haces?»), no de definición.
- Distractores **plausibles**: errores que la gente comete de verdad.
- La explicación dice **por qué** la correcta es correcta, en una línea.
- Una sola respuesta defendible.

### Cómo escribir un VBD (value-based deliverable)
- Es un **artefacto real** del trabajo de la persona: una matriz, un inventario, un runbook, un diagrama, un cambio aplicado.
- Los criterios «listo cuando» son **verificables por otra persona** («revisado con el dueño», «al menos 1 cambio aplicado»).
- El «valor» responde: ¿qué gana el equipo o el negocio cuando esto existe?
- La persona marca cada criterio y entrega (con enlace de evidencia opcional): +25 puntos.

## 3. Videos: selección y auditoría

1. Buscar fuentes **profesionales**: el fabricante o la institución (AWS, Microsoft, NIST, CIS), expertos reconocidos
   (autores de libros de referencia, conferencias como re:Inforce), y canales educativos serios en español.
2. Cada lección: **al menos 2 canales distintos** y, siempre que exista, **al menos 1 video en español**.
3. **Verificar cada video con oEmbed** (`https://www.youtube.com/oembed?url=<URL>&format=json`): guardar el título y canal
   **exactos** que devuelve YouTube y la fecha (`verified`). Nunca inventar IDs.
4. Escribir el «Por qué aquí»: **qué punto de la lección explica** ese video. Si no puedes decirlo, el video no va.
5. Enlaces que no son video solo si son **fuente primaria** (documento oficial, estándar) o una fuente que la persona sigue;
   van como `kind: "link"`.
6. Re-auditar cada 3–6 meses: `python tools/audit_videos.py packs/<tema>`.

## 4. Gamificación

| Acción | Puntos |
|---|---|
| Pregunta correcta al primer intento | 10 |
| Correcta después de fallar | 5 (solo el primer acierto cuenta) |
| Glosario: respuesta correcta | 10 |
| VBD entregado | 25 |

- **5 rangos** definidos por el paquete (nombre, puntos, emoji o ilustración, color), en una línea de medallas animada.
- **Insignias**: primera lección, 10 a la primera, 20 del glosario, primer VBD, 5 VBDs, graduado por nivel, ruta completa.
- Lección completada = sus 3 preguntas acertadas al menos una vez.

## 5. Para equipos (upskilling)

- **Roles → habilidades → lecciones**: el paquete define `roles` (p. ej. de tu Matrix de roles/skills) y cada lección sus
  `skills`; al elegir un rol se marcan con ⭐ las lecciones recomendadas y aparece su ruta en «Progreso».
- **Progreso por persona** (campo «Tu nombre») y pestaña **Equipo** con puntos, rango, lecciones y VBDs de cada uno,
  descargable en CSV para el seguimiento.

## 6. Diseño de pantalla

- Dos columnas: **lección + preguntas + VBD** a la izquierda, **panel de video compacto** a la derecha
  (Mini 220 px / Chico 280 px / Mediano 360 px / Grande 480 px), fijo mientras te desplazas. Cambiar de video no borra las respuestas.
- Arriba: línea de rangos + 4 métricas (puntos, rango, lecciones, VBDs).
- Pestañas: Curso · Glosario · Videoteca · Progreso e insignias · Equipo.
- Tema naranja estilo Avanade (naranja de marca #FF5800 con ámbar #FFB414; verde #00E676 para aciertos y rojo #FF5252
  para errores), en modo oscuro (fondos #14110F / #1E1A17 / #2A2420) y claro (blanco / #FBF1EA); se cambia en `.streamlit/config.toml`.

## 7. Ruta de aprendizaje: formación oficial del proveedor
- Skill de Microsoft → pasos de **Microsoft Learn** (módulos, rutas de aprendizaje, cursos, laboratorios).
- Skill de otro fabricante → la **ruta de carrera oficial de ese fabricante** (p. ej. Anthropic Academy para Claude Code).
- Cada enlace se verifica antes de agregarlo (`verified`); nunca se inventa una URL.
- Las lecciones propias, los videos y los documentos son complemento: explican, practican y comprueban, pero la ruta la marca el proveedor.
