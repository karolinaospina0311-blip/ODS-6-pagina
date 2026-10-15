// ---------- Datos de las metas ----------
const metas = [
  {tag:"Meta 6.1", title:"Acceso universal al agua potable", text:"De aquí a 2030, lograr el acceso universal y equitativo al agua potable, a un precio asequible para todos.", fact:"Se estima que 2.200 millones de personas aún no tienen acceso a agua potable gestionada de forma segura."},
  {tag:"Meta 6.2", title:"Saneamiento e higiene adecuados", text:"Lograr el acceso a servicios de saneamiento e higiene adecuados y equitativos para todos, y poner fin a la defecación al aire libre, prestando especial atención a las necesidades de mujeres, niñas y personas en situación vulnerable.", fact:"3.500 millones de personas todavía carecen de servicios de saneamiento gestionados de forma segura."},
  {tag:"Meta 6.3", title:"Mejorar la calidad del agua", text:"Mejorar la calidad del agua reduciendo la contaminación, eliminando el vertimiento y minimizando la emisión de productos químicos y materiales peligrosos, y aumentando el reciclado y la reutilización segura.", fact:"Alrededor del 80% de las aguas residuales del mundo se vierte a los ecosistemas sin tratamiento adecuado."},
  {tag:"Meta 6.4", title:"Uso eficiente del agua", text:"Aumentar el uso eficiente de los recursos hídricos en todos los sectores y asegurar la sostenibilidad de la extracción y el abastecimiento de agua dulce para hacer frente a la escasez.", fact:"La escasez de agua afecta hoy a más de 2.000 millones de personas en distintas regiones del mundo."},
  {tag:"Meta 6.5", title:"Gestión integrada de los recursos hídricos", text:"Implementar la gestión integrada de los recursos hídricos a todos los niveles, incluso mediante la cooperación transfronteriza, según proceda.", fact:"Más de 150 países comparten al menos una cuenca hídrica o un acuífero con otra nación."},
  {tag:"Meta 6.6", title:"Proteger los ecosistemas relacionados con el agua", text:"Proteger y restablecer los ecosistemas relacionados con el agua, incluidos los bosques, las montañas, los humedales, los ríos, los acuíferos y los lagos.", fact:"Se calcula que desde 1970 el planeta ha perdido cerca del 35% de sus humedales naturales."},
  {tag:"Meta 6.a", title:"Cooperación internacional", text:"Ampliar la cooperación internacional y el apoyo a los países en desarrollo para la creación de capacidad en actividades y programas relativos al agua y el saneamiento.", fact:"La cooperación internacional en agua y saneamiento financia plantas de tratamiento, pozos y redes de distribución en decenas de países."},
  {tag:"Meta 6.b", title:"Participación comunitaria", text:"Apoyar y fortalecer la participación de las comunidades locales en la mejora de la gestión del agua y el saneamiento.", fact:"Los sistemas de agua rural gestionados con participación comunitaria tienden a mantenerse funcionando por más años."}
];

const tabsEl = document.getElementById('metaTabs');
const panelEl = document.getElementById('metaPanel');

function renderPanel(i){
  const m = metas[i];
  panelEl.innerHTML = `
    <div>
      <div class="eyebrow">${m.tag}</div>
      <h3>${m.title}</h3>
      <p>${m.text}</p>
    </div>
    <div class="meta-visual">
      <div class="meta-num-watermark">${m.tag.replace('Meta ','')}</div>
      <div class="meta-fact">
        <div class="fact-label">Dato relacionado</div>
        <div class="fact-text">${m.fact}</div>
      </div>
      <svg class="waves" viewBox="0 0 300 40" preserveAspectRatio="none">
        <path d="M0,20 C40,35 80,5 120,20 C160,35 200,5 240,20 C260,27 280,17 300,22 L300,40 L0,40 Z" fill="var(--aqua)"></path>
      </svg>
    </div>
  `;
}

