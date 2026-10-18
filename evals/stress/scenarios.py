"""Escenarios sintéticos multi-turno para el stress test del CAG.

Cada perfil son 20 turnos sobre un mismo proyecto. Una conversación de N turnos es
el prefijo de la de 20, así que el runner ejecuta UNA conversación y toma fotos del
estado de la sesión tras los turnos de CHECKPOINTS, en vez de cinco conversaciones.

Cada turno es ``(turn_index, transcript, fact)``. ``fact`` es lo que las llamadas
posteriores deberían recordar (``None`` si el turno no declara ninguno). Los facts son
cadenas cortas y poco ambiguas, porque ``MemoryDriftMetric`` hace match exacto
(case-insensitive) sobre el snapshot.

Ningún turno usa el vocabulario de ``AnchorDetector`` a propósito (ver
``tests/test_stress_scenarios.py``): se mide el comportamiento espontáneo, sin ayuda
de la regex. El presupuesto del perfil ``contradiction`` se redacta de forma natural.
"""

from typing import NamedTuple

CHECKPOINTS = (1, 3, 6, 10, 20)
TOTAL_TURNS = 20


class Turn(NamedTuple):
    turn_index: int
    transcript: str
    fact: str | None


class Scenario(NamedTuple):
    name: str
    turns: list[Turn]
    # fact -> sitios del snapshot donde debería sobrevivir (summary, anchors, metadata)
    fact_where: dict[str, list[str]]

    def facts_declared_before(self, turn_index: int) -> list[tuple[int, str]]:
        """Facts declarados en turnos anteriores a ``turn_index`` (el ``N > k`` del enunciado)."""
        return [(t.turn_index, t.fact) for t in self.turns if t.fact and t.turn_index < turn_index]


def fact_has_left_window(fact_turn: int, snapshot_turn: int, window: int = 6) -> bool:
    """El turno ``k`` sale de la ventana al cerrarse el turno ``k + window``. Antes de eso
    el LLM lo ve íntegro y 'recordarlo' no prueba nada sobre la memoria comprimida."""
    return snapshot_turn - fact_turn >= window


def _build(lines: list[tuple[str, str | None]]) -> list[Turn]:
    assert len(lines) == TOTAL_TURNS, f"se esperaban {TOTAL_TURNS} turnos, hay {len(lines)}"
    return [Turn(i, text, fact) for i, (text, fact) in enumerate(lines, start=1)]


# --- 1. Proyecto que crece: requisitos coherentes que se acumulan -------------------------

GROWING = Scenario(
    name="growing",
    turns=_build([
        ("Quiero estimar el proyecto Nimbus: una plataforma web de reservas para hoteles pequeños.", "Nimbus"),
        ("Los huéspedes deben poder registrarse e iniciar sesión con email y contraseña.", None),
        ("Añadimos recuperación de contraseña por correo y verificación del email al registrarse.", None),
        ("Cada hotel tendrá su propio panel de gestión de habitaciones y precios por temporada.", None),
        ("La plataforma será multi-tenant: varios hoteles comparten la misma instalación con datos aislados.", "multi-tenant"),
        ("Necesitamos un audit log que registre quién cambia precios o cancela reservas, y cuándo.", "audit log"),
        ("Los huéspedes recibirán un correo de confirmación con el detalle de la reserva.", None),
        ("Añadimos pago online con tarjeta mediante una pasarela externa de pagos.", None),
        ("El hotel podrá exportar a CSV el listado de reservas de cualquier rango de fechas.", "exportar a CSV"),
        ("Queremos un calendario de disponibilidad visual para cada habitación.", None),
        ("Añadimos un sistema de valoraciones y comentarios de los huéspedes tras su estancia.", None),
        ("Los precios podrán tener descuentos por estancia larga y por reserva anticipada.", None),
        ("Necesitamos un panel de informes con ocupación mensual e ingresos por habitación.", None),
        ("La web debe estar disponible en español, inglés y francés.", None),
        ("Añadimos una API pública para que agencias externas consulten la disponibilidad.", None),
        ("Queremos notificaciones por SMS cuando se cancela una reserva.", None),
        ("Los hoteles podrán gestionar a varios empleados con permisos distintos por rol.", None),
        ("Añadimos lista de espera automática cuando una habitación está completa.", None),
        ("Integración con Google Calendar para que el personal vea las llegadas del día.", None),
        ("Para cerrar: ¿cuánto costaría todo lo anterior y en cuántas semanas se podría entregar?", None),
    ]),
    fact_where={
        "Nimbus": ["metadata", "summary"],
        "multi-tenant": ["summary", "metadata"],
        "audit log": ["summary", "metadata"],
        "exportar a CSV": ["summary", "metadata"],
    },
)

