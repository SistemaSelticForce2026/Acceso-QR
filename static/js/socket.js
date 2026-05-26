const socket = io();

console.log("Socket iniciado");

// ==========================================
// NUEVA VISITA
// ==========================================

socket.on("nueva_visita", (data) => {

    console.log("Nueva visita detectada");

    mostrarToast("Nueva visita registrada");

    setTimeout(() => {

        location.reload();

    }, 800);

});

// ==========================================
// ACTUALIZAR RESIDENTES
// ==========================================

socket.on("actualizar_residentes", () => {

    console.log("Actualizando residentes");

    mostrarToast("Lista de residentes actualizada");

    setTimeout(() => {

        location.reload();

    }, 500);

});

// ==========================================
// ACTUALIZAR GUARDIAS
// ==========================================

socket.on("actualizar_guardias", () => {

    console.log("Actualizando guardias");

    mostrarToast("Lista de guardias actualizada");

    setTimeout(() => {

        location.reload();

    }, 500);

});

// ==========================================
// ACTUALIZAR DASHBOARD
// ==========================================

socket.on("actualizar_dashboard", () => {

    console.log("Actualizando dashboard");

    setTimeout(() => {

        location.reload();

    }, 500);

});

// ==========================================
// TOAST PROFESIONAL
// ==========================================

function mostrarToast(texto) {

    const toast = document.createElement("div");

    toast.className = "socket-toast";

    toast.innerHTML = `
        <i class="fa-solid fa-bell"></i>
        ${texto}
    `;

    document.body.appendChild(toast);

    setTimeout(() => {

        toast.classList.add("show");

    }, 100);

    setTimeout(() => {

        toast.classList.remove("show");

        setTimeout(() => {

            toast.remove();

        }, 300);

    }, 2500);

}