metas.forEach((m, i) => {
  const btn = document.createElement('button');
  btn.className = 'meta-tab' + (i===0 ? ' active' : '');
  btn.setAttribute('role','tab');
  btn.innerHTML = `<span class="tag">${m.tag}</span>${m.title}`;
  btn.addEventListener('click', () => {
    document.querySelectorAll('.meta-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    renderPanel(i);
  });
  tabsEl.appendChild(btn);
});
renderPanel(0);

// ---------- Los 17 ODS y su relación con el agua ----------
const odsList = [
  {n:1, name:"Fin de la pobreza", color:"#E5243B", text:"La falta de agua cercana obliga a muchas familias a gastar tiempo y dinero desproporcionados en conseguirla, lo que profundiza la pobreza."},
  {n:2, name:"Hambre cero", color:"#DDA63A", text:"La agricultura utiliza cerca del 70% del agua dulce del planeta; usarla de forma eficiente es clave para producir alimentos suficientes."},
  {n:3, name:"Salud y bienestar", color:"#4C9F38", text:"El agua contaminada y el saneamiento deficiente siguen causando enfermedades diarreicas, sobre todo en la niñez."},
  {n:4, name:"Educación de calidad", color:"#C5192D", text:"Tener agua y baños seguros en las escuelas reduce el ausentismo, en especial entre las niñas."},
  {n:5, name:"Igualdad de género", color:"#FF3A21", text:"En muchas comunidades son mujeres y niñas quienes recorren largas distancias para acarrear agua, lo que limita su tiempo de estudio y trabajo."},
  {n:6, name:"Agua limpia y saneamiento", color:"#26BDE2", text:"El objetivo central de esta página: garantizar disponibilidad, gestión sostenible del agua y saneamiento para todas las personas."},
  {n:7, name:"Energía asequible y no contaminante", color:"#FCC30B", text:"La generación hidroeléctrica depende directamente de la disponibilidad y buena gestión de los recursos hídricos."},
  {n:8, name:"Trabajo decente y crecimiento económico", color:"#A21942", text:"El acceso al agua sostiene sectores productivos enteros, desde la industria hasta el turismo y la agricultura."},
  {n:9, name:"Industria, innovación e infraestructura", color:"#FD6925", text:"Una infraestructura hídrica moderna reduce fugas, mejora el tratamiento de aguas residuales e impulsa nueva tecnología."},
  {n:10, name:"Reducción de las desigualdades", color:"#DD1367", text:"Cerrar la brecha de acceso al agua entre zonas urbanas y rurales, o entre países, es esencial para reducir la desigualdad."},
  {n:11, name:"Ciudades y comunidades sostenibles", color:"#FD9D24", text:"Una gestión urbana eficiente del agua previene inundaciones, escasez y contaminación en las ciudades."},
  {n:12, name:"Producción y consumo responsables", color:"#BF8B2E", text:"Reducir, reutilizar y tratar el agua en los procesos productivos disminuye la presión sobre las fuentes de agua dulce."},
  {n:13, name:"Acción por el clima", color:"#3F7E44", text:"El cambio climático altera los patrones de lluvia y disponibilidad de agua, intensificando sequías e inundaciones."},
  {n:14, name:"Vida submarina", color:"#0A97D9", text:"Las aguas residuales sin tratar terminan en ríos y océanos, dañando los ecosistemas marinos."},
  {n:15, name:"Vida de ecosistemas terrestres", color:"#56C02B", text:"Bosques y humedales sanos regulan el ciclo del agua y protegen las fuentes de agua dulce."},
  {n:16, name:"Paz, justicia e instituciones sólidas", color:"#00689D", text:"Gestionar cuencas compartidas entre países requiere instituciones sólidas y cooperación pacífica."},
  {n:17, name:"Alianzas para lograr los objetivos", color:"#19486A", text:"Alcanzar el ODS 6 depende de la cooperación internacional, la financiación y el intercambio de conocimiento."}
];

const odsGrid = document.getElementById('odsGrid');
const odsDetail = document.getElementById('odsDetail');

function renderOdsDetail(item){
  odsDetail.innerHTML = `
    <div class="ods-detail-head">
      <div class="swatch" style="background:${item.color}"></div>
      <h3>ODS ${item.n} · ${item.name}</h3>
    </div>
    <p>${item.text}</p>
  `;
}

odsList.forEach(item => {
  const tile = document.createElement('div');
  tile.className = 'ods-tile' + (item.n === 6 ? ' active' : '');
  tile.style.background = item.color;
  tile.textContent = item.n;
  tile.title = item.name;
  tile.addEventListener('click', () => {
    document.querySelectorAll('.ods-tile').forEach(t => t.classList.remove('active'));
    tile.classList.add('active');
    renderOdsDetail(item);
  });
  odsGrid.appendChild(tile);
});
renderOdsDetail(odsList.find(i => i.n === 6));

// ---------- Línea de tiempo ----------
const timelineData = [
  {year:"1977", title:"Conferencia de Mar del Plata", text:"Primera conferencia internacional de la ONU dedicada exclusivamente al agua; reconoce el acceso al agua como una necesidad básica de la humanidad."},
  {year:"2000", title:"Objetivos de Desarrollo del Milenio", text:"Se fija la meta de reducir a la mitad la proporción de personas sin acceso sostenible a agua potable antes de 2015."},
  {year:"2010", title:"El agua como derecho humano", text:"La Asamblea General de la ONU reconoce explícitamente el acceso al agua potable y al saneamiento como un derecho humano."},
  {year:"2015", title:"Nace el ODS 6", text:"Con la Agenda 2030, los 193 Estados miembros de la ONU adoptan formalmente el ODS 6 dentro de los 17 Objetivos de Desarrollo Sostenible."},
  {year:"2023", title:"Conferencia del Agua de la ONU", text:"Primera cumbre mundial sobre el agua en 46 años; se lanza la Agenda de Acción del Agua con miles de compromisos voluntarios de gobiernos y organizaciones."},
  {year:"2030", title:"Fecha límite del ODS 6", text:"Plazo fijado por la Agenda 2030 para lograr el acceso universal al agua potable, el saneamiento y la gestión sostenible del agua."}
];

const timelineList = document.getElementById('timelineList');
timelineData.forEach(item => {
  const el = document.createElement('div');
  el.className = 'timeline-item';
  el.innerHTML = `
    <div class="timeline-year">${item.year}</div>
    <div class="timeline-title">${item.title}</div>
    <span class="timeline-toggle">Leer más</span>
    <div class="timeline-more"><p>${item.text}</p></div>
  `;
  el.addEventListener('click', () => {
    el.classList.toggle('open');
    el.querySelector('.timeline-toggle').textContent = el.classList.contains('open') ? 'Leer menos' : 'Leer más';
  });
  timelineList.appendChild(el);
});

// ---------- Acciones (tarjetas expandibles) ----------
const acciones = [
  {n:"01", h:"Cierra el grifo", t:"Mientras te cepillas los dientes o enjabonas los platos, puedes ahorrar hasta 12 litros de agua por minuto."},
  {n:"02", h:"Repara las fugas", t:"Un grifo que gotea puede desperdiciar más de 11.000 litros de agua al año sin que lo notes."},
  {n:"03", h:"Cuida los ríos y humedales", t:"Evita verter químicos o residuos en fuentes de agua; protegen la biodiversidad y purifican el agua de forma natural."},
  {n:"04", h:"Reutiliza el agua", t:"El agua de enjuague de frutas o de lluvia puede reutilizarse para regar plantas o limpiar espacios exteriores."},
  {n:"05", h:"Apoya el saneamiento comunitario", t:"Infórmate y participa en iniciativas locales que amplían el acceso a agua potable y saneamiento seguro."},
  {n:"06", h:"Consume con conciencia", t:"La producción de alimentos y ropa consume grandes volúmenes de agua; reducir el desperdicio ayuda a aliviar la presión sobre este recurso."}
];

const grid = document.getElementById('accionesGrid');
acciones.forEach(a => {
  const card = document.createElement('div');
  card.className = 'accion-card';
  card.innerHTML = `
    <div class="num">${a.n}</div>
    <h3>${a.h}</h3>
    <span class="toggle">Ver más</span>
    <div class="more"><p>${a.t}</p></div>
  `;
  card.addEventListener('click', () => {
    card.classList.toggle('open');
    const toggle = card.querySelector('.toggle');
    toggle.textContent = card.classList.contains('open') ? 'Ver menos' : 'Ver más';
  });
  grid.appendChild(card);
});

// ---------- Contadores animados ----------
const statNums = document.querySelectorAll('.stat-num');
const statObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if(entry.isIntersecting){
      const el = entry.target;
      const target = parseInt(el.dataset.target, 10);
      const suffix = el.dataset.suffix || '';
      let current = 0;
      const step = Math.max(1, Math.round(target / 60));
      const timer = setInterval(() => {
        current += step;
        if(current >= target){ current = target; clearInterval(timer); }
        el.textContent = current.toLocaleString('es-ES') + suffix;
      }, 20);
      statObserver.unobserve(el);
    }
  });
}, {threshold:0.4});
statNums.forEach(el => statObserver.observe(el));

