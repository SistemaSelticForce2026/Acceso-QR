const socket = io();

console.log("Sistema en tiempo real iniciado");


// =====================================================
// CONTROL GLOBAL
// =====================================================

let actualizando = false;

let timeoutActualizacion = null;


// =====================================================
// RECARGA SUAVE
// mostrar = false  -> recarga en silencio (sin toast)
// =====================================================

function refrescarSistema(tipo = "", mostrar = false) {

    if (actualizando) return;

    actualizando = true;

    document.body.classList.add("updating");

    if (mostrar && tipo) {

        mostrarToast(tipo, "success");

    }

    clearTimeout(timeoutActualizacion);

    timeoutActualizacion = setTimeout(() => {

        location.reload();

    }, 1500);

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
// VISITAS  (silencioso)
// =====================================================

socket.on("actualizar_visitas", () => {

    console.log("Actualizando visitas");

    refrescarSistema(null, false);

});


// =====================================================
// RESIDENTES  (silencioso)
// =====================================================

socket.on("actualizar_residentes", () => {

    console.log("Actualizando residentes");

    refrescarSistema(null, false);

});


// =====================================================
// GUARDIAS  (silencioso)
// =====================================================

socket.on("actualizar_guardias", () => {

    console.log("Actualizando guardias");

    refrescarSistema(null, false);

});


// =====================================================
// DASHBOARD  (silencioso)
// =====================================================

socket.on("actualizar_dashboard", () => {

    console.log("Actualizando dashboard");

    refrescarSistema(null, false);

});


// =====================================================
// REPORTES  (silencioso)
// =====================================================

socket.on("actualizar_reportes", () => {

    console.log("Actualizando reportes");

    refrescarSistema(null, false);

});


// =====================================================
// ACCESOS  (silencioso)
// =====================================================

socket.on("actualizar_accesos", () => {

    console.log("Actualizando accesos");

    refrescarSistema(null, false);

});


// =====================================================
// INCIDENCIAS  (silencioso)
// =====================================================

socket.on("actualizar_incidencias", () => {

    console.log("Actualizando incidencias");

    refrescarSistema(null, false);

});


// =====================================================
// REFRESH GLOBAL  (silencioso: solo recarga, sin mensaje)
// =====================================================

socket.on("refresh", () => {

    console.log("Refrescando sistema");

    refrescarSistema(null, false);

});


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