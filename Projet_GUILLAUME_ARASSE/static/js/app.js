

/* ══════════════════════════════════════════════════════════
   1. ÉTAT GLOBAL DE L'APPLICATION
══════════════════════════════════════════════════════════ */


let chatContext = {};


let isLoading = false;

let leafletMap = null;


/* ══════════════════════════════════════════════════════════
   2. NAVIGATION 
══════════════════════════════════════════════════════════ */
function showPage(id) {

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

 
  document.getElementById('page-' + id).classList.add('active');

  
  if (id === 'actu') {
    document.getElementById('sb-chatbot').className = 'sb-btn inactive';
    document.getElementById('sb-actu').className    = 'sb-btn active';
  } else {
    document.getElementById('sb-chatbot').className = 'sb-btn active';
    document.getElementById('sb-actu').className    = 'sb-btn inactive';
  }
}


 
function goHome() {
  chatContext = {};

 
  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }

  showPage('home');
  document.getElementById('home-input').value = '';
}

function goActu() {
  showPage('actu');
  loadActualites();
}


/* ══════════════════════════════════════════════════════════
   3. POINT D'ENTRÉE 
══════════════════════════════════════════════════════════ */


function homeSubmit() {
  const value = document.getElementById('home-input').value.trim();
  if (value) startChat(value);
}

function startChat(question) {
  chatContext = {};


  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }

  
  document.getElementById('chat-messages').innerHTML = '';

  showPage('chat');
  pushUser(question);
  callAPI(question);
}


function chatSubmit() {
  if (isLoading) return;

  const input = document.getElementById('chat-input');
  const value = input.value.trim();
  if (!value) return;

  input.value = '';
  pushUser(value);
  callAPI(value);
}


/* ══════════════════════════════════════════════════════════
   4. AFFICHAGE DES MESSAGES
══════════════════════════════════════════════════════════ */


const $msgs = () => document.getElementById('chat-messages');


const scroll = () => {
  const container = $msgs();
  container.scrollTop = container.scrollHeight;
};

function pushUser(text) {
  const row = document.createElement('div');
  row.className = 'msg-row user';

  const bubble = document.createElement('div');
  bubble.className   = 'bubble-user';
  bubble.textContent = text;

  row.appendChild(bubble);
  $msgs().appendChild(row);
  scroll();
}


function pushTyping() {
  const row = document.createElement('div');
  row.className = 'msg-row bot';
  row.id        = 'typing-row';

  row.innerHTML = `
    <div class="bubble-typing">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  `;

  $msgs().appendChild(row);
  scroll();
}


function removeTyping() {
  const el = document.getElementById('typing-row');
  if (el) el.remove();
}

function pushBotText(text) {
  const row = document.createElement('div');
  row.className = 'msg-row bot';

  const bubble = document.createElement('div');
  bubble.className   = 'bubble-bot';
  bubble.textContent = text;

  row.appendChild(bubble);
  $msgs().appendChild(row);
  scroll();

  return bubble;
}

function pushDisambig(introText, choices, ctx) {
  const row  = document.createElement('div');
  row.className = 'msg-row bot';

  const wrap = document.createElement('div');
  wrap.className = 'disambig-wrap';

 
  if (introText) {
    const intro = document.createElement('div');
    intro.className   = 'disambig-intro';
    intro.textContent = introText;
    wrap.appendChild(intro);
  }

 
  const choiceList = document.createElement('div');
  choiceList.className = 'disambig-choices';

  choices.forEach((choice, i) => {
    const btn = document.createElement('button');
    btn.className   = 'disambig-choice-btn';
    btn.textContent = `${i + 1}. ${choice.nom}` + (choice.lignes ? ` — ${choice.lignes}` : '');

   
    btn.onclick = () => {
      chatContext = ctx;
      pushUser(String(i + 1));
      callAPI(String(i + 1));
    };

    choiceList.appendChild(btn);
  });

  wrap.appendChild(choiceList);
  row.appendChild(wrap);
  $msgs().appendChild(row);
  scroll();
}


function goChat() {
  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }
  showPage('chat');
}


