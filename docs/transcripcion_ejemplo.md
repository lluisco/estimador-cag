# Transcripción de ejemplo — Reunión con cliente

Transcripción (resumida) de una reunión de descubrimiento con un cliente ficticio,
pensada para usarse como parámetro de entrada (`transcript`) del endpoint
`POST /api/v1/estimate`.

---

**Cliente:** Somos una academia de idiomas con tres sedes físicas. Ahora mismo
gestionamos las matrículas y los horarios de las clases con hojas de Excel
compartidas por email, y se nos cruzan reservas de aula constantemente.

**Consultora:** Entendido. ¿Qué os gustaría que hiciera la nueva plataforma?

**Cliente:** Necesitamos un sistema web donde el personal de administración
pueda dar de alta alumnos, matricularlos en cursos y asignarles horario y
aula sin que se solapen con otro grupo. También queremos que los profesores
puedan entrar a pasar lista y dejar comentarios sobre el progreso de cada
alumno.

**Consultora:** ¿Los alumnos tendrían algún tipo de acceso?

**Cliente:** Sí, nos gustaría que cada alumno pudiera consultar su horario,
ver su asistencia y descargar los justificantes o certificados de nivel
cuando termine un curso. Eso último, la generación de certificados en PDF,
podemos dejarlo para una segunda fase si hace falta, no es imprescindible
para arrancar.

**Consultora:** ¿Cuántos usuarios aproximadamente manejaríais?

**Cliente:** Unos 40 profesores y sobre 900 alumnos activos entre las tres
sedes. Necesitamos que cada sede vea solo sus propias aulas y horarios,
pero la dirección general debe poder ver un resumen agregado de las tres.

**Consultora:** ¿Algo más que consideréis importante?

**Cliente:** Nos gustaría recibir un aviso automático (email o notificación)
cuando un aula se quede sin uso durante una franja horaria, para poder
alquilarla a terceros. Eso sería un "nice to have", no es crítico para el
lanzamiento. Lo que sí es imprescindible es que el sistema evite los
solapamientos de aula y horario, porque es el problema que más nos duele
hoy con Excel.

**Consultora:** Perfecto, con esto ya tenemos suficiente para preparar una
primera estimación.
