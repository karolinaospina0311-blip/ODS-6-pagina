// =====================================================================
// EcoAgua · Reportar una fuga y consultar su estado (parte pública)
// Archivo agregado; no modifica script.js.
// =====================================================================
(function () {
  'use strict';

  var CONFIG = null;
  var MAX_LADO = 1600;               // la foto se reduce en el celular antes de enviarla
  var fotoFinal = null;              // Blob/File que se enviará
  var mapaReporte = null, marcador = null;
  var mapaResultado = null, marcadorResultado = null;
  var CLAVE_LOCAL = 'ecoagua_mis_reportes';

  var $ = function (id) { return document.getElementById(id); };
  var form = $('formReporte');
  if (!form) return;

  // ------------------------------------------------------------ utilidades
  function mostrarErrores(errores) {
    form.querySelectorAll('.campo.invalido').forEach(function (c) { c.classList.remove('invalido'); });
    form.querySelectorAll('[data-error]').forEach(function (e) { e.textContent = ''; });
    $('errorGeneral').textContent = '';
    var primero = null;
    Object.keys(errores || {}).forEach(function (campo) {
      var el = form.querySelector('[data-error="' + campo + '"]');
      if (el) {
        el.textContent = errores[campo];
        var cont = form.querySelector('[data-campo="' + campo + '"]');
        if (cont) { cont.classList.add('invalido'); primero = primero || cont; }
      } else {
        $('errorGeneral').textContent = errores[campo];
        primero = primero || $('errorGeneral');
      }
    });
    if (primero) primero.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function limpiarError(campo) {
    var cont = form.querySelector('[data-campo="' + campo + '"]');
    if (cont) cont.classList.remove('invalido');
    var el = form.querySelector('[data-error="' + campo + '"]');
    if (el) el.textContent = '';
  }

  function tamano(bytes) {
    return bytes > 1048576 ? (bytes / 1048576).toFixed(1) + ' MB' : Math.round(bytes / 1024) + ' KB';
  }

  function leerMisReportes() {
    try { return JSON.parse(localStorage.getItem(CLAVE_LOCAL) || '[]'); } catch (e) { return []; }
  }
  function guardarMiReporte(num) {
    try {
      var l = leerMisReportes().filter(function (n) { return n !== num; });
      l.unshift(num);
      localStorage.setItem(CLAVE_LOCAL, JSON.stringify(l.slice(0, 5)));
    } catch (e) { /* almacenamiento no disponible: no pasa nada */ }
    pintarMisReportes();
  }
  function pintarMisReportes() {
    var cont = $('misReportes');
    var l = leerMisReportes();
    cont.innerHTML = '';
    if (!l.length) return;
    var t = document.createElement('span');
    t.textContent = 'Reportes hechos desde este dispositivo:';
    cont.appendChild(t);
    l.forEach(function (n) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = n;
      b.addEventListener('click', function () { $('numConsulta').value = n; consultar(n); });
      cont.appendChild(b);
    });
  }

  // ------------------------------------------------------------ configuración
  fetch('/api/config')
    .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
    .then(function (c) {
      CONFIG = c;
      var sel = $('tipoFuga');
      c.tipos_fuga.forEach(function (t) {
        var o = document.createElement('option');
        o.value = t.valor; o.textContent = t.texto;
        sel.appendChild(o);
      });
      $('fotoAyuda').textContent = 'JPG, PNG o WEBP, hasta ' + c.max_foto_mb + ' MB.' +
        (c.foto_obligatoria ? '' : ' La foto es opcional, pero ayuda mucho a atender la fuga.');
      iniciarMapaReporte();
    })
    .catch(function () {
      $('avisoServidor').hidden = false;
      $('btnEnviar').disabled = true;
      $('btnConsultar').disabled = true;
    });

  // ------------------------------------------------------------ mapa de selección
  function iniciarMapaReporte() {
    if (typeof L === 'undefined') { $('coordsTexto').textContent = 'No se pudo cargar el mapa. Usa el botón de GPS.'; return; }
    mapaReporte = L.map('mapaReporte', { scrollWheelZoom: false })
      .setView([CONFIG.mapa.lat, CONFIG.mapa.lng], CONFIG.mapa.zoom);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin', attribution: '&copy; OpenStreetMap'
    }).addTo(mapaReporte);
    mapaReporte.on('click', function (e) { fijarUbicacion(e.latlng.lat, e.latlng.lng, 'mapa'); });
    // El mapa está en una sección que aparece con animación; se recalcula su tamaño al verse.
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (ent) {
        ent.forEach(function (x) { if (x.isIntersecting) mapaReporte.invalidateSize(); });
      }).observe($('mapaReporte'));
    }
  }

  function fijarUbicacion(lat, lng, origen, precision) {
    $('latitud').value = lat.toFixed(7);
    $('longitud').value = lng.toFixed(7);
    $('origenUbicacion').value = origen;
    $('precisionGps').value = origen === 'gps' && precision ? precision : '';
    limpiarError('ubicacion');
    if (mapaReporte) {
      if (!marcador) {
        marcador = L.marker([lat, lng], { draggable: true, autoPan: true }).addTo(mapaReporte);
        marcador.on('dragend', function () {
          var p = marcador.getLatLng();
          fijarUbicacion(p.lat, p.lng, 'mapa');
          avisoGps('Ubicación ajustada manualmente.', 'ok');
        });
      } else {
        marcador.setLatLng([lat, lng]);
      }
      mapaReporte.setView([lat, lng], Math.max(mapaReporte.getZoom(), 17));
    }
    $('coordsTexto').textContent = 'Ubicación marcada: ' + lat.toFixed(5) + ', ' + lng.toFixed(5) +
      '. Puedes arrastrar el marcador si no es exacta.';
  }

  function avisoGps(texto, tipo) {
    var el = $('gpsEstado');
    el.textContent = texto;
    el.className = 'gps-estado' + (tipo ? ' ' + tipo : '');
  }

  $('btnGps').addEventListener('click', function () {
    var btn = this;
    if (!('geolocation' in navigator)) {
      avisoGps('Tu navegador no permite usar el GPS. Toca el mapa para marcar la ubicación.', 'aviso');
      return;
    }
    if (window.isSecureContext === false) {
      avisoGps('El GPS solo funciona si la página se abre con https://. Por ahora, toca el mapa para marcar la ubicación.', 'aviso');
      return;
    }
    btn.disabled = true;
    avisoGps('Buscando tu ubicación… acepta el permiso si el navegador lo pide.');
    navigator.geolocation.getCurrentPosition(function (pos) {
      btn.disabled = false;
      var c = pos.coords;
      fijarUbicacion(c.latitude, c.longitude, 'gps', c.accuracy);
      var prec = Math.round(c.accuracy);
      avisoGps('Ubicación obtenida' + (prec ? ' (precisión aproximada de ' + prec + ' m)' : '') +
        '. Revisa en el mapa que el punto sea correcto.', prec > 100 ? 'aviso' : 'ok');
    }, function (err) {
      btn.disabled = false;
      var msg = {
        1: 'No diste permiso para usar tu ubicación. Toca el mapa para marcar dónde está la fuga.',
        2: 'No se pudo obtener tu ubicación. Activa el GPS del celular o toca el mapa.',
        3: 'El GPS tardó demasiado. Intenta de nuevo o toca el mapa.'
      }[err.code] || 'No se pudo obtener tu ubicación. Toca el mapa para marcarla.';
      avisoGps(msg, 'aviso');
    }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 });
  });

  // ------------------------------------------------------------ fotografía
  function reducirImagen(file) {
    return new Promise(function (resolve) {
      if (!window.URL || !document.createElement('canvas').toBlob) return resolve(file);
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        var escala = Math.min(1, MAX_LADO / Math.max(img.naturalWidth, img.naturalHeight));
        if (escala === 1 && file.type === 'image/jpeg' && file.size < 1.5 * 1048576) {
          URL.revokeObjectURL(url); return resolve(file);
        }
        var cv = document.createElement('canvas');
        cv.width = Math.round(img.naturalWidth * escala);
        cv.height = Math.round(img.naturalHeight * escala);
        cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
        URL.revokeObjectURL(url);
        cv.toBlob(function (b) { resolve(b && b.size < file.size ? b : file); }, 'image/jpeg', 0.85);
      };
      img.onerror = function () { URL.revokeObjectURL(url); resolve(file); };
      img.src = url;
    });
  }

  function alElegirFoto(e) {
    var file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    limpiarError('foto');
    var maxMb = CONFIG ? CONFIG.max_foto_mb : 8;
    if (!/^image\//.test(file.type) && !/\.(jpe?g|png|webp)$/i.test(file.name)) {
      mostrarErrores({ foto: 'El archivo elegido no es una imagen. Usa una foto JPG, PNG o WEBP.' });
      return;
    }
    $('fotoInfo').textContent = 'Preparando la foto…';
    $('fotoPreview').classList.add('visible');
    reducirImagen(file).then(function (final) {
      if (final.size > maxMb * 1048576) {
        quitarFoto();
        mostrarErrores({ foto: 'La foto pesa ' + tamano(final.size) + '. El máximo es ' + maxMb + ' MB.' });
        return;
      }
      fotoFinal = final;
      var url = URL.createObjectURL(final);
      $('fotoImg').onload = function () { URL.revokeObjectURL(url); };
      $('fotoImg').onerror = function () { $('fotoImg').removeAttribute('src'); };
      $('fotoImg').src = url;
      $('fotoInfo').textContent = 'Foto lista (' + tamano(final.size) + ')';
      $('fotoArchivoLabel').textContent = 'Cambiar fotografía';
    });
  }

  function quitarFoto() {
    fotoFinal = null;
    $('fotoPreview').classList.remove('visible');
    $('fotoImg').removeAttribute('src');
    $('fotoArchivoLabel').textContent = 'Elegir fotografía';
  }

  $('fotoCamara').addEventListener('change', alElegirFoto);
  $('fotoArchivo').addEventListener('change', alElegirFoto);
  $('fotoQuitar').addEventListener('click', quitarFoto);

  form.querySelectorAll('input, select, textarea').forEach(function (el) {
    el.addEventListener('input', function () {
      var c = el.closest('[data-campo]');
      if (c) limpiarError(c.dataset.campo);
    });
  });

  // ------------------------------------------------------------ envío
  function validarCliente() {
    var e = {};
    var f = form.elements;
    if (CONFIG && CONFIG.foto_obligatoria && !fotoFinal) e.foto = 'Adjunta una fotografía de la fuga.';
    if (!f.tipo_fuga.value) e.tipo_fuga = 'Elige el tipo de fuga.';
    if (f.descripcion.value.trim().length < 10) e.descripcion = 'Describe la fuga con al menos 10 caracteres.';
    if (!f.latitud.value) e.ubicacion = 'Marca la ubicación de la fuga con el GPS o tocando el mapa.';
    if (f.nombre.value.trim().length < 3) e.nombre = 'Escribe tu nombre completo.';
    if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(f.correo.value.trim())) e.correo = 'Escribe un correo electrónico válido, por ejemplo nombre@correo.com.';
    if (f.telefono.value.trim() && !/^[0-9+()\-\s]{7,20}$/.test(f.telefono.value.trim())) e.telefono = 'El teléfono solo puede tener números, espacios y los signos + ( ) -.';
    return e;
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var errores = validarCliente();
    if (Object.keys(errores).length) { mostrarErrores(errores); return; }
    mostrarErrores({});

    var datos = new FormData(form);
    if (fotoFinal) datos.append('foto', fotoFinal, 'foto.jpg');

    var btn = $('btnEnviar');
    btn.disabled = true;
    btn.textContent = 'Enviando reporte…';

    fetch('/api/reportes', { method: 'POST', body: datos })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false, errores: { general: 'Respuesta inesperada del servidor (código ' + r.status + ').' } }; });
      })
      .then(function (res) {
        if (!res.ok) { mostrarErrores(res.errores || { general: 'No se pudo registrar el reporte.' }); return; }
        $('numConfirmado').textContent = res.numero_seguimiento;
        $('btnVerEstado').dataset.numero = res.numero_seguimiento;
        form.hidden = true;
        $('confirmacion').classList.add('visible');
        $('confirmacion').focus({ preventScroll: true });
        $('reportar').scrollIntoView({ behavior: 'smooth' });
        guardarMiReporte(res.numero_seguimiento);
      })
      .catch(function () {
        mostrarErrores({ general: 'No hay conexión con el servidor. Revisa tu internet e intenta de nuevo; tus datos siguen en el formulario.' });
      })
      .finally(function () {
        btn.disabled = false;
        btn.textContent = 'Enviar reporte';
      });
  });

  $('btnCopiar').addEventListener('click', function () {
    var n = $('numConfirmado').textContent, b = this;
    var listo = function () { b.textContent = 'Número copiado'; setTimeout(function () { b.textContent = 'Copiar número'; }, 2500); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(n).then(listo, function () {});
    } else {
      var r = document.createRange(); r.selectNodeContents($('numConfirmado'));
      var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
      try { document.execCommand('copy'); listo(); } catch (e) {}
    }
  });

  $('btnVerEstado').addEventListener('click', function () {
    var n = this.dataset.numero;
    if (n) { $('numConsulta').value = n; consultar(n); }
  });

  $('btnOtro').addEventListener('click', function () {
    form.reset();
    quitarFoto();
    ['latitud', 'longitud', 'precisionGps'].forEach(function (id) { $(id).value = ''; });
    $('origenUbicacion').value = 'mapa';
    if (marcador) { mapaReporte.removeLayer(marcador); marcador = null; }
    $('coordsTexto').textContent = 'Toca el mapa para marcar el punto exacto. Puedes arrastrar el marcador para corregirlo.';
    avisoGps('');
    $('confirmacion').classList.remove('visible');
    form.hidden = false;
    if (mapaReporte) setTimeout(function () { mapaReporte.invalidateSize(); }, 50);
    $('reportar').scrollIntoView({ behavior: 'smooth' });
  });

  // ------------------------------------------------------------ consulta de estado
  var ORDEN = ['pendiente', 'en_proceso', 'resuelto'];

  function consultar(numero) {
    var msg = $('consultaMsg');
    var n = (numero || '').trim().toUpperCase().replace(/\s+/g, '');
    msg.textContent = '';
    if (!/^ECO-\d{4}-\d{5,7}$/.test(n)) {
      msg.textContent = 'Escribe el número completo, con el formato ECO-2026-00001.';
      $('resultado').classList.remove('visible');
      return;
    }
    var btn = $('btnConsultar');
    btn.disabled = true; btn.textContent = 'Consultando…';
    fetch('/api/reportes/' + encodeURIComponent(n))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) { msg.textContent = res.error; $('resultado').classList.remove('visible'); return; }
        pintarResultado(res.reporte);
      })
      .catch(function () { msg.textContent = 'No hay conexión con el servidor. Intenta de nuevo.'; })
      .finally(function () { btn.disabled = false; btn.textContent = 'Consultar estado'; });
  }

  function pintarResultado(r) {
    $('resNumero').textContent = r.numero_seguimiento;
    $('resFechas').textContent = 'Reportado el ' + r.fecha + ' · Última actualización ' + r.fecha_actualizacion;
    var est = $('resEstado');
    est.textContent = 'Estado: ' + r.estado_texto.toUpperCase();
    est.className = 'pastilla est-' + r.estado;

    var idx = ORDEN.indexOf(r.estado);
    $('resProgreso').querySelectorAll('div').forEach(function (d, i) {
      d.className = i < idx ? 'hecho' : (i === idx ? 'actual' : '');
    });

    $('resTipo').textContent = r.tipo_fuga;
    $('resDesc').textContent = r.descripcion;
    var partes = [];
    if (r.barrio) partes.push(r.barrio);
    if (r.direccion) partes.push(r.direccion);
    partes.push(r.latitud.toFixed(5) + ', ' + r.longitud.toFixed(5));
    $('resUbic').textContent = partes.join('\n');

    var foto = $('resFoto');
    if (r.foto) { foto.src = r.foto; foto.hidden = false; } else { foto.hidden = true; foto.removeAttribute('src'); }

    var hist = $('resHistorial');
    hist.innerHTML = '';
    r.historial.slice().reverse().forEach(function (h) {
      var li = document.createElement('li');
      var p = document.createElement('span');
      p.className = 'pastilla pastilla-sm est-' + h.estado;
      p.textContent = h.estado_texto;
      var f = document.createElement('span');
      f.className = 'ayuda';
      f.textContent = h.fecha;
      li.appendChild(p); li.appendChild(f);
      if (h.nota) { var n = document.createElement('p'); n.textContent = h.nota; li.appendChild(n); }
      hist.appendChild(li);
    });

    $('resultado').classList.add('visible');

    if (typeof L !== 'undefined') {
      if (!mapaResultado) {
        mapaResultado = L.map('resMapa', { scrollWheelZoom: false, dragging: !L.Browser.mobile });
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin', attribution: '&copy; OpenStreetMap' }).addTo(mapaResultado);
        marcadorResultado = L.marker([r.latitud, r.longitud]).addTo(mapaResultado);
      }
      marcadorResultado.setLatLng([r.latitud, r.longitud]);
      setTimeout(function () {
        mapaResultado.invalidateSize();
        mapaResultado.setView([r.latitud, r.longitud], 16);
      }, 60);
    } else {
      $('resMapa').hidden = true;
    }
    $('resultado').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  $('formConsulta').addEventListener('submit', function (e) {
    e.preventDefault();
    consultar($('numConsulta').value);
  });

  pintarMisReportes();

  // Permite enlaces directos: /?seguimiento=ECO-2026-00001#consultar
  var qs = new URLSearchParams(location.search).get('seguimiento');
  if (qs) { $('numConsulta').value = qs.toUpperCase(); setTimeout(function () { consultar(qs); }, 300); }
})();
