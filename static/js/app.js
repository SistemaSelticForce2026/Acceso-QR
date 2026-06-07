console.log("Access QR funcionando correctamente");

/* ================================================
   FLASH TOASTS — Auto dismiss
   ================================================ */

function dismissToast(el) {
    el.classList.add('hiding');
    el.addEventListener('animationend', () => el.remove(), { once: true });
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.flash-toast').forEach((toast, i) => {
        toast.style.animationDelay = (i * 0.08) + 's';
        setTimeout(() => dismissToast(toast), 5000 + i * 80);
    });
});