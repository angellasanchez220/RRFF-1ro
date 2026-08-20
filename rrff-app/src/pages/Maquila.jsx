import React, { useState, useEffect } from 'react';
import * as api from '../api';
import MaquilaOrdenes from './MaquilaOrdenes';

export default function Maquila() {
  const [activeTab, setActiveTab] = useState('recetas'); // 'recetas' or 'ordenes'
  const [recetas, setRecetas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [view, setView] = useState('list'); // 'list', 'form', 'calc'
  const [currentRecetaId, setCurrentRecetaId] = useState(null);
  const [search, setSearch] = useState('');
  const [filterActive, setFilterActive] = useState('all'); // 'all', 'active', 'inactive'

  // Form state
  const [formData, setFormData] = useState({
    sku_maquilable: '',
    descripcion: '',
    activa: true,
    componentes: []
  });

  // Calc state
  const [calcData, setCalcData] = useState(null);
  const [calcQty, setCalcQty] = useState(100);

  // Role
  const role = localStorage.getItem('rrff_role') || 'viewer';
  const isAdmin = role === 'admin';

  useEffect(() => {
    // Si viene parametro ?receta=id, abrir detalle o calculo
    const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
    const rid = params.get('receta');
    
    if (rid) {
      setActiveTab('recetas');
      // Remover parametro de URL visualmente sin recargar
      window.history.replaceState(null, '', '#/maquila');
      openCalc(parseInt(rid));
    }
  }, []);

  useEffect(() => {
    if (view === 'list') {
      loadRecetas();
    }
  }, [view]);

  async function loadRecetas() {
    setLoading(true);
    try {
      const res = await api.fetchRecetas();
      setRecetas(res.data || []);
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
        sku_maquilable: data.sku_maquilable,
        descripcion: data.descripcion,
        activa: data.activa,
        componentes: data.componentes || []
      });
      setCurrentRecetaId(id);
      setView('form');
    } catch(err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle(id, currentActive) {
    if (!window.confirm(`¿Seguro que desea ${currentActive ? 'desactivar' : 'activar'} esta receta?`)) return;
    try {
      await api.toggleReceta(id, !currentActive);
      loadRecetas();
    } catch (err) {
      alert(err.message);
    }
  }

  async function handleSaveForm(e) {
    e.preventDefault();
    if (!formData.sku_maquilable) return alert("SKU terminado es requerido");
    if (formData.componentes.length === 0) return alert("Agregue al menos un componente");
    
    try {
      setLoading(true);
      if (currentRecetaId) {
        await api.updateReceta(currentRecetaId, formData);
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

  function addComponente() {
    setFormData({
      ...formData,
      componentes: [...formData.componentes, { sku_componente: '', cantidad_por_unidad: 1 }]
    });
  }

  function removeComponente(idx) {
    const newComps = [...formData.componentes];
    newComps.splice(idx, 1);
    setFormData({ ...formData, componentes: newComps });
  }

  function updateComponente(idx, field, val) {
    const newComps = [...formData.componentes];
    newComps[idx][field] = val;
    setFormData({ ...formData, componentes: newComps });
  }

  async function handleCalculate(e) {
    e.preventDefault();
    if (calcQty <= 0) return alert("Cantidad debe ser mayor a 0");
    try {
      setLoading(true);
      const res = await api.calcularMaquila(currentRecetaId, calcQty);
      setCalcData(res);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function openCalc(id) {
    setCurrentRecetaId(id);
    setCalcData(null);
    setCalcQty(100);
    setView('calc');
  }

  function exportCalcExcel() {
    if (!calcData) return;
    const lines = [
      `Cálculo de Maquila - ${calcData.sku_maquilable}`,
      `Cantidad a fabricar: ${calcData.cantidad_a_fabricar}`,
      "",
      "SKU Componente\tCantidad por Unidad\tCantidad Requerida\tStock Actual\tFaltante\tEstado"
    ];
    
    calcData.componentes.forEach(c => {
      lines.push(`${c.sku}\t${c.cantidad_por_unidad}\t${c.cantidad_requerida}\t${c.stock_actual}\t${c.faltante}\t${c.estado}`);
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `Calculo_Maquila_${calcData.sku_maquilable}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  const filteredRecetas = recetas.filter(r => {
    if (filterActive === 'active' && !r.activa) return false;
    if (filterActive === 'inactive' && r.activa) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!r.sku_maquilable.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  if (loading && view === 'list' && recetas.length === 0 && activeTab === 'recetas') return <div className="page">Cargando recetas...</div>;

  return (
    <div className="content-area">
      <div className="main-panel">
        <div className="page" style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
          
          {/* ── TABS ── */}
          <div style={{ display: 'flex', gap: '20px', borderBottom: '2px solid #eee', marginBottom: '20px' }}>
            <h2 
              style={{ margin: 0, paddingBottom: '10px', cursor: 'pointer', color: activeTab === 'recetas' ? '#1976d2' : '#888', borderBottom: activeTab === 'recetas' ? '3px solid #1976d2' : 'none' }}
              onClick={() => setActiveTab('recetas')}
            >
              Recetas de Maquila
            </h2>
            <h2 
              style={{ margin: 0, paddingBottom: '10px', cursor: 'pointer', color: activeTab === 'ordenes' ? '#1976d2' : '#888', borderBottom: activeTab === 'ordenes' ? '3px solid #1976d2' : 'none' }}
              onClick={() => setActiveTab('ordenes')}
            >
              Órdenes de Compra
            </h2>
          </div>

          {activeTab === 'ordenes' && <MaquilaOrdenes isAdmin={isAdmin} />}

          {activeTab === 'recetas' && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h1 style={{ margin: 0 }}>Maquila</h1>
                {view === 'list' && (
              <button 
                className="btn-primary" 
                style={{ width: 'auto', padding: '10px 20px' }}
                onClick={() => {
                  setCurrentRecetaId(null);
                  setFormData({ sku_maquilable: '', descripcion: '', activa: true, componentes: [] });
                  setView('form');
                }}
              >
                + Nueva receta
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
                  placeholder="Buscar SKU o nombre..." 
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
                    <th style={{ padding: '10px' }}>SKU Final</th>
                    <th style={{ padding: '10px' }}>Componentes</th>
                    <th style={{ padding: '10px' }}>Estado</th>
                    <th style={{ padding: '10px' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRecetas.map(r => (
                    <tr key={r.id} style={{ borderBottom: '1px solid #f5f5f5' }}>
                      <td style={{ padding: '10px', fontWeight: 'bold' }}>{r.sku_maquilable}</td>
                      <td style={{ padding: '10px' }}>{r.cantidad_componentes}</td>
                      <td style={{ padding: '10px' }}>
                        {r.activa 
                          ? <span style={{ background: '#d4edda', color: '#155724', padding: '2px 8px', borderRadius: '12px', fontSize:'0.85em' }}>Activa</span>
                          : <span style={{ background: '#f8d7da', color: '#721c24', padding: '2px 8px', borderRadius: '12px', fontSize:'0.85em' }}>Inactiva</span>
                        }
                      </td>
                      <td style={{ padding: '10px', display: 'flex', gap: '5px' }}>
                        <button style={{ padding: '4px 8px', fontSize: '0.85em', cursor: 'pointer' }} onClick={() => openCalc(r.id)}>🧮 Calcular</button>
                        <button style={{ padding: '4px 8px', fontSize: '0.85em', cursor: 'pointer' }} onClick={() => handleEdit(r.id)}>✏️ Editar</button>
                        <button style={{ padding: '4px 8px', fontSize: '0.85em', cursor: 'pointer' }} onClick={() => handleToggle(r.id, r.activa)}>
                          {r.activa ? 'Desactivar' : 'Activar'}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filteredRecetas.length === 0 && (
                    <tr><td colSpan="5" style={{ padding: '20px', textAlign: 'center', color: '#777' }}>No se encontraron recetas.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ── FORM VIEW ── */}
          {view === 'form' && (
            <form onSubmit={handleSaveForm} className="card" style={{ padding: '20px' }}>
              <h2>{currentRecetaId ? 'Editar Receta' : 'Nueva Receta'}</h2>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '5px' }}>SKU Terminado *</label>
                  <input 
                    type="text" 
                    value={formData.sku_maquilable} 
                    onChange={e => setFormData({...formData, sku_maquilable: e.target.value.toUpperCase()})}
                    style={{ width: '100%', padding: '8px' }}
                    required 
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '5px' }}>Descripción</label>
                  <input 
                    type="text" 
                    value={formData.descripcion} 
                    onChange={e => setFormData({...formData, descripcion: e.target.value})}
                    style={{ width: '100%', padding: '8px' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                    <input 
                      type="checkbox" 
                      checked={formData.activa} 
                      onChange={e => setFormData({...formData, activa: e.target.checked})} 
                    />
                    Receta Activa
                  </label>
                </div>
              </div>

              <hr style={{ margin: '20px 0', borderColor: '#eee', borderStyle: 'solid' }} />
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ margin: 0 }}>Componentes</h3>
                <button type="button" onClick={addComponente} style={{ padding: '4px 8px' }}>+ Agregar Insumo</button>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', marginBottom: '20px' }}>
                <thead>
                  <tr style={{ background: '#f9f9f9' }}>
                    <th style={{ padding: '8px' }}>SKU Componente</th>
                    <th style={{ padding: '8px' }}>Cantidad por Unidad</th>
                    <th style={{ padding: '8px', width: '80px' }}>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {formData.componentes.map((c, i) => (
                    <tr key={i}>
                      <td style={{ padding: '4px 8px' }}>
                        <input 
                          type="text" 
                          value={c.sku_componente} 
                          onChange={e => updateComponente(i, 'sku_componente', e.target.value.toUpperCase())}
                          style={{ width: '100%', padding: '6px' }}
                          required
                        />
                      </td>
                      <td style={{ padding: '4px 8px' }}>
                        <input 
                          type="number" 
                          step="0.001" 
                          min="0.001"
                          value={c.cantidad_por_unidad} 
                          onChange={e => updateComponente(i, 'cantidad_por_unidad', parseFloat(e.target.value))}
                          style={{ width: '100%', padding: '6px' }}
                          required
                        />
                      </td>
                      <td style={{ padding: '4px 8px' }}>
                        <button type="button" onClick={() => removeComponente(i)} style={{ color: 'red' }}>Quitar</button>
                      </td>
                    </tr>
                  ))}
                  {formData.componentes.length === 0 && (
                    <tr><td colSpan="3" style={{ padding: '10px', textAlign: 'center', color: '#999' }}>Sin componentes</td></tr>
                  )}
                </tbody>
              </table>

              <div>
                <button type="submit" className="btn-primary" disabled={loading} style={{ padding: '10px 20px', fontSize: '1.1em' }}>
                  {loading ? 'Guardando...' : 'Guardar Receta'}
                </button>
              </div>
            </form>
          )}

          {/* ── CALC VIEW ── */}
          {view === 'calc' && (
            <div className="card" style={{ padding: '20px' }}>
              <h2>Calculadora de Maquila</h2>
              <form onSubmit={handleCalculate} style={{ display: 'flex', gap: '10px', alignItems: 'flex-end', marginBottom: '20px', background: '#f5f5f5', padding: '15px', borderRadius: '8px' }}>
                <div>
                  <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '5px' }}>Cantidad a fabricar</label>
                  <input 
                    type="number" 
                    min="1" 
                    value={calcQty} 
                    onChange={e => setCalcQty(parseInt(e.target.value))}
                    style={{ padding: '8px', fontSize: '1.1em', width: '150px' }}
                    required 
                  />
                </div>
                <button type="submit" className="btn-primary" disabled={loading} style={{ padding: '8px 16px', fontSize: '1.1em', height: '40px' }}>
                  {loading ? 'Calculando...' : 'Calcular'}
                </button>
              </form>

              {calcData && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                    <h3 style={{ margin: 0 }}>Resultados para {calcData.sku_maquilable} ({calcData.cantidad_a_fabricar} uds)</h3>
                    <button type="button" onClick={exportCalcExcel} style={{ background: '#28a745', color: 'white', border: 'none', padding: '8px 12px', borderRadius: '4px', cursor: 'pointer' }}>
                      📊 Exportar Excel
                    </button>
                  </div>

                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                    <thead>
                      <tr style={{ background: '#eaeaea', borderBottom: '2px solid #ccc' }}>
                        <th style={{ padding: '10px' }}>Componente</th>
                        <th style={{ padding: '10px', textAlign: 'right' }}>Cant / Ud</th>
                        <th style={{ padding: '10px', textAlign: 'right' }}>Requerido</th>
                        <th style={{ padding: '10px', textAlign: 'right' }}>Stock Actual</th>
                        <th style={{ padding: '10px', textAlign: 'right' }}>Faltante</th>
                        <th style={{ padding: '10px' }}>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {calcData.componentes.map((c, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                          <td style={{ padding: '10px', fontWeight: 'bold' }}>{c.sku}</td>
                          <td style={{ padding: '10px', textAlign: 'right' }}>{c.cantidad_por_unidad}</td>
                          <td style={{ padding: '10px', textAlign: 'right', fontWeight: 'bold', color: '#333' }}>{c.cantidad_requerida}</td>
                          <td style={{ padding: '10px', textAlign: 'right' }}>{c.stock_actual}</td>
                          <td style={{ padding: '10px', textAlign: 'right', color: c.faltante > 0 ? '#d9534f' : 'inherit' }}>{c.faltante}</td>
                          <td style={{ padding: '10px' }}>
                            <span style={{
                              padding: '3px 8px', borderRadius: '12px', fontSize: '0.85em',
                              background: c.estado === 'Disponible' ? '#d4edda' : (c.estado === 'Parcial' ? '#fff3cd' : '#f8d7da'),
                              color: c.estado === 'Disponible' ? '#155724' : (c.estado === 'Parcial' ? '#856404' : '#721c24')
                            }}>
                              {c.estado}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

            </>
          )}
        </div>
      </div>
    </div>
  );
}