/* ══════════════════════════════════════════════════════════
   5. PAGE ITINÉRAIRE DÉDIÉE
══════════════════════════════════════════════════════════ */
function showPageItin(data) {

  showPage('itin');


  const introEl = document.getElementById('itin-intro');
  introEl.textContent = 'Parfait, ne bougez pas, voici les possibilité :';

 
  const stepsEl = document.getElementById('itin-steps');
  stepsEl.innerHTML = '';

  const icons = { 0: '🚊', 1: '🚇', 2: '🚆', 3: '🚌' };

  (data.itineraire || []).forEach(segment => {
    const row = document.createElement('div');
    row.className = 'itin-step-row';


    const pillDep = document.createElement('div');
    pillDep.className   = 'itin-step-pill';
    pillDep.textContent = segment.arret_depart_nom || '?';


    const connector = document.createElement('div');
    connector.className = 'itin-step-connector';

    const transportLabels = { 0: 'arrêts en tramway', 1: 'arrêts en métro', 2: 'arrêts en train', 3: 'arrêts en bus' };
    const transportLabel  = transportLabels[segment.type_transport] || 'arrêts';
    const nbArrets        = segment.nb_arrets || '?';

    const phrase = document.createElement('span');
    phrase.className = 'itin-step-phrase';
    phrase.innerHTML = `${icons[segment.type_transport] || '🚍'} <b>${nbArrets} ${transportLabel}</b> · ligne <b>${segment.code_ligne}</b>`;

    connector.appendChild(phrase);

    const pillArr = document.createElement('div');
    pillArr.className   = 'itin-step-pill';
    pillArr.textContent = segment.arret_arrivee_nom || '?';

    row.appendChild(pillDep);
    row.appendChild(connector);
    row.appendChild(pillArr);
    stepsEl.appendChild(row);
  });

 
  const existingAlert = stepsEl.parentElement.querySelector('.itin-page-alert');
  if (existingAlert) existingAlert.remove();

  if (data.alertes) {
    const alertEl = document.createElement('div');
    alertEl.className   = 'itin-page-alert';
    alertEl.textContent = data.alertes;
    stepsEl.insertAdjacentElement('afterend', alertEl);
  }

 
  setTimeout(() => initMapPage(data), 120);
}

function initMapPage(data) {
  
  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }

  const mapEl = document.getElementById('leaflet-map-page');
  if (!mapEl) return;


  leafletMap = L.map('leaflet-map-page', { zoomControl: true, scrollWheelZoom: false });

  /* Fond de carte OpenStreetMap */
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 18
  }).addTo(leafletMap);

  const segments  = data.itineraire || [];
  const lastIndex = segments.length - 1;

 
  const polyPoints = [];

  segments.forEach(segment => {
    if (segment.arret_depart_coords) {
      polyPoints.push([segment.arret_depart_coords.lat, segment.arret_depart_coords.lng]);
    }
    if (segment.arret_arrivee_coords) {
      polyPoints.push([segment.arret_arrivee_coords.lat, segment.arret_arrivee_coords.lng]);
    }
  });

  if (polyPoints.length < 2) {
    leafletMap.setView([43.6047, 1.4442], 13);
    return;
  }

  L.polyline(polyPoints, { color: '#f0a500', weight: 3, dashArray: '7 7' }).addTo(leafletMap);

  
  const coordsDepart = segments[0] && segments[0].arret_depart_coords;
  if (coordsDepart) {
    L.circleMarker([coordsDepart.lat, coordsDepart.lng], {
      color: '#2f9e44', fillColor: '#2f9e44', fillOpacity: 1, radius: 9
    })
    .bindTooltip(`🟢 Départ : ${data.depart || segments[0].arret_depart_nom || 'Départ'}`,
                 { permanent: false })
    .addTo(leafletMap);
  }

  
  segments.forEach((segment, index) => {
    if (index === lastIndex) return;

    const coords = segment.arret_arrivee_coords;
    if (!coords) return;

    L.circleMarker([coords.lat, coords.lng], {
      color: '#f0a500', fillColor: '#ffffff', fillOpacity: 1,
      weight: 2.5, radius: 7
    })
    .bindTooltip(
      `🔄 Correspondance : ${segment.arret_arrivee_nom || 'Changement de ligne'}`
      + `<br><small>${segment.code_ligne} → ${segments[index + 1].code_ligne}</small>`,
      { permanent: false }
    )
    .addTo(leafletMap);
  });

  
  const coordsArrivee = segments[lastIndex] && segments[lastIndex].arret_arrivee_coords;
  if (coordsArrivee) {
    L.circleMarker([coordsArrivee.lat, coordsArrivee.lng], {
      color: '#e53e3e', fillColor: '#e53e3e', fillOpacity: 1, radius: 9
    })
    .bindTooltip(`🔴 Arrivée : ${data.arrivee || segments[lastIndex].arret_arrivee_nom || 'Arrivée'}`,
                 { permanent: false })
    .addTo(leafletMap);
  }

 
  leafletMap.fitBounds(L.latLngBounds(polyPoints), { padding: [36, 36] });
}


