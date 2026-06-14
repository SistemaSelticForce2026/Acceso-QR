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

function refrescarSistema(tipo = "Información actualizada", mostrar = true) {

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
// NUEVA VISITA  (un solo mensaje, limpio)
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
// VISITAS
// =====================================================

socket.on("actualizar_visitas", () => {

    console.log("Actualizando visitas");

    refrescarSistema("Lista de visitas actualizada");

});


// =====================================================
// RESIDENTES
// =====================================================

socket.on("actualizar_residentes", () => {

    console.log("Actualizando residentes");

    refrescarSistema("Información de residentes actualizada");

});


// =====================================================
// GUARDIAS
// =====================================================

socket.on("actualizar_guardias", () => {

    console.log("Actualizando guardias");

    refrescarSistema("Información de guardias actualizada");

});


// =====================================================
// DASHBOARD  (recarga en SILENCIO, sin mostrar aviso)
// =====================================================

socket.on("actualizar_dashboard", () => {

    console.log("Actualizando dashboard");

    refrescarSistema(null, false);

});


// =====================================================
// REPORTES
// =====================================================

socket.on("actualizar_reportes", () => {

    console.log("Actualizando reportes");

    refrescarSistema("Reportes actualizados");

});


// =====================================================
// ACCESOS
// =====================================================

socket.on("actualizar_accesos", () => {

    console.log("Actualizando accesos");

    refrescarSistema("Control de accesos actualizado");

});


// =====================================================
// INCIDENCIAS
// =====================================================

socket.on("actualizar_incidencias", () => {

    console.log("Actualizando incidencias");

    refrescarSistema("Incidencias actualizadas");

});


// =====================================================
// REFRESH GLOBAL  (mensaje profesional)
// =====================================================

socket.on("refresh", () => {

    console.log("Refrescando sistema");

    refrescarSistema("Información actualizada");

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