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
 *
 * ─────────────────────────────────────────────────────────────────
 * CORREGIDO: la versión anterior dependía de que un único setTimeout
 * disparara exactamente a los TIMEOUT_MS. Eso falla en dos casos muy
 * comunes:
 *   1) El navegador throttlea (retrasa) los timers de pestañas en
 *      segundo plano (política estándar de Chrome/Firefox).
 *   2) El equipo se suspende (sleep): mientras duerme, JS se congela
 *      por completo, así que ningún setTimeout corre.
 *
 * En ambos casos, cuando el usuario regresaba (cambiaba de pestaña,
 * hacía foco, o daba clic), el listener de "visibilitychange" llamaba
 * a reiniciarTimer(), que REINICIABA el conteo desde cero sin revisar
 * cuánto tiempo real ya había pasado — regalando minutos extra de
 * sesión en silencio. El único momento en que la sesión sí se cerraba
 * era si esa interacción disparaba una petición real al servidor
 * (por ejemplo, clic en un link que navega), porque ahí el respaldo
 * server-side (verificar_inactividad en app.py) sí comparaba el
 * tiempo real transcurrido.
 *
 * Ahora este script mide el tiempo real con Date.now() y, en vez de
 * "resetear" ciegamente al volver, primero VERIFICA si ya se venció
 * el plazo (y si es así, cierra sesión de inmediato). Además de un
 * setTimeout de referencia, se usa un setInterval barato como red de
 * seguridad que no depende de que un único timer dispare justo a
 * tiempo.
 * ─────────────────────────────────────────────────────────────────
 */
(function () {
    "use strict";

    const TIMEOUT_MS = window.TIEMPO_INACTIVIDAD_MS || 5 * 60 * 1000;

    // Cada cuánto se revisa si ya se venció el plazo. No necesita ser muy
    // preciso: solo es una red de seguridad barata que se suma a los
    // listeners de eventos y de visibilidad/foco.
    const CHECK_INTERVAL_MS = 5000;

    // Endpoint que cierra la sesión. Ajusta si tu ruta de logout es distinta.
    const LOGOUT_URL = "/logout";

    // Marca de tiempo REAL de la última actividad detectada.
    let lastActivity = Date.now();

    // Se pone en true mientras hay un <form> tradicional enviándose
    // (operación larga, ej. carga masiva de Excel), para no cerrar la
    // sesión a la mitad de esa operación. Ver bloque de "submit" abajo.
    let pausado = false;

    let intervalId = null;
    let cerrada = false;

    function cerrarSesionPorInactividad() {
        if (cerrada) return;
        cerrada = true;
        if (intervalId) {
            clearInterval(intervalId);
        }
        // Redirige de inmediato a logout; el backend limpia la sesión y
        // manda de vuelta al login.
        window.location.href = LOGOUT_URL;
    }

    function registrarActividad() {
        lastActivity = Date.now();
    }

    // Verifica el tiempo REAL transcurrido. A diferencia de la versión
    // anterior, esto NO reinicia nada por sí solo: si el plazo ya se
    // venció, cierra sesión de inmediato en vez de regalar otro período
    // completo.
    function verificarInactividad() {
        if (pausado || cerrada) return;
        const transcurrido = Date.now() - lastActivity;
        if (transcurrido >= TIMEOUT_MS) {
            cerrarSesionPorInactividad();
        }
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
        document.addEventListener(evento, registrarActividad, { passive: true });
    });

    // ─────────────────────────────────────────────────────────────
    // PROTECCIÓN PARA OPERACIONES LARGAS (ej. carga masiva de Excel)
    // ─────────────────────────────────────────────────────────────
    // Un <form> tradicional (no AJAX) deja al navegador "congelado"
    // esperando la respuesta del servidor, sin navegar todavía. Si el
    // procesamiento tarda más que el tiempo de inactividad (ej. una
    // carga masiva de miles de residentes), no queremos cerrar la
    // sesión a la mitad de esa operación.
    //
    // Al enviar cualquier formulario, pausamos las verificaciones: si
    // la operación termina y el servidor responde con un redirect, la
    // página siguiente carga este mismo script desde cero (con su
    // propio lastActivity nuevo), así que no hace falta "reanudar"
    // manualmente el flag.
    document.addEventListener(
        "submit",
        function () {
            pausado = true;
        },
        true
    );

    // Si el usuario cambia de pestaña, minimiza, o el equipo se suspende,
    // los timers del navegador pueden retrasarse o congelarse por completo.
    // Al recuperar visibilidad/foco, en vez de reiniciar el conteo,
    // VERIFICAMOS cuánto tiempo real pasó — si ya se venció el plazo,
    // cierra sesión de inmediato; si no, simplemente sigue contando.
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            verificarInactividad();
        }
    });
    window.addEventListener("focus", verificarInactividad);
    window.addEventListener("pageshow", verificarInactividad);

    // Red de seguridad periódica: no depende de que un único setTimeout
    // dispare exactamente a tiempo. Aunque el navegador throttlee este
    // intervalo en segundo plano, en cuanto vuelva a correr comparará
    // Date.now() contra lastActivity y detectará el tiempo real vencido.
    intervalId = setInterval(verificarInactividad, CHECK_INTERVAL_MS);
})();