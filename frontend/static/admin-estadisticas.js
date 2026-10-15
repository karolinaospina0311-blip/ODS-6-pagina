// Estadísticas del panel EcoAgua: todos los datos llegan de /admin/api/estadisticas.
(function () {
  var css = getComputedStyle(document.documentElement);
  var C = {
    pendiente: css.getPropertyValue('--sand').trim() || '#E7B75F',
    en_proceso: css.getPropertyValue('--aqua').trim() || '#26BDE2',
    resuelto: css.getPropertyValue('--teal-deep').trim() || '#045A78',
    teal: css.getPropertyValue('--teal').trim() || '#0B87AE',
    ink: css.getPropertyValue('--ink').trim() || '#0B2733',
    linea: 'rgba(11,39,51,0.10)'
  };
  Chart.defaults.font.family = "'Public Sans', sans-serif";
  Chart.defaults.color = C.ink;
  Chart.defaults.maintainAspectRatio = false;

  function esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  var graficas = {};
  var ejeY = { beginAtZero: true, ticks: { precision: 0 }, grid: { color: C.linea } };

  function crear(d) {
    graficas.estado = new Chart(document.getElementById('gEstado'), {
      type: 'doughnut',
      data: { labels: ['Pendiente', 'En proceso', 'Resuelto'],
              datasets: [{ data: [], backgroundColor: [C.pendiente, C.en_proceso, C.resuelto], borderWidth: 2, borderColor: '#fff' }] },
      options: { cutout: '58%', plugins: { legend: { position: 'bottom' } } }
    });
    graficas.evolucion = new Chart(document.getElementById('gEvolucion'), {
      type: 'line',
      data: { labels: [], datasets: [{ label: 'Reportes', data: [], borderColor: C.teal, backgroundColor: 'rgba(11,135,174,0.12)', fill: true, cubicInterpolationMode: 'monotone', pointRadius: 2 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: ejeY, x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } } } }
    });
    graficas.zonas = new Chart(document.getElementById('gZonas'), {
      type: 'bar',
      data: { labels: [], datasets: [
        { label: 'Pendiente', data: [], backgroundColor: C.pendiente },
        { label: 'En proceso', data: [], backgroundColor: C.en_proceso },
        { label: 'Resuelto', data: [], backgroundColor: C.resuelto }
      ] },
      options: { indexAxis: 'y', plugins: { legend: { position: 'bottom' } },
                 scales: { x: Object.assign({ stacked: true }, ejeY), y: { stacked: true, grid: { display: false } } } }
    });
    graficas.tipo = new Chart(document.getElementById('gTipo'), {
      type: 'bar',
      data: { labels: [], datasets: [{ label: 'Reportes', data: [], backgroundColor: C.teal, borderRadius: 6 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: ejeY, x: { grid: { display: false } } } }
    });
    pintar(d);
  }

  function pintar(d) {
    document.getElementById('kpiTotal').textContent = d.total.toLocaleString('es-CO');
    document.getElementById('kpiPendiente').textContent = d.pendiente.toLocaleString('es-CO');
    document.getElementById('kpiProceso').textContent = d.en_proceso.toLocaleString('es-CO');
    document.getElementById('kpiResuelto').textContent = d.resuelto.toLocaleString('es-CO');
    document.getElementById('vacio').hidden = d.total > 0;
    document.getElementById('graficas').hidden = d.total === 0;

    graficas.estado.data.datasets[0].data = [d.pendiente, d.en_proceso, d.resuelto];
    graficas.evolucion.data.labels = d.evolucion.map(function (x) { return x.fecha; });
    graficas.evolucion.data.datasets[0].data = d.evolucion.map(function (x) { return x.total; });
    graficas.zonas.data.labels = d.zonas.map(function (z) { return z.nombre; });
    graficas.zonas.data.datasets[0].data = d.zonas.map(function (z) { return z.pendiente; });
    graficas.zonas.data.datasets[1].data = d.zonas.map(function (z) { return z.en_proceso; });
    graficas.zonas.data.datasets[2].data = d.zonas.map(function (z) { return z.resuelto; });
    graficas.tipo.data.labels = d.por_tipo.map(function (t) { return t.tipo; });
    graficas.tipo.data.datasets[0].data = d.por_tipo.map(function (t) { return t.total; });
    Object.keys(graficas).forEach(function (k) { graficas[k].update(); });

    document.getElementById('tablaZonas').innerHTML = d.zonas.map(function (z) {
      return '<tr><td data-t="Zona"><strong>' + esc(z.nombre) + '</strong></td>' +
        '<td data-t="Total">' + z.total + '</td><td data-t="Pendientes">' + z.pendiente + '</td>' +
        '<td data-t="En proceso">' + z.en_proceso + '</td><td data-t="Resueltos">' + z.resuelto + '</td>' +
        '<td data-t="Centro"><a href="' + esc(window.ECO_MAPA) + '#' + z.latitud + ',' + z.longitud + '">' +
        z.latitud.toFixed(4) + ', ' + z.longitud.toFixed(4) + '</a></td></tr>';
    }).join('');

    document.getElementById('actualizado').textContent =
      'Actualizado ' + new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
  }

  crear(JSON.parse(document.getElementById('datosIniciales').textContent));

  setInterval(function () {
    if (document.hidden) return;
    fetch(window.ECO_API, { credentials: 'same-origin' })
      .then(function (r) { if (r.status === 401) { location.reload(); } return r.json(); })
      .then(function (d) { if (d && typeof d.total === 'number') pintar(d); })
      .catch(function () {});
  }, 60000);
})();