/* ══════════════════════════════════════════════════════════
   5. COMMUNICATION AVEC L'API BACKEND
══════════════════════════════════════════════════════════ */

/**
 * @param {string} message 
 */
async function callAPI(message) {
  isLoading = true;


  const sendBtn = document.getElementById('chat-send-btn');
  if (sendBtn) sendBtn.disabled = true;

  pushTyping();

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, context: chatContext })
    });

    const data = await response.json();
    removeTyping();

    if (!data.success) {
      pushBotText('❌ Erreur serveur.');
      return;
    }

    if (data.type === 'disambiguation') {
 
      chatContext = data.context || {};
      const choices = (data.context && data.context.choix_possibles) || [];
      const intro   = (data.response || '').split('\n')[0];
      pushDisambig(intro, choices, data.context);

    } else if (data.type === 'itineraire' && data.itineraire) {
  
      chatContext = {};
      showPageItin(data);

    } else {

      chatContext = {};
      const bubble = pushBotText(data.response || '(pas de réponse)');

      if (data.alertes) {
        const alertEl = document.createElement('div');
        alertEl.className   = 'alert-strip';
        alertEl.textContent = data.alertes;
        bubble.parentElement.appendChild(alertEl);
      }
    }

  } catch (error) {
    removeTyping();
    pushBotText('❌ Serveur inaccessible.');
    console.error('Erreur API :', error);
  } finally {
   
    isLoading = false;
    if (sendBtn) sendBtn.disabled = false;
  }
}


/* ══════════════════════════════════════════════════════════
   6. PAGE ACTUALITÉS
══════════════════════════════════════════════════════════ */

/*Affiche un skeleton loader pendant le chargement.
 */
async function loadActualites() {
  const body = document.getElementById('actu-body');


  body.innerHTML = `
    <div class="actu-card">
      <div class="skel" style="width:38%;height:10px"></div>
      <div class="skel" style="width:92%"></div>
      <div class="skel" style="width:76%"></div>
      <div class="skel" style="width:60%"></div>
    </div>
  `;

  try {

    const [resumeRes, actuRes] = await Promise.all([
      fetch('/api/actualites/resume'),
      fetch('/api/actualites')
    ]);

    const resumeData = await resumeRes.json();
    const actuData   = await actuRes.json();
    let html = '';

    /* ── Bloc résumé IA ── */
    if (resumeData.success) {
      html += `
        <div class="actu-card">
          <div class="label">Résumé — ${resumeData.nb_actus || 0} actualité(s)</div>
          <div class="resume" style="font-size:14px;color:#333;line-height:1.6">
            ${esc(resumeData.resume || '')}
          </div>
      `;

      /* Points clés extraits par l'IA */
      if (resumeData.points_cles && resumeData.points_cles.length) {
        html += `<ul class="point-list">`;
        resumeData.points_cles.forEach(point => {
          html += `<li>${esc(point)}</li>`;
        });
        html += `</ul>`;
      }

      /* Alertes signalées dans le résumé */
      if (resumeData.alertes && resumeData.alertes.length) {
        resumeData.alertes.forEach(alerte => {
          html += `
            <div class="alert-strip" style="margin-top:10px;border-radius:6px">
              🚧 ${esc(alerte)}
            </div>
          `;
        });
      }

      html += `</div>`;
    }

    if (actuData.success && actuData.actualites) {
  
      const categoryIcons = {
        travaux       : '🚧',
        perturbation  : '⚠️',
        evenement     : '🎉',
        info_generale : 'ℹ️'
      };

      actuData.actualites.forEach(actu => {
        const icon = categoryIcons[actu.categorie] || '📰';
        html += `
          <div class="actu-card">
            <div class="label">${icon} ${esc(actu.categorie || '')}</div>
            <div class="titre">${esc(actu.titre || '')}</div>
            <div class="resume">${esc(actu.resume || '')}</div>
          </div>
        `;
      });
    }

    body.innerHTML = html || '<p style="color:#888;font-size:14px">Aucune actualité.</p>';

  } catch (error) {
    body.innerHTML = '<p style="color:#888;font-size:14px">❌ Chargement impossible.</p>';
  }
}

function esc(s) {
  return String(s)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;');
}



showPage('home');