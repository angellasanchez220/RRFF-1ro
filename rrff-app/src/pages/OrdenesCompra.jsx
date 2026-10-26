import React, { useState, useEffect } from 'react';
import * as api from '../api';

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
  const [uploadEtapa, setUploadEtapa] = useState('ENTREGA');
  const [uploadOcNum, setUploadOcNum] = useState('');
  const [uploadCliente, setUploadCliente] = useState('');
  const [uploadFechaPedido, setUploadFechaPedido] = useState('');
  const [uploadFechaEntrega, setUploadFechaEntrega] = useState('');
  const [uploading, setUploading] = useState(false);

  // Modal de Detalle
  const [selectedOcId, setSelectedOcId] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailFilter, setDetailFilter] = useState('ALL'); // 'ALL' | 'NO_DESPACHADO' | 'PARCIAL' | 'DESBALANCE'

  // Histórico de quiebres
  const [quiebresHistory, setQuiebresHistory] = useState([]);
  const [quiebresLoading, setQuiebresLoading] = useState(false);

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

  async function handleOpenDetail(id) {
    setSelectedOcId(id);
    setDetailLoading(true);
    try {
      const res = await api.fetchOrdenCompraDetail(id);
      setDetailData(res);
      setDetailFilter('ALL');
    } catch (err) {
      alert("Error al cargar auditoría: " + err.message);
      setSelectedOcId(null);
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

  return (
    <div className="content-area">
      <div className="main-panel" style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
        
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
                style={{ flex: 1, minWidth: '220px', padding: '10px', borderRadius: '6px', border: '1px solid #444', background: '#222', color: '#fff' }}
              />

              <select
                value={filterEtapa}
                onChange={e => setFilterEtapa(e.target.value)}
                style={{ padding: '10px', borderRadius: '6px', border: '1px solid #444', background: '#222', color: '#fff' }}
              >
                <option value="ALL">Todas las Etapas</option>
                <option value="ENTREGA">Solo Entregas (Auditoría)</option>
                <option value="PEDIDO">Solo Pedidos (Opcional)</option>
              </select>

              <select
                value={filterAlertas}
                onChange={e => setFilterAlertas(e.target.value)}
                style={{ padding: '10px', borderRadius: '6px', border: '1px solid #444', background: '#222', color: '#fff' }}
              >
                <option value="ALL">Todas las Alertas</option>
                <option value="QUIEBRES">Con Quiebres (No despachados)</option>
                <option value="DESBALANCE">Con Desbalance Familiar</option>
                <option value="INCOMPLETAS">Cumplimiento &lt; 100%</option>
              </select>
            </div>

            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>Cargando órdenes de compra...</div>
            ) : filteredOcs.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '10px' }}>📭</span>
                No se encontraron órdenes de compra registradas. Sube un archivo Excel/CSV para comenzar la auditoría.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                  <thead>
                    <tr style={{ background: '#252525', textAlign: 'left', borderBottom: '2px solid #333' }}>
                      <th style={{ padding: '12px' }}>N° OC</th>
                      <th style={{ padding: '12px' }}>Cliente</th>
                      <th style={{ padding: '12px' }}>Etapa</th>
                      <th style={{ padding: '12px' }}>Fecha</th>
                      <th style={{ padding: '12px', textAlign: 'right' }}>Items</th>
                      <th style={{ padding: '12px', textAlign: 'right' }}>Pedido</th>
                      <th style={{ padding: '12px', textAlign: 'right' }}>Despachado</th>
                      <th style={{ padding: '12px', textAlign: 'center' }}>Cumplimiento</th>
                      <th style={{ padding: '12px', textAlign: 'center' }}>Alertas Auditoría</th>
                      <th style={{ padding: '12px', textAlign: 'center' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredOcs.map(oc => {
                      const cump = Number(oc.cumplimiento_pct) || 0;
                      return (
                        <tr key={oc.id} style={{ borderBottom: '1px solid #333' }}>
                          <td style={{ padding: '12px', fontWeight: 600 }}>
                            <span 
                              style={{ color: '#64b5f6', cursor: 'pointer', textDecoration: 'underline' }}
                              onClick={() => handleOpenDetail(oc.id)}
                            >
                              {oc.numero_oc}
                            </span>
                          </td>
                          <td style={{ padding: '12px', color: '#ccc' }}>{oc.cliente || '—'}</td>
                          <td style={{ padding: '12px' }}>
                            <span style={{
                              padding: '4px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600,
                              background: oc.etapa === 'ENTREGA' ? 'rgba(76, 175, 80, 0.2)' : 'rgba(33, 150, 243, 0.2)',
                              color: oc.etapa === 'ENTREGA' ? '#81c784' : '#64b5f6',
                              border: `1px solid ${oc.etapa === 'ENTREGA' ? '#4caf50' : '#2196f3'}`
                            }}>
                              {oc.etapa}
                            </span>
                          </td>
                          <td style={{ padding: '12px', color: '#999', fontSize: '0.85rem' }}>
                            {oc.fecha_entrega || oc.fecha_pedido || (oc.fecha_carga ? oc.fecha_carga.substring(0, 10) : '—')}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>{oc.total_items}</td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 500 }}>
                            {Math.round(oc.total_pedido_uds).toLocaleString()}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600, color: '#81c784' }}>
                            {Math.round(oc.total_despachado_uds).toLocaleString()}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                              <span style={{
                                fontWeight: 700,
                                color: cump >= 100 ? '#4caf50' : (cump >= 85 ? '#ff9800' : '#f44336')
                              }}>
                                {cump}%
                              </span>
                              <div style={{ width: '45px', height: '6px', background: '#333', borderRadius: '3px', overflow: 'hidden' }}>
                                <div style={{
                                  width: `${Math.min(cump, 100)}%`, height: '100%',
                                  background: cump >= 100 ? '#4caf50' : (cump >= 85 ? '#ff9800' : '#f44336')
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
                                onClick={() => handleOpenDetail(oc.id)}
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
            <div style={{ marginBottom: '16px' }}>
              <h2 style={{ margin: '0 0 6px', fontSize: '1.2rem', color: '#ff5252' }}>
                🚨 Registro Consolidado de Quiebres y Tiempos de Recuperación
              </h2>
              <p style={{ margin: 0, color: '#aaa', fontSize: '0.85rem' }}>
                Muestra todos los productos que sufrieron quiebre (pedido &gt; 0 con 0 despachado), en qué OC posterior se volvió a despachar y cuántos días tardó la recuperación.
              </p>
            </div>

            {quiebresLoading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>Cargando histórico de quiebres...</div>
            ) : quiebresHistory.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
                <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '10px' }}>🎉</span>
                No se han detectado quiebres de producto en las órdenes de compra analizadas.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                  <thead>
                    <tr style={{ background: '#252525', textAlign: 'left', borderBottom: '2px solid #333' }}>
                      <th style={{ padding: '10px' }}>SKU / Código</th>
                      <th style={{ padding: '10px' }}>Producto</th>
                      <th style={{ padding: '10px' }}>Familia</th>
                      <th style={{ padding: '10px' }}>OC Quiebre</th>
                      <th style={{ padding: '10px' }}>Fecha Quiebre</th>
                      <th style={{ padding: '10px', textAlign: 'right' }}>Cant. Pedida (Sin Despacho)</th>
                      <th style={{ padding: '10px' }}>OC Recuperación</th>
                      <th style={{ padding: '10px' }}>Fecha Recuperación</th>
                      <th style={{ padding: '10px', textAlign: 'center' }}>Tiempo Transcurrido</th>
                      <th style={{ padding: '10px', textAlign: 'center' }}>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quiebresHistory.map((q, idx) => {
                      const recuperado = Boolean(q.oc_recuperacion);
                      return (
                        <tr key={idx} style={{ borderBottom: '1px solid #333' }}>
                          <td style={{ padding: '10px', fontWeight: 600, color: '#64b5f6' }}>
                            {q.sku || q.codigo_femaco}
                          </td>
                          <td style={{ padding: '10px' }}>{q.nombre_producto}</td>
                          <td style={{ padding: '10px', color: '#bbb' }}>{q.nombre_familia || '—'}</td>
                          <td style={{ padding: '10px', fontWeight: 500 }}>{q.numero_oc}</td>
                          <td style={{ padding: '10px', color: '#ff8a80' }}>{q.fecha_quiebre || q.fecha_oc || '—'}</td>
                          <td style={{ padding: '10px', textAlign: 'right', fontWeight: 700, color: '#f44336' }}>
                            {Math.round(q.cantidad_pedida).toLocaleString()}
                          </td>
                          <td style={{ padding: '10px', fontWeight: 500, color: recuperado ? '#81c784' : '#888' }}>
                            {q.oc_recuperacion || '—'}
                          </td>
                          <td style={{ padding: '10px', color: '#81c784' }}>
                            {q.fecha_recuperacion || '—'}
                          </td>
                          <td style={{ padding: '10px', textAlign: 'center' }}>
                            {recuperado ? (
                              <span style={{ fontWeight: 700, color: '#64b5f6' }}>
                                ⏱ {q.dias_recuperacion_quiebre} días
                              </span>
                            ) : (
                              <span style={{ color: '#ffb74d', fontStyle: 'italic' }}>
                                Aún sin recuperar
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '10px', textAlign: 'center' }}>
                            {recuperado ? (
                              <span style={{
                                padding: '3px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600,
                                background: 'rgba(76, 175, 80, 0.2)', color: '#81c784', border: '1px solid #4caf50'
                              }}>
                                ✓ Recuperado
                              </span>
                            ) : (
                              <span style={{
                                padding: '3px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600,
                                background: 'rgba(244, 67, 54, 0.2)', color: '#ff5252', border: '1px solid #d32f2f'
                              }}>
                                ⚠️ Quiebre Activo
                              </span>
                            )}
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

        {/* ── MODAL: SUBIR ORDEN DE COMPRA ── */}
        {showUploadModal && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.85)', zIndex: 9999,
            display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '20px'
          }}>
            <div style={{
              background: '#1e1e1e', border: '1px solid #333', borderRadius: '12px',
              maxWidth: '550px', width: '100%', padding: '28px', boxShadow: '0 8px 30px rgba(0,0,0,0.7)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0, fontSize: '1.3rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>⬆</span> Subir Orden de Compra
                </h2>
                <button
                  style={{ background: 'none', border: 'none', color: '#888', fontSize: '1.5rem', cursor: 'pointer' }}
                  onClick={() => setShowUploadModal(false)}
                >
                  ×
                </button>
              </div>

              <form onSubmit={handleUploadSubmit}>
                {/* Selector de Etapa */}
                <div style={{ marginBottom: '18px' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#ccc', marginBottom: '8px', fontWeight: 600 }}>
                    Etapa de la Orden de Compra:
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <div
                      style={{
                        padding: '12px', borderRadius: '8px', border: `2px solid ${uploadEtapa === 'ENTREGA' ? '#4caf50' : '#444'}`,
                        background: uploadEtapa === 'ENTREGA' ? 'rgba(76, 175, 80, 0.15)' : '#252525',
                        cursor: 'pointer', textAlign: 'center'
                      }}
                      onClick={() => setUploadEtapa('ENTREGA')}
                    >
                      <div style={{ fontWeight: 700, color: uploadEtapa === 'ENTREGA' ? '#81c784' : '#ccc' }}>
                        🚚 ENTREGA / DESPACHO
                      </div>
                      <span style={{ fontSize: '0.75rem', color: '#999' }}>Auditoría real vs pedido</span>
                    </div>

                    <div
                      style={{
                        padding: '12px', borderRadius: '8px', border: `2px solid ${uploadEtapa === 'PEDIDO' ? '#2196f3' : '#444'}`,
                        background: uploadEtapa === 'PEDIDO' ? 'rgba(33, 150, 243, 0.15)' : '#252525',
                        cursor: 'pointer', textAlign: 'center'
                      }}
                      onClick={() => setUploadEtapa('PEDIDO')}
                    >
                      <div style={{ fontWeight: 700, color: uploadEtapa === 'PEDIDO' ? '#64b5f6' : '#ccc' }}>
                        📝 PEDIDO (Opcional)
                      </div>
                      <span style={{ fontSize: '0.75rem', color: '#999' }}>Registro inicial solicitado</span>
                    </div>
                  </div>
                </div>

                {/* Archivo */}
                <div style={{ marginBottom: '18px' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#ccc', marginBottom: '6px', fontWeight: 600 }}>
                    Archivo Excel o CSV:
                  </label>
                  <input
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    onChange={e => setUploadFile(e.target.files[0] || null)}
                    style={{
                      width: '100%', padding: '12px', background: '#252525', border: '1px dashed #555',
                      borderRadius: '8px', color: '#fff', cursor: 'pointer'
                    }}
                    required
                  />
                  <span style={{ fontSize: '0.75rem', color: '#888', marginTop: '4px', display: 'block' }}>
                    Columnas esperadas: SKU/Código, Cantidad Pedida/Comprada y/o Cantidad Despachada/Recibida.
                  </span>
                </div>

                {/* Campos Opcionales */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '18px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '4px' }}>
                      N° OC (Opcional):
                    </label>
                    <input
                      type="text"
                      placeholder="Auto si está en archivo"
                      value={uploadOcNum}
                      onChange={e => setUploadOcNum(e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #444', background: '#252525', color: '#fff' }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '4px' }}>
                      Cliente (Opcional):
                    </label>
                    <input
                      type="text"
                      placeholder="Cliente / Razón Social"
                      value={uploadCliente}
                      onChange={e => setUploadCliente(e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #444', background: '#252525', color: '#fff' }}
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '24px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '4px' }}>
                      Fecha Pedido (Opcional):
                    </label>
                    <input
                      type="date"
                      value={uploadFechaPedido}
                      onChange={e => setUploadFechaPedido(e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #444', background: '#252525', color: '#fff' }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '4px' }}>
                      Fecha Entrega / Despacho:
                    </label>
                    <input
                      type="date"
                      value={uploadFechaEntrega}
                      onChange={e => setUploadFechaEntrega(e.target.value)}
                      style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #444', background: '#252525', color: '#fff' }}
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
              background: '#1a1a1a', border: '1px solid #333', borderRadius: '12px',
              maxWidth: '1200px', width: '100%', maxHeight: '90vh', display: 'flex', flexDirection: 'column',
              boxShadow: '0 8px 30px rgba(0,0,0,0.8)', overflow: 'hidden'
            }}>
              {/* Header Modal */}
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#222' }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.4rem', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span>Auditoría OC:</span>
                    <span style={{ color: '#64b5f6' }}>{detailData?.header?.numero_oc || selectedOcId}</span>
                    <span style={{
                      fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px',
                      background: detailData?.header?.etapa === 'ENTREGA' ? 'rgba(76, 175, 80, 0.2)' : 'rgba(33, 150, 243, 0.2)',
                      color: detailData?.header?.etapa === 'ENTREGA' ? '#81c784' : '#64b5f6',
                      border: `1px solid ${detailData?.header?.etapa === 'ENTREGA' ? '#4caf50' : '#2196f3'}`
                    }}>
                      {detailData?.header?.etapa}
                    </span>
                  </h2>
                  <div style={{ fontSize: '0.85rem', color: '#aaa', marginTop: '4px' }}>
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
                      <div style={{ background: '#252525', padding: '12px', borderRadius: '8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.75rem', color: '#888' }}>Total Pedido</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>
                          {Math.round(detailData.header.total_pedido_uds).toLocaleString()} <span style={{ fontSize: '0.8rem', fontWeight: 400 }}>uds</span>
                        </div>
                      </div>

                      <div style={{ background: '#252525', padding: '12px', borderRadius: '8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.75rem', color: '#888' }}>Total Despachado</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#81c784' }}>
                          {Math.round(detailData.header.total_despachado_uds).toLocaleString()} <span style={{ fontSize: '0.8rem', fontWeight: 400 }}>uds</span>
                        </div>
                      </div>

                      <div style={{ background: '#252525', padding: '12px', borderRadius: '8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.75rem', color: '#888' }}>Cumplimiento</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 700, color: Number(detailData.header.cumplimiento_pct) >= 100 ? '#81c784' : '#ff9800' }}>
                          {detailData.header.cumplimiento_pct}%
                        </div>
                      </div>

                      <div style={{ background: '#252525', padding: '12px', borderRadius: '8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.75rem', color: '#888' }}>No Despachados (Quiebres)</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ff5252' }}>
                          {detailData.header.quiebres_count}
                        </div>
                      </div>

                      <div style={{ background: '#252525', padding: '12px', borderRadius: '8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.75rem', color: '#888' }}>Desbalance Familiar</span>
                        <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ba68c8' }}>
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
                        style={{ padding: '6px 12px', fontSize: '0.8rem', color: detailFilter === 'NO_DESPACHADO' ? '#fff' : '#ff5252' }}
                        onClick={() => setDetailFilter('NO_DESPACHADO')}
                      >
                        🚨 No Despachados (0) ({detailData.items.filter(i => i.estado_entrega === 'NO_DESPACHADO').length})
                      </button>
                      <button
                        className={detailFilter === 'PARCIAL' ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 12px', fontSize: '0.8rem', color: detailFilter === 'PARCIAL' ? '#fff' : '#ffb74d' }}
                        onClick={() => setDetailFilter('PARCIAL')}
                      >
                        ⚠️ Despacho Parcial ({detailData.items.filter(i => i.estado_entrega === 'DESPACHO_PARCIAL').length})
                      </button>
                      <button
                        className={detailFilter === 'DESBALANCE' ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 12px', fontSize: '0.8rem', color: detailFilter === 'DESBALANCE' ? '#fff' : '#ba68c8' }}
                        onClick={() => setDetailFilter('DESBALANCE')}
                      >
                        ⚖️ Desbalance Familiar ({detailData.items.filter(i => i.desbalance_familiar).length})
                      </button>
                    </div>

                    {/* Tabla de Detalle */}
                    <div style={{ overflowX: 'auto' }}>
                      <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                        <thead>
                          <tr style={{ background: '#252525', textAlign: 'left', borderBottom: '2px solid #333' }}>
                            <th style={{ padding: '10px' }}>SKU / Cód.</th>
                            <th style={{ padding: '10px' }}>Producto</th>
                            <th style={{ padding: '10px' }}>Familia</th>
                            <th style={{ padding: '10px', textAlign: 'right' }}>Cant. Pedida</th>
                            <th style={{ padding: '10px', textAlign: 'right' }}>Cant. Despachada</th>
                            <th style={{ padding: '10px', textAlign: 'right' }}>Diferencia</th>
                            <th style={{ padding: '10px', textAlign: 'center' }}>Estado</th>
                            <th style={{ padding: '10px' }}>Desbalance Familiar</th>
                            <th style={{ padding: '10px' }}>Historial Quiebre / Recuperación</th>
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
                                  borderBottom: '1px solid #333',
                                  background: isQuiebre ? 'rgba(244, 67, 54, 0.08)' : (it.desbalance_familiar ? 'rgba(156, 39, 176, 0.06)' : 'transparent')
                                }}>
                                  <td style={{ padding: '10px', fontWeight: 600, color: '#64b5f6' }}>
                                    {it.sku || it.codigo_femaco}
                                  </td>
                                  <td style={{ padding: '10px' }}>{it.nombre_producto}</td>
                                  <td style={{ padding: '10px', color: '#bbb' }}>{it.nombre_familia || '—'}</td>
                                  <td style={{ padding: '10px', textAlign: 'right' }}>
                                    {Math.round(it.cantidad_pedida).toLocaleString()}
                                  </td>
                                  <td style={{ padding: '10px', textAlign: 'right', fontWeight: 600, color: isQuiebre ? '#f44336' : '#81c784' }}>
                                    {Math.round(it.cantidad_despachada).toLocaleString()}
                                  </td>
                                  <td style={{ padding: '10px', textAlign: 'right', fontWeight: 600, color: it.diferencia < 0 ? '#ff5252' : '#81c784' }}>
                                    {it.diferencia > 0 ? `+${Math.round(it.diferencia)}` : Math.round(it.diferencia)}
                                  </td>
                                  <td style={{ padding: '10px', textAlign: 'center' }}>
                                    {isQuiebre && (
                                      <span style={{
                                        background: 'rgba(244, 67, 54, 0.25)', color: '#ff5252', border: '1px solid #d32f2f',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem'
                                      }}>
                                        NO DESPACHADO (0)
                                      </span>
                                    )}
                                    {isParcial && (
                                      <span style={{
                                        background: 'rgba(255, 152, 0, 0.25)', color: '#ffb74d', border: '1px solid #f57c00',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 600, fontSize: '0.75rem'
                                      }}>
                                        PARCIAL
                                      </span>
                                    )}
                                    {isCompleto && (
                                      <span style={{
                                        background: 'rgba(76, 175, 80, 0.2)', color: '#81c784', border: '1px solid #4caf50',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 600, fontSize: '0.75rem'
                                      }}>
                                        ✓ COMPLETO
                                      </span>
                                    )}
                                    {isExcedente && (
                                      <span style={{
                                        background: 'rgba(33, 150, 243, 0.2)', color: '#64b5f6', border: '1px solid #1976d2',
                                        padding: '3px 8px', borderRadius: '4px', fontWeight: 600, fontSize: '0.75rem'
                                      }}>
                                        + EXCEDENTE
                                      </span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px' }}>
                                    {it.desbalance_familiar ? (
                                      <div style={{ color: '#ba68c8', fontSize: '0.8rem', lineHeight: 1.3 }}>
                                        <strong>⚠️ Desbalance en Familia:</strong><br />
                                        {it.desbalance_detalle}
                                      </div>
                                    ) : (
                                      <span style={{ color: '#666' }}>—</span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px', fontSize: '0.8rem' }}>
                                    {it.quiebre_detectado ? (
                                      it.oc_recuperacion ? (
                                        <div style={{ color: '#81c784' }}>
                                          ✓ Recuperado en <strong>{it.oc_recuperacion}</strong><br />
                                          <span style={{ color: '#aaa' }}>({it.dias_recuperacion_quiebre} días después)</span>
                                        </div>
                                      ) : (
                                        <span style={{ color: '#ff8a80', fontWeight: 600 }}>
                                          ⚠️ Quiebre no recuperado en OCs posteriores
                                        </span>
                                      )
                                    ) : (
                                      <span style={{ color: '#666' }}>Sin quiebre</span>
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