// ---------- Calculadora de agua ----------
const shower = document.getElementById('shower');
const toilet = document.getElementById('toilet');
const wash = document.getElementById('wash');
const showerVal = document.getElementById('showerVal');
const toiletVal = document.getElementById('toiletVal');
const washVal = document.getElementById('washVal');
const litersOut = document.getElementById('litersOut');
const calcNote = document.getElementById('calcNote');

function updateCalc(){
  const showerMin = parseInt(shower.value, 10);
  const toiletUses = parseInt(toilet.value, 10);
  const washLoads = parseInt(wash.value, 10);

  showerVal.textContent = showerMin + ' min';
  toiletVal.textContent = toiletUses;
  washVal.textContent = washLoads;

  // estimaciones promedio: ducha ~9L/min, inodoro ~6L/descarga, lavadora ~50L/carga repartida en 7 días
  const liters = Math.round((showerMin * 9) + (toiletUses * 6) + ((washLoads * 50) / 7));
  litersOut.textContent = liters.toLocaleString('es-ES');

  if(liters < 80){
    calcNote.textContent = 'Tu consumo estimado está por debajo del promedio recomendado (110–150 L/día). ¡Buen uso del agua!';
  } else if(liters <= 180){
    calcNote.textContent = 'Tu consumo estimado está dentro del rango promedio recomendado de 110 a 150 litros por persona al día.';
  } else {
    calcNote.textContent = 'Tu consumo estimado supera el promedio recomendado. Pequeños ajustes pueden marcar una diferencia real.';
  }
}
[shower, toilet, wash].forEach(input => input.addEventListener('input', updateCalc));
updateCalc();

// ---------- Reveal on scroll ----------
const revealEls = document.querySelectorAll('.reveal');
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if(entry.isIntersecting){
      entry.target.classList.add('in');
      revealObserver.unobserve(entry.target);
    }
  });
}, {threshold:0.15});
revealEls.forEach(el => revealObserver.observe(el));