// Mapa administrativo de EcoAgua: marcadores reales desde /admin/api/mapa.
(function () {
  var COLORES = { pendiente: '#E7B75F', en_proceso: '#26BDE2', resuelto: '#045A78' };
  var estadoFiltro = '';
  var datos = null;
  var capaMarcadores, capaZonas, primeraVez = true;

  function esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  var mapa = L.map('mapaAdmin');
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin', attribution: '&copy; OpenStreetMap'
  }).addTo(mapa);
  capaZonas = L.layerGroup().addTo(mapa);
  capaMarcadores = L.featureGroup().addTo(mapa);

  function popup(r) {
    return '<div class="popup-eco">' +
      '<a class="num-seg" href="' + esc(r.url) + '">' + esc(r.numero) + '</a>' +
      (r.prueba ? ' <span class="etq-prueba">Prueba</span>' : '') +
      '<div><span class="pastilla pastilla-sm est-' + esc(r.estado) + '">' + esc(r.estado_texto) + '</span></div>' +
      '<div class="tenue">' + esc(r.fecha) + (r.barrio ? ' · ' + esc(r.barrio) : '') + '</div>' +
      '<div><strong>' + esc(r.tipo) + '</strong></div>' +
      '<p>' + esc(r.descripcion) + '</p>' +
      (r.foto ? '<a href="' + esc(r.foto) + '" target="_blank" rel="noopener"><img src="' + esc(r.foto) + '" alt="Foto de ' + esc(r.numero) + '" loading="lazy"></a>' : '') +
      '<a class="btn btn-solid btn-sm" href="' + esc(r.url) + '">Gestionar reporte</a>' +
      '</div>';
  }

  function pintar() {
    capaMarcadores.clearLayers();
    capaZonas.clearLayers();
    var lista = datos.reportes.filter(function (r) { return !estadoFiltro || r.estado === estadoFiltro; });

    if (document.getElementById('verZonas').checked) {
      var max = Math.max.apply(null, datos.zonas.map(function (z) { return z.total; }).concat([1]));
      datos.zonas.forEach(function (z) {
        L.circle([z.latitud, z.longitud], {
          radius: 250 + 550 * (z.total / max), color: '#045A78', weight: 1,
          fillColor: '#26BDE2', fillOpacity: 0.12 + 0.28 * (z.total / max)
        }).bindTooltip(esc(z.nombre) + ': ' + z.total + ' reporte' + (z.total === 1 ? '' : 's')).addTo(capaZonas);
      });
    }

    lista.forEach(function (r) {
      L.circleMarker([r.lat, r.lng], {
        radius: 8, color: '#fff', weight: 2, fillColor: COLORES[r.estado] || '#0B87AE', fillOpacity: 0.95
      }).bindPopup(popup(r), { maxWidth: 280 }).addTo(capaMarcadores);
    });

    var n = lista.length;
    document.getElementById('resumenMapa').textContent = n === 0
      ? (datos.reportes.length === 0 ? 'Todavía no hay reportes con ubicación.' : 'Ningún reporte con ese estado.')
      : n + ' reporte' + (n === 1 ? '' : 's') + ' en el mapa. Toca un punto para ver el detalle.';

    if (primeraVez) {
      primeraVez = false;
      var hash = location.hash.replace('#', '').split(',');
      if (hash.length === 2 && !isNaN(parseFloat(hash[0]))) {
        mapa.setView([parseFloat(hash[0]), parseFloat(hash[1])], 15);
      } else if (n > 0) {
        mapa.fitBounds(capaMarcadores.getBounds(), { padding: [30, 30], maxZoom: 16 });
      } else {
        mapa.setView([datos.centro.lat, datos.centro.lng], datos.centro.zoom);
      }
    }
  }

  function cargar() {
    return fetch(window.ECO_API_MAPA, { credentials: 'same-origin' })
      .then(function (r) { if (r.status === 401) { location.reload(); } return r.json(); })
      .then(function (d) { datos = d; pintar(); })
      .catch(function () { document.getElementById('resumenMapa').textContent = 'No se pudieron cargar los reportes. Recarga la página.'; });
  }

  document.querySelectorAll('.chip').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.chip').forEach(function (x) { x.classList.remove('activo'); });
      b.classList.add('activo');
      estadoFiltro = b.dataset.estado;
      if (datos) pintar();
    });
  });
  document.getElementById('verZonas').addEventListener('change', function () { if (datos) pintar(); });

  cargar();
  setInterval(function () { if (!document.hidden) cargar(); }, 60000);
})();
