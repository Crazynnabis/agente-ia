"use strict";

const POLLING_MS = 5000;
const LIMITE = 10;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function formatearFecha(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function fechaRelativa(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  const diff = Math.round((Date.now() - d.getTime()) / 1000);
  if (diff < 0) return "ahora";
  if (diff < 60) return `hace ${diff} s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return `hace ${Math.floor(diff / 86400)} d`;
}

function escapar(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function fetchJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

function renderEstado(card, info) {
  const estado = info.estado || "desconocido";
  const badge = card.querySelector('[data-campo="estado"]');
  badge.textContent = estado;
  badge.className = "estado-badge estado-" + estado;

  card.querySelector('[data-campo="ultima_tarea"]').textContent =
    info.ultima_tarea || "—";

  const inicio = info.ultimo_ciclo_inicio;
  const fin = info.ultimo_ciclo_fin;
  let cicloTxt = "—";
  if (fin) {
    cicloTxt = `${fechaRelativa(fin)} · ${formatearFecha(fin)}`;
  } else if (inicio) {
    cicloTxt = `iniciado ${fechaRelativa(inicio)}`;
  }
  card.querySelector('[data-campo="ultimo_ciclo"]').textContent = cicloTxt;

  card.querySelector('[data-campo="ciclos"]').textContent =
    `${info.ciclos_completados ?? 0} / ${info.ciclos_con_error ?? 0}`;

  const errEl = card.querySelector(".campo-error");
  if (info.ultimo_error) {
    errEl.classList.remove("oculto");
    errEl.querySelector('[data-campo="ultimo_error"]').textContent =
      info.ultimo_error;
  } else {
    errEl.classList.add("oculto");
  }
}

function renderAgentes(data) {
  const agentes = data.agentes || [];
  const porNombre = Object.fromEntries(agentes.map((a) => [a.nombre, a]));
  $$(".agente-card").forEach((card) => {
    const nombre = card.dataset.agente;
    const info = porNombre[nombre];
    if (info) renderEstado(card, info);
  });
}

function renderMetricas(m) {
  $("#m-activos").textContent = m.agentes_activos ?? "—";
  $("#m-activos-sub").textContent = `de ${m.agentes_total ?? 3}`;
  $("#m-ciclos").textContent = m.ciclos_completados ?? "—";
  $("#m-ciclos-sub").textContent = `tasa éxito ${m.tasa_exito_pct ?? 0}%`;
  $("#m-total").textContent = m.total_general ?? "—";
  const desglose = [
    `${m.total_inversiones ?? 0} inv.`,
    `${m.total_contenido ?? 0} pub.`,
    `${m.total_noticias ?? 0} viajes`,
  ].join(" · ");
  $("#m-total-sub").textContent = desglose;
  $("#m-errores").textContent = m.ciclos_con_error ?? "—";
}

function chipRiesgo(senal) {
  if (!senal) return "";
  const s = senal.toLowerCase();
  let cls = "chip";
  if (s.includes("sobrecomprado") || s.includes("alta")) cls += " chip-warn";
  else if (s.includes("sobrevendido") || s.includes("baja")) cls += " chip-err";
  else if (s.includes("neutral")) cls += " chip-ok";
  return `<span class="${cls}">${escapar(senal)}</span>`;
}

function crearItem(html) {
  const wrap = document.createElement("div");
  wrap.className = "item";
  wrap.innerHTML = html;
  const cuerpo = wrap.querySelector(".item-cuerpo");
  const toggle = wrap.querySelector(".item-toggle");
  if (cuerpo && toggle) {
    toggle.addEventListener("click", () => {
      cuerpo.classList.toggle("expandido");
      toggle.textContent = cuerpo.classList.contains("expandido")
        ? "ver menos"
        : "ver más";
    });
  }
  return wrap;
}

function renderFinanciero(items) {
  const cont = $("#lista-financiero");
  $("#cnt-fin").textContent = items.length;
  if (!items.length) {
    cont.innerHTML = '<p class="placeholder">Sin análisis aún</p>';
    return;
  }
  cont.innerHTML = "";
  for (const it of items) {
    const rend = it.rendimiento_pct;
    const vol = it.volatilidad_pct;
    const rsi = it.rsi;
    const rendChip = rend !== null && rend !== undefined
      ? `<span class="chip ${rend >= 0 ? "chip-ok" : "chip-err"}">rend ${rend > 0 ? "+" : ""}${rend}%</span>`
      : "";
    const volChip = vol !== null && vol !== undefined
      ? `<span class="chip">vol ${vol}%</span>`
      : "";
    const rsiChip = rsi !== null && rsi !== undefined
      ? `<span class="chip">RSI ${rsi}</span>`
      : "";
    const fuenteChip = it.fuente
      ? `<span class="chip">${escapar(it.fuente)}</span>`
      : "";
    const html = `
      <div class="item-cab">
        <span class="item-titulo">${escapar(it.simbolo || "?")}</span>
        <span class="item-fecha">${fechaRelativa(it.created_at)}</span>
      </div>
      <div class="item-meta">
        ${rendChip}${volChip}${rsiChip}${chipRiesgo(it.senal)}${fuenteChip}
      </div>
      <div class="item-cuerpo">${escapar(it.analisis || "Sin análisis")}</div>
      <button class="item-toggle">ver más</button>
    `;
    cont.appendChild(crearItem(html));
  }
}

function renderContenido(items) {
  const cont = $("#lista-contenido");
  $("#cnt-cont").textContent = items.length;
  if (!items.length) {
    cont.innerHTML = '<p class="placeholder">Sin publicaciones aún</p>';
    return;
  }
  cont.innerHTML = "";
  for (const it of items) {
    const titulo = it.tema || `${it.plataforma || "?"} / ${it.categoria || "?"}`;
    const platChip = it.plataforma
      ? `<span class="chip">${escapar(it.plataforma)}</span>`
      : "";
    const catChip = it.categoria
      ? `<span class="chip">${escapar(it.categoria)}</span>`
      : "";
    const formChip = it.formato
      ? `<span class="chip">${escapar(it.formato)}</span>`
      : "";
    const alcChip = it.alcance_estimado
      ? `<span class="chip">alcance ${it.alcance_estimado.toLocaleString()}</span>`
      : "";
    const engChip = it.engagement_pct
      ? `<span class="chip chip-ok">eng ${it.engagement_pct}%</span>`
      : "";
    const html = `
      <div class="item-cab">
        <span class="item-titulo">${escapar(titulo)}</span>
        <span class="item-fecha">${fechaRelativa(it.created_at)}</span>
      </div>
      <div class="item-meta">
        ${platChip}${catChip}${formChip}${alcChip}${engChip}
      </div>
      <div class="item-cuerpo">${escapar(it.brief || "Sin brief")}</div>
      <button class="item-toggle">ver más</button>
    `;
    cont.appendChild(crearItem(html));
  }
}

function renderTuristico(items) {
  const cont = $("#lista-turistico");
  $("#cnt-tur").textContent = items.length;
  if (!items.length) {
    cont.innerHTML = '<p class="placeholder">Sin itinerarios aún</p>';
    return;
  }
  cont.innerHTML = "";
  for (const it of items) {
    const titulo = it.destino || "Destino desconocido";
    const presChip = it.presupuesto
      ? `<span class="chip">${escapar(it.presupuesto)}</span>`
      : "";
    const diasChip = it.dias
      ? `<span class="chip">${it.dias} días</span>`
      : "";
    const costoChip = it.costo_diario_usd
      ? `<span class="chip chip-warn">$${it.costo_diario_usd}/día</span>`
      : "";
    const epocaChip = it.mejor_epoca
      ? `<span class="chip">${escapar(it.mejor_epoca)}</span>`
      : "";
    const html = `
      <div class="item-cab">
        <span class="item-titulo">${escapar(titulo)}</span>
        <span class="item-fecha">${fechaRelativa(it.created_at)}</span>
      </div>
      <div class="item-meta">
        ${presChip}${diasChip}${costoChip}${epocaChip}
      </div>
      <div class="item-cuerpo">${escapar(it.recomendacion || "Sin recomendación")}</div>
      <button class="item-toggle">ver más</button>
    `;
    cont.appendChild(crearItem(html));
  }
}

function setConexion(ok, mensaje) {
  const el = $("#conexion");
  if (ok) {
    el.textContent = "conectado";
    el.className = "badge badge-ok";
  } else {
    el.textContent = mensaje || "sin conexión";
    el.className = "badge badge-err";
  }
}

async function actualizarTodo() {
  try {
    const [agentes, metricas, fin, cont, tur] = await Promise.all([
      fetchJSON("/api/agentes"),
      fetchJSON("/api/metricas"),
      fetchJSON(`/api/financiero/recientes?limite=${LIMITE}`),
      fetchJSON(`/api/contenido/recientes?limite=${LIMITE}`),
      fetchJSON(`/api/turistico/recientes?limite=${LIMITE}`),
    ]);
    renderAgentes(agentes);
    renderMetricas(metricas);
    renderFinanciero(fin.items || []);
    renderContenido(cont.items || []);
    renderTuristico(tur.items || []);
    setConexion(true);
    $("#ultima-actualizacion").textContent =
      "actualizado " + new Date().toLocaleTimeString("es-ES");
  } catch (e) {
    console.error(e);
    setConexion(false, "error de red");
  }
}

actualizarTodo();
setInterval(actualizarTodo, POLLING_MS);
