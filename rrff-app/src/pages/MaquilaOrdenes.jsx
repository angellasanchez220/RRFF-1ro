import React, { useState, useEffect } from 'react';
import * as api from '../api';

export default function MaquilaOrdenes({ isAdmin }) {
  const [view, setView] = useState('list'); // list, upload, detail
  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Upload state
  const [file, setFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  
  // Detail state
  const [activeOc, setActiveOc] = useState(null);

  // Modales OT y Liquidación
  const [otModalOpen, setOtModalOpen] = useState(false);
  const [otData, setOtData] = useState(null);
  const [otLoading, setOtLoading] = useState(false);

  const [liquidarModalOpen, setLiquidarModalOpen] = useState(false);
  const [liquidarLoading, setLiquidarLoading] = useState(false);
  const [liquidarHermanoMap, setLiquidarHermanoMap] = useState({});
  const [liquidarObs, setLiquidarObs] = useState('');
  const [liquidarMermasInsumos, setLiquidarMermasInsumos] = useState({});
  const [liquidarMermaProducto, setLiquidarMermaProducto] = useState(0);
  const [liquidarMotivoMerma, setLiquidarMotivoMerma] = useState('');

  // Modal Reporte Mermas
  const [mermasModalOpen, setMermasModalOpen] = useState(false);
  const [mermasData, setMermasData] = useState([]);
  const [mermasResumen, setMermasResumen] = useState(null);
  const [mermasLoading, setMermasLoading] = useState(false);

  useEffect(() => {
    if (view === 'list') {
      loadOrdenes();
    }
  }, [view]);

  async function loadOrdenes() {
    setLoading(true);
    try {
      const res = await api.fetchOrdenesMaquila();
      setOrdenes(res.data || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleImportPreview(e) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.importarOrdenMaquila(file);
      setPreviewData(res);
      setView('upload');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function confirmUpload() {
    if (!previewData) return;
    setLoading(true);
    try {
      await api.guardarOrdenMaquila(previewData);
      setPreviewData(null);
      setFile(null);
      setView('list');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function openDetail(id) {
    setLoading(true);
    try {
      const res = await api.fetchOrdenMaquilaById(id);
      setActiveOc(res);
      setView('detail');
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function recalcularOc(id) {
    setLoading(true);
    try {
      await api.recalcularOrdenMaquila(id);
      openDetail(id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function updateEstado(id, nuevoEstado) {
    setLoading(true);
    try {
      await api.updateOrdenMaquilaState(id, nuevoEstado, undefined);
      openDetail(id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenOt(id) {
    setOtLoading(true);
    setOtModalOpen(true);
    try {
      const res = await api.fetchOtMaquila(id);
      setOtData(res);
    } catch (err) {
      alert("Error al cargar datos de la Orden de Trabajo: " + err.message);
      setOtModalOpen(false);
    } finally {
      setOtLoading(false);
    }
  }

  async function handleOpenMermas() {
    setMermasModalOpen(true);
    setMermasLoading(true);
    try {
      const res = await api.fetchMermasMaquila();
      setMermasData(res.data || []);
      setMermasResumen(res.resumen || null);
    } catch (e) {
      alert("Error al cargar reporte de mermas: " + e.message);
    } finally {
      setMermasLoading(false);
    }
  }

  function handleOpenLiquidar() {
    if (!activeOc) return;
    // Precargar selección por defecto del primer hermano con stock para cada producto a maquilar
    const map = {};
    activeOc.detalles.forEach(d => {
      if (d.cantidad_a_maquilar > 0 && d.hermanos_disponibles && d.hermanos_disponibles.length > 0) {
        map[d.sku] = d.hermanos_disponibles[0].sku;
      }
    });
    setLiquidarHermanoMap(map);
    setLiquidarMermasInsumos({});
    setLiquidarMermaProducto(0);
    setLiquidarMotivoMerma('');
    setLiquidarObs(`Liquidación de OC ${activeOc.meta.numero_oc} procesada en planta`);
    setLiquidarModalOpen(true);
  }

  async function handleConfirmLiquidar() {
    if (!activeOc) return;
    if (!window.confirm("¿Confirmas la liquidación de esta maquila? Se descontarán los materiales de 'materiales_maquila' (consumo + mermas), se descontarán los productos hermanos de origen y se sumará el producto terminado en 'planificacion_sop'.")) {
      return;
    }

    setLiquidarLoading(true);
    try {
      const res = await api.liquidarOrdenMaquila(activeOc.meta.id, {
        hermano_seleccionado: liquidarHermanoMap,
        observaciones: liquidarObs,
        mermas_insumos: liquidarMermasInsumos,
        merma_producto_origen: Number(liquidarMermaProducto) || 0,
        motivo_merma: liquidarMotivoMerma.trim()
      });
      alert(res.mensaje || "Maquila liquidada e inventarios actualizados con éxito");
      setLiquidarModalOpen(false);
      openDetail(activeOc.meta.id);
    } catch (err) {
      alert("Error al liquidar: " + err.message);
    } finally {
      setLiquidarLoading(false);
    }
  }

  function printOt() {
    window.print();
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 1. VISTA DE LISTADO
  // ─────────────────────────────────────────────────────────────────────────────
  function renderList() {
    return (
      <div style={{ padding: '4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 14 }}>
          <div>
            <h2 style={{ margin: '0 0 4px', fontSize: '1.4rem', color: '#0f172a', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>📑</span> Órdenes de Compra y Maquila de Clientes
            </h2>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.88rem' }}>
              Sube las OCs de clientes para evaluar quiebres contra stock terminado y calcular requerimientos de insumos, tiempos y costos de maquila.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              className="btn-secondary"
              onClick={handleOpenMermas}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 14px', fontSize: '0.88rem', fontWeight: 600, background: '#ffffff', border: '1.5px solid #cbd5e1' }}
              title="Auditoría de mermas y scrap registrados"
            >
              <span>📉</span> Reporte Mermas & Scrap
            </button>

            {isAdmin && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#f8fafc', padding: '8px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}>
                <input 
                  type="file" 
                  accept=".csv" 
                  onChange={(e) => setFile(e.target.files[0])} 
                  style={{ fontSize: '0.85rem' }}
                />
                <button 
                  className="btn-primary" 
                  onClick={handleImportPreview} 
                  disabled={!file || loading}
                  style={{ padding: '8px 16px', fontWeight: 700, fontSize: '0.88rem' }}
                >
                  {loading ? 'Analizando...' : 'Analizar OC (CSV)'}
                </button>
              </div>
            )}
          </div>
        </div>
        
        {error && <div className="alert-box" style={{ background: '#ffebee', color: '#c62828', padding: '12px 16px', borderRadius: '6px', marginBottom: '16px' }}>{error}</div>}
        
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Cargando órdenes de maquila...</div>
        ) : (
          <div style={{ overflowX: 'auto', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                  <th style={{ padding: '12px 14px', width: '70px' }}>ID</th>
                  <th style={{ padding: '12px 14px' }}>Número OC</th>
                  <th style={{ padding: '12px 14px' }}>Fecha Carga</th>
                  <th style={{ padding: '12px 14px', textAlign: 'center' }}>SKUs Totales (Maq.)</th>
                  <th style={{ padding: '12px 14px', textAlign: 'right' }}>Presupuesto Maquila</th>
                  <th style={{ padding: '12px 14px', textAlign: 'right' }}>Horas Est.</th>
                  <th style={{ padding: '12px 14px', textAlign: 'center' }}>Estado Operativo</th>
                  <th style={{ padding: '12px 14px', textAlign: 'center' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {ordenes.map(o => {
                  const isLiquidada = o.estado_procesamiento === 'Liquidada';
                  const isBloqueada = (o.estado_procesamiento || '').includes('Bloquead');
                  const isPrep = (o.estado_procesamiento || '').includes('preparación');

                  return (
                    <tr key={o.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 14px', color: '#64748b', fontWeight: 600 }}>#{o.id}</td>
                      <td style={{ padding: '12px 14px', fontWeight: 800, color: '#0369a1', fontFamily: 'monospace', fontSize: '0.95rem' }}>
                        {o.numero_oc}
                      </td>
                      <td style={{ padding: '12px 14px', color: '#475569' }}>{o.fecha_carga}</td>
                      <td style={{ padding: '12px 14px', textAlign: 'center', fontWeight: 700 }}>
                        {o.sku_count} <span style={{ color: '#0284c7' }}>({o.maq_count} maq.)</span>
                      </td>
                      <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 700, color: '#16a34a' }}>
                        {o.costo_total_estimado > 0 ? `$${Math.round(o.costo_total_estimado).toLocaleString('es-CL')}` : '-'}
                      </td>
                      <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b' }}>
                        {o.horas_estimadas_1p > 0 ? `${o.horas_estimadas_1p}h` : '-'}
                      </td>
                      <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                        <span style={{
                          padding: '4px 10px',
                          borderRadius: '12px',
                          fontSize: '0.76rem',
                          fontWeight: 700,
                          background: isLiquidada ? '#dcfce7' : isBloqueada ? '#fee2e2' : isPrep ? '#eff6ff' : '#fef3c7',
                          color: isLiquidada ? '#166534' : isBloqueada ? '#991b1b' : isPrep ? '#1d4ed8' : '#92400e',
                          border: '1px solid currentColor'
                        }}>
                          {isLiquidada ? '✓ Liquidada' : o.estado_procesamiento}
                        </span>
                      </td>
                      <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
                          <button 
                            className="btn-secondary" 
                            onClick={() => openDetail(o.id)}
                            style={{ padding: '6px 12px', fontSize: '0.8rem', fontWeight: 700 }}
                          >
                            Ver Detalle
                          </button>
                          <button
                            onClick={() => handleOpenOt(o.id)}
                            style={{ padding: '6px 10px', fontSize: '0.8rem', background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}
                            title="Imprimir Orden de Trabajo"
                          >
                            🖨️ OT
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {ordenes.length === 0 && (
                  <tr>
                    <td colSpan="8" style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                      No hay órdenes de maquila registradas. Sube un archivo CSV de Orden de Compra para iniciar.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 2. VISTA PREVIA TRAS IMPORTAR CSV
  // ─────────────────────────────────────────────────────────────────────────────
  function renderPreview() {
    if (!previewData) return null;
    const { meta, detalles, componentes, estado_general, costos_resumen } = previewData;
    const maq = detalles.filter(d => d.es_maquilable);
    const insumos = componentes.filter(c => c.tipo === 'MATERIAL');
    const hermanos = componentes.filter(c => c.tipo === 'PRODUCTO');

    return (
      <div style={{ padding: '4px' }}>
        <button 
          className="btn-secondary" 
          onClick={() => { setView('list'); setPreviewData(null); }} 
          style={{ marginBottom: 16, display: 'inline-flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}
        >
          ← Volver al listado
        </button>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div>
            <h2 style={{ margin: '0 0 4px', fontSize: '1.4rem', color: '#0f172a', fontWeight: 800 }}>
              Vista Previa de Importación: OC {meta.numero_oc}
            </h2>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.88rem' }}>
              Archivo: <b>{meta.nombre_archivo}</b> | Líneas analizadas: {meta.total_lineas} | SKUs consolidados: {detalles.length}
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>Estado Proyectado:</span>
            <span style={{
              padding: '6px 14px', borderRadius: '20px', fontWeight: 800, fontSize: '0.85rem',
              background: estado_general.includes('Bloquead') ? '#fee2e2' : '#eff6ff',
              color: estado_general.includes('Bloquead') ? '#991b1b' : '#1d4ed8',
              border: '1px solid currentColor'
            }}>
              {estado_general}
            </span>
          </div>
        </div>

        {/* Tarjetas de Presupuesto y Tiempos de Maquila */}
        {costos_resumen && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', marginBottom: '20px' }}>
            <div className="card" style={{ padding: '14px 18px', background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#166534', textTransform: 'uppercase' }}>Costo Total Presupuestado</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#15803d', marginTop: '2px' }}>
                ${Math.round(costos_resumen.costo_total_estimado || 0).toLocaleString('es-CL')}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#166534', marginTop: '2px' }}>Insumos + Mano de Obra</div>
            </div>

            <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Costo Insumos / Empaques</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0369a1', marginTop: '2px' }}>
                ${Math.round(costos_resumen.costo_insumos_estimado || 0).toLocaleString('es-CL')}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>Etiquetas, mangas y cajas</div>
            </div>

            <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Costo Mano de Obra</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#7e22ce', marginTop: '2px' }}>
                ${Math.round(costos_resumen.costo_mo_estimado || 0).toLocaleString('es-CL')}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>Según costo por hora</div>
            </div>

            <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Tiempo Total Estimado</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#0f172a', marginTop: '2px' }}>
                {costos_resumen.horas_estimadas_1p}h <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b' }}>(1 pers.)</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: '#0369a1', fontWeight: 600, marginTop: '2px' }}>
                Con 3p: {costos_resumen.horas_estimadas_3p}h | Con 6p: {costos_resumen.horas_estimadas_6p}h
              </div>
            </div>
          </div>
        )}

        {/* Tabla Productos a Maquilar */}
        <h3 style={{ margin: '0 0 10px', fontSize: '1.1rem', color: '#0f172a' }}>
          1. Productos de la OC que Requieren Maquila ({maq.length})
        </h3>
        <div style={{ overflowX: 'auto', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 20 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                <th style={{ padding: '10px 12px' }}>SKU</th>
                <th style={{ padding: '10px 12px' }}>Descripción</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Pedido</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Recibido</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Pendiente</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Stock Terminado</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', background: '#fef3c7', color: '#92400e' }}>A Maquilar</th>
              </tr>
            </thead>
            <tbody>
              {maq.map(m => (
                <tr key={m.sku} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 800, color: '#0369a1', fontFamily: 'monospace' }}>{m.sku}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 600 }}>{m.nombre_producto}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>{m.cantidad_solicitada}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>{m.cantidad_recibida}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 700 }}>{m.cantidad_pendiente}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', color: '#64748b' }}>{m.stock_producto_terminado}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 800, background: '#fffbeb', color: m.cantidad_a_maquilar > 0 ? '#b45309' : '#15803d' }}>
                    {m.cantidad_a_maquilar > 0 ? m.cantidad_a_maquilar : '0 (Cubierto)'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Tabla Insumos y Materiales */}
        <h3 style={{ margin: '0 0 10px', fontSize: '1.1rem', color: '#0f172a' }}>
          2. Insumos y Materiales de Maquila Requeridos ({insumos.length})
        </h3>
        <div style={{ overflowX: 'auto', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 20 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                <th style={{ padding: '10px 12px' }}>SKU Insumo</th>
                <th style={{ padding: '10px 12px' }}>Nombre Insumo</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Requerido</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Stock en Bodega</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Faltante</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Costo Unit.</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {insumos.map(c => {
                const hasFaltante = c.faltante > 0;
                return (
                  <tr key={c.sku} style={{ borderBottom: '1px solid #f1f5f9', background: hasFaltante ? '#fff1f2' : 'inherit' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 700, fontFamily: 'monospace' }}>{c.sku}</td>
                    <td style={{ padding: '10px 12px' }}>{c.nombre}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700 }}>{c.requerido}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: hasFaltante ? '#dc2626' : '#15803d', fontWeight: 700 }}>{c.stock_actual}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 800, color: hasFaltante ? '#e11d48' : '#15803d' }}>
                      {hasFaltante ? `⚠️ ${c.faltante}` : '0 (OK)'}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>${c.costo_unitario}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#16a34a' }}>${Math.round(c.costo_total).toLocaleString('es-CL')}</td>
                  </tr>
                );
              })}
              {insumos.length === 0 && (
                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '16px', color: '#94a3b8' }}>No se requieren insumos adicionales para esta orden.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <button 
          className="btn-primary" 
          onClick={confirmUpload} 
          disabled={loading} 
          style={{ width: '100%', padding: '14px', fontSize: '1.05rem', fontWeight: 800, borderRadius: '8px' }}
        >
          {loading ? 'Guardando Orden...' : '✓ Confirmar e Importar Orden de Maquila'}
        </button>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 3. VISTA DETALLE DE UNA ORDEN GUARDADA
  // ─────────────────────────────────────────────────────────────────────────────
  function renderDetail() {
    if (!activeOc) return null;
    const { meta, detalles, componentes, costos_resumen } = activeOc;
    const maq = detalles.filter(d => d.es_maquilable);
    const noMaq = detalles.filter(d => !d.es_maquilable);
    const insumos = componentes.filter(c => c.tipo === 'MATERIAL');
    const hermanos = componentes.filter(c => c.tipo === 'PRODUCTO');
    const isLiquidada = meta.estado_procesamiento === 'Liquidada';

    const handleExport = () => {
      let csvContent = "\uFEFFSKU,Nombre,Tipo,Requerido,Stock_Actual,Faltante,Costo_Unitario,Total_Costo\n";
      componentes.forEach(c => {
        csvContent += `"${c.sku}","${c.nombre}","${c.tipo}",${c.requerido},${c.stock_actual},${c.faltante},${c.costo_unitario},${c.costo_total}\n`;
      });
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Plan_Maquila_OC_${meta.numero_oc}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    };

    return (
      <div style={{ padding: '4px' }}>
        {/* Barra superior de navegación y acciones */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
          <button 
            className="btn-secondary" 
            onClick={() => { setView('list'); setActiveOc(null); }}
            style={{ fontWeight: 600 }}
          >
            ← Volver al listado
          </button>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {isAdmin && (
              <button 
                className="btn-secondary" 
                onClick={() => recalcularOc(meta.id)} 
                disabled={loading || isLiquidada}
                style={{ fontWeight: 600 }}
              >
                🔄 Recalcular con Inventario Actual
              </button>
            )}

            <button 
              className="btn-secondary" 
              onClick={() => handleOpenOt(meta.id)}
              style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <span>🖨️</span> Generar Orden de Trabajo (OT)
            </button>

            <button 
              className="btn-secondary" 
              onClick={handleExport}
              style={{ fontWeight: 600 }}
            >
              📥 Exportar CSV
            </button>

            {isAdmin && !isLiquidada && (
              <button 
                className="btn-primary" 
                onClick={handleOpenLiquidar}
                style={{ background: '#16a34a', border: 'none', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <span>⚡</span> Liquidar y Descontar Stock
              </button>
            )}
          </div>
        </div>

        {error && <div className="alert-box" style={{ background: '#ffebee', color: '#c62828', padding: '12px', borderRadius: '6px', marginBottom: '16px' }}>{error}</div>}

        {/* Encabezado de la Orden */}
        <div className="card" style={{ padding: '20px 24px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h2 style={{ margin: 0, fontSize: '1.5rem', color: '#0f172a', fontWeight: 800 }}>
                  OC Cliente: {meta.numero_oc}
                </h2>
                <span style={{
                  padding: '4px 12px', borderRadius: '20px', fontWeight: 700, fontSize: '0.8rem',
                  background: isLiquidada ? '#dcfce7' : (meta.estado_procesamiento || '').includes('Bloquead') ? '#fee2e2' : '#eff6ff',
                  color: isLiquidada ? '#166534' : (meta.estado_procesamiento || '').includes('Bloquead') ? '#991b1b' : '#1d4ed8',
                  border: '1px solid currentColor'
                }}>
                  {meta.estado_procesamiento}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 20, marginTop: 8, fontSize: '0.88rem', color: '#64748b', flexWrap: 'wrap' }}>
                <span><strong>Tipo de Orden:</strong> {meta.tipo_orden || 'Retail'}</span>
                <span><strong>Fecha Emisión:</strong> {meta.fecha_emision || '-'}</span>
                <span><strong>Fecha Límite:</strong> {meta.fecha_fin_recepcion || '-'}</span>
                <span><strong>Archivo Origen:</strong> {meta.nombre_archivo}</span>
              </div>
            </div>

            {isAdmin && !isLiquidada && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#475569' }}>Cambiar Estado:</span>
                <select 
                  value={meta.estado_procesamiento} 
                  onChange={(e) => updateEstado(meta.id, e.target.value)}
                  style={{ padding: '6px 10px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 600, fontSize: '0.85rem' }}
                  disabled={loading}
                >
                  <option value="Pendiente">Pendiente</option>
                  <option value="En preparación">En preparación</option>
                  <option value="Preparada">Preparada</option>
                  <option value="Bloqueada por falta de Insumos">Bloqueada por falta de Insumos</option>
                  <option value="Bloqueada por falta de Hermanos">Bloqueada por falta de Hermanos</option>
                  <option value="Bloqueada por faltantes (Insumos y Hermanos)">Bloqueada por faltantes totales</option>
                  <option value="Cancelada">Cancelada</option>
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Tarjetas de Presupuesto y Tiempos */}
        {costos_resumen && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', marginBottom: '22px' }}>
            <div className="card" style={{ padding: '16px 20px', background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#166534', textTransform: 'uppercase' }}>Costo Total Presupuestado</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#15803d', marginTop: '2px' }}>
                ${Math.round(costos_resumen.costo_total_estimado || 0).toLocaleString('es-CL')}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#166534', marginTop: '2px' }}>Insumos + Mano de Obra</div>
            </div>

            <div className="card" style={{ padding: '16px 20px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Costo Insumos / Empaque</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0369a1', marginTop: '2px' }}>
                ${Math.round(costos_resumen.costo_insumos_estimado || 0).toLocaleString('es-CL')}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '2px' }}>Etiquetas, mangas y cajas</div>
            </div>

            <div className="card" style={{ padding: '16px 20px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Costo Mano de Obra</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#7e22ce', marginTop: '2px' }}>
                ${Math.round(costos_resumen.costo_mo_estimado || 0).toLocaleString('es-CL')}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '2px' }}>Según tiempo estándar</div>
            </div>

            <div className="card" style={{ padding: '16px 20px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Tiempo Total Estimado</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginTop: '2px' }}>
                {costos_resumen.horas_estimadas_1p}h <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b' }}>(1 operario)</span>
              </div>
              <div style={{ fontSize: '0.78rem', color: '#0369a1', fontWeight: 600, marginTop: '2px' }}>
                Con 3 pers: <b>{costos_resumen.horas_estimadas_3p}h</b> | Con 6 pers: <b>{costos_resumen.horas_estimadas_6p}h</b>
              </div>
            </div>
          </div>
        )}

        {/* Sección 1: Productos Maquilables */}
        <h3 style={{ margin: '0 0 10px', fontSize: '1.15rem', color: '#0f172a', fontWeight: 700 }}>
          1. Productos de la OC a Maquilar ({maq.length})
        </h3>
        <div style={{ overflowX: 'auto', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 24, boxShadow: '0 2px 4px rgba(0,0,0,0.03)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                <th style={{ padding: '10px 12px' }}>SKU Terminado</th>
                <th style={{ padding: '10px 12px' }}>Producto</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Pedido</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Recibido</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Pendiente</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>Stock Terminado</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', background: '#fef3c7', color: '#92400e' }}>A Maquilar</th>
                <th style={{ padding: '10px 12px' }}>Hermanos Disponibles</th>
              </tr>
            </thead>
            <tbody>
              {maq.map(m => (
                <tr key={m.sku} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 800, color: '#0369a1', fontFamily: 'monospace' }}>{m.sku}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 600 }}>{m.nombre_producto}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>{m.cantidad_solicitada}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>{m.cantidad_recibida}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 700 }}>{m.cantidad_pendiente}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', color: '#64748b' }}>{m.stock_producto_terminado}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 800, background: '#fffbeb', color: m.cantidad_a_maquilar > 0 ? '#b45309' : '#15803d' }}>
                    {m.cantidad_a_maquilar > 0 ? m.cantidad_a_maquilar : '0 (Cubierto)'}
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: '0.8rem' }}>
                    {m.hermanos_disponibles && m.hermanos_disponibles.length > 0 ? (
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                        {m.hermanos_disponibles.map(h => (
                          <span key={h.sku} style={{ padding: '2px 6px', background: '#f1f5f9', borderRadius: '4px', border: '1px solid #cbd5e1' }}>
                            <b>{h.sku}</b>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: '#94a3b8' }}>-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Sección 2: Insumos de Maquila Requeridos */}
        <h3 style={{ margin: '0 0 10px', fontSize: '1.15rem', color: '#0f172a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>🏷️</span> 2. Insumos y Materiales de Maquila Requeridos ({insumos.length})
        </h3>
        <div style={{ overflowX: 'auto', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 24, boxShadow: '0 2px 4px rgba(0,0,0,0.03)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                <th style={{ padding: '10px 12px' }}>SKU Insumo</th>
                <th style={{ padding: '10px 12px' }}>Nombre Insumo</th>
                <th style={{ padding: '10px 12px' }}>Utilizado en</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Requerido Total</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Stock en Bodega</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Faltante</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Costo Unit.</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Subtotal ($)</th>
              </tr>
            </thead>
            <tbody>
              {insumos.map(c => {
                const hasFaltante = c.faltante > 0;
                return (
                  <tr key={c.sku} style={{ borderBottom: '1px solid #f1f5f9', background: hasFaltante ? '#fff1f2' : 'inherit' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 700, fontFamily: 'monospace', color: '#0369a1' }}>{c.sku}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{c.nombre}</td>
                    <td style={{ padding: '10px 12px', color: '#64748b', fontSize: '0.8rem' }}>{c.utilizado_por ? c.utilizado_por.join(', ') : '-'}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700 }}>{c.requerido}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: hasFaltante ? '#dc2626' : '#15803d', fontWeight: 700 }}>
                      {c.stock_actual}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 800, color: hasFaltante ? '#e11d48' : '#15803d' }}>
                      {hasFaltante ? `⚠️ ${c.faltante}` : '0 (OK)'}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>${c.costo_unitario}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#16a34a' }}>
                      ${Math.round(c.costo_total).toLocaleString('es-CL')}
                    </td>
                  </tr>
                );
              })}
              {insumos.length === 0 && (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: '20px', color: '#94a3b8' }}>
                    No se requieren insumos adicionales para esta orden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Sección 3: Productos Hermanos (Bases de transformación) */}
        {hermanos.length > 0 && (
          <>
            <h3 style={{ margin: '0 0 10px', fontSize: '1.15rem', color: '#0f172a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>🔄</span> 3. Productos Hermanos Compatibles para Transformación ({hermanos.length})
            </h3>
            <div style={{ overflowX: 'auto', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 24, boxShadow: '0 2px 4px rgba(0,0,0,0.03)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                    <th style={{ padding: '10px 12px' }}>SKU Hermano</th>
                    <th style={{ padding: '10px 12px' }}>Nombre Producto</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Stock Disponible en SOP</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Unidades Requeridas Máx.</th>
                    <th style={{ padding: '10px 12px' }}>Compatible con</th>
                  </tr>
                </thead>
                <tbody>
                  {hermanos.map(h => (
                    <tr key={h.sku} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 700, fontFamily: 'monospace' }}>{h.sku}</td>
                      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{h.nombre}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: h.stock_actual > 0 ? '#15803d' : '#dc2626' }}>
                        {h.stock_actual}
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700 }}>{h.requerido}</td>
                      <td style={{ padding: '10px 12px', color: '#64748b', fontSize: '0.8rem' }}>{h.utilizado_por ? h.utilizado_por.join(', ') : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Sección 4: Productos No Maquilables */}
        {noMaq.length > 0 && (
          <>
            <h3 style={{ margin: '0 0 10px', fontSize: '1.15rem', color: '#64748b', fontWeight: 700 }}>
              4. Productos Sin Receta de Maquila ({noMaq.length})
            </h3>
            <div style={{ overflowX: 'auto', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: 24, opacity: 0.85 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                    <th style={{ padding: '10px 12px' }}>SKU</th>
                    <th style={{ padding: '10px 12px' }}>Producto</th>
                    <th style={{ padding: '10px 12px', textAlign: 'center' }}>Pendiente</th>
                    <th style={{ padding: '10px 12px' }}>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {noMaq.map(m => (
                    <tr key={m.sku} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 700, fontFamily: 'monospace' }}>{m.sku}</td>
                      <td style={{ padding: '10px 12px' }}>{m.nombre_producto}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 700 }}>{m.cantidad_pendiente}</td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>No tiene familia o receta configurada</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 4. MODAL DE ORDEN DE TRABAJO (OT / PICKING LIST IMPRIMIBLE)
  // ─────────────────────────────────────────────────────────────────────────────
  function renderOtModal() {
    if (!otModalOpen) return null;

    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(15, 23, 42, 0.7)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
      }}>
        <div style={{
          width: '94%', maxWidth: '850px', maxHeight: '92vh', overflowY: 'auto',
          background: '#ffffff', borderRadius: '10px', padding: '28px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35)'
        }}>
          {otLoading || !otData ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
              Cargando Hoja de Ruta / Orden de Trabajo...
            </div>
          ) : (
            <div id="printable-ot-sheet">
              {/* Encabezado OT */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '2px solid #0f172a', paddingBottom: '14px', marginBottom: '16px' }}>
                <div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 800, color: '#0284c7', textTransform: 'uppercase' }}>
                    FEMACO / PLANTA DE MAQUILA Y TRANSFORMACIÓN
                  </div>
                  <h1 style={{ margin: '4px 0', fontSize: '1.6rem', color: '#0f172a', fontWeight: 900 }}>
                    ORDEN DE TRABAJO (OT): {otData.ot_numero}
                  </h1>
                  <div style={{ fontSize: '0.85rem', color: '#475569' }}>
                    Referencia OC Cliente: <b>{otData.oc.numero_oc}</b> ({otData.oc.tipo_orden || 'Retail'})
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.8rem', color: '#64748b' }}>Fecha de Emisión:</div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a' }}>{otData.fecha_emision}</div>
                  <div style={{ fontSize: '0.8rem', color: '#e11d48', fontWeight: 700, marginTop: '2px' }}>
                    Fecha Entrega: {otData.oc.fecha_fin_recepcion || 'Prioritaria'}
                  </div>
                </div>
              </div>

              {/* Botones no imprimibles */}
              <div className="no-print" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginBottom: '16px' }}>
                <button 
                  type="button" 
                  onClick={printOt}
                  style={{ padding: '8px 18px', background: '#0284c7', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <span>🖨️</span> Imprimir OT
                </button>
                <button 
                  type="button" 
                  onClick={() => setOtModalOpen(false)}
                  style={{ padding: '8px 14px', background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cerrar
                </button>
              </div>

              {/* Resumen de Producción */}
              <div style={{ background: '#f8fafc', padding: '12px 16px', borderRadius: '6px', border: '1px solid #e2e8f0', marginBottom: '18px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px' }}>
                <div>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Unidades a Producir</span>
                  <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#0f172a' }}>{otData.resumen_produccion.total_unidades} uds</div>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Tiempo Est. 1 Persona</span>
                  <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#0284c7' }}>{otData.resumen_produccion.total_horas_1p} hrs</div>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Tiempo Est. 3 Personas</span>
                  <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#7e22ce' }}>{otData.resumen_produccion.total_horas_3p} hrs</div>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Costo Presupuestado</span>
                  <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#16a34a' }}>${Math.round(otData.resumen_produccion.costo_total_estimado).toLocaleString('es-CL')}</div>
                </div>
              </div>

              {/* 1. Lista de Picking de Insumos */}
              <h3 style={{ fontSize: '1rem', color: '#0f172a', borderBottom: '1.5px solid #cbd5e1', paddingBottom: '4px', margin: '0 0 8px' }}>
                📦 1. Lista de Despacho de Bodega - Insumos (Picking List)
              </h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem', marginBottom: '18px' }}>
                <thead>
                  <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #cbd5e1' }}>
                    <th style={{ padding: '6px 8px', width: '30px', textAlign: 'center' }}>[✓]</th>
                    <th style={{ padding: '6px 8px' }}>SKU Insumo</th>
                    <th style={{ padding: '6px 8px' }}>Descripción</th>
                    <th style={{ padding: '6px 8px', textAlign: 'center' }}>Categoría</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Cantidad a Despachar</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Stock Bodega</th>
                  </tr>
                </thead>
                <tbody>
                  {otData.picking_insumos.map((p, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <div style={{ width: '16px', height: '16px', border: '1.5px solid #475569', borderRadius: '3px', margin: '0 auto' }}></div>
                      </td>
                      <td style={{ padding: '6px 8px', fontWeight: 800, fontFamily: 'monospace' }}>{p.sku}</td>
                      <td style={{ padding: '6px 8px' }}>{p.nombre}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'center', fontSize: '0.75rem' }}>{p.categoria}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 800 }}>{p.cantidad_despachar} {p.unidad_medida}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', color: '#64748b' }}>{p.stock_bodega}</td>
                    </tr>
                  ))}
                  {otData.picking_insumos.length === 0 && (
                    <tr><td colSpan="6" style={{ padding: '10px', textAlign: 'center', color: '#94a3b8' }}>Sin insumos adicionales</td></tr>
                  )}
                </tbody>
              </table>

              {/* 2. Lista de Picking de Productos Hermanos a Transformar */}
              <h3 style={{ fontSize: '1rem', color: '#0f172a', borderBottom: '1.5px solid #cbd5e1', paddingBottom: '4px', margin: '0 0 8px' }}>
                🔄 2. Lista de Despacho de Bodega - Productos Hermanos Origen
              </h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem', marginBottom: '18px' }}>
                <thead>
                  <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #cbd5e1' }}>
                    <th style={{ padding: '6px 8px', width: '30px', textAlign: 'center' }}>[✓]</th>
                    <th style={{ padding: '6px 8px' }}>SKU Hermano Origen</th>
                    <th style={{ padding: '6px 8px' }}>Nombre Producto</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Cantidad a Despachar</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Stock Disponible</th>
                  </tr>
                </thead>
                <tbody>
                  {otData.picking_hermanos.map((p, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <div style={{ width: '16px', height: '16px', border: '1.5px solid #475569', borderRadius: '3px', margin: '0 auto' }}></div>
                      </td>
                      <td style={{ padding: '6px 8px', fontWeight: 800, fontFamily: 'monospace' }}>{p.sku}</td>
                      <td style={{ padding: '6px 8px' }}>{p.nombre}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 800 }}>{p.cantidad_despachar} UN</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', color: '#64748b' }}>{p.stock_bodega}</td>
                    </tr>
                  ))}
                  {otData.picking_hermanos.length === 0 && (
                    <tr><td colSpan="5" style={{ padding: '10px', textAlign: 'center', color: '#94a3b8' }}>Sin productos hermanos especificados</td></tr>
                  )}
                </tbody>
              </table>

              {/* 3. Control de Planta y Tiempos */}
              <h3 style={{ fontSize: '1rem', color: '#0f172a', borderBottom: '1.5px solid #cbd5e1', paddingBottom: '4px', margin: '0 0 8px' }}>
                ⏱️ 3. Control de Ejecución en Línea
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', fontSize: '0.84rem', marginBottom: '20px' }}>
                <div style={{ border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: '4px' }}>
                  <b>Operario / Supervisor Línea:</b>
                  <div style={{ borderBottom: '1px dotted #94a3b8', height: '22px', marginTop: '4px' }}></div>
                </div>
                <div style={{ border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: '4px' }}>
                  <b>Fecha y Hora Inicio:</b>
                  <div style={{ borderBottom: '1px dotted #94a3b8', height: '22px', marginTop: '4px' }}></div>
                </div>
                <div style={{ border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: '4px' }}>
                  <b>Fecha y Hora Término:</b>
                  <div style={{ borderBottom: '1px dotted #94a3b8', height: '22px', marginTop: '4px' }}></div>
                </div>
                <div style={{ border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: '4px' }}>
                  <b>Unidades Buenas Terminadas:</b>
                  <div style={{ borderBottom: '1px dotted #94a3b8', height: '22px', marginTop: '4px' }}></div>
                </div>
                <div style={{ border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: '4px' }}>
                  <b>Mermas / Desperdicio (Uds):</b>
                  <div style={{ borderBottom: '1px dotted #94a3b8', height: '22px', marginTop: '4px' }}></div>
                </div>
                <div style={{ border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: '4px' }}>
                  <b>Dotación Real de Personas:</b>
                  <div style={{ borderBottom: '1px dotted #94a3b8', height: '22px', marginTop: '4px' }}></div>
                </div>
              </div>

              {/* 4. Firmas de Conformidad */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px', marginTop: '30px', textAlign: 'center', fontSize: '0.8rem' }}>
                <div>
                  <div style={{ borderTop: '1px solid #0f172a', paddingTop: '6px', fontWeight: 700 }}>
                    Bodega Entrega Insumos
                  </div>
                  <div style={{ color: '#64748b', fontSize: '0.74rem' }}>Firma y Nombre</div>
                </div>
                <div>
                  <div style={{ borderTop: '1px solid #0f172a', paddingTop: '6px', fontWeight: 700 }}>
                    Maquila Recibe y Procesa
                  </div>
                  <div style={{ color: '#64748b', fontSize: '0.74rem' }}>Firma y Nombre</div>
                </div>
                <div>
                  <div style={{ borderTop: '1px solid #0f172a', paddingTop: '6px', fontWeight: 700 }}>
                    Bodega Recibe Producto Terminado
                  </div>
                  <div style={{ color: '#64748b', fontSize: '0.74rem' }}>Firma y Nombre</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 5. MODAL DE LIQUIDACIÓN Y ACTUALIZACIÓN DE STOCK
  // ─────────────────────────────────────────────────────────────────────────────
  function renderLiquidarModal() {
    if (!liquidarModalOpen || !activeOc) return null;
    const { meta, detalles, componentes } = activeOc;
    const aMaquilarList = detalles.filter(d => d.cantidad_a_maquilar > 0);

    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(15, 23, 42, 0.7)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
      }}>
        <div style={{
          width: '92%', maxWidth: '640px', background: '#ffffff', borderRadius: '10px',
          padding: '24px', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35)', maxHeight: '90vh', overflowY: 'auto'
        }}>
          <h2 style={{ margin: '0 0 6px', fontSize: '1.3rem', color: '#0f172a', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>⚡</span> Liquidación y Cierre de Maquila: OC {meta.numero_oc}
          </h2>
          <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: '0.86rem' }}>
            Esta acción confirma que la maquila fue realizada en planta. El sistema actualizará automáticamente todos los inventarios en vivo.
          </p>

          <div style={{ background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: '8px', padding: '14px', marginBottom: '16px', fontSize: '0.85rem' }}>
            <span style={{ fontWeight: 800, color: '#166534', display: 'block', marginBottom: '6px' }}>
              ✓ Impacto automático en inventarios:
            </span>
            <ul style={{ margin: 0, paddingLeft: '20px', color: '#15803d' }}>
              <li>Se <b>descontarán</b> las etiquetas, mangas y cajas de <b>materiales_maquila</b>.</li>
              <li>Se <b>descontará</b> el stock del producto hermano origen seleccionado de <b>planificacion_sop</b>.</li>
              <li>Se <b>sumará</b> el stock del producto terminado a <b>planificacion_sop</b>.</li>
              <li>Quedará registrado el histórico auditable con costos, fechas y usuario responsable.</li>
            </ul>
          </div>

          {/* Selección de Hermano Origen para cada producto */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontWeight: 700, fontSize: '0.88rem', color: '#0f172a', marginBottom: '8px' }}>
              Confirmar Producto Hermano Utilizado como Base:
            </label>
            {aMaquilarList.map(item => (
              <div key={item.sku} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', marginBottom: '8px', gap: '10px' }}>
                <div>
                  <span style={{ fontWeight: 800, color: '#0369a1' }}>{item.sku}</span> ({item.cantidad_a_maquilar} uds)
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Descontar de:</span>
                  <select
                    value={liquidarHermanoMap[item.sku] || ''}
                    onChange={e => setLiquidarHermanoMap({ ...liquidarHermanoMap, [item.sku]: e.target.value })}
                    style={{ padding: '6px 10px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 700, fontSize: '0.84rem' }}
                  >
                    {item.hermanos_disponibles && item.hermanos_disponibles.map(h => (
                      <option key={h.sku} value={h.sku}>
                        {h.sku} (Stock: {h.stock_actual})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            ))}
          </div>

          {/* Mermas Reales en Planta */}
          <div style={{ background: '#fff1f2', border: '1.5px solid #fecdd3', borderRadius: '8px', padding: '14px', marginBottom: '16px' }}>
            <div style={{ fontWeight: 800, color: '#9f1239', fontSize: '0.9rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>📉</span> Registro de Mermas y Scrap en Planta (Opcional):
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px', marginBottom: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: '#881337', marginBottom: '4px' }}>
                  Merma de Producto Origen (uds dañadas):
                </label>
                <input
                  type="number"
                  min="0"
                  value={liquidarMermaProducto}
                  onChange={e => setLiquidarMermaProducto(e.target.value)}
                  style={{ width: '100%', padding: '7px 10px', borderRadius: '6px', border: '1.5px solid #fda4af', fontWeight: 700 }}
                  placeholder="0"
                />
              </div>

              {componentes && componentes.filter(c => c.tipo === 'MATERIAL').map(mat => (
                <div key={mat.sku}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: '#881337', marginBottom: '4px' }}>
                    Merma {mat.sku} ({mat.nombre?.substring(0, 20)}...):
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={liquidarMermasInsumos[mat.sku] || ''}
                    onChange={e => setLiquidarMermasInsumos({ ...liquidarMermasInsumos, [mat.sku]: Number(e.target.value) || 0 })}
                    style={{ width: '100%', padding: '7px 10px', borderRadius: '6px', border: '1.5px solid #fda4af', fontWeight: 700 }}
                    placeholder="0"
                  />
                </div>
              ))}
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: '#881337', marginBottom: '4px' }}>
                Motivo / Causa de la Merma:
              </label>
              <input
                type="text"
                value={liquidarMotivoMerma}
                onChange={e => setLiquidarMotivoMerma(e.target.value)}
                placeholder="Ej. Calibración de mangas, etiquetas rasgadas por bobina defectuosa"
                style={{ width: '100%', padding: '7px 10px', borderRadius: '6px', border: '1.5px solid #fda4af', fontSize: '0.84rem' }}
              />
            </div>
          </div>

          {/* Observaciones */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontWeight: 700, fontSize: '0.85rem', color: '#334155', marginBottom: '4px' }}>
              Observaciones de Cierre / Bitácora:
            </label>
            <input
              type="text"
              value={liquidarObs}
              onChange={e => setLiquidarObs(e.target.value)}
              style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontSize: '0.88rem' }}
              placeholder="Ej: Lote finalizado conforme en turno mañana"
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setLiquidarModalOpen(false)}
              disabled={liquidarLoading}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleConfirmLiquidar}
              disabled={liquidarLoading}
              style={{ background: '#16a34a', border: 'none', padding: '10px 22px', fontWeight: 800 }}
            >
              {liquidarLoading ? 'Liquidando e impactando inventario...' : '✓ Confirmar y Liquidar Maquila'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 6. MODAL REPORTE DE MERMAS Y SCRAP
  // ─────────────────────────────────────────────────────────────────────────────
  function renderMermasModal() {
    if (!mermasModalOpen) return null;

    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(15, 23, 42, 0.7)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
      }}>
        <div style={{
          width: '94%', maxWidth: '960px', background: '#ffffff', borderRadius: '12px',
          padding: '24px', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35)', maxHeight: '90vh', display: 'flex', flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
            <div>
              <h2 style={{ margin: '0 0 4px', fontSize: '1.25rem', color: '#0f172a', fontWeight: 800 }}>
                📉 Reporte Histórico de Mermas y Scrap de Maquila
              </h2>
              <div style={{ fontSize: '0.82rem', color: '#64748b' }}>
                Control y auditoría de desperdicios registrados al liquidar cada orden de trabajo
              </div>
            </div>
            <button onClick={() => setMermasModalOpen(false)} style={{ background: 'none', border: 'none', fontSize: '1.4rem', cursor: 'pointer', color: '#64748b' }}>✕</button>
          </div>

          {/* Tarjetas resumen */}
          {mermasResumen && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '18px' }}>
              <div style={{ padding: '12px 14px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.74rem', color: '#64748b', fontWeight: 700 }}>UDS TERMINADAS</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#0f172a' }}>{mermasResumen.unidades_producidas?.toLocaleString()}</div>
              </div>
              <div style={{ padding: '12px 14px', background: '#fff1f2', borderRadius: '8px', border: '1px solid #fecdd3' }}>
                <div style={{ fontSize: '0.74rem', color: '#9f1239', fontWeight: 700 }}>MERMAS PRODUCTO (UDS)</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#e11d48' }}>{mermasResumen.mermas_producto_uds?.toLocaleString()}</div>
              </div>
              <div style={{ padding: '12px 14px', background: '#fef3c7', borderRadius: '8px', border: '1px solid #fde68a' }}>
                <div style={{ fontSize: '0.74rem', color: '#92400e', fontWeight: 700 }}>TASA DE MERMA REAL</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#b45309' }}>{mermasResumen.tasa_merma_pct}%</div>
              </div>
              <div style={{ padding: '12px 14px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                <div style={{ fontSize: '0.74rem', color: '#166534', fontWeight: 700 }}>COSTO TOTAL MERMAS</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#15803d' }}>${Math.round(mermasResumen.costo_total_mermas || 0).toLocaleString('es-CL')}</div>
              </div>
            </div>
          )}

          <div style={{ flex: 1, overflowY: 'auto' }}>
            {mermasLoading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Cargando reporte de mermas...</div>
            ) : mermasData.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>No se han registrado mermas en las liquidaciones procesadas.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                    <th style={{ padding: '10px 12px' }}>Fecha</th>
                    <th style={{ padding: '10px 12px' }}>OC</th>
                    <th style={{ padding: '10px 12px' }}>SKU Producido</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Cant. Producida</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Merma Prod.</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>% Scrap</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Costo Merma</th>
                    <th style={{ padding: '10px 12px' }}>Motivo</th>
                    <th style={{ padding: '10px 12px' }}>Usuario</th>
                  </tr>
                </thead>
                <tbody>
                  {mermasData.map((m, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', background: m.merma_unidades_producto > 0 ? '#fff1f2' : '#ffffff' }}>
                      <td style={{ padding: '10px 12px', color: '#64748b' }}>{m.fecha_registro}</td>
                      <td style={{ padding: '10px 12px', fontWeight: 700, color: '#0369a1' }}>{m.numero_oc}</td>
                      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{m.sku_producido}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700 }}>{m.cantidad_producida?.toLocaleString()}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: m.merma_unidades_producto > 0 ? '#e11d48' : '#64748b' }}>
                        {m.merma_unidades_producto?.toLocaleString()}
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#b45309' }}>
                        {m.tasa_merma_pct}%
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 800, color: '#16a34a' }}>
                        ${Math.round(m.costo_merma_total || 0).toLocaleString('es-CL')}
                      </td>
                      <td style={{ padding: '10px 12px', color: '#475569' }}>{m.motivo_merma || 'Sin observaciones'}</td>
                      <td style={{ padding: '10px 12px', color: '#64748b', fontSize: '0.8rem' }}>{m.usuario}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px', borderTop: '1px solid #e2e8f0', paddingTop: '12px' }}>
            <button className="btn-secondary" onClick={() => setMermasModalOpen(false)}>Cerrar Reporte</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ordenes-maquila" style={{ width: '100%' }}>
      {view === 'list' && renderList()}
      {view === 'upload' && renderPreview()}
      {view === 'detail' && renderDetail()}
      {renderOtModal()}
      {renderLiquidarModal()}
      {renderMermasModal()}
    </div>
  );
}