# --- 2. Proyecto que pivota: el turno 5 cambia React por Flutter --------------------------

PIVOT = Scenario(
    name="pivot",
    turns=_build([
        ("Proyecto Orion: una app para que una cadena de gimnasios gestione clases y socios.", "Orion"),
        ("El frontend lo haremos en React, con un backend en Node.js y base de datos PostgreSQL.", "React"),
        ("Los socios podrán reservar plaza en las clases y cancelar hasta dos horas antes.", None),
        ("Habrá un panel para que los monitores vean la lista de asistentes de cada clase.", None),
        ("Cambio de planes: la app será móvil nativa y el frontend se hará en Flutter, ya no en React.", "Flutter"),
        ("El equipo mantiene el backend en Node.js sin cambios; solo cambia el cliente.", None),
        ("Los socios recibirán notificaciones push antes de cada clase reservada.", None),
        ("Añadimos pago de cuotas mensuales con domiciliación bancaria.", None),
        ("Cada gimnasio podrá definir sus propios tipos de clase y aforos.", None),
        ("Queremos un perfil de socio con historial de asistencia y marcas personales.", None),
        ("Los monitores podrán marcar la asistencia desde el móvil durante la clase.", None),
        ("Añadimos códigos QR para el acceso a las instalaciones.", None),
        ("Necesitamos informes de ocupación por clase y por franja horaria.", None),
        ("Los socios podrán invitar a un amigo a una clase de prueba gratuita.", None),
        ("Añadimos un chat interno entre socios y recepción.", None),
        ("La app debe funcionar sin conexión para consultar las reservas ya hechas.", None),
        ("Integración con pulseras de actividad para importar pasos y pulsaciones.", None),
        ("Añadimos retos mensuales con clasificación entre socios del mismo gimnasio.", None),
        ("Los administradores podrán exportar la lista de socios y sus cuotas.", None),
        ("Para cerrar: ¿cuánto costaría todo esto y en cuántas semanas se podría entregar?", None),
    ]),
    fact_where={
        "Orion": ["metadata", "summary"],
        "React": ["metadata", "summary"],
        "Flutter": ["metadata", "summary"],
    },
)

# --- 3. Proyecto que se contradice: presupuesto 30000 (turno 3) -> 80000 (turno 8) --------

CONTRADICTION = Scenario(
    name="contradiction",
    turns=_build([
        ("Proyecto Kestrel: una aplicación para que una clínica veterinaria gestione citas y fichas.", "Kestrel"),
        ("Los clientes podrán pedir cita online indicando la mascota y el motivo de la visita.", None),
        ("Tenemos un presupuesto de 30000 EUR para todo el proyecto.", "30000"),
        ("Cada mascota tendrá una ficha clínica con vacunas, alergias e historial de visitas.", None),
        ("Los veterinarios podrán adjuntar radiografías e informes en PDF a cada ficha.", None),
        ("Enviaremos recordatorios automáticos de vacunas por correo y por SMS.", None),
        ("Habrá un módulo de facturación con IVA y envío de la factura al cliente.", None),
        ("Hemos revisado las cuentas y el presupuesto es de 80000 EUR para todo el proyecto.", "80000"),
        ("Añadimos un inventario de medicamentos con alertas de stock mínimo y caducidad.", None),
        ("Los clientes tendrán un área privada con el historial de sus mascotas.", None),
        ("Queremos agenda con varios veterinarios y gestión de quirófano.", None),
        ("Añadimos una tienda online de alimentación y accesorios para mascotas.", None),
        ("Los propietarios podrán pagar la consulta online al reservar la cita.", None),
        ("Necesitamos informes de ingresos por servicio y por veterinario.", None),
        ("Añadimos telemedicina: consultas por videollamada con el veterinario.", None),
        ("Los chips identificativos de las mascotas se registrarán en la ficha.", None),
        ("Habrá un panel para la recepción con las citas del día y la sala de espera.", None),
        ("Integración con un laboratorio externo para recibir los resultados de análisis.", None),
        ("Los clientes podrán valorar la atención recibida tras cada visita.", None),
        ("Para cerrar: ¿cuánto costaría todo esto y en cuántas semanas se podría entregar?", None),
    ]),
    fact_where={
        "Kestrel": ["metadata", "summary"],
        "30000": ["anchors", "summary", "metadata"],
        "80000": ["anchors", "summary", "metadata"],
    },
)

SCENARIOS: dict[str, Scenario] = {s.name: s for s in (GROWING, PIVOT, CONTRADICTION)}
