/* Placeholder "dd/mm/aaaa" propio para inputs de fecha — SOLO MÓVIL.
   En escritorio el span ni se crea (lo gestiona date_placeholder.js);
   esta regla base lo mantiene oculto por si quedara de una sesión previa
   al ensanchar la ventana. */
(function () {
    var mq = window.matchMedia('(max-width: 680px)');
    var placers = [];

    function build(inp) {
        if (inp.dataset.phBound) return;
        inp.dataset.phBound = '1';

        var field = inp.parentNode;
        if (getComputedStyle(field).position === 'static') {
            field.style.position = 'relative';
        }

        var cs = getComputedStyle(inp);
        var ph = document.createElement('span');
        ph.className = 'date-ph';
        ph.textContent = 'dd/mm/aaaa';
        ph.style.fontSize = cs.fontSize;
        ph.style.fontFamily = cs.fontFamily;
        ph.style.paddingLeft = cs.paddingLeft;   
        field.appendChild(ph);                 

        function place() {
            ph.style.top = inp.offsetTop + 'px';
            ph.style.left = inp.offsetLeft + 'px';
            ph.style.width = inp.offsetWidth + 'px';
            ph.style.height = inp.offsetHeight + 'px';
        }
        function refresh() {
            // mostrar nuestro placeholder solo si está vacío y sin foco
            var show = inp.value === '' && document.activeElement !== inp;
            ph.classList.toggle('is-hidden', !show);
            inp.classList.toggle('date-ph-empty', show); 
        }

        place();
        refresh();
        placers.push(place);
        inp.addEventListener('input', refresh);
        inp.addEventListener('change', refresh);
        inp.addEventListener('focus', refresh);
        inp.addEventListener('blur', function () { place(); refresh(); });
    }

    function placeAll() {
        placers.forEach(function (f) { f(); });
    }

    function init() {
        if (!mq.matches) return;       
        document.querySelectorAll('input[type="date"]').forEach(build);
        placeAll();
    }

    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);

    window.addEventListener('load', placeAll);    
    window.addEventListener('resize', placeAll);
    mq.addEventListener('change', init);         
})();
