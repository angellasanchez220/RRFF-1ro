import { useState, useEffect } from 'react';
import * as api from '../api';
import MaquilaOrdenes from './MaquilaOrdenes';

export default function FamiliasReemplazo() {
  const [activeTab, setActiveTab] = useState('recetas'); // 'recetas' = familias/recetas, 'distribucion', 'ordenes'
  const [familias, setFamilias] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [view, setView] = useState('list'); // 'list', 'form'
  const [currentFamiliaId, setCurrentFamiliaId] = useState(null);
  const [search, setSearch] = useState('');
  const [filterActive, setFilterActive] = useState('all');

  // Catálogo de productos para autocompletado y sugerencias
  const [catalogo, setCatalogo] = useState([]);
  const [materialesMaquila, setMaterialesMaquila] = useState([]);

  // Form state
  const [formData, setFormData] = useState({
    nombre_familia: '',
    producto_objetivo: '',
    activa: true,
    tiempo_base_1p_min: '',
    unidades_base_tiempo: 100,
    miembros: [],
    tiempos: []
  });

  // Modal rápido de registro de prueba de tiempo
  const [quickTimeModal, setQuickTimeModal] = useState({
    open: false,
    recetaId: null,
    nombreFamilia: '',
    cantidadPersonas: 6,
    unidadesBase: 100,
    tiempoMinutos: '',
    observaciones: '',
    loading: false
  });

  // Distribución Homogénea State
  const [distribucionData, setDistribucionData] = useState([]);
  const [loadingDistribucion, setLoadingDistribucion] = useState(false);
  const [searchDistribucion, setSearchDistribucion] = useState('');
  const [filterDistribucion, setFilterDistribucion] = useState('ALL');

  // Simulador de Maquila State
  const [simuladorData, setSimuladorData] = useState([]);
  const [loadingSimulador, setLoadingSimulador] = useState(false);
  const [searchSimulador, setSearchSimulador] = useState('');
  const [filterCuello, setFilterCuello] = useState('ALL');

  async function loadSimulador() {
    setLoadingSimulador(true);
    try {
      const res = await api.simularMaquila();
      setSimuladorData(res.data || []);
    } catch (err) {
      console.error("Error al cargar simulador:", err);
    } finally {
      setLoadingSimulador(false);
    }
  }

  useEffect(() => {
    if (activeTab === 'simulador') {
      loadSimulador();
    }
  }, [activeTab]);

  // Role
  const role = localStorage.getItem('rrff_role') || 'viewer';
  const isAdmin = role === 'admin';

  useEffect(() => {
    // Carga de catálogo ligera para autocompletado
    async function loadCatalog() {
      try {
        const res = await api.fetchSOP();
        if (res && res.data) {
          const map = res.data.map(p => ({
            codigo_femaco: String(p.codigo_femaco || '').trim().toUpperCase(),
            sku: String(p.sku || '').trim().toUpperCase(),
            nombre_producto: String(p.nombre_producto || '').trim()
          }));
          setCatalogo(map);
        }
      } catch (err) {
        console.warn("No se pudo precargar catálogo SOP:", err);
      }
    }
    loadCatalog();
    loadMateriales();
  }, []);

  async function loadMateriales() {
    try {
      const res = await api.fetchMaterialesMaquila({ solo_activos: true });
      setMaterialesMaquila(res.data || []);
    } catch (err) {
      console.warn("No se pudo precargar materiales maquila:", err);
    }
  }

  useEffect(() => {
    if (view === 'list' && activeTab === 'recetas') {
      loadFamilias();
    } else if (activeTab === 'distribucion') {
      loadDistribucion();
    }
    if (view === 'form') {
      loadMateriales();
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
        nombre_familia: data.descripcion || data.nombre_familia || '',
        producto_objetivo: data.producto_objetivo || '',
        activa: data.activa !== false,
        tiempo_base_1p_min: data.tiempo_base_1p_min != null ? data.tiempo_base_1p_min : '',
        unidades_base_tiempo: data.unidades_base_tiempo || 100,
        costo_hora: data.costo_hora != null && Number(data.costo_hora) > 0 ? data.costo_hora : '',
        costo_maquila_estimado: Number(data.costo_maquila_estimado) || 0,
        miembros: (data.miembros || []).map(m => ({
          codigo_femaco: m.codigo_femaco || m.sku_componente || '',
          nombre_componente: m.nombre_componente || m.nombre_producto || '',
          cantidad_por_unidad: m.cantidad_por_unidad != null ? m.cantidad_por_unidad : 1.0,
          costo_unitario: m.costo_unitario != null ? Number(m.costo_unitario) : 0,
          tipo_componente: m.tipo_componente || 'PRODUCTO',
          unidad_medida: m.unidad_medida || 'UN',
          no_transformable: Boolean(m.no_transformable),
          observacion: m.observacion || ''
        })),
        tiempos: (data.tiempos || []).map(t => ({
          id: t.id,
          cantidad_personas: t.cantidad_personas || 1,
          tiempo_minutos: t.tiempo_minutos != null ? t.tiempo_minutos : '',
          unidades_base: t.unidades_base || 100,
          observaciones: t.observaciones || ''
        }))
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
    if (!window.confirm(`¿Seguro que desea ${currentActive ? 'desactivar' : 'activar'} esta familia/receta?`)) return;
    try {
      await api.toggleReceta(id, !currentActive);
      loadFamilias();
    } catch (err) {
      alert(err.message);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("¿Seguro que desea eliminar esta familia/receta permanentemente? Se eliminarán también sus componentes y registros de tiempos.")) return;
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
    if (!formData.nombre_familia.trim()) return alert("El nombre de la familia o receta es requerido");
    if (!formData.miembros || formData.miembros.length === 0) {
      return alert("Debe agregar al menos un integrante o material a la receta");
    }

    for (let i = 0; i < formData.miembros.length; i++) {
      const m = formData.miembros[i];
      if (!m.codigo_femaco || !m.codigo_femaco.trim()) {
        return alert(`La fila #${i + 1} no tiene código especificado`);
      }
      if (m.cantidad_por_unidad == null || Number(m.cantidad_por_unidad) <= 0) {
        return alert(`La fila #${i + 1} (${m.codigo_femaco}) debe tener una proporción/cantidad mayor a 0`);
      }
    }

    // Calcular costo maquila unitario estimado automáticamente
    const costoInsumos = formData.miembros
      .filter(m => m.tipo_componente === 'MATERIAL')
      .reduce((sum, m) => sum + ((Number(m.cantidad_por_unidad) || 0) * (Number(m.costo_unitario) || 0)), 0);
    
    const cHora = Number(formData.costo_hora) || 0;
    const tBaseMin = Number(formData.tiempo_base_1p_min) || 0;
    const uBase = Number(formData.unidades_base_tiempo) || 100;
    const velUdsHora = tBaseMin > 0 ? (uBase / tBaseMin) * 60 : 0;
    const cManoObra = velUdsHora > 0 && cHora > 0 ? (cHora / velUdsHora) : 0;
    const costoMaquilaEstimado = Number((costoInsumos + cManoObra).toFixed(2));
    
    try {
      setLoading(true);
      const payload = {
        ...formData,
        tiempo_base_1p_min: formData.tiempo_base_1p_min !== '' ? Number(formData.tiempo_base_1p_min) : null,
        unidades_base_tiempo: Number(formData.unidades_base_tiempo) || 100,
        costo_hora: cHora,
        costo_maquila_estimado: costoMaquilaEstimado,
        miembros: formData.miembros.map(m => ({
          ...m,
          codigo_femaco: m.codigo_femaco.trim().toUpperCase(),
          cantidad_por_unidad: Number(m.cantidad_por_unidad) || 1.0,
          costo_unitario: Number(m.costo_unitario) || 0
        })),
        tiempos: formData.tiempos.filter(t => t.tiempo_minutos !== '' && Number(t.tiempo_minutos) > 0).map(t => ({
          ...t,
          cantidad_personas: Number(t.cantidad_personas) || 1,
          tiempo_minutos: Number(t.tiempo_minutos),
          unidades_base: Number(t.unidades_base) || 100
        }))
      };

      if (currentFamiliaId) {
        await api.updateReceta(currentFamiliaId, payload);
      } else {
        await api.createReceta(payload);
      }
      setView('list');
      loadFamilias();
    } catch(err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function addMiembro(tipo = 'PRODUCTO') {
    let defaultCodigo = '';
    let defaultNombre = '';
    let defaultUm = 'UN';
    let defaultCosto = 0;

    if (tipo === 'MATERIAL' && materialesMaquila.length > 0) {
      const usedSkus = new Set(formData.miembros.map(m => m.codigo_femaco));
      const available = materialesMaquila.find(m => !usedSkus.has(m.sku)) || materialesMaquila[0];
      defaultCodigo = available.sku;
      defaultNombre = available.nombre || '';
      defaultUm = available.unidad_medida || 'UN';
      defaultCosto = Number(available.costo_unitario) || 0;
    }

    setFormData({
      ...formData,
      miembros: [
        ...formData.miembros,
        {
          codigo_femaco: defaultCodigo,
          nombre_componente: defaultNombre,
          cantidad_por_unidad: 1.0,
          costo_unitario: defaultCosto,
          tipo_componente: tipo,
          unidad_medida: defaultUm,
          no_transformable: false,
          observacion: ''
        }
      ]
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

    // Si cambia de tipo
    if (field === 'tipo_componente') {
      if (val === 'MATERIAL') {
        const mat = materialesMaquila.find(x => x.sku === newMembers[idx].codigo_femaco) || materialesMaquila[0];
        if (mat) {
          newMembers[idx].codigo_femaco = mat.sku;
          newMembers[idx].nombre_componente = mat.nombre || '';
          newMembers[idx].unidad_medida = mat.unidad_medida || 'UN';
          newMembers[idx].costo_unitario = Number(mat.costo_unitario) || 0;
        }
      }
    }

    // Si escribe o selecciona el código
    if (field === 'codigo_femaco') {
      const upper = String(val || '').trim().toUpperCase();
      if (newMembers[idx].tipo_componente === 'MATERIAL') {
        const mat = materialesMaquila.find(m => m.sku === upper);
        if (mat) {
          newMembers[idx].nombre_componente = mat.nombre || '';
          newMembers[idx].unidad_medida = mat.unidad_medida || 'UN';
          newMembers[idx].costo_unitario = Number(mat.costo_unitario) || 0;
        }
      } else {
        const match = catalogo.find(c => c.codigo_femaco === upper || c.sku === upper);
        if (match && !newMembers[idx].nombre_componente) {
          newMembers[idx].nombre_componente = match.nombre_producto;
        }
      }
    }
    setFormData({ ...formData, miembros: newMembers });
  }

  function addTiempoRow() {
    const personasExistentes = formData.tiempos.map(t => Number(t.cantidad_personas));
    let nextP = 1;
    if (personasExistentes.includes(1) && !personasExistentes.includes(3)) nextP = 3;
    else if (personasExistentes.includes(3) && !personasExistentes.includes(4)) nextP = 4;
    else if (personasExistentes.includes(4) && !personasExistentes.includes(6)) nextP = 6;
    else if (personasExistentes.includes(6)) nextP = Math.max(...personasExistentes) + 2;

    setFormData({
      ...formData,
      tiempos: [
        ...formData.tiempos,
        {
          cantidad_personas: nextP,
          tiempo_minutos: '',
          unidades_base: Number(formData.unidades_base_tiempo) || 100,
          observaciones: ''
        }
      ]
    });
  }

  function updateTiempoRow(idx, field, val) {
    const newTiempos = [...formData.tiempos];
    newTiempos[idx][field] = val;
    setFormData({ ...formData, tiempos: newTiempos });
  }

  function removeTiempoRow(idx) {
    const newTiempos = [...formData.tiempos];
    newTiempos.splice(idx, 1);
    setFormData({ ...formData, tiempos: newTiempos });
  }

  function openQuickTimeModal(receta) {
    setQuickTimeModal({
      open: true,
      recetaId: receta.id,
      nombreFamilia: receta.nombre_familia || receta.identificador,
      cantidadPersonas: 6,
      unidadesBase: receta.unidades_base_tiempo || 100,
      tiempoMinutos: '',
      observaciones: '',
      loading: false
    });
  }

  async function handleSaveQuickTime() {
    if (!quickTimeModal.tiempoMinutos || Number(quickTimeModal.tiempoMinutos) <= 0) {
      alert("Ingrese los minutos demorados en la prueba");
      return;
    }
    try {
      setQuickTimeModal(prev => ({ ...prev, loading: true }));
      await api.addRecetaTiempo(quickTimeModal.recetaId, {
        cantidad_personas: Number(quickTimeModal.cantidadPersonas) || 1,
        unidades_base: Number(quickTimeModal.unidadesBase) || 100,
        tiempo_minutos: Number(quickTimeModal.tiempoMinutos),
        observaciones: quickTimeModal.observaciones.trim()
      });
      setQuickTimeModal({ open: false, recetaId: null });
      loadFamilias();
    } catch (err) {
      alert("Error al registrar prueba de tiempo: " + err.message);
      setQuickTimeModal(prev => ({ ...prev, loading: false }));
    }
  }

  const filteredFamilias = familias.filter(r => {
    if (filterActive === 'active' && !r.activa) return false;
    if (filterActive === 'inactive' && r.activa) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!r.nombre_familia?.toLowerCase().includes(q) && 
          !r.identificador?.toLowerCase().includes(q) &&
          !r.producto_objetivo?.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  if (loading && view === 'list' && familias.length === 0 && activeTab === 'recetas') {
    return <div className="page" style={{ padding: '40px', textAlign: 'center' }}>Cargando familias y recetas...</div>;
  }

  return (
    <div className="content-area">
      <div className="main-panel">
        <div className="page" style={{ padding: '20px', maxWidth: '1240px', margin: '0 auto', width: '100%' }}>
          
          {/* ── TABS PRINCIPALES ── */}
          <div style={{ display: 'flex', gap: '20px', borderBottom: '2px solid #cbd5e1', marginBottom: '20px' }}>
            <h2 
              style={{ 
                margin: 0, paddingBottom: '10px', cursor: 'pointer', 
                color: activeTab === 'recetas' ? '#1976d2' : '#64748b', 
                borderBottom: activeTab === 'recetas' ? '3px solid #1976d2' : 'none', 
                fontSize: '1.15rem', fontWeight: activeTab === 'recetas' ? 700 : 500 
              }}
              onClick={() => setActiveTab('recetas')}
            >
              👨‍👦 Hermanos y Recetas de Maquila
            </h2>
            <h2 
              style={{ 
                margin: 0, paddingBottom: '10px', cursor: 'pointer', 
                color: activeTab === 'distribucion' ? '#1976d2' : '#64748b', 
                borderBottom: activeTab === 'distribucion' ? '3px solid #1976d2' : 'none', 
                fontSize: '1.15rem', fontWeight: activeTab === 'distribucion' ? 700 : 500 
              }}
              onClick={() => setActiveTab('distribucion')}
            >
              ⚖️ Distribución Homogénea (Plan de Maquila)
            </h2>
            <h2 
              style={{ 
                margin: 0, paddingBottom: '10px', cursor: 'pointer', 
                color: activeTab === 'ordenes' ? '#1976d2' : '#64748b', 
                borderBottom: activeTab === 'ordenes' ? '3px solid #1976d2' : 'none', 
                fontSize: '1.15rem', fontWeight: activeTab === 'ordenes' ? 700 : 500 
              }}
              onClick={() => setActiveTab('ordenes')}
            >
              📑 Órdenes de Corte / Trabajo
            </h2>
            <h2 
              style={{ 
                margin: 0, paddingBottom: '10px', cursor: 'pointer', 
                color: activeTab === 'simulador' ? '#1976d2' : '#64748b', 
                borderBottom: activeTab === 'simulador' ? '3px solid #1976d2' : 'none', 
                fontSize: '1.15rem', fontWeight: activeTab === 'simulador' ? 700 : 500 
              }}
              onClick={() => setActiveTab('simulador')}
            >
              🧮 Simulador: ¿Cuánto Puedo Maquilar Hoy?
            </h2>
          </div>

          {activeTab === 'ordenes' && <MaquilaOrdenes isAdmin={isAdmin} />}

          {/* ── TAB SIMULADOR: ¿CUÁNTO PUEDO MAQUILAR HOY? ── */}
          {activeTab === 'simulador' && (() => {
            const filteredSim = simuladorData.filter(item => {
              if (searchSimulador) {
                const q = searchSimulador.toLowerCase();
                const matchSku = (item.sku || '').toLowerCase().includes(q);
                const matchNom = (item.nombre || '').toLowerCase().includes(q);
                const matchFam = (item.familia_nombre || '').toLowerCase().includes(q);
                if (!matchSku && !matchNom && !matchFam) return false;
              }
              if (filterCuello === 'DISPONIBLE') return item.max_producible > 0;
              if (filterCuello === 'CERO') return item.max_producible === 0;
              if (filterCuello === 'MATERIAL') return item.cuello_de_botella?.tipo === 'MATERIAL';
              if (filterCuello === 'PRODUCTO') return item.cuello_de_botella?.tipo === 'PRODUCTO';
              return true;
            });

            const totalSim = simuladorData.length;
            const conStock = simuladorData.filter(s => s.max_producible > 0).length;
            const limitMat = simuladorData.filter(s => s.cuello_de_botella?.tipo === 'MATERIAL').length;
            const limitProd = simuladorData.filter(s => s.cuello_de_botella?.tipo === 'PRODUCTO').length;

            return (
              <div>
                {/* Banner de Introducción */}
                <div className="card" style={{ padding: '18px 22px', marginBottom: '20px', borderLeft: '4px solid #7e22ce', background: '#faf5ff', border: '1px solid #e9d5ff' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
                    <div style={{ flex: 1, minWidth: '300px' }}>
                      <h3 style={{ margin: '0 0 6px', color: '#6b21a8', fontSize: '1.15rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span>🧮</span> Simulador de Capacidad y Detección de Cuellos de Botella
                      </h3>
                      <p style={{ margin: 0, color: '#334155', fontSize: '0.88rem', lineHeight: 1.5 }}>
                        Calcula al instante cuántas unidades máximas de cada producto puedes armar hoy, cruzando el stock de productos hermanos en <b>planificacion_sop</b> con los insumos y empaques en <b>materiales_maquila</b>.
                        Te indica exactamente qué material falta o si estás limitado por el producto base.
                      </p>
                    </div>
                    <button
                      className="btn-secondary"
                      onClick={loadSimulador}
                      disabled={loadingSimulador}
                      style={{ padding: '8px 16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <span>🔄</span> {loadingSimulador ? 'Recalculando...' : 'Actualizar Stock en Vivo'}
                    </button>
                  </div>
                </div>

                {/* KPIs Rápidos */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', marginBottom: '20px' }}>
                  <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #e2e8f0', borderLeft: '4px solid #0284c7', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Productos Evaluados</div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0f172a', marginTop: '2px' }}>{totalSim}</div>
                    <div style={{ fontSize: '0.75rem', color: '#0284c7', fontWeight: 600 }}>En familias activas</div>
                  </div>

                  <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #e2e8f0', borderLeft: '4px solid #16a34a', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Con Capacidad Inmediata</div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#16a34a', marginTop: '2px' }}>{conStock}</div>
                    <div style={{ fontSize: '0.75rem', color: '#16a34a', fontWeight: 600 }}>Listos para producir hoy</div>
                  </div>

                  <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #e2e8f0', borderLeft: '4px solid #e11d48', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Limitados por Insumos</div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#e11d48', marginTop: '2px' }}>{limitMat}</div>
                    <div style={{ fontSize: '0.75rem', color: '#be123c', fontWeight: 600 }}>Faltan etiquetas/mangas/cajas</div>
                  </div>

                  <div className="card" style={{ padding: '14px 18px', background: '#ffffff', border: '1px solid #e2e8f0', borderLeft: '4px solid #f59e0b', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Limitados por Hermanos</div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#b45309', marginTop: '2px' }}>{limitProd}</div>
                    <div style={{ fontSize: '0.75rem', color: '#b45309', fontWeight: 600 }}>Falta stock base para desarmar</div>
                  </div>
                </div>

                {/* Filtros */}
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '20px', alignItems: 'center' }}>
                  <input
                    type="text"
                    value={searchSimulador}
                    onChange={e => setSearchSimulador(e.target.value)}
                    placeholder="🔍 Buscar por SKU o nombre de producto..."
                    style={{ flex: 1, minWidth: '240px', padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontSize: '0.9rem' }}
                  />
                  <select
                    value={filterCuello}
                    onChange={e => setFilterCuello(e.target.value)}
                    style={{ padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 600, fontSize: '0.88rem', background: '#ffffff' }}
                  >
                    <option value="ALL">Todos los Estados</option>
                    <option value="DISPONIBLE">✓ Con Capacidad Inmediata (&gt;0)</option>
                    <option value="MATERIAL">⚠️ Limitados por Insumos (Etiquetas / Mangas)</option>
                    <option value="PRODUCTO">🔄 Limitados por Stock de Hermanos</option>
                    <option value="CERO">🔴 Sin Capacidad (0 unidades)</option>
                  </select>
                </div>

                {loadingSimulador && simuladorData.length === 0 ? (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Calculando capacidad de maquila en vivo...</div>
                ) : filteredSim.length === 0 ? (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    No se encontraron productos coincidentes con los filtros seleccionados.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {filteredSim.map((item, idx) => {
                      const isZero = item.max_producible === 0;
                      const cuello = item.cuello_de_botella || {};
                      const isMatCuello = cuello.tipo === 'MATERIAL';

                      return (
                        <div key={`${item.receta_id}-${item.sku}-${idx}`} className="card" style={{ padding: '20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.03)' }}>
                          {/* Cabecera del ítem */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', borderBottom: '1px solid #f1f5f9', paddingBottom: '14px', marginBottom: '14px' }}>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: '1.15rem', color: '#0369a1' }}>
                                  {item.sku}
                                </span>
                                <span style={{ fontSize: '0.78rem', background: '#f1f5f9', color: '#475569', padding: '3px 8px', borderRadius: '4px', fontWeight: 600 }}>
                                  {item.familia_nombre}
                                </span>
                              </div>
                              <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem', marginTop: '2px' }}>
                                {item.nombre}
                              </div>
                              <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '2px' }}>
                                Stock terminado actual en bodega: <b>{item.stock_actual} uds</b>
                              </div>
                            </div>

                            {/* Badge Capacidad Máxima */}
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                                Máximo Producible Hoy
                              </div>
                              <div style={{
                                display: 'inline-block',
                                padding: '6px 16px',
                                borderRadius: '24px',
                                marginTop: '4px',
                                fontWeight: 900,
                                fontSize: '1.25rem',
                                background: isZero ? '#fee2e2' : item.max_producible < 100 ? '#fef3c7' : '#dcfce7',
                                color: isZero ? '#991b1b' : item.max_producible < 100 ? '#b45309' : '#166534',
                                border: '1.5px solid currentColor'
                              }}>
                                {item.max_producible.toLocaleString()} uds
                              </div>
                            </div>
                          </div>

                          {/* Banner Cuello de Botella */}
                          <div style={{
                            padding: '10px 14px',
                            borderRadius: '6px',
                            marginBottom: '14px',
                            fontSize: '0.86rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: isZero ? '#fff1f2' : isMatCuello ? '#fffbeb' : '#f0fdf4',
                            border: `1px solid ${isZero ? '#fecdd3' : isMatCuello ? '#fde68a' : '#bbf7d0'}`,
                            color: isZero ? '#9f1239' : isMatCuello ? '#92400e' : '#166534'
                          }}>
                            <span style={{ fontSize: '1.1rem' }}>{isZero ? '🔴' : isMatCuello ? '⚠️' : '✓'}</span>
                            <div>
                              <b>{isZero ? 'Sin Capacidad Inmediata:' : isMatCuello ? 'Cuello de Botella en Insumos:' : 'Capacidad de Producción:'}</b>{' '}
                              {isMatCuello ? (
                                <span>Limitado por <b>{cuello.nombre} ({cuello.sku})</b>. Stock actual de insumo: <b>{cuello.stock_actual}</b> (alcanza para <b>{cuello.max_posible} uds</b>).</span>
                              ) : (
                                <span>{cuello.motivo || `Rinde hasta ${item.max_producible} unidades.`}</span>
                              )}
                            </div>
                          </div>

                          {/* 2 Columnas: Hermanos vs Insumos */}
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginBottom: '14px' }}>
                            {/* Columna Hermanos */}
                            <div style={{ background: '#f8fafc', padding: '12px 14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                              <div style={{ fontSize: '0.8rem', fontWeight: 800, color: '#334155', textTransform: 'uppercase', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
                                <span>🔄 Hermanos para Desarmar</span>
                                <span style={{ color: '#0284c7' }}>Capacidad: {item.capacidad_por_hermanos} uds</span>
                              </div>
                              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                                <tbody>
                                  {item.hermanos_disponibles.map(h => (
                                    <tr key={h.sku} style={{ borderBottom: '1px solid #e2e8f0' }}>
                                      <td style={{ padding: '5px 0', fontWeight: 700, fontFamily: 'monospace' }}>{h.sku}</td>
                                      <td style={{ padding: '5px 4px', color: '#64748b' }}>Stock: {h.stock_actual}</td>
                                      <td style={{ padding: '5px 0', textAlign: 'right', fontWeight: 700, color: h.unidades_producibles > 0 ? '#15803d' : '#94a3b8' }}>
                                        rinde {h.unidades_producibles} uds
                                      </td>
                                    </tr>
                                  ))}
                                  {item.hermanos_disponibles.length === 0 && (
                                    <tr><td colSpan="3" style={{ padding: '6px 0', color: '#94a3b8' }}>Sin otros hermanos compatibles</td></tr>
                                  )}
                                </tbody>
                              </table>
                            </div>

                            {/* Columna Insumos */}
                            <div style={{ background: '#f8fafc', padding: '12px 14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                              <div style={{ fontSize: '0.8rem', fontWeight: 800, color: '#334155', textTransform: 'uppercase', marginBottom: '6px', display: 'flex', justifyContent: 'space-between' }}>
                                <span>📦 Insumos en Bodega</span>
                                <span style={{ color: '#7e22ce' }}>Capacidad: {item.capacidad_por_materiales} uds</span>
                              </div>
                              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                                <tbody>
                                  {item.materiales_evaluacion.map(m => (
                                    <tr key={m.sku} style={{ borderBottom: '1px solid #e2e8f0', background: m.es_cuello_botella ? '#fef2f2' : 'inherit' }}>
                                      <td style={{ padding: '5px 0', fontWeight: 700, fontFamily: 'monospace', color: m.es_cuello_botella ? '#b91c1c' : '#334155' }}>
                                        {m.sku}
                                        {m.es_cuello_botella && <span style={{ color: '#e11d48', marginLeft: '4px' }}>★</span>}
                                      </td>
                                      <td style={{ padding: '5px 4px', color: '#64748b' }}>Stock: {m.stock_actual}</td>
                                      <td style={{ padding: '5px 0', textAlign: 'right', fontWeight: 700, color: m.es_cuello_botella ? '#e11d48' : '#15803d' }}>
                                        alcanza {m.max_posible} uds
                                      </td>
                                    </tr>
                                  ))}
                                  {item.materiales_evaluacion.length === 0 && (
                                    <tr><td colSpan="3" style={{ padding: '6px 0', color: '#94a3b8' }}>No requiere insumos adicionales</td></tr>
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </div>

                          {/* Barra de Costeo y Productividad del Lote */}
                          {item.max_producible > 0 && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f1f5f9', padding: '10px 14px', borderRadius: '6px', flexWrap: 'wrap', gap: '10px', fontSize: '0.84rem' }}>
                              <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                                <span>Costo Insumos: <b>${Math.round(item.costeo_lote.costo_insumos).toLocaleString('es-CL')}</b></span>
                                <span>Mano de Obra: <b>${Math.round(item.costeo_lote.costo_mano_obra).toLocaleString('es-CL')}</b></span>
                                <span style={{ color: '#16a34a' }}>Costo Total Lote: <b>${Math.round(item.costeo_lote.costo_total).toLocaleString('es-CL')}</b> (${item.costeo_lote.costo_unitario_maquila}/ud)</span>
                                <span style={{ color: '#7e22ce' }}>Tiempo: <b>{item.costeo_lote.horas_1p}h</b> (1 pers.) | <b>{item.costeo_lote.horas_3p}h</b> (3 pers.)</span>
                              </div>
                              <button
                                type="button"
                                onClick={() => setActiveTab('ordenes')}
                                style={{ padding: '5px 12px', background: '#0284c7', color: '#fff', border: 'none', borderRadius: '4px', fontWeight: 700, fontSize: '0.78rem', cursor: 'pointer' }}
                              >
                                Ir a Órdenes de Maquila →
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })()}

          {/* ── TAB DISTRIBUCIÓN HOMOGÉNEA DE FAMILIAS ── */}
          {activeTab === 'distribucion' && (
            <div>
              <div className="card" style={{ padding: '16px 20px', marginBottom: '20px', borderLeft: '4px solid #1976d2', background: '#eff6ff', border: '1px solid #bfdbfe' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                  <div style={{ flex: 1, minWidth: '300px' }}>
                    <h3 style={{ margin: '0 0 6px', color: '#1e40af', fontSize: '1.1rem', fontWeight: 700 }}>
                      🏭 Regla de Negocio: Sustitución y Transformación Homogénea Familiar
                    </h3>
                    <p style={{ margin: 0, color: '#1e293b', fontSize: '0.88rem', lineHeight: 1.5 }}>
                      Los productos que pertenecen a una familia de reemplazo no se compran si el grupo familiar tiene inventario suficiente para cubrir la demanda.
                      Las unidades se distribuyen de manera homogénea entre los integrantes. Solo si el total familiar queda en déficit, el saldo faltante pasa a compra en el módulo Compras.
                    </p>
                  </div>
                  <button
                    className="btn-primary"
                    style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', whiteSpace: 'nowrap', fontWeight: 600 }}
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
                  style={{ flex: 1, minWidth: '220px', padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a', fontSize: '0.9rem', outline: 'none' }}
                />
                <select
                  value={filterDistribucion}
                  onChange={e => setFilterDistribucion(e.target.value)}
                  style={{ padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', background: '#ffffff', color: '#0f172a', fontSize: '0.9rem', fontWeight: 500, outline: 'none' }}
                >
                  <option value="ALL">Todas las Familias</option>
                  <option value="CUBIERTAS">100% Cubiertas por Maquila (0 compra)</option>
                  <option value="DEFICIT">Con Déficit Familiar (Pasa a compra)</option>
                </select>
              </div>

              {loadingDistribucion ? (
                <div style={{ padding: '40px', textAlign: 'center', color: '#475569', fontWeight: 500 }}>Calculando distribución homogénea familiar...</div>
              ) : distribucionData.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: '#475569', fontWeight: 500 }}>No hay familias activas registradas para calcular distribución.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {distribucionData
                    .filter(f => {
                      if (filterDistribucion === 'CUBIERTAS' && !f.cubre_con_stock_familiar) return false;
                      if (filterDistribucion === 'DEFICIT' && f.cubre_con_stock_familiar) return false;
                      if (searchDistribucion) {
                        const q = searchDistribucion.toLowerCase();
                        const matchName = f.nombre_familia.toLowerCase().includes(q);
                        const matchMember = f.miembros.some(m => (m.sku || '').toLowerCase().includes(q) || (m.codigo_femaco || '').toLowerCase().includes(q));
                        if (!matchName && !matchMember) return false;
                      }
                      return true;
                    })
                    .map(f => {
                      const cubre = f.cubre_con_stock_familiar;
                      return (
                        <div key={f.familia_id} className="card" style={{ padding: '18px 20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', borderLeft: `5px solid ${cubre ? '#16a34a' : '#ea580c'}`, boxShadow: '0 2px 5px rgba(0,0,0,0.06)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                            <div>
                              <h3 style={{ margin: '0 0 4px', fontSize: '1.2rem', color: '#0f172a', fontWeight: 700 }}>
                                {f.nombre_familia}
                              </h3>
                              <span style={{ fontSize: '0.82rem', color: '#64748b', fontWeight: 500 }}>
                                {f.cantidad_miembros} integrantes vinculados | ID #{f.familia_id}
                              </span>
                            </div>

                            <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>Stock Familiar Disponible</div>
                                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0284c7' }}>
                                  {Math.round(f.total_stock_familia).toLocaleString()} uds
                                </div>
                              </div>

                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>Demanda Total Familia</div>
                                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a' }}>
                                  {Math.round(f.total_demanda_familia).toLocaleString()} uds
                                </div>
                              </div>

                              <div style={{ textAlign: 'center', padding: '6px 14px', borderRadius: '6px', background: cubre ? '#ecfdf5' : '#fffbeb', border: `1px solid ${cubre ? '#86efac' : '#fcd34d'}` }}>
                                <span style={{ fontSize: '0.7rem', display: 'block', textTransform: 'uppercase', color: cubre ? '#15803d' : '#b45309', fontWeight: 700 }}>
                                  Cobertura Familiar
                                </span>
                                <span style={{ fontSize: '1.15rem', fontWeight: 800, color: cubre ? '#166534' : '#9a3412' }}>
                                  {f.cobertura_pct}%
                                </span>
                              </div>

                              <div>
                                {cubre ? (
                                  <span style={{
                                    padding: '7px 14px', borderRadius: '6px', fontSize: '0.82rem', fontWeight: 700,
                                    background: '#ecfdf5', color: '#15803d', border: '1px solid #86efac', display: 'inline-block'
                                  }}>
                                    ✓ Cubierto 100% por Maquila (0 compra)
                                  </span>
                                ) : (
                                  <span style={{
                                    padding: '7px 14px', borderRadius: '6px', fontSize: '0.82rem', fontWeight: 700,
                                    background: '#fef2f2', color: '#b91c1c', border: '1px solid #fca5a5', display: 'inline-block'
                                  }}>
                                    🛒 Déficit: Comprar {Math.round(f.total_compra_remanente_sugerida).toLocaleString()} uds
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          <div style={{ overflowX: 'auto', borderRadius: '6px', border: '1px solid #cbd5e1' }}>
                            <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                              <thead>
                                <tr style={{ background: '#1e293b', textAlign: 'left', borderBottom: '2px solid #0f172a' }}>
                                  <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600 }}>Cód. Interno / SKU</th>
                                  <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600 }}>Producto</th>
                                  <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600 }}>Stock Inicial Total</th>
                                  <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600 }}>Demanda Objetivo</th>
                                  <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600 }}>Asignación Homogénea</th>
                                  <th style={{ padding: '10px 12px', textAlign: 'center', color: '#ffffff', fontWeight: 600 }}>Saldo Transformación (Maquila)</th>
                                  <th style={{ padding: '10px 12px', textAlign: 'center', color: '#ffffff', fontWeight: 600 }}>Cobertura Lograda</th>
                                  <th style={{ padding: '10px 12px', textAlign: 'right', color: '#ffffff', fontWeight: 600 }}>Compra Neta</th>
                                  <th style={{ padding: '10px 12px', color: '#ffffff', fontWeight: 600 }}>Resolución Operativa</th>
                                </tr>
                              </thead>
                              <tbody>
                                {f.miembros.map((m, idx) => {
                                  const transf = m.saldo_transformacion;
                                  return (
                                    <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0', background: idx % 2 === 0 ? '#ffffff' : '#f8fafc' }}>
                                      <td style={{ padding: '10px 12px', fontWeight: 700, color: '#0369a1' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                                          <span>{m.codigo_femaco} {m.sku && m.sku !== m.codigo_femaco && `(${m.sku})`}</span>
                                          {m.es_descontinuado && (
                                            <span style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: '4px', background: '#fee2e2', color: '#991b1b', fontWeight: 700 }}>
                                              DESCONTINUADO
                                            </span>
                                          )}
                                          {m.estado && m.estado.includes('BLOQUE') && (
                                            <span style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: '4px', background: '#fef3c7', color: '#92400e', fontWeight: 700 }}>
                                              BLOQUEADO
                                            </span>
                                          )}
                                        </div>
                                      </td>
                                      <td style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 500 }}>{m.nombre_producto}</td>
                                      <td style={{ padding: '10px 12px', textAlign: 'right', color: '#334155', fontWeight: 600 }}>
                                        {Math.round(m.stock_total).toLocaleString()}
                                      </td>
                                      <td style={{ padding: '10px 12px', textAlign: 'right', color: '#334155', fontWeight: 600 }}>
                                        {Math.round(m.demanda).toLocaleString()}
                                      </td>
                                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#0284c7' }}>
                                        {Math.round(m.stock_asignado_homogeneo).toLocaleString()}
                                      </td>
                                      <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                                        {transf > 0 ? (
                                          <span style={{ color: '#15803d', fontWeight: 700 }}>
                                            + Recibir {Math.round(transf).toLocaleString()} uds (Maquilar)
                                          </span>
                                        ) : transf < 0 ? (
                                          <span style={{ color: '#c2410c', fontWeight: 700 }}>
                                            - Ceder {Math.round(Math.abs(transf)).toLocaleString()} uds a hermanos
                                          </span>
                                        ) : (
                                          <span style={{ color: '#64748b', fontWeight: 500 }}>Equilibrado</span>
                                        )}
                                      </td>
                                      <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 700, color: m.cobertura_post_distribucion_pct >= 100 ? '#15803d' : '#d97706' }}>
                                        {m.cobertura_post_distribucion_pct}%
                                      </td>
                                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 800, color: m.compra_remanente_sugerida > 0 ? '#dc2626' : '#15803d' }}>
                                        {m.compra_remanente_sugerida > 0 ? `${m.compra_remanente_sugerida.toLocaleString()} uds` : '0 (No comprar)'}
                                      </td>
                                      <td style={{ padding: '10px 12px', fontSize: '0.82rem', fontWeight: 500, color: m.cubierto_por_maquila ? '#15803d' : '#334155' }}>
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

          {/* ── TAB RECETAS / FAMILIAS ── */}
          {activeTab === 'recetas' && (
            <>
              {/* Header de la sección */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h1 style={{ margin: '0 0 4px', fontSize: '1.6rem', color: '#0f172a', fontWeight: 800 }}>
                    Hermanos y Recetas de Maquila (BOM)
                  </h1>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '0.9rem' }}>
                    Configuración de relaciones de sustitución, receta de ensamble (proporciones de producto y materiales) y tiempos de productividad.
                  </p>
                </div>
                {view === 'list' && isAdmin && (
                  <button 
                    className="btn-primary" 
                    style={{ padding: '10px 20px', fontSize: '0.95rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}
                    onClick={() => {
                      setCurrentFamiliaId(null);
                      setFormData({ 
                        nombre_familia: '', 
                        producto_objetivo: '', 
                        activa: true, 
                        tiempo_base_1p_min: '',
                        unidades_base_tiempo: 100,
                        costo_hora: '',
                        costo_maquila_estimado: 0,
                        miembros: [
                          { codigo_femaco: '', nombre_componente: '', cantidad_por_unidad: 1.0, costo_unitario: 0, tipo_componente: 'PRODUCTO', unidad_medida: 'UN', no_transformable: false, observacion: '' }
                        ], 
                        tiempos: [] 
                      });
                      setView('form');
                    }}
                  >
                    <span>➕</span> Nueva Familia / Receta
                  </button>
                )}
                {view !== 'list' && (
                  <button className="btn-secondary" style={{ padding: '8px 16px', fontWeight: 600 }} onClick={() => setView('list')}>
                    ← Volver al Listado
                  </button>
                )}
              </div>

              {error && <div className="alert-error" style={{ marginBottom: '1rem', color: '#b91c1c', background: '#fee2e2', padding: '12px', borderRadius: '6px' }}>{error}</div>}

              {/* ── VISTA LISTADO ── */}
              {view === 'list' && (
                <div className="card" style={{ padding: '20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
                  <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
                    <input 
                      type="text" 
                      placeholder="🔍 Buscar por nombre de familia, código o producto objetivo..." 
                      value={search} 
                      onChange={e => setSearch(e.target.value)}
                      style={{ flex: 1, minWidth: '260px', padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1' }}
                    />
                    <select 
                      value={filterActive} 
                      onChange={e => setFilterActive(e.target.value)} 
                      style={{ padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 500 }}
                    >
                      <option value="all">Todas las recetas</option>
                      <option value="active">Solo Activas</option>
                      <option value="inactive">Solo Inactivas</option>
                    </select>
                  </div>

                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Familia / Receta</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Producto Objetivo</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Composición (BOM)</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Tiempo Base (1 Persona)</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Costo Maquila ($/ud)</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Pruebas con Dotación</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Estado</th>
                          <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700, textAlign: 'center' }}>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredFamilias.map(r => {
                          const baseMin = r.tiempo_base_1p_min != null ? Number(r.tiempo_base_1p_min) : null;
                          const uBase = r.unidades_base_tiempo || 100;
                          const rate1p = baseMin && baseMin > 0 ? Math.round((uBase / baseMin) * 60) : null;
                          const cMaq = Number(r.costo_maquila_estimado) || 0;
                          const cHora = Number(r.costo_hora) || 0;
                          
                          return (
                            <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '12px 14px', fontWeight: 700, color: '#0f172a' }}>
                                <div style={{ fontSize: '0.95rem' }}>{r.nombre_familia || r.identificador}</div>
                                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>ID #{r.id} • {r.identificador}</div>
                              </td>

                              <td style={{ padding: '12px 14px' }}>
                                {r.producto_objetivo ? (
                                  <span style={{ background: '#dcfce7', color: '#15803d', padding: '4px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.82rem' }}>
                                    🎯 {r.producto_objetivo}
                                  </span>
                                ) : (
                                  <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.82rem' }}>Intercambio general</span>
                                )}
                              </td>

                              <td style={{ padding: '12px 14px' }}>
                                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                                  <span style={{ background: '#e0f2fe', color: '#0369a1', padding: '3px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                                    📦 {r.cantidad_productos || r.cantidad_miembros || 0} hermanos
                                  </span>
                                  {r.cantidad_materiales > 0 && (
                                    <span style={{ background: '#fef3c7', color: '#b45309', padding: '3px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                                      🏷️ {r.cantidad_materiales} materiales/insumos
                                    </span>
                                  )}
                                </div>
                              </td>

                              <td style={{ padding: '12px 14px' }}>
                                {baseMin ? (
                                  <div>
                                    <span style={{ fontWeight: 700, color: '#0284c7' }}>{baseMin} min</span>
                                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}> / {uBase} uds</span>
                                    {rate1p && (
                                      <div style={{ fontSize: '0.75rem', color: '#16a34a', fontWeight: 600 }}>
                                        ⚡ {rate1p} uds/h
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span style={{ color: '#94a3b8', fontSize: '0.82rem' }}>No registrado</span>
                                )}
                              </td>

                              <td style={{ padding: '12px 14px' }}>
                                {cMaq > 0 ? (
                                  <div>
                                    <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#15803d' }}>
                                      ${cMaq.toLocaleString('es-CL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </div>
                                    {cHora > 0 && (
                                      <div style={{ fontSize: '0.74rem', color: '#64748b', fontWeight: 600 }}>
                                        M.O: ${cHora.toLocaleString('es-CL')}/h
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>Sin costo reg.</span>
                                )}
                              </td>

                              <td style={{ padding: '12px 14px' }}>
                                {r.cantidad_pruebas_tiempo > 0 ? (
                                  <span style={{ background: '#f3e8ff', color: '#7e22ce', padding: '4px 10px', borderRadius: '12px', fontSize: '0.82rem', fontWeight: 700 }}>
                                    👥 {r.cantidad_pruebas_tiempo} pruebas registradas
                                  </span>
                                ) : (
                                  <span style={{ color: '#94a3b8', fontSize: '0.82rem' }}>Sin pruebas adicionales</span>
                                )}
                              </td>

                              <td style={{ padding: '12px 14px' }}>
                                {r.activa 
                                  ? <span style={{ background: '#dcfce7', color: '#166534', padding: '3px 10px', borderRadius: '12px', fontSize: '0.82rem', fontWeight: 700 }}>Activa</span>
                                  : <span style={{ background: '#fee2e2', color: '#991b1b', padding: '3px 10px', borderRadius: '12px', fontSize: '0.82rem', fontWeight: 700 }}>Inactiva</span>
                                }
                              </td>

                              <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                                <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', flexWrap: 'wrap' }}>
                                  <button 
                                    style={{ padding: '6px 10px', fontSize: '0.82rem', cursor: 'pointer', background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '4px', fontWeight: 600 }} 
                                    onClick={() => handleEdit(r.id)}
                                  >
                                    ✏️ Editar
                                  </button>
                                  {isAdmin && (
                                    <button 
                                      style={{ padding: '6px 10px', fontSize: '0.82rem', cursor: 'pointer', background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe', borderRadius: '4px', fontWeight: 600 }} 
                                      onClick={() => openQuickTimeModal(r)}
                                      title="Registrar una prueba de tiempo con dotación de personas"
                                    >
                                      ⏱️ + Prueba Tiempo
                                    </button>
                                  )}
                                  {isAdmin && (
                                    <button 
                                      style={{ padding: '6px 10px', fontSize: '0.82rem', cursor: 'pointer', background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '4px' }} 
                                      onClick={() => handleToggle(r.id, r.activa)}
                                    >
                                      {r.activa ? 'Desactivar' : 'Activar'}
                                    </button>
                                  )}
                                  {isAdmin && (
                                    <button 
                                      style={{ padding: '6px 10px', fontSize: '0.82rem', cursor: 'pointer', background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca', borderRadius: '4px', fontWeight: 600 }} 
                                      onClick={() => handleDelete(r.id)}
                                    >
                                      🗑️
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                        {filteredFamilias.length === 0 && (
                          <tr><td colSpan="7" style={{ padding: '30px', textAlign: 'center', color: '#94a3b8' }}>No se encontraron familias o recetas registradas.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── VISTA FORMULARIO COMPLETO (CREAR / EDITAR) ── */}
              {view === 'form' && (
                <form onSubmit={handleSaveForm} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  
                  {/* SECCIÓN 1: Identificación y Producto Objetivo */}
                  <div className="card" style={{ padding: '22px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
                    <h2 style={{ margin: '0 0 16px', fontSize: '1.25rem', color: '#0f172a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>📝</span> {currentFamiliaId ? 'Editar Familia y Receta de Maquila' : 'Nueva Familia y Receta de Maquila'}
                    </h2>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                      <div>
                        <label style={{ display: 'block', fontWeight: 700, marginBottom: '6px', color: '#334155' }}>
                          Nombre / Descripción de la Familia o Receta *
                        </label>
                        <input 
                          type="text" 
                          value={formData.nombre_familia} 
                          onChange={e => setFormData({ ...formData, nombre_familia: e.target.value })}
                          style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontSize: '0.95rem' }}
                          placeholder="Ej: Hermanos Producto B / Pack Maquila Especial"
                          required 
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontWeight: 700, marginBottom: '6px', color: '#334155' }}>
                          Producto Objetivo / Salida (Opcional)
                        </label>
                        <input 
                          type="text" 
                          list="catalogo-skus"
                          value={formData.producto_objetivo} 
                          onChange={e => setFormData({ ...formData, producto_objetivo: e.target.value.toUpperCase() })}
                          style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontSize: '0.95rem' }}
                          placeholder="Ej: PROD-B (CÓD. o SKU del producto final a maquilar)"
                        />
                        <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                          Si la maquila busca elaborar un producto específico, indícalo aquí.
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', paddingTop: '24px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: 600, color: '#0f172a' }}>
                          <input 
                            type="checkbox" 
                            checked={formData.activa} 
                            onChange={e => setFormData({ ...formData, activa: e.target.checked })} 
                            style={{ transform: 'scale(1.2)' }}
                          />
                          Familia / Receta Activa para Operaciones
                        </label>
                      </div>
                    </div>
                  </div>

                  {/* ── CUADRO RESUMEN DE MAQUILA Y COSTOS POR INTEGRANTE ── */}
                  {(() => {
                    const hermanos = formData.miembros.filter(m => (m.tipo_componente || 'PRODUCTO') === 'PRODUCTO' && (m.codigo_femaco || '').trim());
                    const materiales = formData.miembros.filter(m => m.tipo_componente === 'MATERIAL' && (m.codigo_femaco || '').trim());
                    
                    const costoInsumosUnit = materiales.reduce((sum, m) => sum + ((Number(m.cantidad_por_unidad) || 0) * (Number(m.costo_unitario) || 0)), 0);
                    
                    const cHora = Number(formData.costo_hora) || 0;
                    const tBaseMin = Number(formData.tiempo_base_1p_min) || 0;
                    const uBase = Number(formData.unidades_base_tiempo) || 100;
                    const velUdsHora = tBaseMin > 0 ? (uBase / tBaseMin) * 60 : 0;
                    const costoManoObraUnit = velUdsHora > 0 && cHora > 0 ? (cHora / velUdsHora) : 0;
                    const costoMaquilaTotal = costoInsumosUnit + costoManoObraUnit;

                    return (
                      <div className="card" style={{ padding: '22px', background: '#ffffff', borderRadius: '10px', border: '1.5px solid #0284c7', boxShadow: '0 4px 12px rgba(2, 132, 199, 0.08)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ fontSize: '1.3rem' }}>📊</span>
                              <h3 style={{ margin: 0, fontSize: '1.2rem', color: '#0f172a', fontWeight: 800 }}>
                                Cuadro Resumen de Maquila y Costos por Integrante
                              </h3>
                            </div>
                            <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '0.86rem' }}>
                              Calculado automáticamente en tiempo real según los productos hermanos, materiales adicionales y el costo por hora ingresado.
                            </p>
                          </div>

                          {/* Mini indicadores del cálculo */}
                          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                            <div style={{ padding: '6px 12px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}>
                              <span style={{ color: '#64748b', fontWeight: 600 }}>Costo Insumos: </span>
                              <b style={{ color: '#0369a1' }}>${costoInsumosUnit.toFixed(2)} / ud</b>
                            </div>
                            <div style={{ padding: '6px 12px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}>
                              <span style={{ color: '#64748b', fontWeight: 600 }}>Mano de Obra: </span>
                              <b style={{ color: '#7e22ce' }}>${costoManoObraUnit.toFixed(2)} / ud</b>
                            </div>
                            <div style={{ padding: '6px 14px', background: '#ecfdf5', borderRadius: '6px', border: '1.5px solid #10b981', fontSize: '0.85rem' }}>
                              <span style={{ color: '#065f46', fontWeight: 700 }}>Total Maquila: </span>
                              <b style={{ color: '#15803d', fontSize: '1rem' }}>${costoMaquilaTotal.toFixed(2)} / ud</b>
                            </div>
                          </div>
                        </div>

                        {hermanos.length === 0 ? (
                          <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8', background: '#f8fafc', borderRadius: '6px', border: '1px dashed #cbd5e1' }}>
                            Agrega productos hermanos abajo en la sección de <b>Composición (BOM)</b> para ver con quiénes se puede maquilar cada integrante y el desglose de costos.
                          </div>
                        ) : (
                          <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.86rem' }}>
                              <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800 }}>SKU Integrante</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800 }}>Descripción Producto</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800, textAlign: 'right' }}>Costo SKU ($)</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800 }}>¿Con quiénes se puede maquilar?</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800, textAlign: 'right' }}>Insumos ($)</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800, textAlign: 'right' }}>M.O. ($)</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800, textAlign: 'right' }}>Costo Maquila</th>
                                  <th style={{ padding: '10px 12px', color: '#0f172a', fontWeight: 800, textAlign: 'right' }}>Costo Terminado Est.</th>
                                </tr>
                              </thead>
                              <tbody>
                                {hermanos.map((h, idx) => {
                                  // Hermanos transformables que pueden originar este producto
                                  const compatibles = hermanos.filter(other => other.codigo_femaco !== h.codigo_femaco && !other.no_transformable);
                                  const costoBaseH = Number(h.costo_unitario) || 0;

                                  return (
                                    <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0', background: idx % 2 === 0 ? '#ffffff' : '#fcfcfd' }}>
                                      <td style={{ padding: '10px 12px', fontWeight: 800, color: '#0369a1', fontFamily: 'monospace', fontSize: '0.92rem' }}>
                                        {h.codigo_femaco}
                                        {formData.producto_objetivo === h.codigo_femaco && (
                                          <span style={{ marginLeft: '6px', fontSize: '0.7rem', padding: '2px 6px', background: '#dcfce7', color: '#15803d', borderRadius: '4px', fontWeight: 700 }}>
                                            🎯 Objetivo
                                          </span>
                                        )}
                                      </td>

                                      <td style={{ padding: '10px 12px', color: '#1e293b', fontWeight: 600 }}>
                                        {h.nombre_componente || '(Sin nombre)'}
                                        {h.no_transformable && (
                                          <div style={{ fontSize: '0.72rem', color: '#b45309', fontWeight: 700 }}>
                                            ⚠️ No transformable (solo receptor)
                                          </div>
                                        )}
                                      </td>

                                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: costoBaseH > 0 ? '#0f172a' : '#94a3b8' }}>
                                        {costoBaseH > 0 ? `$${costoBaseH.toLocaleString('es-CL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00'}
                                      </td>

                                      <td style={{ padding: '10px 12px' }}>
                                        {compatibles.length === 0 ? (
                                          <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem' }}>
                                            {hermanos.length === 1 ? 'Solo 1 producto en familia' : 'Sin otros hermanos transformables'}
                                          </span>
                                        ) : (
                                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                            {compatibles.map((comp, cIdx) => (
                                              <span key={cIdx} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.78rem', color: '#0369a1', background: '#e0f2fe', padding: '2px 7px', borderRadius: '4px', fontWeight: 600, width: 'fit-content' }}>
                                                <span>🔄</span> Con <b>{comp.codigo_femaco}</b> (prop. {comp.cantidad_por_unidad}:1)
                                                {Number(comp.costo_unitario) > 0 && (
                                                  <span style={{ color: '#0284c7', fontSize: '0.74rem' }}>
                                                    [Base: ${Number(comp.costo_unitario).toLocaleString('es-CL')}]
                                                  </span>
                                                )}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                      </td>

                                      <td style={{ padding: '10px 12px', textAlign: 'right', color: '#475569', fontWeight: 600 }}>
                                        ${costoInsumosUnit.toFixed(2)}
                                      </td>

                                      <td style={{ padding: '10px 12px', textAlign: 'right', color: '#7e22ce', fontWeight: 600 }}>
                                        ${costoManoObraUnit.toFixed(2)}
                                      </td>

                                      <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                                        <span style={{ display: 'inline-block', padding: '3px 8px', background: '#ecfdf5', color: '#15803d', borderRadius: '6px', fontWeight: 800, fontSize: '0.92rem' }}>
                                          ${costoMaquilaTotal.toFixed(2)}
                                        </span>
                                      </td>

                                      <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                                        {compatibles.length > 0 ? (
                                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
                                            {compatibles.map((comp, cIdx) => {
                                              const cComp = Number(comp.costo_unitario) || 0;
                                              const qComp = Number(comp.cantidad_por_unidad) || 1;
                                              const finalEst = (cComp * qComp) + costoMaquilaTotal;
                                              return (
                                                <div key={cIdx} style={{ fontSize: '0.8rem', fontWeight: 700, color: '#0f172a' }}>
                                                  {cComp > 0 ? (
                                                    <span>${finalEst.toLocaleString('es-CL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <span style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 500 }}>(de {comp.codigo_femaco})</span></span>
                                                  ) : (
                                                    <span style={{ color: '#64748b' }}>Base {comp.codigo_femaco} + ${costoMaquilaTotal.toFixed(2)}</span>
                                                  )}
                                                </div>
                                              );
                                            })}
                                          </div>
                                        ) : (
                                          <span style={{ color: '#64748b', fontSize: '0.8rem' }}>
                                            Base + ${costoMaquilaTotal.toFixed(2)}
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
                    );
                  })()}

                  {/* SECCIÓN 2: Estructura de Componentes, Materiales y Proporciones (BOM) */}
                  <div className="card" style={{ padding: '22px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                      <div>
                        <h2 style={{ margin: '0 0 4px', fontSize: '1.25rem', color: '#0f172a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span>🧩</span> Composición de la Receta (BOM) y Proporciones
                        </h2>
                        <p style={{ margin: 0, color: '#64748b', fontSize: '0.88rem' }}>
                          Define las proporciones de productos hermanos y asocia materiales requeridos (etiquetas, mangas de celofán, empaques, etc.).
                        </p>
                      </div>

                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <button 
                          type="button" 
                          onClick={() => addMiembro('PRODUCTO')} 
                          style={{ padding: '8px 14px', background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                        >
                          <span>📦</span> + Agregar Producto Hermano
                        </button>
                        <button 
                          type="button" 
                          onClick={() => addMiembro('MATERIAL')} 
                          style={{ padding: '8px 14px', background: '#fef3c7', color: '#b45309', border: '1px solid #fde68a', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                        >
                          <span>🏷️</span> + Seleccionar Material / Insumo
                        </button>
                        <button 
                          type="button" 
                          onClick={() => { window.location.hash = '/materiales-maquila'; }} 
                          style={{ padding: '8px 14px', background: '#f8fafc', color: '#334155', border: '1px solid #cbd5e1', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                          title="Ir al módulo Materiales Maquila para crear códigos o subir inventario Excel"
                        >
                          <span>↗️</span> Ir a Materiales Maquila (Crear / Excel)
                        </button>
                      </div>
                    </div>

                    {/* Banner explicativo de la proporción */}
                    <div style={{ padding: '12px 16px', background: '#f8fafc', borderLeft: '4px solid #0284c7', borderRadius: '6px', marginBottom: '16px', fontSize: '0.88rem', color: '#334155', lineHeight: 1.5 }}>
                      <strong>ℹ️ Cómo funciona la proporción y costos:</strong> Especifica cuántas unidades se requieren de cada componente para obtener <b>1 unidad terminada</b> e indica su costo por unidad.<br/>
                      <em>Ejemplo:</em> Para hacer 1 unidad del Producto B se requieren <b>3 unidades</b> del Producto A, <b>1</b> Etiqueta XXXXX y <b>2</b> Mangas de celofán.
                      <span style={{ display: 'block', marginTop: '6px', color: '#b45309', fontWeight: 600 }}>
                        🏷️ <b>Materiales e Insumos:</b> Se seleccionan del catálogo creado en el módulo <a href="#/materiales-maquila" style={{ color: '#0284c7', textDecoration: 'underline' }}>Materiales Maquila</a>, donde también puedes subir el Excel de inventario con costos (columnas <code>sku</code>, <code>descripcion</code>, <code>categoria</code>, <code>unidades</code> y <code>costo</code>).
                      </span>
                    </div>
                    <div style={{ overflowX: 'auto', marginBottom: '16px' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                        <thead>
                          <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                            <th style={{ padding: '10px 12px', width: '130px' }}>Tipo de Ítem</th>
                            <th style={{ padding: '10px 12px', width: '220px' }}>Código Interno / Material *</th>
                            <th style={{ padding: '10px 12px' }}>Descripción / Insumo y Stock</th>
                            <th style={{ padding: '10px 12px', width: '110px', textAlign: 'center' }}>Proporción *</th>
                            <th style={{ padding: '10px 12px', width: '80px', textAlign: 'center' }}>Unidad</th>
                            <th style={{ padding: '10px 12px', width: '120px', textAlign: 'center' }}>Costo Unit. ($)</th>
                            <th style={{ padding: '10px 12px', width: '110px', textAlign: 'right' }}>Subtotal ($)</th>
                            <th style={{ padding: '10px 12px', width: '120px', textAlign: 'center' }}>No Transformable</th>
                            <th style={{ padding: '10px 12px', width: '160px' }}>Observaciones</th>
                            <th style={{ padding: '10px 12px', width: '50px', textAlign: 'center' }}>Acción</th>
                          </tr>
                        </thead>
                        <tbody>
                          {formData.miembros.map((m, i) => {
                            const isMaterial = m.tipo_componente === 'MATERIAL';
                            return (
                              <tr key={i} style={{ borderBottom: '1px solid #e2e8f0', background: isMaterial ? '#fffbeb' : '#ffffff' }}>
                                {/* Tipo de componente */}
                                <td style={{ padding: '8px 10px' }}>
                                  <select
                                    value={m.tipo_componente || 'PRODUCTO'}
                                    onChange={e => updateMiembro(i, 'tipo_componente', e.target.value)}
                                    style={{
                                      width: '100%', padding: '6px 8px', borderRadius: '4px',
                                      border: isMaterial ? '1.5px solid #f59e0b' : '1.5px solid #0284c7',
                                      background: isMaterial ? '#fef3c7' : '#e0f2fe',
                                      color: isMaterial ? '#92400e' : '#0369a1',
                                      fontWeight: 700, fontSize: '0.82rem'
                                    }}
                                  >
                                    <option value="PRODUCTO">📦 Producto</option>
                                    <option value="MATERIAL">🏷️ Insumo/Mat.</option>
                                  </select>
                                </td>

                                {/* Código interno / Material */}
                                <td style={{ padding: '8px 10px' }}>
                                  {isMaterial ? (
                                    materialesMaquila.length === 0 ? (
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                        <span style={{ fontSize: '0.78rem', color: '#b45309', fontWeight: 600 }}>
                                          ⚠️ Sin materiales registrados
                                        </span>
                                        <button
                                          type="button"
                                          onClick={() => { window.location.hash = '/materiales-maquila'; }}
                                          style={{ fontSize: '0.75rem', padding: '3px 6px', background: '#fef3c7', border: '1px solid #fde68a', color: '#92400e', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}
                                        >
                                          Crear en Materiales Maquila
                                        </button>
                                      </div>
                                    ) : (
                                      <select
                                        value={m.codigo_femaco || ''}
                                        onChange={e => {
                                          const sku = e.target.value;
                                          const mat = materialesMaquila.find(x => x.sku === sku);
                                          const newMembers = [...formData.miembros];
                                          newMembers[i].codigo_femaco = sku;
                                          if (mat) {
                                            newMembers[i].nombre_componente = mat.nombre || '';
                                            newMembers[i].unidad_medida = mat.unidad_medida || 'UN';
                                            newMembers[i].costo_unitario = Number(mat.costo_unitario) || 0;
                                          }
                                          setFormData({ ...formData, miembros: newMembers });
                                        }}
                                        style={{
                                          width: '100%',
                                          padding: '6px 8px',
                                          borderRadius: '4px',
                                          border: '1.5px solid #f59e0b',
                                          fontWeight: 700,
                                          color: '#92400e',
                                          background: '#ffffff'
                                        }}
                                        required
                                      >
                                        <option value="">-- Seleccionar Material Creado --</option>
                                        {materialesMaquila.map(mat => (
                                          <option key={mat.id || mat.sku} value={mat.sku}>
                                            {mat.sku} - {mat.nombre} ({mat.stock_actual || 0} {mat.unidad_medida || 'UN'}) - ${Number(mat.costo_unitario || 0).toFixed(2)}
                                          </option>
                                        ))}
                                      </select>
                                    )
                                  ) : (
                                    <input 
                                      type="text" 
                                      list="catalogo-skus"
                                      value={m.codigo_femaco || ''}
                                      onChange={e => updateMiembro(i, 'codigo_femaco', e.target.value.toUpperCase())}
                                      style={{ width: '100%', padding: '6px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontWeight: 700, color: '#0f172a' }}
                                      placeholder="Ej: CÓD. interno"
                                      required
                                    />
                                  )}
                                </td>

                                {/* Nombre / Descripción */}
                                <td style={{ padding: '8px 10px' }}>
                                  {isMaterial ? (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', padding: '4px 6px' }}>
                                      <span style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.85rem' }}>
                                        {m.nombre_componente || '(Seleccione un material)'}
                                      </span>
                                      {(() => {
                                        const mat = materialesMaquila.find(x => x.sku === m.codigo_femaco);
                                        const stock = mat ? Number(mat.stock_actual || 0) : null;
                                        return stock !== null ? (
                                          <span style={{
                                            fontSize: '0.72rem',
                                            padding: '2px 7px',
                                            borderRadius: '10px',
                                            background: stock > 0 ? '#dcfce7' : '#fee2e2',
                                            color: stock > 0 ? '#15803d' : '#b91c1c',
                                            fontWeight: 700,
                                            whiteSpace: 'nowrap'
                                          }}>
                                            Stock: {stock.toLocaleString()} {m.unidad_medida || 'UN'}
                                          </span>
                                        ) : null;
                                      })()}
                                    </div>
                                  ) : (
                                    <input 
                                      type="text" 
                                      value={m.nombre_componente || ''}
                                      onChange={e => updateMiembro(i, 'nombre_componente', e.target.value)}
                                      style={{ width: '100%', padding: '6px 8px', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                                      placeholder="Nombre del producto..."
                                    />
                                  )}
                                </td>

                                {/* Proporción / Cantidad requerida */}
                                <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
                                    <input 
                                      type="number" 
                                      step="0.01"
                                      min="0.01"
                                      value={m.cantidad_por_unidad ?? 1.0}
                                      onChange={e => updateMiembro(i, 'cantidad_por_unidad', e.target.value)}
                                      style={{ width: '70px', padding: '6px 6px', textAlign: 'center', borderRadius: '4px', border: '1.5px solid #0284c7', fontWeight: 800, color: '#0284c7' }}
                                      title="Cantidad requerida para 1 unidad terminada"
                                      required
                                    />
                                  </div>
                                </td>

                                {/* Unidad de Medida */}
                                <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                  <input 
                                    type="text" 
                                    value={m.unidad_medida || 'UN'}
                                    onChange={e => updateMiembro(i, 'unidad_medida', e.target.value.toUpperCase())}
                                    style={{ width: '100%', padding: '6px 4px', textAlign: 'center', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.82rem', fontWeight: 600 }}
                                    placeholder="UN"
                                  />
                                </td>

                                {/* Costo Unitario por SKU / Material */}
                                <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px' }}>
                                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}>$</span>
                                    <input 
                                      type="number" 
                                      step="0.01"
                                      min="0"
                                      value={m.costo_unitario ?? 0}
                                      onChange={e => updateMiembro(i, 'costo_unitario', e.target.value)}
                                      style={{ width: '75px', padding: '6px 6px', textAlign: 'right', borderRadius: '4px', border: '1.5px solid #16a34a', fontWeight: 700, color: '#16a34a' }}
                                      title="Costo unitario por SKU o insumo"
                                      placeholder="0.00"
                                    />
                                  </div>
                                </td>

                                {/* Subtotal Costo */}
                                <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 800, color: '#0f172a' }}>
                                  ${((Number(m.cantidad_por_unidad) || 0) * (Number(m.costo_unitario) || 0)).toLocaleString('es-CL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>

                                {/* No transformable */}
                                <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                  {!isMaterial ? (
                                    <input 
                                      type="checkbox" 
                                      checked={Boolean(m.no_transformable)} 
                                      onChange={e => updateMiembro(i, 'no_transformable', e.target.checked)}
                                      style={{ transform: 'scale(1.2)', cursor: 'pointer' }}
                                      title="Este producto puede recibir de otros pero no puede ceder su inventario"
                                    />
                                  ) : (
                                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Insumo</span>
                                  )}
                                </td>

                                {/* Observaciones */}
                                <td style={{ padding: '8px 10px' }}>
                                  <input 
                                    type="text" 
                                    value={m.observacion || ''} 
                                    onChange={e => updateMiembro(i, 'observacion', e.target.value)}
                                    style={{ width: '100%', padding: '6px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}
                                    placeholder="Notas específicas..."
                                  />
                                </td>

                                {/* Quitar */}
                                <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                  <button 
                                    type="button" 
                                    onClick={() => removeMiembro(i)} 
                                    style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '1.1rem' }}
                                    title="Quitar componente"
                                  >
                                    🗑️
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                          {formData.miembros.length === 0 && (
                            <tr>
                              <td colSpan="10" style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>
                                Agrega integrantes con los botones superiores (+ Producto Hermano o + Material / Insumo).
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Resumen en vivo de la Receta */}
                    {formData.miembros.length > 0 && (
                      <div style={{ padding: '12px 16px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '6px', fontSize: '0.88rem' }}>
                        <div style={{ fontWeight: 700, color: '#166534', marginBottom: '6px' }}>
                          📋 Resumen de Receta para 1 Unidad {formData.producto_objetivo ? `del producto objetivo (${formData.producto_objetivo})` : 'terminada'}:
                        </div>
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                          {formData.miembros.map((m, idx) => (
                            <span key={idx} style={{ background: '#ffffff', padding: '4px 10px', borderRadius: '4px', border: '1px solid #86efac', color: '#15803d', fontWeight: 600 }}>
                              {m.cantidad_por_unidad} {m.unidad_medida || 'UN'} × <b>{m.codigo_femaco || 'CÓD'}</b> {m.nombre_componente && `(${m.nombre_componente})`} {Number(m.costo_unitario) > 0 && <span style={{ color: '#16a34a', fontWeight: 700 }}>[${Number(m.costo_unitario).toFixed(2)}]</span>}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* SECCIÓN 3: Tiempos de Maquila y Rendimiento por Personas */}
                  <div className="card" style={{ padding: '22px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                      <div>
                        <h2 style={{ margin: '0 0 4px', fontSize: '1.25rem', color: '#0f172a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span>⏱️</span> Tiempos de Maquila, Productividad y Costo por Hora
                        </h2>
                        <p style={{ margin: 0, color: '#64748b', fontSize: '0.88rem' }}>
                          Ingresa cuánto demora 1 persona para 100 unidades y el costo por hora de mano de obra. Con esto se calcula automáticamente el costo por unidad en el cuadro resumen.
                        </p>
                      </div>

                      <button 
                        type="button" 
                        onClick={addTiempoRow} 
                        style={{ padding: '8px 14px', background: '#f3e8ff', color: '#7e22ce', border: '1px solid #d8b4fe', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                      >
                        <span>👥</span> + Agregar Prueba con N Personas
                      </button>
                    </div>

                    {/* Subsección: Tiempo Base 1 Persona y Costo por Hora */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px', padding: '16px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', marginBottom: '20px' }}>
                      <div>
                        <label style={{ display: 'block', fontWeight: 700, marginBottom: '6px', color: '#0f172a' }}>
                          Tiempo que demora 1 PERSONA para 100 unidades:
                        </label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <input 
                            type="number" 
                            step="0.1"
                            min="0"
                            value={formData.tiempo_base_1p_min} 
                            onChange={e => setFormData({ ...formData, tiempo_base_1p_min: e.target.value })}
                            style={{ width: '120px', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #0284c7', fontSize: '1.1rem', fontWeight: 800, color: '#0284c7' }}
                            placeholder="Ej: 45"
                          />
                          <span style={{ fontWeight: 600, color: '#475569' }}>minutos / 100 uds</span>
                        </div>
                        <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                          Estándar base de referencia individual.
                        </span>
                      </div>

                      <div>
                        <label style={{ display: 'block', fontWeight: 700, marginBottom: '6px', color: '#0f172a' }}>
                          Costo Mano de Obra por Hora ($ / hora):
                        </label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: 800, color: '#16a34a', fontSize: '1.1rem' }}>$</span>
                          <input 
                            type="number" 
                            step="100"
                            min="0"
                            value={formData.costo_hora} 
                            onChange={e => setFormData({ ...formData, costo_hora: e.target.value })}
                            style={{ width: '130px', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #16a34a', fontSize: '1.1rem', fontWeight: 800, color: '#16a34a' }}
                            placeholder="Ej: 15000"
                          />
                          <span style={{ fontWeight: 600, color: '#475569' }}>pesos / hora</span>
                        </div>
                        <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                          Se divide entre la velocidad (uds/h) para calcular el costo por unidad.
                        </span>
                      </div>

                      {/* Tarjeta de cálculo automático base */}
                      {formData.tiempo_base_1p_min && Number(formData.tiempo_base_1p_min) > 0 ? (
                        <div style={{ padding: '12px 16px', background: '#ffffff', borderRadius: '6px', border: '1px solid #cbd5e1', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                            Rendimiento y Costo Calculado (1 Persona)
                          </div>
                          <div style={{ display: 'flex', gap: '14px', marginTop: '4px', flexWrap: 'wrap', alignItems: 'center' }}>
                            <div>
                              <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#16a34a' }}>
                                {Math.round((Number(formData.unidades_base_tiempo || 100) / Number(formData.tiempo_base_1p_min)) * 60)}
                              </span>
                              <span style={{ fontSize: '0.8rem', color: '#475569', fontWeight: 600 }}> uds / hora</span>
                            </div>
                            {Number(formData.costo_hora) > 0 && (
                              <div style={{ borderLeft: '2px solid #e2e8f0', paddingLeft: '12px' }}>
                                <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#7e22ce' }}>
                                  ${(Number(formData.costo_hora) / ((Number(formData.unidades_base_tiempo || 100) / Number(formData.tiempo_base_1p_min)) * 60)).toFixed(2)}
                                </span>
                                <span style={{ fontSize: '0.8rem', color: '#475569', fontWeight: 600 }}> M.O. / ud</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ) : null}
                    </div>

                    {/* Subsección: Pruebas con Múltiples Personas */}
                    <div>
                      <h3 style={{ margin: '0 0 10px', fontSize: '1rem', color: '#334155', fontWeight: 700 }}>
                        Mediciones Reales y Pruebas con Dotaciones de Personas (ej. 3, 4, 6 personas)
                      </h3>

                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                          <thead>
                            <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                              <th style={{ padding: '10px 12px', width: '140px' }}>Dotación (Personas)</th>
                              <th style={{ padding: '10px 12px', width: '130px' }}>Uds Base / Lote</th>
                              <th style={{ padding: '10px 12px', width: '160px' }}>Tiempo Demorado (minutos)</th>
                              <th style={{ padding: '10px 12px' }}>Rendimiento Calculado de Línea</th>
                              <th style={{ padding: '10px 12px' }}>Notas de la Prueba / Observaciones</th>
                              <th style={{ padding: '10px 12px', width: '60px', textAlign: 'center' }}>Acción</th>
                            </tr>
                          </thead>
                          <tbody>
                            {formData.tiempos.map((t, idx) => {
                              const p = Number(t.cantidad_personas) || 1;
                              const ub = Number(t.unidades_base) || 100;
                              const min = Number(t.tiempo_minutos);
                              const rateTotal = min > 0 ? Math.round((ub / min) * 60) : 0;
                              const ratePerPerson = min > 0 && p > 0 ? Math.round(((ub / min) * 60) / p) : 0;
                              const minPerUnit = min > 0 && ub > 0 ? (min / ub).toFixed(2) : '-';

                              return (
                                <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0' }}>
                                  <td style={{ padding: '8px 10px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      <span style={{ fontSize: '1rem' }}>👥</span>
                                      <input 
                                        type="number" 
                                        min="1"
                                        value={t.cantidad_personas} 
                                        onChange={e => updateTiempoRow(idx, 'cantidad_personas', e.target.value)}
                                        style={{ width: '70px', padding: '6px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontWeight: 700, textAlign: 'center' }}
                                        required
                                      />
                                      <span style={{ fontSize: '0.8rem', color: '#64748b' }}>pers.</span>
                                    </div>
                                  </td>

                                  <td style={{ padding: '8px 10px' }}>
                                    <input 
                                      type="number" 
                                      min="1"
                                      value={t.unidades_base || 100} 
                                      onChange={e => updateTiempoRow(idx, 'unidades_base', e.target.value)}
                                      style={{ width: '80px', padding: '6px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', textAlign: 'center' }}
                                    />
                                    <span style={{ fontSize: '0.8rem', color: '#64748b', marginLeft: '4px' }}>uds</span>
                                  </td>

                                  <td style={{ padding: '8px 10px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      <input 
                                        type="number" 
                                        step="0.1"
                                        min="0.1"
                                        value={t.tiempo_minutos} 
                                        onChange={e => updateTiempoRow(idx, 'tiempo_minutos', e.target.value)}
                                        style={{ width: '80px', padding: '6px 8px', borderRadius: '4px', border: '1.5px solid #7e22ce', fontWeight: 800, color: '#7e22ce', textAlign: 'center' }}
                                        placeholder="Minutos"
                                        required
                                      />
                                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>minutos</span>
                                    </div>
                                  </td>

                                  <td style={{ padding: '8px 10px' }}>
                                    {min > 0 ? (
                                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                                        <span style={{ background: '#ecfdf5', color: '#15803d', padding: '3px 8px', borderRadius: '4px', fontWeight: 700, fontSize: '0.8rem' }}>
                                          ⚡ {rateTotal} uds/hora total
                                        </span>
                                        <span style={{ background: '#f8fafc', color: '#475569', padding: '3px 8px', borderRadius: '4px', fontSize: '0.8rem', border: '1px solid #cbd5e1' }}>
                                          👤 {ratePerPerson} uds/h/operario
                                        </span>
                                        <span style={{ color: '#64748b', fontSize: '0.78rem' }}>
                                          ({minPerUnit} min/ud)
                                        </span>
                                      </div>
                                    ) : (
                                      <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>Ingresa los minutos</span>
                                    )}
                                  </td>

                                  <td style={{ padding: '8px 10px' }}>
                                    <input 
                                      type="text" 
                                      value={t.observaciones || ''} 
                                      onChange={e => updateTiempoRow(idx, 'observaciones', e.target.value)}
                                      style={{ width: '100%', padding: '6px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.82rem' }}
                                      placeholder="Ej: Prueba con 6 personas en mesa 2, turno tarde..."
                                    />
                                  </td>

                                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                    <button 
                                      type="button" 
                                      onClick={() => removeTiempoRow(idx)} 
                                      style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '1.1rem' }}
                                      title="Quitar medición"
                                    >
                                      🗑️
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                            {formData.tiempos.length === 0 && (
                              <tr>
                                <td colSpan="6" style={{ padding: '20px', textAlign: 'center', color: '#94a3b8' }}>
                                  No hay pruebas registradas aún. Haz clic en <b>"+ Agregar Prueba con N Personas"</b> para registrar cuánto demora una dotación (ej. 3, 4 o 6 personas).
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>

                  {/* Botones de acción finales */}
                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '10px' }}>
                    <button 
                      type="button" 
                      className="btn-secondary" 
                      onClick={() => setView('list')}
                      style={{ padding: '10px 20px', fontSize: '1rem' }}
                    >
                      Cancelar
                    </button>
                    <button 
                      type="submit" 
                      className="btn-primary" 
                      disabled={loading} 
                      style={{ padding: '10px 28px', fontSize: '1rem', fontWeight: 700 }}
                    >
                      {loading ? 'Guardando...' : currentFamiliaId ? '💾 Actualizar Familia y Receta' : '💾 Guardar Nueva Familia y Receta'}
                    </button>
                  </div>

                </form>
              )}

              {/* MODAL RÁPIDO PARA REGISTRAR PRUEBA DE TIEMPO DIRECTAMENTE */}
              {quickTimeModal.open && (
                <div style={{
                  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                  background: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(2px)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
                }}>
                  <div className="card" style={{ width: '90%', maxWidth: '480px', padding: '24px', background: '#ffffff', borderRadius: '8px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
                    <h3 style={{ margin: '0 0 8px', fontSize: '1.2rem', color: '#0f172a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>⏱️</span> Registrar Prueba de Tiempo de Maquila
                    </h3>
                    <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: '0.85rem' }}>
                      Familia: <b>{quickTimeModal.nombreFamilia}</b>
                    </p>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '20px' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                          Dotación de Personas probadas:
                        </label>
                        <input 
                          type="number" 
                          min="1"
                          value={quickTimeModal.cantidadPersonas} 
                          onChange={e => setQuickTimeModal({ ...quickTimeModal, cantidadPersonas: e.target.value })}
                          style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1' }}
                          placeholder="Ej: 3, 4, 6..."
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                          Unidades de la prueba (Lote):
                        </label>
                        <input 
                          type="number" 
                          min="1"
                          value={quickTimeModal.unidadesBase} 
                          onChange={e => setQuickTimeModal({ ...quickTimeModal, unidadesBase: e.target.value })}
                          style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1' }}
                          placeholder="Default: 100"
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                          Tiempo demorado en minutos: *
                        </label>
                        <input 
                          type="number" 
                          step="0.1"
                          min="0.1"
                          value={quickTimeModal.tiempoMinutos} 
                          onChange={e => setQuickTimeModal({ ...quickTimeModal, tiempoMinutos: e.target.value })}
                          style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #7e22ce', fontWeight: 700, color: '#7e22ce' }}
                          placeholder="Ej: 14.5"
                          autoFocus
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                          Notas / Turno / Observaciones:
                        </label>
                        <input 
                          type="text" 
                          value={quickTimeModal.observaciones} 
                          onChange={e => setQuickTimeModal({ ...quickTimeModal, observaciones: e.target.value })}
                          style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1' }}
                          placeholder="Ej: Prueba con 6 personas en mesa 1"
                        />
                      </div>

                      {quickTimeModal.tiempoMinutos && Number(quickTimeModal.tiempoMinutos) > 0 && (
                        <div style={{ padding: '10px 14px', background: '#ecfdf5', borderRadius: '6px', border: '1px solid #a7f3d0', fontSize: '0.85rem', color: '#065f46' }}>
                          ⚡ <b>Rendimiento calculado:</b> {Math.round((Number(quickTimeModal.unidadesBase || 100) / Number(quickTimeModal.tiempoMinutos)) * 60)} uds/hora total (
                          {Math.round(((Number(quickTimeModal.unidadesBase || 100) / Number(quickTimeModal.tiempoMinutos)) * 60) / Number(quickTimeModal.cantidadPersonas || 1))} uds/h por persona)
                        </div>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                      <button 
                        type="button" 
                        className="btn-secondary" 
                        onClick={() => setQuickTimeModal({ open: false, recetaId: null })}
                        disabled={quickTimeModal.loading}
                      >
                        Cancelar
                      </button>
                      <button 
                        type="button" 
                        className="btn-primary" 
                        onClick={handleSaveQuickTime}
                        disabled={quickTimeModal.loading}
                        style={{ padding: '8px 18px', fontWeight: 700 }}
                      >
                        {quickTimeModal.loading ? 'Guardando...' : 'Guardar Medición'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Datalist para autocompletar SKUs del catálogo */}
              <datalist id="catalogo-skus">
                {catalogo.slice(0, 1000).map((c, i) => (
                  <option key={i} value={c.codigo_femaco}>
                    {c.codigo_femaco} {c.sku ? `(${c.sku})` : ''} - {c.nombre_producto}
                  </option>
                ))}
              </datalist>

            </>
          )}

        </div>
      </div>
    </div>
  );
}
