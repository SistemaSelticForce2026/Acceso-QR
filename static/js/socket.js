const socket = io();

console.log("Sistema en tiempo real iniciado");


// =====================================================
// CONTROL GLOBAL
// =====================================================

let actualizando = false;


// =====================================================
// RECARGA DE GOLPE
// =====================================================

function refrescarSistema(tipo = "", mostrar = false) {

    if (actualizando) return;

    actualizando = true;

    if (mostrar && tipo) {
        mostrarToast(tipo, "success");
    }

    location.reload();

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