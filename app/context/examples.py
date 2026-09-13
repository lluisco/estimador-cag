ESTIMATION_EXAMPLES = [
    {
        "meeting_summary": (
            "El cliente necesita una plataforma web de gestión de inventario que permita a los usuarios agregar, actualizar y eliminar productos, así como generar reportes de inventario en tiempo real.",
            "El cliente usa actualmente Excel, y quiere substituir este sistema por una plataforma web",
            "Requieren alta y edición de productos con referencia y proveedor",
            "Control de entradas y salidas del alamecen, incluyendo alertas por stock bajo",
            "Tres perfiles de usuario: administrador, gestor de inventario y lector",
            "Incluir dashboard con métricas clave",
            "Lectura por código de barras, como nice to have."
        ),
        "estimation": """
        ## Estimación: Plataforma de Gestión de Inventario
        
        ### Desglose de tareas:
        1. Diseño UI/UX: 40 horas
        2. Backend API (CRUD inventario): 60 horas
        3. Autenticación y roles: 20 horas
        4. Dashboard con métricas: 30 horas
        5. Testing y QA: 25 horas
        
        **Total estimado: 175 horas**
        **Equipo recomendado: 2 desarrolladores full-stack + 1 diseñador UX (part-time)**
        **Duración estimada: 6-8 semanas**
        """
    },
    {
        "meeting_summary": (
            "El cliente necesita una aplicación móvil para gestionar y controlar las tareas diarias de los empleados",
            "Actualmente la comunicación se realiza mediante hojas físicas con la lista de tareas y responsable de cada uno",
            "Quieren una app en donde cada uno pueda ver sus tareas y pueda reportar su progreso.",
            "Quieren recibir notificaciones push para recordar tareas importantes.",
            "Quieren poder enviar mensajes escritos o de voz para consultar dudas a su responsable",
            "Permitir categorización de tareas por prioridad y tipo.",
            "Funcionalidad offline para poder acceder a las tareas sin conexión a internet.",
            "Sincronización automática cuando se restablece la conexión a internet."
        ),
        "estimation": """
        ## Estimación: Aplicación Móvil de Gestión de Tareas
        
        ### Desglose de tareas:
        1. Diseño UI/UX: 30 horas
        2. Backend API (CRUD tareas): 50 horas
        3. Autenticación y roles: 20 horas
        4. Notificaciones push: 15 horas
        5. Mensajería interna (texto y voz): 25 horas
        6. Funcionalidad offline y sincronización: 30 horas
        7. Testing y QA: 20 horas
        
        **Total estimado: 190 horas**
        **Equipo recomendado: 2 desarrolladores full-stack + 1 diseñador UX (part-time)**
        **Duración estimada: 6-8 semanas**
        """
    }
]