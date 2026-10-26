import { useState, useEffect } from 'react';
import * as api from '../api';
import MaquilaOrdenes from './MaquilaOrdenes';

export default function FamiliasReemplazo() {
  const [activeTab, setActiveTab] = useState('recetas'); // 'recetas' = familias, 'ordenes'
  const [familias, setFamilias] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [view, setView] = useState('list'); // 'list', 'form'
  const [currentFamiliaId, setCurrentFamiliaId] = useState(null);
  const [search, setSearch] = useState('');
  const [filterActive, setFilterActive] = useState('all');

  // Form state
  const [formData, setFormData] = useState({
    nombre_familia: '',
    activa: true,
    miembros: []
  });

  // Distribución Homogénea State
  const [distribucionData, setDistribucionData] = useState([]);
  const [loadingDistribucion, setLoadingDistribucion] = useState(false);
  const [searchDistribucion, setSearchDistribucion] = useState('');
  const [filterDistribucion, setFilterDistribucion] = useState('ALL');

  // Role
  const role = localStorage.getItem('rrff_role') || 'viewer';
  const isAdmin = role === 'admin';

  useEffect(() => {
    if (view === 'list' && activeTab === 'recetas') {
      loadFamilias();
    } else if (activeTab === 'distribucion') {
      loadDistribucion();
    }
  }, [view, activeTab]);

  async function loadDistribucion() {
    setLoadingDistribucion(true);
    try {
      const res = await api.fetchMaquilaDistribucionHomogenea();
      setDistribucionData(res.data || []);
    } catch (err) {
      alert("Error al cargar distribución homogénea: " + err.message);
    } finally {
      setLoadingDistribucion(false);
    }
  }

  async function handleDownloadDistribucionExcel() {
    try {
      const { blob, filename } = await api.downloadMaquilaDistribucionExcel();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Error al descargar Excel: " + err.message);
    }
  }

  async function loadFamilias() {
    setLoading(true);
    try {
      const res = await api.fetchRecetas();
      setFamilias(res.data || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleEdit(id) {
    try {
      setLoading(true);
      const data = await api.fetchRecetaDetail(id);
      setFormData({
        nombre_familia: data.descripcion, // guardamos el nombre en descripcion
        activa: data.activa,
        miembros: data.miembros || []
      });
      setCurrentFamiliaId(id);
      setView('form');
    } catch(err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle(id, currentActive) {
    if (!window.confirm(`¿Seguro que desea ${currentActive ? 'desactivar' : 'activar'} esta familia?`)) return;
    try {
      await api.toggleReceta(id, !currentActive);
      loadFamilias();
    } catch (err) {
      alert(err.message);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("¿Seguro que desea eliminar esta familia permanentemente?")) return;
    try {
      setLoading(true);
      await api.deleteReceta(id);
      loadFamilias();
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveForm(e) {
    e.preventDefault();
    if (!formData.nombre_familia) return alert("Nombre de la familia es requerido");
    if (formData.miembros.length < 2) return alert("Agregue al menos dos códigos internos a la familia");
    
    try {
      setLoading(true);
      if (currentFamiliaId) {
        await api.updateReceta(currentFamiliaId, formData);
      } else {
        await api.createReceta(formData);
      }
      setView('list');
    } catch(err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function addMiembro() {
    setFormData({
      ...formData,
      miembros: [...formData.miembros, { codigo_femaco: '', no_transformable: false }]
    });
  }

  function removeMiembro(idx) {
    const newMembers = [...formData.miembros];
    newMembers.splice(idx, 1);
    setFormData({ ...formData, miembros: newMembers });
  }

  function updateMiembro(idx, field, val) {
    const newMembers = [...formData.miembros];
    newMembers[idx][field] = val;
    setFormData({ ...formData, miembros: newMembers });
  }

  const filteredFamilias = familias.filter(r => {
    if (filterActive === 'active' && !r.activa) return false;
    if (filterActive === 'inactive' && r.activa) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!r.nombre_familia?.toLowerCase().includes(q) && !r.identificador?.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  if (loading && view === 'list' && familias.length === 0 && activeTab === 'recetas') return <div className="page">Cargando familias...</div>;

  return (
    <div className="content-area">
      <div className="main-panel">
        <div className="page" style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
          
          {/* ── TABS ── */}
          <div style={{ display: 'flex', gap: '20px', borderBottom: '2px solid #333', marginBottom: '20px' }}>
            <h2 
              style={{ margin: 0, paddingBottom: '10px', cursor: 'pointer', color: activeTab === 'recetas' ? '#1976d2' : '#888', borderBottom: activeTab === 'recetas' ? '3px solid #1976d2' : 'none', fontSize: '1.15rem' }}
              onClick={() => setActiveTab('recetas')}
            >
              👨‍👦 Hermanos de Reemplazo
            </h2>
            <h2 
              style={{ margin: 0, paddingBottom: '10px', cursor: 'pointer', color: activeTab === 'distribucion' ? '#1976d2' : '#888', borderBottom: activeTab === 'distribucion' ? '3px solid #1976d2' : 'none', fontSize: '1.15rem' }}
              onClick={() => setActiveTab('distribucion')}
            >
              ⚖️ Distribución Homogénea (Plan de Maquila)
            </h2>
            <h2 
              style={{ margin: 0, paddingBottom: '10px', cursor: 'pointer', color: activeTab === 'ordenes' ? '#1976d2' : '#888', borderBottom: activeTab === 'ordenes' ? '3px solid #1976d2' : 'none', fontSize: '1.15rem' }}
              onClick={() => setActiveTab('ordenes')}
            >
              📑 Órdenes de Corte / Trabajo
            </h2>
          </div>

          {activeTab === 'ordenes' && <MaquilaOrdenes isAdmin={isAdmin} />}

          {/* ── TAB DISTRIBUCIÓN HOMOGÉNEA DE FAMILIAS ── */}
          {activeTab === 'distribucion' && (
            <div>
              {/* Banner explicativo de la regla de maquila */}
              <div className="card" style={{ padding: '16px 20px', marginBottom: '20px', borderLeft: '4px solid #1976d2', background: 'rgba(25, 118, 210, 0.08)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                  <div style={{ flex: 1, minWidth: '300px' }}>
                    <h3 style={{ margin: '0 0 6px', color: '#64b5f6', fontSize: '1.1rem' }}>
                      🏭 Regla de Negocio: Sustitución y Transformación Homogénea Familiar
                    </h3>
                    <p style={{ margin: 0, color: '#ccc', fontSize: '0.85rem', lineHeight: 1.4 }}>
                      Los productos que pertenecen a una familia de reemplazo no se compran si el grupo familiar tiene inventario suficiente para cubrir la demanda.
                      Las unidades se distribuyen de manera homogénea entre los integrantes. Solo si el total familiar queda en déficit, el saldo faltante pasa a compra en el módulo Compras.
                    </p>
                  </div>
                  <button
                    className="btn-primary"
                    style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', whiteSpace: 'nowrap' }}
                    onClick={handleDownloadDistribucionExcel}
                  >
                    <span style={{ fontSize: '1.2rem' }}>📥</span> Descargar Plan de Distribución y Maquila (Excel)
                  </button>
                </div>
              </div>

              {/* Filtros de familias */}
              <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
                <input
                  type="text"
                  placeholder="🔍 Buscar por nombre de familia o código..."
                  value={searchDistribucion}
                  onChange={e => setSearchDistribucion(e.target.value)}
                  style={{ flex: 1, minWidth: '220px', padding: '10px', borderRadius: '6px', border: '1px solid #444', background: '#222', color: '#fff' }}
                />
                <select
                  value={filterDistribucion}
                  onChange={e => setFilterDistribucion(e.target.value)}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #444', background: '#222', color: '#fff' }}
                >
                  <option value="ALL">Todas las Familias</option>
                  <option value="CUBIERTAS">100% Cubiertas por Maquila (0 compra)</option>
                  <option value="DEFICIT">Con Déficit Familiar (Pasa a compra)</option>
                </select>
              </div>

              {loadingDistribucion ? (
                <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>Calculando distribución homogénea familiar...</div>
              ) : distribucionData.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>No hay familias activas registradas para calcular distribución.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {distribucionData
                    .filter(f => {
                      if (filterDistribucion === 'CUBIERTAS' && !f.cubre_con_stock_familiar) return false;
                      if (filterDistribucion === 'DEFICIT' && f.cubre_con_stock_familiar) return false;
                      if (searchDistribucion) {
                        const q = searchDistribucion.toLowerCase();
                        const matchName = f.nombre_familia.toLowerCase().includes(q);
                        const matchMember = f.miembros.some(m => m.sku.toLowerCase().includes(q) || m.codigo_femaco.toLowerCase().includes(q));
                        if (!matchName && !matchMember) return false;
                      }
                      return true;
                    })
                    .map(f => {
                      const cubre = f.cubre_con_stock_familiar;
                      return (
                        <div key={f.familia_id} className="card" style={{ padding: '18px 20px', borderLeft: `4px solid ${cubre ? '#4caf50' : '#ff9800'}` }}>
                          {/* Encabezado Familia */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                            <div>
                              <h3 style={{ margin: '0 0 4px', fontSize: '1.15rem', color: '#fff' }}>
                                {f.nombre_familia}
                              </h3>
                              <span style={{ fontSize: '0.8rem', color: '#888' }}>
                                {f.cantidad_miembros} integrantes vinculados | ID #{f.familia_id}
                              </span>
                            </div>

                            <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: '0.75rem', color: '#888' }}>Stock Familiar Disponible</div>
                                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#64b5f6' }}>
                                  {Math.round(f.total_stock_familia).toLocaleString()} uds
                                </div>
                              </div>

                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: '0.75rem', color: '#888' }}>Demanda Total Familia</div>
                                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fff' }}>
                                  {Math.round(f.total_demanda_familia).toLocaleString()} uds
                                </div>
                              </div>

                              <div style={{ textAlign: 'center', padding: '6px 12px', borderRadius: '6px', background: cubre ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 152, 0, 0.15)', border: `1px solid ${cubre ? '#4caf50' : '#ff9800'}` }}>
                                <span style={{ fontSize: '0.7rem', display: 'block', textTransform: 'uppercase', color: cubre ? '#81c784' : '#ffb74d', fontWeight: 600 }}>
                                  Cobertura Familiar
                                </span>
                                <span style={{ fontSize: '1.1rem', fontWeight: 700, color: cubre ? '#81c784' : '#ffb74d' }}>
                                  {f.cobertura_pct}%
                                </span>
                              </div>

                              <div>
                                {cubre ? (
                                  <span style={{
                                    padding: '6px 12px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700,
                                    background: 'rgba(76, 175, 80, 0.2)', color: '#81c784', border: '1px solid #4caf50'
                                  }}>
                                    ✓ Cubierto 100% por Maquila (0 compra)
                                  </span>
                                ) : (
                                  <span style={{
                                    padding: '6px 12px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700,
                                    background: 'rgba(244, 67, 54, 0.2)', color: '#ff5252', border: '1px solid #d32f2f'
                                  }}>
                                    🛒 Déficit: Comprar {Math.round(f.total_compra_remanente_sugerida).toLocaleString()} uds
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Tabla de Miembros y Distribución */}
                          <div style={{ overflowX: 'auto' }}>
                            <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                              <thead>
                                <tr style={{ background: '#252525', textAlign: 'left', borderBottom: '1px solid #333' }}>
                                  <th style={{ padding: '8px' }}>Cód. Interno / SKU</th>
                                  <th style={{ padding: '8px' }}>Producto</th>
                                  <th style={{ padding: '8px', textAlign: 'right' }}>Stock Inicial Total</th>
                                  <th style={{ padding: '8px', textAlign: 'right' }}>Demanda Objetivo</th>
                                  <th style={{ padding: '8px', textAlign: 'right' }}>Asignación Homogénea</th>
                                  <th style={{ padding: '8px', textAlign: 'center' }}>Saldo Transformación (Maquila)</th>
                                  <th style={{ padding: '8px', textAlign: 'center' }}>Cobertura Lograda</th>
                                  <th style={{ padding: '8px', textAlign: 'right' }}>Compra Neta</th>
                                  <th style={{ padding: '8px' }}>Resolución Operativa</th>
                                </tr>
                              </thead>
                              <tbody>
                                {f.miembros.map((m, idx) => {
                                  const transf = m.saldo_transformacion;
                                  return (
                                    <tr key={idx} style={{ borderBottom: '1px solid #333' }}>
                                      <td style={{ padding: '8px', fontWeight: 600, color: '#64b5f6' }}>
                                        {m.codigo_femaco} {m.sku && m.sku !== m.codigo_femaco && `(${m.sku})`}
                                      </td>
                                      <td style={{ padding: '8px' }}>{m.nombre_producto}</td>
                                      <td style={{ padding: '8px', textAlign: 'right' }}>
                                        {Math.round(m.stock_total).toLocaleString()}
                                      </td>
                                      <td style={{ padding: '8px', textAlign: 'right' }}>
                                        {Math.round(m.demanda).toLocaleString()}
                                      </td>
                                      <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#64b5f6' }}>
                                        {Math.round(m.stock_asignado_homogeneo).toLocaleString()}
                                      </td>
                                      <td style={{ padding: '8px', textAlign: 'center' }}>
                                        {transf > 0 ? (
                                          <span style={{ color: '#81c784', fontWeight: 600 }}>
                                            + Recibir {Math.round(transf).toLocaleString()} uds (Maquilar)
                                          </span>
                                        ) : transf < 0 ? (
                                          <span style={{ color: '#ffb74d', fontWeight: 500 }}>
                                            - Ceder {Math.round(Math.abs(transf)).toLocaleString()} uds a hermanos
                                          </span>
                                        ) : (
                                          <span style={{ color: '#888' }}>Equilibrado</span>
                                        )}
                                      </td>
                                      <td style={{ padding: '8px', textAlign: 'center', fontWeight: 600, color: m.cobertura_post_distribucion_pct >= 100 ? '#81c784' : '#ff9800' }}>
                                        {m.cobertura_post_distribucion_pct}%
                                      </td>
                                      <td style={{ padding: '8px', textAlign: 'right', fontWeight: 700, color: m.compra_remanente_sugerida > 0 ? '#ff5252' : '#81c784' }}>
                                        {m.compra_remanente_sugerida > 0 ? `${m.compra_remanente_sugerida.toLocaleString()} uds` : '0 (No comprar)'}
                                      </td>
                                      <td style={{ padding: '8px', fontSize: '0.8rem', color: m.cubierto_por_maquila ? '#81c784' : '#ccc' }}>
                                        {m.observacion}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          )}


          {activeTab === 'recetas' && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h1 style={{ margin: 0 }}>Hermanos</h1>
                {view === 'list' && (
              <button 
                className="btn-primary" 
                style={{ width: 'auto', padding: '10px 20px' }}
                onClick={() => {
                  setCurrentFamiliaId(null);
                  setFormData({ nombre_familia: '', activa: true, miembros: [] });
                  setView('form');
                }}
              >
                + Nuevos Hermanos
              </button>
            )}
            {view !== 'list' && (
              <button className="btn-secondary" onClick={() => setView('list')}>← Volver al Listado</button>
            )}
          </div>

          {error && <div className="alert-error" style={{marginBottom: '1rem', color:'red'}}>{error}</div>}

          {/* ── LIST VIEW ── */}
          {view === 'list' && (
            <div className="card" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
                <input 
                  type="text" 
                  placeholder="Buscar familia..." 
                  value={search} 
                  onChange={e => setSearch(e.target.value)}
                  style={{ flex: 1, padding: '8px' }}
                />
                <select value={filterActive} onChange={e => setFilterActive(e.target.value)} style={{ padding: '8px' }}>
                  <option value="all">Todas</option>
                  <option value="active">Activas</option>
                  <option value="inactive">Inactivas</option>
                </select>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #eee' }}>
                    <th style={{ padding: '10px' }}>Nombre Hermanos</th>
                    <th style={{ padding: '10px' }}>Miembros</th>
                    <th style={{ padding: '10px' }}>Estado</th>
                    <th style={{ padding: '10px' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFamilias.map(r => (
                    <tr key={r.id} style={{ borderBottom: '1px solid #f5f5f5' }}>
                      <td style={{ padding: '10px', fontWeight: 'bold' }}>{r.nombre_familia || r.identificador}</td>
                      <td style={{ padding: '10px' }}>{r.cantidad_miembros}</td>
                      <td style={{ padding: '10px' }}>
                        {r.activa 
                          ? <span style={{ background: '#d4edda', color: '#155724', padding: '2px 8px', borderRadius: '12px', fontSize:'0.85em' }}>Activa</span>
                          : <span style={{ background: '#f8d7da', color: '#721c24', padding: '2px 8px', borderRadius: '12px', fontSize:'0.85em' }}>Inactiva</span>
                        }
                      </td>
                      <td style={{ padding: '10px', display: 'flex', gap: '5px' }}>
                        <button style={{ padding: '4px 8px', fontSize: '0.85em', cursor: 'pointer' }} onClick={() => handleEdit(r.id)}>✏️ Editar</button>
                        <button style={{ padding: '4px 8px', fontSize: '0.85em', cursor: 'pointer' }} onClick={() => handleToggle(r.id, r.activa)}>
                          {r.activa ? 'Desactivar' : 'Activar'}
                        </button>
                        <button style={{ padding: '4px 8px', fontSize: '0.85em', cursor: 'pointer', background: '#dc3545', color: 'white', border: 'none', borderRadius: '4px' }} onClick={() => handleDelete(r.id)}>
                          🗑️ Borrar
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filteredFamilias.length === 0 && (
                    <tr><td colSpan="5" style={{ padding: '20px', textAlign: 'center', color: '#777' }}>No se encontraron familias.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ── FORM VIEW ── */}
          {view === 'form' && (
            <form onSubmit={handleSaveForm} className="card" style={{ padding: '20px' }}>
              <h2>{currentFamiliaId ? 'Editar Hermanos' : 'Nuevos Hermanos de Reemplazo'}</h2>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '5px' }}>Nombre / Descripción de Hermanos *</label>
                  <input 
                    type="text" 
                    value={formData.nombre_familia} 
                    onChange={e => setFormData({...formData, nombre_familia: e.target.value})}
                    style={{ width: '100%', padding: '8px' }}
                    placeholder="Ej. Hermanos Tornillo X"
                    required 
                  />
                </div>
                <div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                    <input 
                      type="checkbox" 
                      checked={formData.activa} 
                      onChange={e => setFormData({...formData, activa: e.target.checked})} 
                    />
                    Hermanos Activos
                  </label>
                </div>
              </div>

              <hr style={{ margin: '20px 0', borderColor: '#eee', borderStyle: 'solid' }} />
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ margin: 0 }}>Integrantes por código interno</h3>
                <button type="button" onClick={addMiembro} style={{ padding: '4px 8px' }}>+ Agregar Miembro</button>
              </div>

              <div style={{ padding: '10px', background: '#e9ecef', borderRadius: '4px', marginBottom: '20px', fontSize: '0.9em' }}>
                <strong>ⓘ Nota:</strong> Ingresa el código interno que aparece como <b>CÓD.</b> en el dashboard. Al agregar un código que ya pertenece a otra familia, ambas familias quedarán conectadas como un único gran conjunto de reemplazo.<br/><br/>
                <strong>No transformable:</strong> Este producto puede ser reemplazado por otros miembros de su familia, pero no puede utilizarse para reemplazar a otros productos.
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', marginBottom: '20px' }}>
                <thead>
                  <tr style={{ background: '#f9f9f9' }}>
                    <th style={{ padding: '8px' }}>Código interno (CÓD.)</th>
                    <th style={{ padding: '8px', textAlign: 'center' }}>No Transformable</th>
                    <th style={{ padding: '8px', width: '80px' }}>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {formData.miembros.map((m, i) => (
                    <tr key={i}>
                      <td style={{ padding: '4px 8px' }}>
                        <input 
                          type="text" 
                          value={m.codigo_femaco || ''}
                          onChange={e => updateMiembro(i, 'codigo_femaco', e.target.value.toUpperCase())}
                          style={{ width: '100%', padding: '6px' }}
                          placeholder="CÓD. interno..."
                          required
                        />
                      </td>
                      <td style={{ padding: '4px 8px', textAlign: 'center' }}>
                        <input 
                          type="checkbox" 
                          checked={m.no_transformable} 
                          onChange={e => updateMiembro(i, 'no_transformable', e.target.checked)}
                          style={{ transform: 'scale(1.2)' }}
                        />
                      </td>
                      <td style={{ padding: '4px 8px' }}>
                        <button type="button" onClick={() => removeMiembro(i)} style={{ color: 'red' }}>Quitar</button>
                      </td>
                    </tr>
                  ))}
                  {formData.miembros.length === 0 && (
                    <tr><td colSpan="3" style={{ padding: '10px', textAlign: 'center', color: '#999' }}>Agregue al menos dos códigos internos a la familia</td></tr>
                  )}
                </tbody>
              </table>

              <div>
                <button type="submit" className="btn-primary" disabled={loading} style={{ padding: '10px 20px', fontSize: '1.1em' }}>
                  {loading ? 'Guardando...' : 'Guardar Hermanos'}
                </button>
              </div>
            </form>
          )}

            </>
          )}
        </div>
      </div>
    </div>
  );
}
