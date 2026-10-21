/* =====================================================
   AccessQR · Tiempo real (Socket.IO)
   -----------------------------------------------------
   - Recarga la vista cuando el servidor avisa de cambios.
   - NO recarga el escáner del guardia (no corta la cámara
     ni la tarjeta del visitante que se está revisando).
   - NO recarga si el usuario está llenando un formulario:
     muestra un aviso con botón "Actualizar".
   - Deja ver el aviso de "Nueva visita" antes de recargar.
   - Recarga limpia: quita ?auto_qr y nunca reenvía un POST.
   - Si se cae la conexión y vuelve, sincroniza la vista.
===================================================== */

(function () {
    "use strict";

    if (typeof io === "undefined") {
        console.warn("AccessQR: Socket.IO no está cargado.");
        return;
    }

    const socket = io();

    // =====================================================
    // CONFIGURACIÓN
    // =====================================================

    const RETRASO_RECARGA_MS = 1500;   // tiempo para leer el aviso antes de recargar
    const DURACION_AVISO_MS = 3500;    // tiempo que se queda un aviso normal

    let recargaProgramada = false;
    let avisoPendiente = null;         // aviso "Actualizar" ya visible
    let formularioModificado = false;  // el usuario escribió algo sin guardar
    let primeraConexion = true;

    // =====================================================
    // ESTILOS DEL AVISO (se inyectan una sola vez para que
    // funcione igual en admin, guardia y residente)
    // =====================================================

    function inyectarEstilos() {
        if (document.getElementById("aqr-toast-styles")) return;

        const css = `
            .aqr-toast-wrap{
                position:fixed; top:20px; right:20px; z-index:999999;
                display:flex; flex-direction:column; gap:10px;
                pointer-events:none; max-width:calc(100vw - 40px);
            }
            .aqr-toast{
                pointer-events:auto;
                display:flex; align-items:center; gap:12px;
                min-width:280px; max-width:380px;
                padding:12px 14px;
                background:#1a1c2e; color:#ffffff;
                border-radius:16px;
                box-shadow:0 14px 36px -12px rgba(1,2,17,.45);
                font-family:'Plus Jakarta Sans','Inter',system-ui,sans-serif;
                opacity:0; transform:translateY(-8px);
                transition:opacity .25s ease, transform .25s ease;
            }
            .aqr-toast.show{ opacity:1; transform:translateY(0); }
            .aqr-toast-ico{
                width:36px; height:36px; flex-shrink:0;
                border-radius:11px;
                display:flex; align-items:center; justify-content:center;
                background:rgba(46,91,255,.20); color:#b8c3ff;
                font-size:15px;
            }
            .aqr-toast.success .aqr-toast-ico{ background:rgba(0,152,105,.22); color:#7fd1a9; }
            .aqr-toast-body{ display:flex; flex-direction:column; line-height:1.3; min-width:0; }
            .aqr-toast-body strong{ font-size:13.5px; font-weight:800; }
            .aqr-toast-body span{
                font-size:12.5px; color:#b8bccb;
                overflow:hidden; text-overflow:ellipsis;
            }
            .aqr-toast-btn{
                margin-left:auto; flex-shrink:0;
                border:none; cursor:pointer;
                padding:8px 12px; border-radius:10px;
                background:#2e5bff; color:#ffffff;
                font:inherit; font-size:12.5px; font-weight:700;
            }
            .aqr-toast-btn:hover{ background:#0040e0; }
            @media(max-width:600px){
                .aqr-toast-wrap{ top:12px; right:12px; left:12px; max-width:none; }
                .aqr-toast{ min-width:0; max-width:none; }
            }
        `;

        const style = document.createElement("style");
        style.id = "aqr-toast-styles";
        style.textContent = css;
        document.head.appendChild(style);
    }

    function contenedorAvisos() {
        let wrap = document.getElementById("aqr-toast-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.id = "aqr-toast-wrap";
            wrap.className = "aqr-toast-wrap";
            wrap.setAttribute("aria-live", "polite");
            document.body.appendChild(wrap);
        }
        return wrap;
    }

    // =====================================================
    // AVISO (toast)
    // El texto se pone con textContent para que un nombre
    // de visitante nunca se interprete como HTML.
    // =====================================================

    function mostrarAviso(texto, tipo = "info", opciones = {}) {
        inyectarEstilos();

        const toast = document.createElement("div");
        toast.className = `aqr-toast ${tipo}`;
        toast.setAttribute("role", "status");

        const ico = document.createElement("div");
        ico.className = "aqr-toast-ico";
        const i = document.createElement("i");
        i.className = tipo === "success" ? "fa-solid fa-circle-check" : "fa-solid fa-rotate";
        ico.appendChild(i);

        const body = document.createElement("div");
        body.className = "aqr-toast-body";
        const titulo = document.createElement("strong");
        titulo.textContent = opciones.titulo || "AccessQR";
        const detalle = document.createElement("span");
        detalle.textContent = texto;
        body.appendChild(titulo);
        body.appendChild(detalle);

        toast.appendChild(ico);
        toast.appendChild(body);

        if (opciones.boton) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "aqr-toast-btn";
            btn.textContent = opciones.boton;
            btn.addEventListener("click", opciones.alClic);
            toast.appendChild(btn);
        }

        contenedorAvisos().appendChild(toast);
        requestAnimationFrame(() => toast.classList.add("show"));

        if (!opciones.fijo) {
            setTimeout(() => cerrarAviso(toast), DURACION_AVISO_MS);
        }

        return toast;
    }

    function cerrarAviso(toast) {
        if (!toast || !toast.parentNode) return;
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }

    // =====================================================
    // ¿DÓNDE ESTÁ EL USUARIO?
    // =====================================================

    // Escáner del guardia: tiene el lector de cámara (#reader).
    function enEscaner() {
        return !!document.getElementById("reader");
    }

    // Está escribiendo en un campo o dejó un formulario a medias.
    function estaEditando() {
        if (formularioModificado) return true;
        // Una vista puede pausar la recarga mientras el usuario hace algo
        // importante (por ejemplo, tener abierto el QR para compartirlo).
        if (document.body && document.body.classList.contains("aqr-pausa")) return true;
        const el = document.activeElement;
        if (!el) return false;
        const tag = el.tagName;
        return (
            tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
            el.isContentEditable
        );
    }

    // Marca el formulario como "modificado" en cuanto el usuario escribe.
    document.addEventListener("input", (e) => {
        if (e.target && e.target.closest && e.target.closest("form")) {
            formularioModificado = true;
        }
    }, true);

    // Al enviar un formulario ya no hay nada pendiente de guardar.
    document.addEventListener("submit", () => {
        formularioModificado = false;
    }, true);

    // =====================================================
    // RECARGA LIMPIA
    // =====================================================

    function recargar() {
        const url = new URL(window.location.href);
        url.searchParams.delete("auto_qr");   // no volver a abrir el QR
        // replace() hace un GET normal: nunca pide "reenviar formulario".
        window.location.replace(url.pathname + url.search + url.hash);
    }

    // =====================================================
    // DECIDIR QUÉ HACER CUANDO LLEGA UN CAMBIO
    // =====================================================

    function refrescarSistema(mensaje = "", mostrar = false) {

        if (recargaProgramada) return;

        // 1) Escáner del guardia: solo avisar, nunca recargar.
        if (enEscaner()) {
            if (mostrar && mensaje) mostrarAviso(mensaje, "success");
            return;
        }

        // 2) El usuario está llenando algo: no perder lo que escribió.
        if (estaEditando()) {
            if (avisoPendiente && avisoPendiente.parentNode) return;
            avisoPendiente = mostrarAviso(
                mensaje || "Hay información nueva disponible.",
                mostrar ? "success" : "info",
                {
                    titulo: "Hay cambios nuevos",
                    boton: "Actualizar",
                    fijo: true,
                    alClic: () => {
                        formularioModificado = false;
                        recargar();
                    },
                }
            );
            return;
        }

        // 3) Caso normal: avisar (si aplica) y recargar.
        recargaProgramada = true;

        if (mostrar && mensaje) {
            mostrarAviso(mensaje, "success");
            setTimeout(recargar, RETRASO_RECARGA_MS);
        } else {
            recargar();
        }
    }

    // =====================================================
    // EVENTOS DEL SERVIDOR
    // =====================================================

    // Nueva visita: único evento que muestra mensaje.
    socket.on("nueva_visita", (data) => {
        const visitante = data && data.visitante ? String(data.visitante) : "";
        refrescarSistema(
            visitante ? `Nueva visita registrada · ${visitante}` : "Nueva visita registrada",
            true
        );
    });

    // Eventos silenciosos.
    [
        "actualizar_visitas",
        "actualizar_residentes",
        "actualizar_guardias",
        "actualizar_dashboard",
        "actualizar_reportes",
        "actualizar_accesos",
        "actualizar_incidencias",
        "refresh",
    ].forEach((evento) => {
        socket.on(evento, () => refrescarSistema("", false));
    });

    // =====================================================
    // CONEXIÓN
    // Si la conexión se cayó y regresó, pudieron pasar cosas
    // mientras tanto: se sincroniza la vista.
    // =====================================================

    socket.on("connect", () => {
        if (primeraConexion) {
            primeraConexion = false;
            return;
        }
        refrescarSistema("", false);
    });

    // Disponible para depurar desde la consola del navegador.
    window.AccessQRSocket = { socket, mostrarAviso, refrescarSistema };

})();