import React, { useState, useEffect, useRef } from 'react';
import * as api from '../api';

export default function MaterialesMaquila() {
  const [materiales, setMateriales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filtros
  const [search, setSearch] = useState('');
  const [categoriaFilter, setCategoriaFilter] = useState('ALL');
  const [soloActivos, setSoloActivos] = useState(false);

  // Modal Crear / Editar Material
  const [modalOpen, setModalOpen] = useState(false);
  const [editingMaterial, setEditingMaterial] = useState(null); // null = nuevo, objeto = editar
  const [formMaterial, setFormMaterial] = useState({
    sku: '',
    nombre: '',
    descripcion: '',
    categoria: 'ETIQUETA',
    unidad_medida: 'UN',
    stock_actual: 0,
    observaciones: '',
    activo: true
  });
  const [saving, setSaving] = useState(false);

  // Modal Cargar Excel
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const fileInputRef = useRef(null);

  // Role
  const role = localStorage.getItem('rrff_role') || 'viewer';
  const isAdmin = role === 'admin';

  useEffect(() => {
    loadData();
  }, [categoriaFilter, soloActivos]);

  async function loadData() {
    setLoading(true);
    try {
      const res = await api.fetchMaterialesMaquila({
        search,
        categoria: categoriaFilter,
        solo_activos: soloActivos
      });
      setMateriales(res.data || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleSearchSubmit(e) {
    e.preventDefault();
    loadData();
  }

  function handleOpenCreate() {
    setEditingMaterial(null);
    setFormMaterial({
      sku: '',
      nombre: '',
      descripcion: '',
      categoria: 'ETIQUETA',
      unidad_medida: 'UN',
      stock_actual: 0,
      observaciones: '',
      activo: true
    });
    setModalOpen(true);
  }

  function handleOpenEdit(mat) {
    setEditingMaterial(mat);
    setFormMaterial({
      sku: mat.sku,
      nombre: mat.nombre,
      descripcion: mat.descripcion || '',
      categoria: mat.categoria || 'INSUMO',
      unidad_medida: mat.unidad_medida || 'UN',
      stock_actual: mat.stock_actual ?? 0,
      observaciones: mat.observaciones || '',
      activo: mat.activo !== false
    });
    setModalOpen(true);
  }

  async function handleSaveMaterial(e) {
    e.preventDefault();
    if (!formMaterial.sku.trim()) return alert("El SKU o código es obligatorio");
    if (!formMaterial.nombre.trim()) return alert("El nombre o descripción es obligatorio");

    setSaving(true);
    try {
      if (editingMaterial) {
        await api.updateMaterialMaquila(editingMaterial.id, formMaterial);
      } else {
        await api.createMaterialMaquila(formMaterial);
      }
      setModalOpen(false);
      loadData();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteMaterial(mat) {
    if (!window.confirm(`¿Seguro que deseas eliminar el material '${mat.sku}' (${mat.nombre})?`)) return;
    try {
      setLoading(true);
      await api.deleteMaterialMaquila(mat.id);
      loadData();
    } catch (err) {
      alert(err.message);
      setLoading(false);
    }
  }

  async function handleDownloadPlantilla() {
    try {
      const { blob, filename } = await api.downloadPlantillaMaterialesExcel();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Error al descargar plantilla: " + err.message);
    }
  }

  async function handleExportExcel() {
    try {
      const { blob, filename } = await api.downloadExportMaterialesExcel();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Error al exportar inventario: " + err.message);
    }
  }

  async function handleUploadExcelSubmit(e) {
    e.preventDefault();
    if (!selectedFile) return alert("Selecciona un archivo Excel primero");

    setUploading(true);
    setUploadResult(null);
    try {
      const res = await api.uploadInventarioMateriales(selectedFile);
      setUploadResult(res);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadData();
    } catch (err) {
      alert("Error al cargar archivo: " + err.message);
    } finally {
      setUploading(false);
    }
  }

  // Filtrado local por buscador instantáneo
  const filteredMateriales = materiales.filter(m => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (m.sku || '').toLowerCase().includes(q) ||
      (m.nombre || '').toLowerCase().includes(q) ||
      (m.categoria || '').toLowerCase().includes(q) ||
      (m.observaciones || '').toLowerCase().includes(q)
    );
  });

  // KPIs
  const totalItems = materiales.length;
  const totalStockUds = materiales.reduce((acc, m) => acc + (Number(m.stock_actual) || 0), 0);
  const quiebresCount = materiales.filter(m => (Number(m.stock_actual) || 0) <= 0).length;

  return (
    <div className="content-area">
      <div className="main-panel">
        <div className="page" style={{ padding: '24px', maxWidth: '1280px', margin: '0 auto', width: '100%' }}>
          
          {/* ── ENCABEZADO DE PÁGINA ── */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px', marginBottom: '24px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '1.8rem' }}>📦</span>
                <h1 style={{ margin: 0, fontSize: '1.6rem', color: '#0f172a', fontWeight: 800 }}>
                  Materiales e Insumos de Maquila
                </h1>
              </div>
              <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '0.92rem' }}>
                Catálogo exclusivo e inventario de materiales adicionales (etiquetas, mangas de celofán, adhesivos, empaques).
                Los materiales creados aquí quedan automáticamente disponibles para ser seleccionados en las recetas de maquila.
              </p>
            </div>

            {/* Botones de acción principales */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                className="btn-secondary"
                onClick={handleDownloadPlantilla}
                style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 14px', fontSize: '0.88rem', fontWeight: 600, background: '#ffffff', border: '1.5px solid #cbd5e1' }}
                title="Descargar plantilla Excel con columnas 'sku' y 'unidades'"
              >
                <span>📄</span> Plantilla Excel
              </button>

              <button
                className="btn-secondary"
                onClick={handleExportExcel}
                style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 14px', fontSize: '0.88rem', fontWeight: 600, background: '#ffffff', border: '1.5px solid #cbd5e1' }}
              >
                <span>📥</span> Exportar Excel
              </button>

              {isAdmin && (
                <button
                  className="btn-primary"
                  onClick={() => { setUploadModalOpen(true); setUploadResult(null); }}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 16px', fontSize: '0.88rem', fontWeight: 700, background: '#0284c7', borderColor: '#0284c7' }}
                >
                  <span>📤</span> Cargar Inventario (Excel)
                </button>
              )}

              {isAdmin && (
                <button
                  className="btn-primary"
                  onClick={handleOpenCreate}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', fontSize: '0.88rem', fontWeight: 700 }}
                >
                  <span>➕</span> Nuevo Material
                </button>
              )}
            </div>
          </div>

          {/* ── TARJETAS KPIS RESUMEN ── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            <div className="card" style={{ padding: '16px 20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', borderLeft: '4px solid #0284c7', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' }}>
              <div style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Total Materiales Registrados</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#0f172a', marginTop: '4px' }}>
                {totalItems}
              </div>
              <div style={{ fontSize: '0.8rem', color: '#0284c7', fontWeight: 500, marginTop: '2px' }}>
                Insumos activos en catálogo
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', borderLeft: '4px solid #16a34a', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' }}>
              <div style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Stock Total de Insumos</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#16a34a', marginTop: '4px' }}>
                {Math.round(totalStockUds).toLocaleString()}
              </div>
              <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500, marginTop: '2px' }}>
                Unidades físicas en inventario
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', borderLeft: `4px solid ${quiebresCount > 0 ? '#dc2626' : '#16a34a'}`, boxShadow: '0 2px 4px rgba(0,0,0,0.04)' }}>
              <div style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Materiales con Stock 0 (Quiebre)</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: quiebresCount > 0 ? '#dc2626' : '#16a34a', marginTop: '4px' }}>
                {quiebresCount}
              </div>
              <div style={{ fontSize: '0.8rem', color: quiebresCount > 0 ? '#b91c1c' : '#16a34a', fontWeight: 600, marginTop: '2px' }}>
                {quiebresCount > 0 ? '⚠️ Requieren reposición' : '✓ Todos con stock disponible'}
              </div>
            </div>
          </div>

          {error && (
            <div style={{ padding: '14px', background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: '6px', color: '#b91c1c', marginBottom: '20px' }}>
              {error}
            </div>
          )}

          {/* ── CARD PRINCIPAL: FILTROS Y TABLA ── */}
          <div className="card" style={{ padding: '20px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' }}>
            
            {/* Barra de Filtros */}
            <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '20px' }}>
              <div style={{ flex: 1, minWidth: '260px' }}>
                <input
                  type="text"
                  placeholder="🔍 Buscar por SKU, nombre, o notas..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ width: '100%', padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontSize: '0.9rem' }}
                />
              </div>

              <div>
                <select
                  value={categoriaFilter}
                  onChange={e => setCategoriaFilter(e.target.value)}
                  style={{ padding: '10px 14px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 600, fontSize: '0.88rem', background: '#ffffff' }}
                >
                  <option value="ALL">Todas las Categorías</option>
                  <option value="ETIQUETA">🏷️ Etiquetas</option>
                  <option value="MANGA">📜 Mangas de Celofán</option>
                  <option value="EMPAQUE">📦 Empaques / Cajas</option>
                  <option value="INSUMO">🧩 Insumos Generales</option>
                  <option value="OTRO">Otros</option>
                </select>
              </div>

              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem', fontWeight: 600, color: '#334155' }}>
                <input
                  type="checkbox"
                  checked={soloActivos}
                  onChange={e => setSoloActivos(e.target.checked)}
                  style={{ transform: 'scale(1.2)' }}
                />
                Solo Activos
              </label>

              <button type="submit" className="btn-secondary" style={{ padding: '10px 18px', fontWeight: 600 }}>
                Buscar
              </button>
            </form>

            {/* Tabla de Materiales */}
            {loading && materiales.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Cargando catálogo de materiales...</div>
            ) : filteredMateriales.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                No se encontraron materiales registrados. Haz clic en <b>"+ Nuevo Material"</b> o <b>"Cargar Inventario (Excel)"</b> para comenzar.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>SKU / Código</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Nombre del Material / Insumo</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Categoría</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700, textAlign: 'center' }}>Unidad</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700, textAlign: 'right' }}>Stock Actual (Unidades)</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Observaciones</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700 }}>Estado</th>
                      <th style={{ padding: '12px 14px', color: '#475569', fontWeight: 700, textAlign: 'center' }}>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMateriales.map((m, idx) => {
                      const stockNum = Number(m.stock_actual) || 0;
                      const isQuiebre = stockNum <= 0;

                      return (
                        <tr key={m.id || idx} style={{ borderBottom: '1px solid #f1f5f9', background: idx % 2 === 0 ? '#ffffff' : '#fcfcfd' }}>
                          <td style={{ padding: '12px 14px', fontWeight: 800, color: '#0369a1', fontFamily: 'monospace', fontSize: '0.95rem' }}>
                            {m.sku}
                          </td>

                          <td style={{ padding: '12px 14px', color: '#0f172a', fontWeight: 600 }}>
                            {m.nombre}
                            {m.descripcion && (
                              <div style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 400 }}>
                                {m.descripcion}
                              </div>
                            )}
                          </td>

                          <td style={{ padding: '12px 14px' }}>
                            <span style={{
                              padding: '3px 8px', borderRadius: '4px', fontSize: '0.78rem', fontWeight: 700,
                              background: m.categoria === 'ETIQUETA' ? '#e0f2fe' : m.categoria === 'MANGA' ? '#f3e8ff' : m.categoria === 'EMPAQUE' ? '#fef3c7' : '#f1f5f9',
                              color: m.categoria === 'ETIQUETA' ? '#0369a1' : m.categoria === 'MANGA' ? '#7e22ce' : m.categoria === 'EMPAQUE' ? '#b45309' : '#475569'
                            }}>
                              {m.categoria || 'INSUMO'}
                            </span>
                          </td>

                          <td style={{ padding: '12px 14px', textAlign: 'center', fontWeight: 600, color: '#64748b' }}>
                            {m.unidad_medida || 'UN'}
                          </td>

                          <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                              <span style={{ fontSize: '1.05rem', fontWeight: 800, color: isQuiebre ? '#dc2626' : '#15803d' }}>
                                {stockNum.toLocaleString()}
                              </span>
                              {isQuiebre ? (
                                <span style={{ fontSize: '0.7rem', color: '#b91c1c', fontWeight: 700, textTransform: 'uppercase' }}>
                                  Sin Stock
                                </span>
                              ) : (
                                <span style={{ fontSize: '0.7rem', color: '#16a34a', fontWeight: 600 }}>
                                  Disponible
                                </span>
                              )}
                            </div>
                          </td>

                          <td style={{ padding: '12px 14px', color: '#475569', fontSize: '0.82rem' }}>
                            {m.observaciones || '-'}
                          </td>

                          <td style={{ padding: '12px 14px' }}>
                            {m.activo ? (
                              <span style={{ background: '#dcfce7', color: '#166534', padding: '3px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>
                                Activo
                              </span>
                            ) : (
                              <span style={{ background: '#fee2e2', color: '#991b1b', padding: '3px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>
                                Inactivo
                              </span>
                            )}
                          </td>

                          <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
                              {isAdmin && (
                                <button
                                  onClick={() => handleOpenEdit(m)}
                                  style={{ padding: '5px 10px', fontSize: '0.8rem', background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}
                                  title="Editar material"
                                >
                                  ✏️ Editar
                                </button>
                              )}
                              {isAdmin && (
                                <button
                                  onClick={() => handleDeleteMaterial(m)}
                                  style={{ padding: '5px 8px', fontSize: '0.8rem', background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca', borderRadius: '4px', cursor: 'pointer' }}
                                  title="Eliminar material"
                                >
                                  🗑️
                                </button>
                              )}
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

          {/* ── MODAL: CREAR / EDITAR MATERIAL ── */}
          {modalOpen && (
            <div style={{
              position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(15, 23, 42, 0.65)', backdropFilter: 'blur(3px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
            }}>
              <div className="card" style={{ width: '92%', maxWidth: '540px', padding: '26px', background: '#ffffff', borderRadius: '10px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.25)' }}>
                <h2 style={{ margin: '0 0 6px', fontSize: '1.3rem', color: '#0f172a', fontWeight: 800 }}>
                  {editingMaterial ? '✏️ Editar Material / Insumo' : '➕ Nuevo Material de Maquila'}
                </h2>
                <p style={{ margin: '0 0 18px', color: '#64748b', fontSize: '0.85rem' }}>
                  Ingresa los datos del material. Podrá ser seleccionado en las recetas de maquila.
                </p>

                <form onSubmit={handleSaveMaterial} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                      SKU / Código del Material *
                    </label>
                    <input
                      type="text"
                      disabled={!!editingMaterial}
                      value={formMaterial.sku}
                      onChange={e => setFormMaterial({ ...formMaterial, sku: e.target.value.toUpperCase() })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 700, fontFamily: 'monospace', background: editingMaterial ? '#f1f5f9' : '#ffffff' }}
                      placeholder="Ej: ETIQ-BARRA-50X30, MANGA-CELOFAN-20"
                      required
                    />
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                      Código identificador único (no modificable después de crear).
                    </span>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                      Nombre del Material o Insumo *
                    </label>
                    <input
                      type="text"
                      value={formMaterial.nombre}
                      onChange={e => setFormMaterial({ ...formMaterial, nombre: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1' }}
                      placeholder="Ej: Etiqueta adhesiva frontal blanca 50x30mm"
                      required
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                        Categoría:
                      </label>
                      <select
                        value={formMaterial.categoria}
                        onChange={e => setFormMaterial({ ...formMaterial, categoria: e.target.value })}
                        style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontWeight: 600, background: '#ffffff' }}
                      >
                        <option value="ETIQUETA">🏷️ Etiqueta</option>
                        <option value="MANGA">📜 Manga de Celofán</option>
                        <option value="EMPAQUE">📦 Empaque / Caja</option>
                        <option value="INSUMO">🧩 Insumo General</option>
                        <option value="OTRO">Otro</option>
                      </select>
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                        Unidad de Medida:
                      </label>
                      <input
                        type="text"
                        value={formMaterial.unidad_medida}
                        onChange={e => setFormMaterial({ ...formMaterial, unidad_medida: e.target.value.toUpperCase() })}
                        style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', textAlign: 'center', fontWeight: 700 }}
                        placeholder="UN, ROLLO, MTS, etc."
                        required
                      />
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                      Stock Actual / Inventario Disponible (Unidades):
                    </label>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      value={formMaterial.stock_actual}
                      onChange={e => setFormMaterial({ ...formMaterial, stock_actual: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #0284c7', fontSize: '1.1rem', fontWeight: 800, color: '#0284c7' }}
                      placeholder="0"
                    />
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                      También puedes actualizar masivamente el stock subiendo el Excel simple de inventario.
                    </span>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px', color: '#334155' }}>
                      Observaciones / Instrucciones de uso:
                    </label>
                    <input
                      type="text"
                      value={formMaterial.observaciones}
                      onChange={e => setFormMaterial({ ...formMaterial, observaciones: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1.5px solid #cbd5e1', fontSize: '0.88rem' }}
                      placeholder="Ej: Pegar en el centro del reverso, usar selladora térmica..."
                    />
                  </div>

                  <div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.88rem', fontWeight: 600, color: '#0f172a' }}>
                      <input
                        type="checkbox"
                        checked={formMaterial.activo}
                        onChange={e => setFormMaterial({ ...formMaterial, activo: e.target.checked })}
                        style={{ transform: 'scale(1.2)' }}
                      />
                      Material Activo para Recetas de Maquila
                    </label>
                  </div>

                  <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setModalOpen(false)}
                      disabled={saving}
                    >
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={saving}
                      style={{ padding: '9px 24px', fontWeight: 700 }}
                    >
                      {saving ? 'Guardando...' : editingMaterial ? 'Actualizar Material' : 'Crear Material'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* ── MODAL: CARGAR EXCEL SIMPLE DE INVENTARIO ── */}
          {uploadModalOpen && (
            <div style={{
              position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(15, 23, 42, 0.65)', backdropFilter: 'blur(3px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
            }}>
              <div className="card" style={{ width: '92%', maxWidth: '520px', padding: '26px', background: '#ffffff', borderRadius: '10px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.25)' }}>
                <h2 style={{ margin: '0 0 6px', fontSize: '1.3rem', color: '#0f172a', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>📤</span> Carga Masiva de Inventario de Materiales
                </h2>
                <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: '0.88rem', lineHeight: 1.4 }}>
                  Sube un archivo Excel simple (.xlsx o .xls) que contenga únicamente dos columnas: <b>sku</b> y <b>unidades</b>.
                  Actualizará el stock de los existentes y registrará los nuevos automáticamente.
                </p>

                {/* Banner Plantilla */}
                <div style={{ padding: '12px 14px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '6px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.82rem', color: '#1e40af', fontWeight: 600 }}>
                    ¿Necesitas el formato exacto?
                  </span>
                  <button
                    type="button"
                    onClick={handleDownloadPlantilla}
                    style={{ background: '#ffffff', border: '1px solid #93c5fd', color: '#1d4ed8', padding: '5px 10px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}
                  >
                    📄 Descargar Plantilla
                  </button>
                </div>

                <form onSubmit={handleUploadExcelSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{
                    padding: '24px', border: '2px dashed #cbd5e1', borderRadius: '8px',
                    textAlign: 'center', background: '#f8fafc', cursor: 'pointer'
                  }}
                  onClick={() => fileInputRef.current && fileInputRef.current.click()}
                  >
                    <span style={{ fontSize: '2rem', display: 'block', marginBottom: '8px' }}>📁</span>
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept=".xlsx,.xls,.csv"
                      onChange={e => setSelectedFile(e.target.files[0] || null)}
                      style={{ display: 'none' }}
                    />
                    {selectedFile ? (
                      <div style={{ fontWeight: 700, color: '#0284c7', fontSize: '0.95rem' }}>
                        Archivo seleccionado: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                      </div>
                    ) : (
                      <>
                        <div style={{ fontWeight: 600, color: '#334155', fontSize: '0.9rem' }}>
                          Haz clic aquí para seleccionar el archivo Excel
                        </div>
                        <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                          Formatos admitidos: .xlsx, .xls, .csv
                        </span>
                      </>
                    )}
                  </div>

                  {/* Resultados de carga */}
                  {uploadResult && (
                    <div style={{ padding: '14px', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '6px' }}>
                      <div style={{ fontWeight: 700, color: '#166534', fontSize: '0.9rem', marginBottom: '4px' }}>
                        ✓ {uploadResult.mensaje}
                      </div>
                      <div style={{ fontSize: '0.82rem', color: '#15803d' }}>
                        • Actualizados: <b>{uploadResult.actualizados}</b><br/>
                        • Nuevos creados: <b>{uploadResult.creados}</b>
                      </div>
                      {uploadResult.errores && uploadResult.errores.length > 0 && (
                        <div style={{ marginTop: '8px', color: '#b91c1c', fontSize: '0.78rem' }}>
                          <b>Observaciones:</b>
                          {uploadResult.errores.map((err, i) => <div key={i}>• {err}</div>)}
                        </div>
                      )}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => { setUploadModalOpen(false); setSelectedFile(null); setUploadResult(null); }}
                      disabled={uploading}
                    >
                      Cerrar
                    </button>
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={!selectedFile || uploading}
                      style={{ padding: '9px 24px', fontWeight: 700 }}
                    >
                      {uploading ? 'Procesando Carga...' : 'Subir e Importar Inventario'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
