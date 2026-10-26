import React, { useState, useEffect } from 'react';
import * as api from '../api';

function formatCleanDate(val) {
  if (!val) return '—';
  const s = String(val).trim();
  if (s === '—' || s === 'None' || s === 'null' || !s) return '—';
  if (s.includes('T')) return s.split('T')[0];
  if (s.includes(' ')) return s.split(' ')[0];
  return s.length > 10 ? s.substring(0, 10) : s;
}

export default function OrdenesCompra() {
  const [ocs, setOcs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('list'); // 'list' | 'quiebres'
  
  // Filtros de listado
  const [searchTerm, setSearchTerm] = useState('');
  const [filterEtapa, setFilterEtapa] = useState('ALL');
  const [filterAlertas, setFilterAlertas] = useState('ALL');

  // Modal de Carga
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadEtapa, setUploadEtapa] = useState('AUTO');
  const [uploadOcNum, setUploadOcNum] = useState('');
  const [uploadCliente, setUploadCliente] = useState('');
  const [uploadFechaPedido, setUploadFechaPedido] = useState('');
  const [uploadFechaEntrega, setUploadFechaEntrega] = useState('');
  const [uploading, setUploading] = useState(false);

  // Modal de Detalle
  const [selectedOcId, setSelectedOcId] = useState(null);
  const [selectedOcNumero, setSelectedOcNumero] = useState('');
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailFilter, setDetailFilter] = useState('ALL'); // 'ALL' | 'NO_DESPACHADO' | 'PARCIAL' | 'DESBALANCE'

  // Histórico de quiebres
  const [quiebresHistory, setQuiebresHistory] = useState([]);
  const [quiebresLoading, setQuiebresLoading] = useState(false);
  const [filterCatalogStates, setFilterCatalogStates] = useState({
    ACTIVO: true,
    BLOQUEADO: true,
    DESCONTINUADO: false, // Por defecto no mostrar descontinuados
  });

  useEffect(() => {
    loadOcs();
  }, []);

  async function loadOcs() {
    setLoading(true);
    try {
      const res = await api.fetchOrdenesCompra();
      setOcs(res.data || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadQuiebres() {
    setQuiebresLoading(true);
    try {
      const res = await api.fetchQuiebresHistoricos();
      setQuiebresHistory(res.data || []);
    } catch (err) {
      alert("Error al cargar historial de quiebres: " + err.message);
    } finally {
      setQuiebresLoading(false);
    }
  }

  async function handleOpenDetail(id, numero_oc = '') {
    setSelectedOcId(id);
    setSelectedOcNumero(numero_oc || '');
    setDetailLoading(true);
    try {
      const res = await api.fetchOrdenCompraDetail(id);
      setDetailData(res);
      setDetailFilter('ALL');
    } catch (err) {
      alert("Error al cargar auditoría: " + err.message);
      setSelectedOcId(null);
      setSelectedOcNumero('');
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleDeleteOc(id, num) {
    if (!window.confirm(`¿Seguro que deseas eliminar la Orden de Compra ${num}?`)) return;
    try {
      await api.deleteOrdenCompra(id);
      loadOcs();
      if (selectedOcId === id) {
        setSelectedOcId(null);
        setDetailData(null);
      }
    } catch (err) {
      alert("Error al eliminar: " + err.message);
    }
  }

  async function handleDownloadExcel(id) {
    try {
      const { blob, filename } = await api.downloadOrdenCompraExcel(id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Error al exportar Excel: " + err.message);
    }
  }

  async function handleUploadSubmit(e) {
    e.preventDefault();
    if (!uploadFile) {
      alert("Por favor selecciona un archivo Excel (.xlsx, .xls) o CSV.");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('etapa', uploadEtapa);
      if (uploadOcNum.trim()) formData.append('numero_oc', uploadOcNum.trim());
      if (uploadCliente.trim()) formData.append('cliente', uploadCliente.trim());
      if (uploadFechaPedido) formData.append('fecha_pedido', uploadFechaPedido);
      if (uploadFechaEntrega) formData.append('fecha_entrega', uploadFechaEntrega);

      const res = await api.uploadOrdenCompra(formData);
      alert(res.msg || "Orden de compra procesada con éxito.");
      setShowUploadModal(false);
      setUploadFile(null);
      setUploadOcNum('');
      setUploadCliente('');
      setUploadFechaPedido('');
      setUploadFechaEntrega('');
      loadOcs();
      if (res.oc_id) {
        handleOpenDetail(res.oc_id);
      }
    } catch (err) {
      alert("Error al procesar archivo: " + err.message);
    } finally {
      setUploading(false);
    }
  }

  // Métricas globales
  const totalOcs = ocs.length;
  const totalUdsPed = ocs.reduce((acc, o) => acc + (Number(o.total_pedido_uds) || 0), 0);
  const totalUdsDesp = ocs.reduce((acc, o) => acc + (Number(o.total_despachado_uds) || 0), 0);
  const cumplimientoGlobal = totalUdsPed > 0 ? (totalUdsDesp / totalUdsPed * 100).toFixed(1) : '100.0';
  const totalQuiebres = ocs.reduce((acc, o) => acc + (Number(o.quiebres_count) || 0), 0);
  const totalDesbalances = ocs.reduce((acc, o) => acc + (Number(o.desbalance_familiar_count) || 0), 0);

  // Filtrado de lista
  const filteredOcs = ocs.filter(o => {
    if (filterEtapa !== 'ALL' && o.etapa !== filterEtapa) return false;
    if (filterAlertas === 'QUIEBRES' && (o.quiebres_count || 0) === 0) return false;
    if (filterAlertas === 'DESBALANCE' && (o.desbalance_familiar_count || 0) === 0) return false;
    if (filterAlertas === 'INCOMPLETAS' && (Number(o.cumplimiento_pct) >= 100)) return false;

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const numMatch = (o.numero_oc || '').toLowerCase().includes(term);
      const cliMatch = (o.cliente || '').toLowerCase().includes(term);
      const fileMatch = (o.nombre_archivo || '').toLowerCase().includes(term);
      if (!numMatch && !cliMatch && !fileMatch) return false;
    }
    return true;
  });

  // Métricas y filtrado de histórico de quiebres por casillas
  const countActivos = quiebresHistory.filter(q => {
    const est = String(q.estado_producto || '').toUpperCase();
    return !est.includes('DESCONTINUAD') && !est.includes('INACTIV') && !est.includes('BLOQUEAD');
  }).length;

  const countBloqueados = quiebresHistory.filter(q => {
    const est = String(q.estado_producto || '').toUpperCase();
    return est.includes('BLOQUEAD');
  }).length;

  const countDescontinuados = quiebresHistory.filter(q => {
    const est = String(q.estado_producto || '').toUpperCase();
    return est.includes('DESCONTINUAD') || est.includes('INACTIV');
  }).length;

  const filteredQuiebres = quiebresHistory.filter(q => {
    const est = String(q.estado_producto || '').toUpperCase();
    const isDesc = est.includes('DESCONTINUAD') || est.includes('INACTIV');
    const isBloq = est.includes('BLOQUEAD');
    const isAct = !isDesc && !isBloq;

    if (isDesc && !filterCatalogStates.DESCONTINUADO) return false;
    if (isBloq && !filterCatalogStates.BLOQUEADO) return false;
    if (isAct && !filterCatalogStates.ACTIVO) return false;
    return true;
  });

  return (
    <div className="content-area">
      <div className="main-panel" style={{ padding: '20px 24px', maxWidth: '100%', margin: 0, width: '100%' }}>
        
        {/* ── HEADER PRINCIPAL ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.8rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px' }}>
              📄 Auditoría de Órdenes de Compra
            </h1>
            <p style={{ margin: '6px 0 0', color: '#888', fontSize: '0.9rem' }}>
              Control de pedidos vs despachos reales, detección de quiebres, seguimiento de recuperación y desbalances familiares.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button 
              className="btn-primary"
              style={{ padding: '10px 20px', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
              onClick={() => setShowUploadModal(true)}
            >
              <span style={{ fontSize: '1.2rem' }}>⬆</span> Subir Orden de Compra
            </button>
          </div>
        </div>

        {/* ── TARJETAS DE MÉTRICAS (KPIs) ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #1976d2' }}>
            <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Órdenes Totales</span>
            <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#1976d2' }}>{totalOcs}</div>
            <span style={{ fontSize: '0.8rem', color: '#666' }}>{totalUdsPed.toLocaleString()} uds pedidas</span>
          </div>

          <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #2e7d32' }}>
            <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Cumplimiento Despacho</span>
            <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: Number(cumplimientoGlobal) >= 95 ? '#2e7d32' : '#ed6c02' }}>
              {cumplimientoGlobal}%
            </div>
            <span style={{ fontSize: '0.8rem', color: '#666' }}>{totalUdsDesp.toLocaleString()} uds entregadas</span>
          </div>

          <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #d32f2f' }}>
            <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Quiebres (No Despachados)</span>
            <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#d32f2f' }}>{totalQuiebres}</div>
            <span style={{ fontSize: '0.8rem', color: '#888' }}>Líneas con 0 unidades despachadas</span>
          </div>

          <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #9c27b0' }}>
            <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Desbalances Familiares</span>
            <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#9c27b0' }}>{totalDesbalances}</div>
            <span style={{ fontSize: '0.8rem', color: '#888' }}>Hermanos despachados vs no despachados</span>
          </div>
        </div>

        {/* ── NAVEGACIÓN DE VISTAS ── */}
        <div style={{ display: 'flex', gap: '20px', borderBottom: '2px solid #333', marginBottom: '20px' }}>
          <button
            style={{
              background: 'none', border: 'none', padding: '10px 16px', cursor: 'pointer',
              fontSize: '1rem', fontWeight: 600,
              color: activeTab === 'list' ? '#1976d2' : '#888',
              borderBottom: activeTab === 'list' ? '3px solid #1976d2' : 'none'
            }}
            onClick={() => setActiveTab('list')}
          >
            📋 Listado de Órdenes de Compra ({ocs.length})
          </button>
          <button
            style={{
              background: 'none', border: 'none', padding: '10px 16px', cursor: 'pointer',
              fontSize: '1rem', fontWeight: 600,
              color: activeTab === 'quiebres' ? '#1976d2' : '#888',
              borderBottom: activeTab === 'quiebres' ? '3px solid #1976d2' : 'none'
            }}
            onClick={() => {
              setActiveTab('quiebres');
              loadQuiebres();
            }}
          >
            ⏱ Auditoría Histórica de Quiebres y Tiempo de Recuperación
          </button>
        </div>

        {error && <div className="alert-error" style={{ marginBottom: '16px', color: '#d32f2f' }}>{error}</div>}

        {/* ── TAB 1: LISTADO DE OCS ── */}
        {activeTab === 'list' && (
          <div className="card" style={{ padding: '20px' }}>
            
            {/* Filtros */}
            <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
              <input
                type="text"
                placeholder="🔍 Buscar por N° OC, cliente o archivo..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                style={{ flex: 1, minWidth: '220px', padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a', fontSize: '0.9rem', outline: 'none' }}
              />

              <select
                value={filterEtapa}
                onChange={e => setFilterEtapa(e.target.value)}
                style={{ padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a', fontSize: '0.9rem', fontWeight: 500, outline: 'none' }}
              >
                <option value="ALL">Todas las Etapas</option>
                <option value="ENTREGA">Solo Entregas (Auditoría)</option>
                <option value="PEDIDO">Solo Pedidos (Opcional)</option>
              </select>

              <select
                value={filterAlertas}
                onChange={e => setFilterAlertas(e.target.value)}
                style={{ padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a', fontSize: '0.9rem', fontWeight: 500, outline: 'none' }}
              >
                <option value="ALL">Todas las Alertas</option>
                <option value="QUIEBRES">Con Quiebres (No despachados)</option>
                <option value="DESBALANCE">Con Desbalance Familiar</option>
                <option value="INCOMPLETAS">Cumplimiento &lt; 100%</option>
              </select>
            </div>

            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#64748b', fontWeight: 500 }}>Cargando órdenes de compra...</div>
            ) : filteredOcs.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
                <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '10px' }}>📭</span>
                No se encontraron órdenes de compra registradas. Sube un archivo Excel/CSV para comenzar la auditoría.
              </div>
            ) : (
              <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid #cbd5e1' }}>
                <table className="table" style={{ width: '100%', minWidth: '1050px', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                  <thead>
                    <tr style={{ background: '#1e293b', textAlign: 'left', borderBottom: '2px solid #0f172a' }}>
                      <th style={{ padding: '12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>N° OC</th>
                      <th style={{ padding: '12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cliente</th>
                      <th style={{ padding: '12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Etapa</th>
                      <th style={{ padding: '12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Fecha</th>
                      <th style={{ padding: '12px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Items</th>
                      <th style={{ padding: '12px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Pedido</th>
                      <th style={{ padding: '12px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Despachado</th>
                      <th style={{ padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cumplimiento</th>
                      <th style={{ padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Alertas Auditoría</th>
                      <th style={{ padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredOcs.map(oc => {
                      const cump = Number(oc.cumplimiento_pct) || 0;
                      return (
                        <tr key={oc.id} style={{ borderBottom: '1px solid #e2e8f0', background: '#ffffff' }}>
                          <td style={{ padding: '12px', fontWeight: 700, whiteSpace: 'nowrap' }}>
                            <span 
                              style={{ color: '#0284c7', cursor: 'pointer', textDecoration: 'underline' }}
                              onClick={() => handleOpenDetail(oc.id, oc.numero_oc)}
                            >
                              {oc.numero_oc}
                            </span>
                          </td>
                          <td style={{ padding: '12px', color: '#0f172a', fontWeight: 500, whiteSpace: 'nowrap' }}>{oc.cliente || '—'}</td>
                          <td style={{ padding: '12px', whiteSpace: 'nowrap' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                              <span style={{
                                padding: '3px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 700,
                                background: oc.etapa === 'ENTREGA' ? '#ecfdf5' : '#eff6ff',
                                color: oc.etapa === 'ENTREGA' ? '#15803d' : '#1d4ed8',
                                border: `1px solid ${oc.etapa === 'ENTREGA' ? '#86efac' : '#93c5fd'}`
                              }}>
                                {oc.etapa}
                              </span>
                              {oc.estado_oc && (
                                <span style={{
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 600,
                                  background: oc.estado_oc.includes('RECE') ? '#dcfce7' : (oc.estado_oc.includes('CURS') ? '#fef3c7' : '#f1f5f9'),
                                  color: oc.estado_oc.includes('RECE') ? '#166534' : (oc.estado_oc.includes('CURS') ? '#92400e' : '#475569'),
                                  border: `1px solid ${oc.estado_oc.includes('RECE') ? '#bbf7d0' : (oc.estado_oc.includes('CURS') ? '#fde68a' : '#cbd5e1')}`
                                }}>
                                  {oc.estado_oc}
                                </span>
                              )}
                            </div>
                          </td>
                          <td style={{ padding: '12px', color: '#475569', fontSize: '0.85rem', whiteSpace: 'nowrap' }}>
                            {formatCleanDate(oc.fecha_entrega || oc.fecha_pedido || oc.fecha_carga)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right', color: '#334155', fontWeight: 600 }}>{oc.total_items}</td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600, color: '#334155' }}>
                            {Math.round(oc.total_pedido_uds).toLocaleString()}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#15803d' }}>
                            {Math.round(oc.total_despachado_uds).toLocaleString()}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                              <span style={{
                                fontWeight: 800,
                                color: cump >= 100 ? '#15803d' : (cump >= 85 ? '#d97706' : '#dc2626')
                              }}>
                                {cump}%
                              </span>
                              <div style={{ width: '45px', height: '6px', background: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
                                <div style={{
                                  width: `${Math.min(cump, 100)}%`, height: '100%',
                                  background: cump >= 100 ? '#16a34a' : (cump >= 85 ? '#f59e0b' : '#ef4444')
                                }} />
                              </div>
                            </div>
                          </td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', flexWrap: 'wrap' }}>
                              {(oc.quiebres_count > 0) && (
                                <span style={{
                                  background: 'rgba(244, 67, 54, 0.2)', color: '#ff5252', border: '1px solid #d32f2f',
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600
                                }} title={`${oc.quiebres_count} productos no despachados`}>
                                  🚨 {oc.quiebres_count} quiebres
                                </span>
                              )}
                              {(oc.desbalance_familiar_count > 0) && (
                                <span style={{
                                  background: 'rgba(156, 39, 176, 0.2)', color: '#ba68c8', border: '1px solid #9c27b0',
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600
                                }} title={`${oc.desbalance_familiar_count} casos de desbalance en familia`}>
                                  ⚖️ Desbalance
                                </span>
                              )}
                              {oc.quiebres_count === 0 && oc.desbalance_familiar_count === 0 && (
                                <span style={{ color: '#4caf50', fontSize: '0.8rem' }}>✓ OK</span>
                              )}
                            </div>
                          </td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                              <button
                                className="btn-secondary"
                                style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                                onClick={() => handleOpenDetail(oc.id, oc.numero_oc)}
                                title="Ver Auditoría Detallada"
                              >
                                👁 Ver
                              </button>
                              <button
                                className="btn-secondary"
                                style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                                onClick={() => handleDownloadExcel(oc.id)}
                                title="Descargar Excel"
                              >
                                📥
                              </button>
                              <button
                                style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', padding: '4px' }}
                                onClick={() => handleDeleteOc(oc.id, oc.numero_oc)}
                                title="Eliminar"
                              >
                                🗑
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── TAB 2: AUDITORÍA HISTÓRICA DE QUIEBRES Y RECUPERACIÓN ── */}
        {activeTab === 'quiebres' && (
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
              <div>
                <h2 style={{ margin: '0 0 6px', fontSize: '1.25rem', color: '#ff5252', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>🚨</span> Registro Consolidado de Quiebres y Tiempos de Recuperación
                </h2>
                <p style={{ margin: 0, color: '#475569', fontSize: '0.85rem' }}>
                  Muestra todos los productos que sufrieron quiebre (pedido &gt; 0 con 0 despachado), en qué OC posterior se volvió a despachar y cuántos días tardó la recuperación.
                </p>
              </div>

              {/* Filtro por Estado de Catálogo con Casillas (Checkboxes) */}
              <div style={{
                display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap',
                background: '#f8fafc', padding: '8px 14px', borderRadius: '8px', border: '1px solid #cbd5e1'
              }}>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#1e293b' }}>
                  Filtrar Catálogo:
                </span>

                {/* Casilla Activo */}
                <label style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer',
                  padding: '4px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600,
                  background: filterCatalogStates.ACTIVO ? '#f0fdf4' : '#ffffff',
                  border: `1.5px solid ${filterCatalogStates.ACTIVO ? '#86efac' : '#cbd5e1'}`,
                  color: filterCatalogStates.ACTIVO ? '#166534' : '#64748b',
                  userSelect: 'none'
                }}>
                  <input
                    type="checkbox"
                    checked={filterCatalogStates.ACTIVO}
                    onChange={e => setFilterCatalogStates(prev => ({ ...prev, ACTIVO: e.target.checked }))}
                    style={{ cursor: 'pointer', accentColor: '#16a34a' }}
                  />
                  ✓ Activos ({countActivos})
                </label>

                {/* Casilla Bloqueado */}
                <label style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer',
                  padding: '4px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700,
                  background: filterCatalogStates.BLOQUEADO ? '#faf5ff' : '#ffffff',
                  border: `1.5px solid ${filterCatalogStates.BLOQUEADO ? '#d8b4fe' : '#cbd5e1'}`,
                  color: filterCatalogStates.BLOQUEADO ? '#6b21a8' : '#64748b',
                  userSelect: 'none'
                }}>
                  <input
                    type="checkbox"
                    checked={filterCatalogStates.BLOQUEADO}
                    onChange={e => setFilterCatalogStates(prev => ({ ...prev, BLOQUEADO: e.target.checked }))}
                    style={{ cursor: 'pointer', accentColor: '#9333ea' }}
                  />
                  🔒 Bloqueados ({countBloqueados})
                </label>

                {/* Casilla Descontinuado (Por default desmarcado) */}
                <label style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer',
                  padding: '4px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700,
                  background: filterCatalogStates.DESCONTINUADO ? '#fff1f2' : '#ffffff',
                  border: `1.5px solid ${filterCatalogStates.DESCONTINUADO ? '#fca5a5' : '#cbd5e1'}`,
                  color: filterCatalogStates.DESCONTINUADO ? '#991b1b' : '#64748b',
                  userSelect: 'none'
                }}>
                  <input
                    type="checkbox"
                    checked={filterCatalogStates.DESCONTINUADO}
                    onChange={e => setFilterCatalogStates(prev => ({ ...prev, DESCONTINUADO: e.target.checked }))}
                    style={{ cursor: 'pointer', accentColor: '#dc2626' }}
                  />
                  🚫 Descontinuados ({countDescontinuados})
                </label>

                <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600, marginLeft: '6px' }}>
                  ({filteredQuiebres.length} visibles)
                </span>
              </div>
            </div>

            {quiebresLoading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>Cargando histórico de quiebres...</div>
            ) : quiebresHistory.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '10px' }}>🎉</span>
                No se han detectado quiebres de producto en las órdenes de compra analizadas.
              </div>
            ) : (
              <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid #cbd5e1', width: '100%' }}>
                <table className="table" style={{ width: '100%', minWidth: '1050px', borderCollapse: 'collapse', fontSize: '0.84rem' }}>
                  <thead>
                    <tr style={{ background: '#1e293b', textAlign: 'left', borderBottom: '2px solid #0f172a' }}>
                      <th style={{ padding: '9px 10px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>SKU</th>
                      <th style={{ padding: '9px 10px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cód. Femaco</th>
                      <th style={{ padding: '9px 10px', color: '#ffffff', fontWeight: 600, minWidth: '180px' }}>Producto</th>
                      <th style={{ padding: '9px 8px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Estado Catálogo</th>
                      <th style={{ padding: '9px 8px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Familia</th>
                      <th style={{ padding: '9px 8px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>OC Quiebre</th>
                      <th style={{ padding: '9px 8px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Fecha Quiebre</th>
                      <th style={{ padding: '9px 10px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cant. Pedida</th>
                      <th style={{ padding: '9px 8px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>OC Recup.</th>
                      <th style={{ padding: '9px 8px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Fecha Recup.</th>
                      <th style={{ padding: '9px 8px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Tiempo</th>
                      <th style={{ padding: '9px 10px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Estado Despacho</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredQuiebres.length === 0 ? (
                      <tr>
                        <td colSpan="12" style={{ padding: '30px', textAlign: 'center', color: '#64748b' }}>
                          No hay productos para los estados seleccionados. Marca alguna de las casillas de arriba para visualizarlos.
                        </td>
                      </tr>
                    ) : (
                      filteredQuiebres.map((q, idx) => {
                        const recuperado = Boolean(q.oc_recuperacion);
                        const est = String(q.estado_producto || '').toUpperCase();
                        const isDescontinuado = est.includes('DESCONTINUAD') || est.includes('INACTIV');
                        const isBloqueado = est.includes('BLOQUEAD');

                        const rowBg = isDescontinuado ? '#fff1f2' : (isBloqueado ? '#faf5ff' : '#ffffff');
                        const borderLeft = isDescontinuado ? '4px solid #ef4444' : (isBloqueado ? '4px solid #a855f7' : '4px solid transparent');

                        return (
                          <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0', background: rowBg }}>
                            <td style={{ padding: '8px 10px', fontWeight: 700, color: '#0284c7', borderLeft: borderLeft, whiteSpace: 'nowrap' }}>
                              {q.sku || '—'}
                            </td>
                            <td style={{ padding: '8px 10px', fontWeight: 700, color: '#334155', whiteSpace: 'nowrap' }}>
                              <span style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.8rem' }}>
                                {q.codigo_femaco || '—'}
                              </span>
                            </td>
                            <td style={{ padding: '8px 10px', color: '#0f172a', fontWeight: 500, minWidth: '180px', lineHeight: '1.25' }}>
                              {q.nombre_producto}
                            </td>
                            <td style={{ padding: '8px 6px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                              {isDescontinuado ? (
                                <span style={{
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 800,
                                  background: '#fee2e2', color: '#991b1b', border: '1px solid #fca5a5', display: 'inline-block', whiteSpace: 'nowrap'
                                }}>
                                  🚫 DESCONTINUADO
                                </span>
                              ) : isBloqueado ? (
                                <span style={{
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 800,
                                  background: '#f3e8ff', color: '#6b21a8', border: '1px solid #d8b4fe', display: 'inline-block', whiteSpace: 'nowrap'
                                }}>
                                  🔒 BLOQUEADO
                                </span>
                              ) : (
                                <span style={{
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 600,
                                  background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0', display: 'inline-block', whiteSpace: 'nowrap'
                                }}>
                                  ✓ ACTIVO
                                </span>
                              )}
                            </td>
                            <td style={{ padding: '8px 8px', color: '#475569', whiteSpace: 'nowrap' }}>{q.nombre_familia || '—'}</td>
                            <td style={{ padding: '8px 8px', fontWeight: 600, color: '#334155', whiteSpace: 'nowrap' }}>{q.numero_oc}</td>
                            <td style={{ padding: '8px 8px', color: '#dc2626', fontWeight: 600, whiteSpace: 'nowrap' }}>
                              {formatCleanDate(q.fecha_quiebre || q.fecha_oc)}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: '#dc2626', whiteSpace: 'nowrap' }}>
                              {Math.round(q.cantidad_pedida).toLocaleString()}
                            </td>
                            <td style={{ padding: '8px 8px', fontWeight: 600, color: recuperado ? '#15803d' : '#64748b', whiteSpace: 'nowrap' }}>
                              {q.oc_recuperacion || '—'}
                            </td>
                            <td style={{ padding: '8px 8px', color: '#15803d', fontWeight: 600, whiteSpace: 'nowrap' }}>
                              {formatCleanDate(q.fecha_recuperacion)}
                            </td>
                            <td style={{ padding: '8px 8px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                              {recuperado ? (
                                <span style={{ fontWeight: 700, color: '#0284c7', whiteSpace: 'nowrap' }}>
                                  ⏱ {q.dias_recuperacion_quiebre} d
                                </span>
                              ) : (
                                <span style={{ color: '#d97706', fontStyle: 'italic', fontWeight: 600, whiteSpace: 'nowrap' }}>
                                  Sin recuperar
                                </span>
                              )}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                              {recuperado ? (
                                <span style={{
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 700,
                                  background: '#ecfdf5', color: '#15803d', border: '1px solid #86efac', display: 'inline-block', whiteSpace: 'nowrap'
                                }}>
                                  ✓ Recuperado
                                </span>
                              ) : (
                                <span style={{
                                  padding: '2px 6px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 700,
                                  background: '#fef2f2', color: '#b91c1c', border: '1px solid #fca5a5', display: 'inline-block', whiteSpace: 'nowrap'
                                }}>
                                  ⚠️ Quiebre Activo
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── MODAL: SUBIR ORDEN DE COMPRA ── */}
        {showUploadModal && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.85)', zIndex: 9999,
            display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '20px'
          }}>
            <div style={{
              background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '12px',
              maxWidth: '550px', width: '100%', padding: '28px', boxShadow: '0 12px 40px rgba(0,0,0,0.25)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0, fontSize: '1.3rem', display: 'flex', alignItems: 'center', gap: '8px', color: '#0f172a', fontWeight: 700 }}>
                  <span>⬆</span> Subir Orden de Compra
                </h2>
                <button
                  style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '1.5rem', cursor: 'pointer', fontWeight: 700 }}
                  onClick={() => setShowUploadModal(false)}
                >
                  ×
                </button>
              </div>

              <form onSubmit={handleUploadSubmit}>
                {/* Selector de Etapa */}
                <div style={{ marginBottom: '18px' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#334155', marginBottom: '8px', fontWeight: 600 }}>
                    Modo de Procesamiento / Etapa:
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
                    <div
                      style={{
                        padding: '10px', borderRadius: '8px', border: `2px solid ${uploadEtapa === 'AUTO' ? '#0284c7' : '#cbd5e1'}`,
                        background: uploadEtapa === 'AUTO' ? '#f0f9ff' : '#f8fafc',
                        cursor: 'pointer', textAlign: 'center'
                      }}
                      onClick={() => setUploadEtapa('AUTO')}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.85rem', color: uploadEtapa === 'AUTO' ? '#0369a1' : '#475569' }}>
                        ⭐ AUTO (B2B Retail)
                      </div>
                      <span style={{ fontSize: '0.72rem', color: '#64748b' }}>Lee Estado OC (Cursado/Recepción)</span>
                    </div>

                    <div
                      style={{
                        padding: '10px', borderRadius: '8px', border: `2px solid ${uploadEtapa === 'ENTREGA' ? '#16a34a' : '#cbd5e1'}`,
                        background: uploadEtapa === 'ENTREGA' ? '#ecfdf5' : '#f8fafc',
                        cursor: 'pointer', textAlign: 'center'
                      }}
                      onClick={() => setUploadEtapa('ENTREGA')}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.85rem', color: uploadEtapa === 'ENTREGA' ? '#15803d' : '#475569' }}>
                        🚚 Solo Entregas
                      </div>
                      <span style={{ fontSize: '0.72rem', color: '#64748b' }}>Auditoría vs pedido</span>
                    </div>

                    <div
                      style={{
                        padding: '10px', borderRadius: '8px', border: `2px solid ${uploadEtapa === 'PEDIDO' ? '#2563eb' : '#cbd5e1'}`,
                        background: uploadEtapa === 'PEDIDO' ? '#eff6ff' : '#f8fafc',
                        cursor: 'pointer', textAlign: 'center'
                      }}
                      onClick={() => setUploadEtapa('PEDIDO')}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.85rem', color: uploadEtapa === 'PEDIDO' ? '#1d4ed8' : '#475569' }}>
                        📝 Solo Pedidos
                      </div>
                      <span style={{ fontSize: '0.72rem', color: '#64748b' }}>Registro inicial (Cursado)</span>
                    </div>
                  </div>
                </div>

                {/* Archivo */}
                <div style={{ marginBottom: '18px' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#334155', marginBottom: '6px', fontWeight: 600 }}>
                    Archivo Excel o CSV:
                  </label>
                  <input
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    onChange={e => setUploadFile(e.target.files[0] || null)}
                    style={{
                      width: '100%', padding: '12px', background: '#f8fafc', border: '1.5px dashed #94a3b8',
                      borderRadius: '8px', color: '#0f172a', cursor: 'pointer'
                    }}
                    required
                  />
                  <span style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px', display: 'block' }}>
                    Soporta archivos mensuales con múltiples OCs (Sodimac / Falabella B2B), consolidando locales por SKU y distinguiendo pedidos cursados de recepcionados.
                  </span>
                </div>

                {/* Campos Opcionales */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '18px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#475569', marginBottom: '4px', fontWeight: 600 }}>
                      N° OC (Opcional):
                    </label>
                    <input
                      type="text"
                      placeholder="Auto si está en archivo"
                      value={uploadOcNum}
                      onChange={e => setUploadOcNum(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a' }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#475569', marginBottom: '4px', fontWeight: 600 }}>
                      Cliente (Opcional):
                    </label>
                    <input
                      type="text"
                      placeholder="Cliente / Razón Social"
                      value={uploadCliente}
                      onChange={e => setUploadCliente(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a' }}
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '24px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#475569', marginBottom: '4px', fontWeight: 600 }}>
                      Fecha Pedido (Opcional):
                    </label>
                    <input
                      type="date"
                      value={uploadFechaPedido}
                      onChange={e => setUploadFechaPedido(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a' }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#475569', marginBottom: '4px', fontWeight: 600 }}>
                      Fecha Entrega / Despacho:
                    </label>
                    <input
                      type="date"
                      value={uploadFechaEntrega}
                      onChange={e => setUploadFechaEntrega(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a' }}
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setShowUploadModal(false)}
                    disabled={uploading}
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={uploading}
                    style={{ padding: '10px 24px', cursor: 'pointer' }}
                  >
                    {uploading ? "Procesando..." : "Subir y Analizar"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ── MODAL / DETALLE DE AUDITORÍA DE OC ── */}
        {selectedOcId && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.85)', zIndex: 9999,
            display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '20px'
          }}>
            <div style={{
              background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '12px',
              maxWidth: '1200px', width: '100%', maxHeight: '90vh', display: 'flex', flexDirection: 'column',
              boxShadow: '0 12px 40px rgba(0,0,0,0.3)', overflow: 'hidden'
            }}>
              {/* Header Modal */}
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc' }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.4rem', display: 'flex', alignItems: 'center', gap: '10px', color: '#0f172a', fontWeight: 700 }}>
                    <span>Auditoría OC:</span>
                    <span style={{ color: '#0284c7' }}>{detailData?.header?.numero_oc || selectedOcNumero || (detailLoading ? 'Cargando...' : selectedOcId)}</span>
                    <span style={{
                      fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px', fontWeight: 700,
                      background: detailData?.header?.etapa === 'ENTREGA' ? '#ecfdf5' : '#eff6ff',
                      color: detailData?.header?.etapa === 'ENTREGA' ? '#15803d' : '#1d4ed8',
                      border: `1px solid ${detailData?.header?.etapa === 'ENTREGA' ? '#86efac' : '#93c5fd'}`
                    }}>
                      {detailData?.header?.etapa}
                    </span>
                    {detailData?.header?.estado_oc && (
                      <span style={{
                        fontSize: '0.72rem', padding: '3px 7px', borderRadius: '4px', fontWeight: 600,
                        background: detailData.header.estado_oc.includes('RECE') ? '#dcfce7' : '#fef3c7',
                        color: detailData.header.estado_oc.includes('RECE') ? '#166534' : '#92400e',
                        border: `1px solid ${detailData.header.estado_oc.includes('RECE') ? '#bbf7d0' : '#fde68a'}`
                      }}>
                        {detailData.header.estado_oc}
                      </span>
                    )}
                  </h2>
                  <div style={{ fontSize: '0.85rem', color: '#475569', marginTop: '4px' }}>
                    Cliente: <strong>{detailData?.header?.cliente || '—'}</strong> | Fecha Entrega: <strong>{detailData?.header?.fecha_entrega || '—'}</strong> | Archivo: {detailData?.header?.nombre_archivo}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <button
                    className="btn-secondary"
                    style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                    onClick={() => handleDownloadExcel(selectedOcId)}
                  >
                    📥 Descargar Excel
                  </button>
                  <button
                    style={{ background: 'none', border: 'none', color: '#888', fontSize: '1.8rem', cursor: 'pointer', lineHeight: 1 }}
                    onClick={() => { setSelectedOcId(null); setDetailData(null); }}
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Contenido Modal */}
              <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
                {detailLoading ? (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>Cargando análisis...</div>
                ) : !detailData ? (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>No se pudo cargar la información.</div>
                ) : (
                  <>
                    {/* Tarjetas resumen de auditoría */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '20px' }}>
                      <div style={{ background: '#ffffff', padding: '14px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                        <span style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>Total Pedido</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a' }}>
                          {Math.round(detailData.header.total_pedido_uds).toLocaleString()} <span style={{ fontSize: '0.8rem', fontWeight: 500, color: '#64748b' }}>uds</span>
                        </div>
                      </div>

                      <div style={{ background: '#ffffff', padding: '14px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                        <span style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>Total Despachado</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#15803d' }}>
                          {Math.round(detailData.header.total_despachado_uds).toLocaleString()} <span style={{ fontSize: '0.8rem', fontWeight: 500, color: '#64748b' }}>uds</span>
                        </div>
                      </div>

                      <div style={{ background: '#ffffff', padding: '14px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                        <span style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>Cumplimiento</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: Number(detailData.header.cumplimiento_pct) >= 100 ? '#15803d' : '#d97706' }}>
                          {detailData.header.cumplimiento_pct}%
                        </div>
                      </div>

                      <div style={{ background: '#ffffff', padding: '14px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                        <span style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>No Despachados (Quiebres)</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#b91c1c' }}>
                          {detailData.header.quiebres_count}
                        </div>
                      </div>

                      <div style={{ background: '#ffffff', padding: '14px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                        <span style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>Desbalance Familiar</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#7e22ce' }}>
                          {detailData.header.desbalance_familiar_count}
                        </div>
                      </div>
                    </div>

                    {/* Filtros de la tabla de items */}
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
                      <button
                        className={detailFilter === 'ALL' ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                        onClick={() => setDetailFilter('ALL')}
                      >
                        Todos ({detailData.items.length})
                      </button>
                      <button
                        className={detailFilter === 'NO_DESPACHADO' ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 12px', fontSize: '0.8rem', color: detailFilter === 'NO_DESPACHADO' ? '#fff' : '#b91c1c' }}
                        onClick={() => setDetailFilter('NO_DESPACHADO')}
                      >
                        🚨 No Despachados (0) ({detailData.items.filter(i => i.estado_entrega === 'NO_DESPACHADO').length})
                      </button>
                      <button
                        className={detailFilter === 'PARCIAL' ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 12px', fontSize: '0.8rem', color: detailFilter === 'PARCIAL' ? '#fff' : '#b45309' }}
                        onClick={() => setDetailFilter('PARCIAL')}
                      >
                        ⚠️ Despacho Parcial ({detailData.items.filter(i => i.estado_entrega === 'DESPACHO_PARCIAL').length})
                      </button>
                      <button
                        className={detailFilter === 'DESBALANCE' ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 12px', fontSize: '0.8rem', color: detailFilter === 'DESBALANCE' ? '#fff' : '#7e22ce' }}
                        onClick={() => setDetailFilter('DESBALANCE')}
                      >
                        ⚖️ Desbalance Familiar ({detailData.items.filter(i => i.desbalance_familiar).length})
                      </button>
                    </div>

                    {/* Tabla de Detalle */}
                    <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid #cbd5e1' }}>
                      <table className="table" style={{ width: '100%', minWidth: '1200px', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                        <thead>
                          <tr style={{ background: '#1e293b', textAlign: 'left', borderBottom: '2px solid #0f172a' }}>
                            <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>SKU</th>
                            <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cód. Femaco</th>
                            <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600, minWidth: '200px' }}>Producto</th>
                            <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Familia</th>
                            <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cant. Pedida</th>
                            <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Cant. Despachada</th>
                            <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Diferencia</th>
                            <th style={{ padding: '10px 12px', textAlign: 'center', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Estado</th>
                            <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Desbalance Familiar</th>
                            <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600, whiteSpace: 'nowrap' }}>Historial Quiebre / Recuperación</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detailData.items
                            .filter(it => {
                              if (detailFilter === 'NO_DESPACHADO') return it.estado_entrega === 'NO_DESPACHADO';
                              if (detailFilter === 'PARCIAL') return it.estado_entrega === 'DESPACHO_PARCIAL';
                              if (detailFilter === 'DESBALANCE') return it.desbalance_familiar;
                              return true;
                            })
                            .map((it, idx) => {
                              const isQuiebre = it.estado_entrega === 'NO_DESPACHADO';
                              const isParcial = it.estado_entrega === 'DESPACHO_PARCIAL';
                              const isCompleto = it.estado_entrega === 'COMPLETO';
                              const isExcedente = it.estado_entrega === 'EXCEDENTE';

                              return (
                                <tr key={idx} style={{
                                  borderBottom: '1px solid #e2e8f0',
                                  background: isQuiebre ? '#fff5f5' : (it.desbalance_familiar ? '#faf5ff' : '#ffffff')
                                }}>
                                  <td style={{ padding: '10px 12px', fontWeight: 700, color: '#0284c7', whiteSpace: 'nowrap' }}>
                                    {it.sku || '—'}
                                  </td>
                                  <td style={{ padding: '10px 12px', fontWeight: 700, color: '#334155', whiteSpace: 'nowrap' }}>
                                    <span style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.8rem' }}>
                                      {it.codigo_femaco || '—'}
                                    </span>
                                  </td>
                                  <td style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 500, minWidth: '200px', maxWidth: '320px', whiteSpace: 'normal', lineHeight: '1.3' }}>
                                    {it.nombre_producto}
                                    {it.estado_producto && String(it.estado_producto).toUpperCase().includes('DESCONTINUAD') && (
                                      <span style={{ marginLeft: '6px', padding: '1px 5px', borderRadius: '3px', fontSize: '0.68rem', fontWeight: 700, background: '#fee2e2', color: '#991b1b', border: '1px solid #fca5a5', whiteSpace: 'nowrap' }}>
                                        🚫 DESCONTINUADO
                                      </span>
                                    )}
                                    {it.estado_producto && String(it.estado_producto).toUpperCase().includes('BLOQUEAD') && (
                                      <span style={{ marginLeft: '6px', padding: '1px 5px', borderRadius: '3px', fontSize: '0.68rem', fontWeight: 700, background: '#f3e8ff', color: '#6b21a8', border: '1px solid #d8b4fe', whiteSpace: 'nowrap' }}>
                                        🔒 BLOQUEADO
                                      </span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px 12px', color: '#475569', whiteSpace: 'nowrap' }}>{it.nombre_familia || '—'}</td>
                                  <td style={{ padding: '10px 12px', textAlign: 'right', color: '#334155', fontWeight: 600, whiteSpace: 'nowrap' }}>
                                    {Math.round(it.cantidad_pedida).toLocaleString()}
                                  </td>
                                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: isQuiebre ? '#dc2626' : '#15803d', whiteSpace: 'nowrap' }}>
                                    {Math.round(it.cantidad_despachada).toLocaleString()}
                                  </td>
                                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: it.diferencia < 0 ? '#dc2626' : '#15803d', whiteSpace: 'nowrap' }}>
                                    {it.diferencia > 0 ? `+${Math.round(it.diferencia)}` : Math.round(it.diferencia)}
                                  </td>
                                  <td style={{ padding: '10px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                                    {isQuiebre && (
                                      <span style={{
                                        background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem', display: 'inline-block', whiteSpace: 'nowrap'
                                      }}>
                                        NO DESPACHADO (0)
                                      </span>
                                    )}
                                    {isParcial && (
                                      <span style={{
                                        background: '#fef3c7', color: '#b45309', border: '1px solid #fcd34d',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem', display: 'inline-block', whiteSpace: 'nowrap'
                                      }}>
                                        PARCIAL
                                      </span>
                                    )}
                                    {isCompleto && (
                                      <span style={{
                                        background: '#ecfdf5', color: '#15803d', border: '1px solid #86efac',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem', display: 'inline-block', whiteSpace: 'nowrap'
                                      }}>
                                        ✓ COMPLETO
                                      </span>
                                    )}
                                    {isExcedente && (
                                      <span style={{
                                        background: '#eff6ff', color: '#1d4ed8', border: '1px solid #93c5fd',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem', display: 'inline-block', whiteSpace: 'nowrap'
                                      }}>
                                        EXCEDENTE (+)
                                      </span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px 12px', color: '#334155', whiteSpace: 'nowrap' }}>
                                    {it.desbalance_familiar ? (
                                      <span style={{
                                        display: 'inline-block', padding: '3px 8px', borderRadius: '4px',
                                        background: '#faf5ff', color: '#7e22ce', border: '1px solid #e9d5ff',
                                        fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap'
                                      }}>
                                        ⚖️ {it.desbalance_detalle || 'Desbalance detectado'}
                                      </span>
                                    ) : (
                                      <span style={{ color: '#94a3b8' }}>—</span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px 12px', fontSize: '0.8rem', color: '#334155', whiteSpace: 'nowrap' }}>
                                    {it.quiebre_detectado ? (
                                      <div style={{ color: '#dc2626' }}>
                                        <strong>⚠️ Quiebre</strong> {it.fecha_quiebre ? `(${formatCleanDate(it.fecha_quiebre)})` : ''}
                                        {it.oc_recuperacion && (
                                          <div style={{ color: '#15803d', fontSize: '0.75rem' }}>
                                            Recuperado en OC {it.oc_recuperacion} ({it.dias_recuperacion_quiebre} días)
                                          </div>
                                        )}
                                      </div>
                                    ) : (
                                      <span style={{ color: '#94a3b8' }}>Normal</span>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
