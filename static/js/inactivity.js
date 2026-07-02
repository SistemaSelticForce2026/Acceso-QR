/**
 * inactivity.js
 * -------------
 * Cierra la sesión AL MOMENTO en que se cumple el tiempo de inactividad,
 * sin esperar a que el usuario recargue la página o dé clic en algo.
 *
 * Requiere que la página defina, antes de cargar este script:
 *   window.TIEMPO_INACTIVIDAD_MS = {{ tiempo_inactividad_ms }};
 *
 * Uso (en el <head> o antes de </body> de tu layout autenticado,
 * NO en la pantalla de login):
 *
 *   <script>
 *     window.TIEMPO_INACTIVIDAD_MS = {{ tiempo_inactividad_ms }};
 *   </script>
 *   <script src="{{ url_for('static', filename='js/inactivity.js') }}"></script>
 */
(function () {
    "use strict";

    const TIMEOUT_MS = window.TIEMPO_INACTIVIDAD_MS || 5 * 60 * 1000;

    // Endpoint que cierra la sesión. Ajusta si tu ruta de logout es distinta.
    const LOGOUT_URL = "/logout";

    let timer = null;

    function cerrarSesionPorInactividad() {
        // Redirige de inmediato a logout; el backend limpia la sesión y
        // manda de vuelta al login (verificar_inactividad ya no importa
        // en este flujo porque el cliente actúa primero).
        window.location.href = LOGOUT_URL;
    }

    function reiniciarTimer() {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(cerrarSesionPorInactividad, TIMEOUT_MS);
    }

    // Eventos que cuentan como "actividad" del usuario.
    const EVENTOS_ACTIVIDAD = [
        "mousemove",
        "mousedown",
        "keydown",
        "scroll",
        "touchstart",
        "click",
    ];

    EVENTOS_ACTIVIDAD.forEach(function (evento) {
        document.addEventListener(evento, reiniciarTimer, { passive: true });
    });

    // ─────────────────────────────────────────────────────────────
    // PROTECCIÓN PARA OPERACIONES LARGAS (ej. carga masiva de Excel)
    // ─────────────────────────────────────────────────────────────
    // Un <form> tradicional (no AJAX) deja al navegador "congelado"
    // esperando la respuesta del servidor, sin navegar todavía. Si el
    // procesamiento tarda más que el tiempo de inactividad (ej. una
    // carga masiva de miles de residentes), el timer podría disparar
    // el logout a la mitad de esa operación y cancelarla.
    //
    // Al enviar cualquier formulario, cancelamos el timer por completo:
    // si la operación termina y el servidor responde con un redirect,
    // la página siguiente carga este mismo script desde cero (con un
    // timer nuevo), así que no hace falta "reanudarlo" manualmente.
    document.addEventListener(
        "submit",
        function () {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
        },
        true
    );

    // Si el usuario cambia de pestaña y vuelve después del tiempo límite,
    // revalidamos al recuperar el foco (evita que el timer de una pestaña
    // en segundo plano se retrase por throttling del navegador).
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            reiniciarTimer();
        }
    });

    reiniciarTimer();
})();