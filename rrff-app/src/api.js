// src/api.js — Cliente HTTP centralizado RRFF Soft v2.1
let BASE = 'http://localhost:8000/api';

if (window.location.hostname.includes('onrender.com')) {
  // Autodescubrimiento del backend basado en la URL del frontend (Blueprint)
  const apiHost = window.location.hostname.replace('rrff-frontend', 'rrff-api');
  BASE = `https://${apiHost}/api`;
} else if (import.meta.env.VITE_API_URL) {
  const cleanUrl = import.meta.env.VITE_API_URL.replace(/\/$/, '');
  BASE = cleanUrl.startsWith('http') ? `${cleanUrl}/api` : `https://${cleanUrl}/api`;
}

export function getToken() {
  return localStorage.getItem('rrff_token') || '';
}

export function getPermisos() {
  try {
    return JSON.parse(localStorage.getItem('rrff_permisos') || '{}');
  } catch { return {}; }
}

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${getToken()}`,
  };
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error de autenticación');
  const data = await res.json();
  // Persistir sesión
  localStorage.setItem('rrff_token', data.access_token);
  localStorage.setItem('rrff_role', data.role);
  localStorage.setItem('rrff_user', data.username);
  localStorage.setItem('rrff_permisos', JSON.stringify(data.permisos || {}));
  return data;
}

// ── S&OP ─────────────────────────────────────────────────────────────────────

export async function fetchSOP() {
  const res = await fetch(`${BASE}/sop/`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando datos S&OP');
  return res.json();
}

export async function fetchTransito(sku) {
  const res = await fetch(`${BASE}/sop/transito/${sku}`, { headers: authHeaders() });
  if (!res.ok) return { ordenes: [] };
  return res.json();
}

export async function fetchObservacion(sku) {
  const res = await fetch(`${BASE}/sop/observacion/${sku}`, { headers: authHeaders() });
  if (!res.ok) return { observacion: '' };
  return res.json();
}

export async function saveObservacion(sku, observacion) {
  const res = await fetch(`${BASE}/sop/observacion/${sku}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ observacion }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error guardando observación');
  return res.json();
}

// ── Upload ────────────────────────────────────────────────────────────────────

export async function uploadFile(endpoint, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload/${endpoint}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error en upload');
  return res.json();
}

