const socket = io();

console.log("Sistema en tiempo real iniciado");


// =====================================================
// CONTROL GLOBAL
// =====================================================

let actualizando = false;
let timeoutActualizacion = null;
let aqrRot = 0;


// =====================================================
// INDICADOR DE REFRESH (se inyecta solo, una vez)
// =====================================================

function asegurarIndicador() {

    let el = document.getElementById("aqr-refresh-indicator");

    if (el) return el;

    // --- Estilos (una sola vez) ---
    const style = document.createElement("style");
    style.textContent = `
        #aqr-refresh-indicator {
            position: fixed;
            bottom: 22px;
            right: 22px;
            width: 46px;
            height: 46px;
            border-radius: 50%;
            background: #ffffff;
            border: 1px solid rgba(15, 23, 42, 0.08);
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.14);
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transform: translateY(10px) scale(0.85);
            transition: opacity .4s ease,
                        transform .4s cubic-bezier(0.34, 1.4, 0.5, 1);
            pointer-events: none;
            z-index: 99999;
        }
        #aqr-refresh-indicator.visible {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
        #aqr-refresh-indicator svg {
            width: 23px;
            height: 23px;
            color: #2563eb;
            transition: transform .7s cubic-bezier(0.34, 1.4, 0.5, 1);
        }
    `;
    document.head.appendChild(style);

    // --- Ícono SVG (refresh) ---
    el = document.createElement("div");
    el.id = "aqr-refresh-indicator";
    el.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-2.64-6.36"></path>
            <path d="M21 3v6h-6"></path>
        </svg>
    `;
    document.body.appendChild(el);

    return el;
}


function girarRefresh() {

    const el = asegurarIndicador();
    const svg = el.querySelector("svg");

    el.classList.add("visible");

    // Un solo giro hacia adelante (suma 360 cada vez)
    aqrRot += 360;
    svg.style.transform = `rotate(${aqrRot}deg)`;
}


// =====================================================
// RECARGA SUAVE
// mostrar = false  -> recarga en silencio (sin toast)
// =====================================================

function refrescarSistema(tipo = "", mostrar = false) {

    if (actualizando) return;

    actualizando = true;

    document.body.classList.add("updating");

    girarRefresh();

    if (mostrar && tipo) {

        mostrarToast(tipo, "success");

    }

    clearTimeout(timeoutActualizacion);

    timeoutActualizacion = setTimeout(() => {

        location.reload();

    }, 900);

}


// =====================================================
// NUEVA VISITA  (único mensaje que sí se muestra)
// =====================================================

socket.on("nueva_visita", (data) => {

    console.log("Nueva visita registrada");

    const visitante = (data && data.visitante) ? data.visitante : "";

    refrescarSistema(
        visitante
            ? `Nueva visita registrada · ${visitante}`
            : "Nueva visita registrada",
        true
    );

});


// =====================================================
// EVENTOS SILENCIOSOS
// =====================================================

socket.on("actualizar_visitas",     () => refrescarSistema(null, false));
socket.on("actualizar_residentes",  () => refrescarSistema(null, false));
socket.on("actualizar_guardias",    () => refrescarSistema(null, false));
socket.on("actualizar_dashboard",   () => refrescarSistema(null, false));
socket.on("actualizar_reportes",    () => refrescarSistema(null, false));
socket.on("actualizar_accesos",     () => refrescarSistema(null, false));
socket.on("actualizar_incidencias", () => refrescarSistema(null, false));
socket.on("refresh",                () => refrescarSistema(null, false));


// =====================================================
// TOAST PROFESIONAL
// =====================================================

function mostrarToast(texto, tipo = "info") {

    const toast = document.createElement("div");

    toast.className = `socket-toast ${tipo}`;

    let icono = "fa-circle-info";

    if (tipo === "success") {
        icono = "fa-circle-check";
    }

    if (tipo === "error") {
        icono = "fa-circle-exclamation";
    }

    toast.innerHTML = `
        <div class="toast-icon">
            <i class="fa-solid ${icono}"></i>
        </div>

        <div class="toast-content">
            <strong>AccessQR</strong>
            <span>${texto}</span>
        </div>
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add("show");
    }, 100);

    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => {
            toast.remove();
        }, 400);
    }, 3200);

}