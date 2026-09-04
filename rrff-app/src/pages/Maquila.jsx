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

  // Role
  const role = localStorage.getItem('rrff_role') || 'viewer';
  const isAdmin = role === 'admin';

  useEffect(() => {
    if (view === 'list') {
      loadFamilias();
    }
  }, [view]);

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
          <div style={{ display: 'flex', gap: '20px', borderBottom: '2px solid #eee', marginBottom: '20px' }}>
            <h2 
              style={{ margin: 0, paddingBottom: '10px', cursor: 'pointer', color: activeTab === 'recetas' ? '#1976d2' : '#888', borderBottom: activeTab === 'recetas' ? '3px solid #1976d2' : 'none' }}
              onClick={() => setActiveTab('recetas')}
            >
              Familias de Reemplazo
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
                <h1 style={{ margin: 0 }}>Familias</h1>
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
                + Nueva Familia
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
                    <th style={{ padding: '10px' }}>Nombre Familia</th>
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
              <h2>{currentFamiliaId ? 'Editar Familia' : 'Nueva Familia de Reemplazo'}</h2>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '5px' }}>Nombre / Descripción de la Familia *</label>
                  <input 
                    type="text" 
                    value={formData.nombre_familia} 
                    onChange={e => setFormData({...formData, nombre_familia: e.target.value})}
                    style={{ width: '100%', padding: '8px' }}
                    placeholder="Ej. Familia Tornillo X"
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
                    Familia Activa
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
                  {loading ? 'Guardando...' : 'Guardar Familia'}
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
