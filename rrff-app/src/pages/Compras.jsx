import React, { useState, useEffect } from 'react';
import { fetchSOP } from '../api';
import * as XLSX from 'xlsx';
import SkuDetailModal from '../components/SkuDetailModal';

// Helper: Obtener número de semana (ISO)
function getWeekNumber(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return { year: date.getUTCFullYear(), week: weekNo };
}

// Helper: Obtener rango de fechas de la semana (Lunes a Domingo)
function getWeekDateRange(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diffToMonday = date.getDate() - day + (day === 0 ? -6 : 1);
  const start = new Date(date.setDate(diffToMonday));
  const end = new Date(start.getTime());
  end.setDate(end.getDate() + 6);
  
  const getDayMonth = (dateObj) => {
    const months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    return `${dateObj.getDate()} de ${months[dateObj.getMonth()]}`;
  };
  
  return `semana del ${getDayMonth(start)} al ${getDayMonth(end)}`;
}

export default function Compras() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [filterAlert, setFilterAlert] = useState('ALL');
  const [filterTransit, setFilterTransit] = useState('ALL');
  const [filterComparacion, setFilterComparacion] = useState('ALL');
  const [selectedSku, setSelectedSku] = useState(null);

  const LEAD_TIME_DAYS = 60; // Días de tránsito (margen)

  useEffect(() => {
    async function loadData() {
      try {
        const sopData = await fetchSOP();
        setData(sopData.data || []); // El backend retorna { data: [...], total: N }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  // ── APLICAR FILTROS GLOBALES ──
  let filteredData = Array.isArray(data) ? data : [];
  if (filterAlert !== 'ALL') {
    filteredData = filteredData.filter(s => s.nivel_alerta === filterAlert);
  }
  if (filterTransit === 'WITH') {
    filteredData = filteredData.filter(s => (s.cantidad_transito || 0) > 0);
  } else if (filterTransit === 'WITHOUT') {
    filteredData = filteredData.filter(s => (s.cantidad_transito || 0) === 0);
  }
  if (filterComparacion !== 'ALL') {
    if (filterComparacion === '>20%') {
      filteredData = filteredData.filter(s => (s.diferencia_porcentual_dinamica_legacy || 0) > 0.2);
    } else if (filterComparacion === 'SOLO_LEGACY') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'Legacy compra / Dinamica no compra');
    } else if (filterComparacion === 'SOLO_DINAMICA') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'Dinamica compra / Legacy no compra');
    } else if (filterComparacion === 'AMBAS') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'Ambas recomiendan comprar' || s.recomendacion_coincide === 'Ambas compran con diferencia superior al 20%');
    } else if (filterComparacion === 'SIN_ANALISIS') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'No comparable por falta de datos' || !s.recomendacion_coincide);
    }
  }

  // ── 1. PROCESAR SUGERENCIAS AUTOMÁTICAS ──
  const sugList = filteredData.filter(s => (s.sugerencia_compra_inmediata_uds || 0) > 0 || (s.sugerencia_compra_dinamica || 0) > 0);
  
  // ── PROCESAR REVISIONES (EXCEPCIONES) ──
  const revisionList = filteredData.filter(s => s.requiere_revision);
  
  const groupedSug = {};
  sugList.forEach(s => {
    // duracion_fisica_solo son MESES. 1 mes ~= 30.4 días.
    const daysToStockout = (s.duracion_fisica_solo || 0) * 30.4;
    const stockoutDate = new Date();
    stockoutDate.setDate(stockoutDate.getDate() + daysToStockout);
    
    const idealDate = new Date(stockoutDate);
    idealDate.setDate(idealDate.getDate() - LEAD_TIME_DAYS);
    
    s.idealDateObj = idealDate;
    
    const wk = getWeekNumber(idealDate);
    // Si la fecha ideal ya pasó, la agrupamos como "URGENTE / ATRASADA"
    const hoy = new Date();
    let groupKey = '';
    let groupLabel = '';
    
    if (idealDate < hoy) {
      groupKey = '0000-URGENTE';
      groupLabel = '🚨 PEDIDOS ATRASADOS (Emitir YA)';
    } else {
      groupKey = `${wk.year}-W${wk.week.toString().padStart(2, '0')}`;
      groupLabel = `📅 ${getWeekDateRange(idealDate)}`;
    }

    if (!groupedSug[groupKey]) groupedSug[groupKey] = { label: groupLabel, items: [] };
    groupedSug[groupKey].items.push(s);
  });

  // ── 2. PROCESAR OBSERVACIONES HUMANAS ──
  // Regex para atrapar "comprar", "compra" + [palabras opcionales] + NUMERO
  const regexNum = /compr(?:ar|a)\s*(?:unas?\s+|unos?\s+|cajas?\s+|uds?\s*)?(\d+)/i;
  const obsList = [];
  
  (Array.isArray(data) ? data : []).forEach(s => {
    if (s.observacion && s.observacion.toLowerCase().includes('compra')) {
      const match = s.observacion.match(regexNum);
      const extraido = match ? match[1] : '';
      obsList.push({ ...s, extraido });
    }
  });

  // Ordenar grupos de sugerencias cronológicamente
  const sortedGroupKeys = Object.keys(groupedSug).sort();

    const handleExportExcel = (onlyUrgentes = false) => {
    // Hoja 1: Sugerencias Automáticas
    const wsSugData = [];
    const keysToExport = onlyUrgentes ? sortedGroupKeys.filter(k => k === '0000-URGENTE') : sortedGroupKeys;
    
    keysToExport.forEach(key => {
      const group = groupedSug[key];
      group.items.forEach(s => {
        const stockoutDate = s.fecha_estimada_quiebre ? new Date(s.fecha_estimada_quiebre).toLocaleDateString('es-CL') : '—';
        const etaStr = s.eta_proxima ? new Date(s.eta_proxima).toLocaleDateString('es-CL') : '—';
        const familiaStr = s.familia_maquila && s.familia_maquila.length > 0
          ? ' | Familia Maquila: ' + s.familia_maquila.map(c => `${c.sku} (Stock: ${c.stock_act}, Venta/mes: ${c.ritmo_mensual})`).join(', ')
          : '';
        
        wsSugData.push({
          'Grupo': group.label,
          'SKU': s.sku,
          'Código Femaco': s.codigo_femaco || '',
          'Nombre de Producto': s.nombre_producto,
          'Stock Físico': s.stock_act || 0,
          'Ventas (4 sem)': s.total_4_sem_verificado || 0,
          'Sugerido (Uds)': s.sugerencia_compra_inmediata_uds || 0
        });
      });
    });
    
    // Hoja 2: Observaciones Manuales
    const wsObsData = obsList.map(s => {
      const familiaStr = s.familia_maquila && s.familia_maquila.length > 0
          ? ' | Familia Maquila: ' + s.familia_maquila.map(c => `${c.sku} (Stock: ${c.stock_act}, Venta/mes: ${c.ritmo_mensual})`).join(', ')
          : '';
      return {
        'SKU': s.sku,
        'Código Femaco': s.codigo_femaco || '',
        'Nombre de Producto': s.nombre_producto,
        'U/E': s.ump || '',
        'Stock Físico': s.stock_act || 0,
        'Ventas (4 sem)': s.total_4_sem_verificado || 0,
        'Observación Original': (s.observacion || '') + familiaStr,
        'Extracción (Uds)': s.extraido || '?'
      };
    });

    // Hoja 3: Resumen
    const wsResumenData = [];
    keysToExport.forEach(key => {
      const group = groupedSug[key];
      group.items.forEach(s => {
        const sugerido = s.sugerencia_compra_inmediata_uds || 0;
        const dinamico = s.sugerencia_compra_dinamica || 0;
        const diferencia = dinamico - sugerido;
        wsResumenData.push({
          'SKU': s.sku,
          'Código Femaco': s.codigo_femaco || '',
          'Grupo': group.label,
          'Stock Físico': s.stock_act || 0,
          'Sugerido (Uds)': sugerido,
          'Sugerido Dinámico (Uds)': dinamico,
          'Diferencia (Dinámico - Sugerido)': diferencia
        });
      });
    });

    const wb = XLSX.utils.book_new();
    
    if (wsSugData.length > 0) {
      const wsSug = XLSX.utils.json_to_sheet(wsSugData);
      XLSX.utils.book_append_sheet(wb, wsSug, 'Sugerencias Automáticas');
    }
    
    if (wsObsData.length > 0) {
      const wsObs = XLSX.utils.json_to_sheet(wsObsData);
      XLSX.utils.book_append_sheet(wb, wsObs, 'Notas Manuales');
    }

    if (wsResumenData.length > 0) {
      const wsResumen = XLSX.utils.json_to_sheet(wsResumenData);
      XLSX.utils.book_append_sheet(wb, wsResumen, 'Resumen');
    }

    if (wsSugData.length === 0 && wsObsData.length === 0) {
      alert("No hay datos para exportar.");
      return;
    }

    XLSX.writeFile(wb, 'Plan_de_Compras.xlsx');
  };

  return (
    <div className="content-area">
      <main className="main-panel" style={{ maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>🛒 Plan de Compras</h1>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ fontSize: '0.85rem', color: '#666', background: '#fff', padding: '6px 12px', borderRadius: 20, border: '1px solid #ddd', display: 'flex', flexDirection: 'column' }}>
              <span>⏱ Lead time estándar de reposición: <b>5 meses</b></span>
              <span style={{ fontSize: '0.75rem', fontStyle: 'italic', marginTop: '2px' }}>Valor operativo provisional. Las ETA reales tienen prioridad cuando están disponibles.</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button 
                onClick={() => handleExportExcel(false)}
                style={{ padding: '8px 16px', background: '#1d6b3e', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                📥 Excel (Todo)
              </button>
              <button 
                onClick={() => handleExportExcel(true)}
                style={{ padding: '8px 16px', background: '#d32f2f', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                📥 Excel (Urgentes)
              </button>
            </div>
          </div>
        </div>

        {/* ── ADVERTENCIA DE REGLAS ── */}
        <div style={{ backgroundColor: '#fff3cd', border: '1px solid #ffeeba', color: '#856404', padding: '15px 20px', borderRadius: '8px', marginBottom: '25px', fontSize: '0.9rem', lineHeight: '1.5' }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            ⚠️ Precaución: Reglas de Cálculo del Motor
          </h4>
          <p style={{ margin: '0 0 8px 0' }}>Estas sugerencias de compra se generan de forma automática basándose en las siguientes reglas:</p>
          <ul style={{ margin: 0, paddingLeft: '20px' }}>
            <li><b>Target de Cobertura:</b> Las sugerencias buscan cubrir <b>5 meses</b> de inventario por defecto (Configurable globalmente, por SKU o categoría).</li>
            <li><b>Lead Time (Tránsito):</b> Se asume que los pedidos tardan <b>{LEAD_TIME_DAYS} días</b> en llegar.</li>
            <li><b>Ritmo de Venta:</b> El consumo mensual estimado se calcula en base al pico máximo histórico mensual del SKU.</li>
            <li><b>Filtro de Tránsito:</b> Si un SKU tiene al menos 1 unidad ya en tránsito (estado Morado), <b>NO</b> se sugiere volver a comprar.</li>
            <li><b>Disparador (Trigger):</b> Solo se sugiere comprar cuando el stock proyectado cae por debajo de 4 meses (Amarillo, Naranja o Rojo).</li>
          </ul>
        </div>

        {loading ? (
          <div className="loader-wrap"><div className="spinner" /></div>
        ) : error ? (
          <div className="upload-result err">❌ {error}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 30 }}>
            
            {/* ── FILTROS ── */}
            <div style={{ display: 'flex', gap: 15, background: '#fff', padding: 15, borderRadius: 8, border: '1px solid #ddd' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Nivel Alerta</label>
                <select value={filterAlert} onChange={e => setFilterAlert(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}>
                  <option value="ALL">Todas</option>
                  <option value="ROJO">🔴 Rojo</option>
                  <option value="NARANJA">🟠 Naranja</option>
                  <option value="AMARILLO">🟡 Amarillo</option>
                  <option value="MORADO">🟣 Morado</option>
                  <option value="VERDE">🟢 Verde</option>
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Tránsito</label>
                <select value={filterTransit} onChange={e => setFilterTransit(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}>
                  <option value="ALL">Todos</option>
                  <option value="WITH">Con Tránsito (&gt;0)</option>
                  <option value="WITHOUT">Sin Tránsito (0)</option>
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Comparación Modelos</label>
                <select value={filterComparacion} onChange={e => setFilterComparacion(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc', background: '#e3f2fd' }}>
                  <option value="ALL">Todas</option>
                  <option value=">20%">Diferencia &gt;20%</option>
                  <option value="AMBAS">Ambos sugieren comprar</option>
                  <option value="SOLO_LEGACY">Solo Oficial (Legacy) compra</option>
                  <option value="SOLO_DINAMICA">Solo Dinámico compra</option>
                  <option value="SIN_ANALISIS">Sin análisis dinámico</option>
                </select>
              </div>
            </div>

            {/* ── SECCIÓN 1: SUGERENCIAS AUTOMÁTICAS ── */}
            <section>
              <h2 style={{ fontSize: '1.2rem', color: '#1d6b3e', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                🤖 Sugerencias del Motor
              </h2>
              
              {sortedGroupKeys.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', background: '#f9f9f9', borderRadius: 8, color: '#888' }}>
                  No hay sugerencias de compra automáticas activas en este momento.
                </div>
              ) : (
                sortedGroupKeys.map(key => {
                  const group = groupedSug[key];
                  // Ordenar ítems dentro del grupo por categoría, luego por fecha ideal
                  group.items.sort((a, b) => {
                    const catA = a.categoria || '';
                    const catB = b.categoria || '';
                    if (catA < catB) return -1;
                    if (catA > catB) return 1;
                    return a.idealDateObj - b.idealDateObj;
                  });
                  
                  const isUrgente = key === '0000-URGENTE';
                  
                  return (
                    <details key={key} open={isUrgente} style={{ marginBottom: 12, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: '#fff' }}>
                      <summary style={{ padding: '12px 16px', background: isUrgente ? '#FFEBEC' : '#f9f9f9', cursor: 'pointer', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ color: isUrgente ? '#E63946' : '#333' }}>
                          {group.label} 
                          <span style={{ marginLeft: 16, fontSize: '0.85rem', fontWeight: 'normal', color: 'var(--gray)' }}>
                            ({group.items.length} SKUs sugeridos)
                          </span>
                        </div>
                      </summary>
                      <div style={{ overflowX: 'auto', borderTop: '1px solid var(--border)' }}>
                        <table className="preview-table" style={{ margin: 0, border: 'none', borderRadius: 0 }}>
                          <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Categoría</th>
                              <th>Estado</th>
                              <th>Cobertura</th>
                              <th>Tránsito</th>
                              <th style={{ background: '#e8f5e9', borderLeft: '2px solid #a5d6a7', color: '#1b5e20' }}>Legacy (Oficial)</th>
                              <th style={{ background: '#e3f2fd', color: '#0d47a1' }}>Dinámico (Exp.)</th>
                              <th style={{ background: '#f5f5f5', color: '#333' }}>Comparativa</th>
                              <th>Detalle</th>
                            </tr>
                          </thead>
                          <tbody>
                            {group.items.map(s => {
                              const stockoutDate = new Date(s.idealDateObj);
                              stockoutDate.setDate(stockoutDate.getDate() + LEAD_TIME_DAYS);
                              
                              return (
                                <tr key={s.sku}>
                                  <td>
                                    <div><b>{s.sku}</b></div>
                                    <div style={{ fontSize: '0.75rem', color: '#666', maxWidth: 180, whiteSpace: 'normal' }}>{s.nombre_producto}</div>
                                  </td>
                                  <td style={{ fontSize: '0.8rem', maxWidth: 120 }}>{s.categoria || '—'}</td>
                                  <td>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                      <span style={{ 
                                        padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold', width: 'fit-content',
                                        background: s.nivel_alerta === 'ROJO' ? '#ffebee' : s.nivel_alerta === 'NARANJA' ? '#fff3e0' : s.nivel_alerta === 'AMARILLO' ? '#fffde7' : s.nivel_alerta === 'MORADO' ? '#f3e5f5' : '#e8f5e9',
                                        color: s.nivel_alerta === 'ROJO' ? '#c62828' : s.nivel_alerta === 'NARANJA' ? '#ef6c00' : s.nivel_alerta === 'AMARILLO' ? '#f57f17' : s.nivel_alerta === 'MORADO' ? '#6a1b9a' : '#2e7d32'
                                      }}>
                                        {s.nivel_alerta}
                                      </span>
                                      {s.excepciones && s.excepciones.length > 0 && s.excepciones.map((ex, i) => (
                                        <span key={ex} title={s.explicacion_excepcion?.[i] || ex} style={{ background: '#FFF3EB', color: '#b35f1a', padding: '2px 6px', borderRadius: 4, fontSize: '0.65rem', border: '1px solid #F4864A', cursor: 'help', width: 'fit-content' }}>
                                          {ex.replace(/_/g, ' ')}
                                        </span>
                                      ))}
                                    </div>
                                  </td>
                                  <td>{Number(s.duracion_fisica_solo || 0).toFixed(1)} m</td>
                                  <td>{Number(s.cantidad_transito || 0).toLocaleString('es-CL')}</td>
                                  
                                  <td style={{ fontWeight: 'bold', background: '#E7F7ED', color: '#1d6b3e', borderLeft: '2px solid #a5d6a7' }}>
                                    {Number(s.sugerencia_compra_inmediata_uds || 0).toLocaleString('es-CL')}
                                  </td>
                                  
                                  <td style={{ background: '#e3f2fd', color: '#0d47a1', fontSize: '0.8rem', verticalAlign: 'top' }}>
                                    <div style={{ marginBottom: '4px' }}>
                                      <span style={{ color: '#555' }}>Compra dinámica:</span>{' '}
                                      <b>{s.sugerencia_compra_dinamica != null ? Number(s.sugerencia_compra_dinamica).toLocaleString('es-CL') : 'No disponible'}</b>
                                    </div>
                                    <div style={{ marginBottom: '4px' }}>
                                      <span style={{ color: '#555' }}>Cobertura:</span>{' '}
                                      <b>{s.cobertura_proyectada_meses != null ? `${Number(s.cobertura_proyectada_meses).toFixed(1)} meses` : 'No disponible'}</b>
                                    </div>
                                    <div>
                                      <span style={{ color: '#555' }}>Estado:</span>{' '}
                                      {s.estado_alerta ? (
                                        <span style={{
                                          padding: '2px 6px',
                                          borderRadius: '4px',
                                          display: 'inline-block',
                                          marginTop: '2px',
                                          fontWeight: 'bold',
                                          fontSize: '0.75rem'
                                        }} className={`dynamic-status-${s.estado_alerta.toLowerCase().replace(/ /g, '-')}`}>
                                          {s.estado_alerta}
                                        </span>
                                      ) : (
                                        <span style={{
                                          padding: '2px 6px',
                                          borderRadius: '4px',
                                          display: 'inline-block',
                                          marginTop: '2px',
                                          fontWeight: 'bold',
                                          fontSize: '0.75rem'
                                        }} className="dynamic-status-sin-analisis">
                                          Sin análisis
                                        </span>
                                      )}
                                    </div>
                                  </td>
                                  
                                  <td style={{ background: '#f5f5f5', fontSize: '0.8rem' }}>
                                    {s.recomendacion_coincide === 'No comparable por falta de datos' || !s.recomendacion_coincide ? (
                                      <span style={{ color: '#888' }}>Sin Análisis</span>
                                    ) : (
                                      <div>
                                        <div style={{ fontWeight: 'bold', color: (s.diferencia_porcentual_dinamica_legacy || 0) > 0.2 ? '#d32f2f' : '#2e7d32' }}>
                                          Dif: {s.diferencia_compra_dinamica_legacy > 0 ? '+' : ''}{Number(s.diferencia_compra_dinamica_legacy || 0).toLocaleString('es-CL')} 
                                          ({Number((s.diferencia_porcentual_dinamica_legacy || 0) * 100).toFixed(0)}%)
                                        </div>
                                        <div style={{ color: '#555', fontSize: '0.75rem', marginTop: 2 }}>{s.recomendacion_coincide}</div>
                                      </div>
                                    )}
                                  </td>
                                  
                                  <td>
                                    <button onClick={() => setSelectedSku(s)} style={{ padding: '4px 8px', background: '#2196f3', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.8rem' }}>
                                      Ver Detalle
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  );
                })
              )}
            </section>

            <hr style={{ border: 'none', borderTop: '2px dashed #eee' }} />

            {/* ── SECCIÓN 2: REQUIERE REVISIÓN ── */}
            <section>
              <h2 style={{ fontSize: '1.2rem', color: '#b35f1a', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                ⚠️ Requiere Revisión (Excepciones)
              </h2>
              
              {revisionList.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', background: '#f9f9f9', borderRadius: 8, color: '#888' }}>
                  No hay productos que requieran revisión actualmente.
                </div>
              ) : (
                <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <table className="preview-table" style={{ margin: 0, border: 'none' }}>
                          <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Nombre de Producto</th>
                              <th>Categoría</th>
                              <th>Stock Físico</th>
                              <th>Excepciones</th>
                              <th>Estado Compra</th>
                            </tr>
                          </thead>
                    <tbody>
                      {revisionList.map(s => (
                        <tr key={s.sku}>
                          <td><b>{s.sku}</b></td>
                          <td style={{ fontSize: '0.8rem', maxWidth: 200 }}>{s.nombre_producto}</td>
                          <td>{s.categoria || '—'}</td>
                          <td>{Number(s.stock_act || 0).toLocaleString('es-CL')}</td>
                          <td>
                            {s.excepciones && s.excepciones.length > 0 && (
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                {s.excepciones.map((ex, i) => (
                                  <span key={ex} title={s.explicacion_excepcion?.[i] || ex} style={{ background: '#FFF3EB', color: '#b35f1a', padding: '4px 8px', borderRadius: 4, fontSize: '0.75rem', border: '1px solid #F4864A', cursor: 'help' }}>
                                    {ex.replace(/_/g, ' ')}
                                  </span>
                                ))}
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: 'center', fontWeight: 'bold', color: s.bloquea_compra_automatica ? '#E63946' : '#888' }}>
                            {s.bloquea_compra_automatica ? 'BLOQUEADA' : 'NO'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <hr style={{ border: 'none', borderTop: '2px dashed #eee' }} />

            {/* ── SECCIÓN 2: OBSERVACIONES HUMANAS ── */}
            <section>
              <h2 style={{ fontSize: '1.2rem', color: '#3A86C8', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                ✍️ Notas de Compra Manuales (Humano)
              </h2>
              
              {obsList.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', background: '#f9f9f9', borderRadius: 8, color: '#888' }}>
                  No se encontraron notas que contengan la palabra "comprar".
                </div>
              ) : (
                <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <table className="preview-table" style={{ margin: 0, border: 'none' }}>
                            <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Nombre de Producto</th>
                              <th>Categoría</th>
                              <th>U/E</th>
                              <th>Stock Físico</th>
                              <th>Observación Original</th>
                              <th>Extracción (Uds)</th>
                            </tr>
                          </thead>
                    <tbody>
                      {obsList.map(s => (
                        <tr key={s.sku}>
                          <td><b>{s.sku}</b></td>
                          <td style={{ fontSize: '0.8rem', maxWidth: 200 }}>{s.nombre_producto}</td>
                          <td>{s.categoria || '—'}</td>
                          <td>{s.ump || '—'}</td>
                          <td>{Number(s.stock_act || 0).toLocaleString('es-CL')}</td>
                          <td style={{ fontSize: '0.8rem', fontStyle: 'italic', color: '#555', maxWidth: 300 }}>
                            "{s.observacion}"
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {s.extraido ? (
                              <span style={{ background: '#E8F2FB', color: '#1a6aa8', padding: '4px 10px', borderRadius: 12, fontWeight: 'bold' }}>
                                {Number(s.extraido).toLocaleString('es-CL')}
                              </span>
                            ) : (
                              <span style={{ color: '#ccc' }}>?</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

          </div>
        )}
      </main>
      {selectedSku && <SkuDetailModal skuData={selectedSku} onClose={() => setSelectedSku(null)} />}
    </div>
  );
}