export async function uploadTransito(file, nombrePedido, etaFecha) {
  const form = new FormData();
  form.append('file', file);
  form.append('nombre_pedido', nombrePedido || '');
  form.append('eta_fecha', etaFecha || '');
  const res = await fetch(`${BASE}/upload/transito`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error subiendo OC');
  return res.json();
}

export async function reprocess() {
  const res = await fetch(`${BASE}/upload/reprocess`, {
    method: 'POST', headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Error reprocesando');
  return res.json();
}

export async function extractShinyapps() {
  const res = await fetch(`${BASE}/upload/extract`, {
    method: 'POST', headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Error extrayendo datos de Matrix');
  return res.json();
}

// ── Embarques / OCs ───────────────────────────────────────────────────────────

export async function fetchEmbarques() {
  const res = await fetch(`${BASE}/upload/embarques`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando embarques');
  return res.json();
}

export async function marcarAforo(id) {
  const res = await fetch(`${BASE}/upload/embarques/${id}/aforo`, {
    method: 'POST', headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error marcando aforo');
  return res.json();
}

export async function cambiarEta(id, nueva_eta, motivo = '') {
  const res = await fetch(`${BASE}/upload/embarques/${id}/eta`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ nueva_eta, motivo }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error cambiando ETA');
  return res.json();
}

export async function confirmarLlegada(id, fecha_llegada = null) {
  const res = await fetch(`${BASE}/upload/embarques/${id}/llegada`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(fecha_llegada ? { fecha_llegada } : {}),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error confirmando llegada');
  return res.json();
}


export async function marcarAforoOc(nombrePedido) {
  const res = await fetch(`${BASE}/upload/embarques/oc/${encodeURIComponent(nombrePedido)}/aforo`, {
    method: 'POST', headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error marcando aforo OC');
  return res.json();
}

export async function cambiarEtaOc(nombrePedido, nueva_eta, motivo = '') {
  const res = await fetch(`${BASE}/upload/embarques/oc/${encodeURIComponent(nombrePedido)}/eta`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ nueva_eta, motivo }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error cambiando ETA OC');
  return res.json();
}

export async function confirmarLlegadaOc(nombrePedido, fecha_llegada = null) {
  const res = await fetch(`${BASE}/upload/embarques/oc/${encodeURIComponent(nombrePedido)}/llegada`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(fecha_llegada ? { fecha_llegada } : {}),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error confirmando llegada OC');
  return res.json();
}

export async function deleteOc(nombrePedido) {
  const res = await fetch(`${BASE}/upload/embarques/oc/${encodeURIComponent(nombrePedido)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error borrando OC');
  return res.json();
}

// ── Usuarios (admin) ──────────────────────────────────────────────────────────

export async function fetchUsuarios() {
  const res = await fetch(`${BASE}/auth/usuarios`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando usuarios');
  return res.json();
}

export async function createUsuario(data) {
  const res = await fetch(`${BASE}/auth/usuarios`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error creando usuario');
  return res.json();
}

export async function updateUsuario(username, data) {
  const res = await fetch(`${BASE}/auth/usuarios/${username}`, {
    method: 'PUT', headers: authHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error actualizando usuario');
  return res.json();
}

export async function deleteUsuario(username) {
  const res = await fetch(`${BASE}/auth/usuarios/${username}`, {
    method: 'DELETE', headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error eliminando usuario');
  return res.json();
}


// ── Maquila ───────────────────────────────────────────────────────────────────

export async function fetchRecetas() {
  const res = await fetch(`${BASE}/maquila/recetas`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando recetas');
  return res.json();
}

export async function fetchRecetaDetail(id) {
  const res = await fetch(`${BASE}/maquila/recetas/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando detalle de receta');
  return res.json();
}

export async function createReceta(data) {
  const res = await fetch(`${BASE}/maquila/recetas`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error creando receta');
  return res.json();
}

export async function updateReceta(id, data) {
  const res = await fetch(`${BASE}/maquila/recetas/${id}`, {
    method: 'PUT', headers: authHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error editando receta');
  return res.json();
}

export async function toggleReceta(id, activa) {
  const res = await fetch(`${BASE}/maquila/recetas/${id}/estado`, {
    method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ activa }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error cambiando estado');
  return res.json();
}

export async function deleteReceta(id) {
  const res = await fetch(`${BASE}/maquila/recetas/${id}`, {
    method: 'DELETE', headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error eliminando receta');
  return res.json();
}

export async function calcularMaquila(receta_id, cantidad_a_fabricar) {
  const res = await fetch(`${BASE}/maquila/calcular`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify({ receta_id, cantidad_a_fabricar }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error calculando maquila');
  return res.json();
}

// ── Órdenes Maquila ──────────────────────────────────────────────────────────

export async function importarOrdenMaquila(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/maquila/ordenes/importar`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error al importar OC');
  return res.json();
}

export async function guardarOrdenMaquila(data) {
  const res = await fetch(`${BASE}/maquila/ordenes`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error guardando OC');
  return res.json();
}

export async function fetchOrdenesMaquila() {
  const res = await fetch(`${BASE}/maquila/ordenes`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando listado de órdenes');
  return res.json();
}

export async function fetchOrdenMaquilaById(id) {
  const res = await fetch(`${BASE}/maquila/ordenes/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Error cargando detalle de la orden');
  return res.json();
}

export async function recalcularOrdenMaquila(id) {
  const res = await fetch(`${BASE}/maquila/ordenes/${id}/recalcular`, {
    method: 'POST', headers: authHeaders()
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error recalculando OC');
  return res.json();
}

export async function updateOrdenMaquilaState(id, estado_procesamiento, observaciones) {
  const body = {};
  if (estado_procesamiento) body.estado_procesamiento = estado_procesamiento;
  if (observaciones !== undefined) body.observaciones = observaciones;
  
  const res = await fetch(`${BASE}/maquila/ordenes/${id}/estado`, {
    method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Error actualizando OC');
  return res.json();
}


// -- Exportaciones -------------------------------------------------------------

export async function downloadRrffExcel() {
  const res = await fetch(`${BASE}/export/rrff/completo/excel`, {
    headers: { 'Authorization': "Bearer " + getToken() }
  });
  if (!res.ok) throw new Error('No se pudo generar el Excel RRFF. Intenta nuevamente.');
  
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition');
  let filename = 'RRFF_completo.xlsx';
  
  if (disposition && disposition.indexOf('filename=') !== -1) {
    const filenameRegex = /filename[^;=\n]*=((['\x22]).*?\2|[^;\n]*)/;
    const matches = filenameRegex.exec(disposition);
    if (matches != null && matches[1]) {
      filename = matches[1].replace(/['\x22]/g, '');
    }
  }
  return { blob, filename };
}

