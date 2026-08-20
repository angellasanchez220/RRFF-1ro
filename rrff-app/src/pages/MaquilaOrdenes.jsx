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
      // Reload
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

  function renderList() {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2>Listado de Órdenes</h2>
          {isAdmin && (
            <div style={{ display: 'flex', gap: 10 }}>
              <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files[0])} />
              <button className="btn-primary" onClick={handleImportPreview} disabled={!file || loading}>
                Subir OC (CSV)
              </button>
            </div>
          )}
        </div>
        
        {error && <div className="alert-box" style={{ background: '#ffebee', color: '#c62828', padding: 10 }}>{error}</div>}
        {loading ? <p>Cargando...</p> : (
          <table className="rrff-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Número OC</th>
                <th>Fecha Carga</th>
                <th>SKUs (Maquilables)</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {ordenes.map(o => (
                <tr key={o.id}>
                  <td>{o.id}</td>
                  <td><strong>{o.numero_oc}</strong></td>
                  <td>{o.fecha_carga}</td>
                  <td>{o.sku_count} ({o.maq_count})</td>
                  <td><span className="chip" style={{ background: o.estado_procesamiento.includes('Complet') ? '#c8e6c9' : '#fff9c4' }}>{o.estado_procesamiento}</span></td>
                  <td>
                    <button className="btn-logout" onClick={() => openDetail(o.id)}>Ver Detalle</button>
                  </td>
                </tr>
              ))}
              {ordenes.length === 0 && (
                <tr><td colSpan="6" style={{ textAlign: 'center' }}>No hay órdenes registradas.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    );
  }

  function renderPreview() {
    if (!previewData) return null;
    const { meta, detalles, componentes, estado_general } = previewData;
    const maq = detalles.filter(d => d.es_maquilable);
    
    return (
      <div>
        <button className="btn-logout" onClick={() => { setView('list'); setPreviewData(null); }} style={{ marginBottom: 20 }}>
          ← Cancelar
        </button>
        <h2>Vista Previa OC: {meta.numero_oc}</h2>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
          <div className="card" style={{ padding: 15, background: '#f5f5f5' }}>
            <p><strong>Archivo:</strong> {meta.nombre_archivo}</p>
            <p><strong>Filas detectadas:</strong> {meta.total_lineas}</p>
            <p><strong>SKUs consolidados:</strong> {detalles.length}</p>
            <p><strong>Estado General:</strong> <span className="chip">{estado_general}</span></p>
          </div>
        </div>

        {error && <div className="alert-box">{error}</div>}

        <h3>Productos a Maquilar ({maq.length})</h3>
        <table className="rrff-table" style={{ marginBottom: 20, width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc' }}>
              <th style={{ padding: '10px' }}>SKU</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Solicitado</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Recibido</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Pendiente</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Stock</th>
              <th style={{ padding: '10px', textAlign: 'center', background: '#f5f5f5' }}>A Maquilar</th>
            </tr>
          </thead>
          <tbody>
            {maq.map(m => (
              <tr key={m.sku} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '10px' }}>{m.sku}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.cantidad_solicitada}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.cantidad_recibida}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.cantidad_pendiente}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.stock_producto_terminado}</td>
                <td style={{ 
                  padding: '10px', 
                  textAlign: 'center', 
                  fontWeight: 'bold', 
                  background: '#f5f5f5',
                  color: m.cantidad_a_maquilar > 0 ? '#e65100' : '#388e3c' 
                }}>
                  {m.cantidad_a_maquilar > 0 ? m.cantidad_a_maquilar : "0 (Cubierto)"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <button className="btn-primary" onClick={confirmUpload} disabled={loading} style={{ width: '100%', padding: 15, fontSize: '1.1rem' }}>
          {loading ? 'Guardando...' : 'Confirmar e Importar OC'}
        </button>
      </div>
    );
  }

  function renderDetail() {
    if (!activeOc) return null;
    const { meta, detalles, componentes } = activeOc;
    const maq = detalles.filter(d => d.es_maquilable);
    const noMaq = detalles.filter(d => !d.es_maquilable);

    const handleExport = () => {
      // Exportación básica a CSV (resumen maquilables y componentes)
      // Idealmente, se llama a endpoint de XLSX, pero lo haremos con CSV simple aquí o mockeamos.
      let csvContent = "data:text/csv;charset=utf-8,SKU,Requerido,Stock,Faltante\n";
      componentes.forEach(c => {
        csvContent += `${c.sku},${c.requerido},${c.stock_actual},${c.faltante}\n`;
      });
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `plan_maquila_${meta.numero_oc}.csv`);
      document.body.appendChild(link);
      link.click();
    };

    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
          <button className="btn-logout" onClick={() => { setView('list'); setActiveOc(null); }}>
            ← Volver al listado
          </button>
          <div style={{ display: 'flex', gap: 10 }}>
            {isAdmin && <button className="btn-logout" onClick={() => recalcularOc(meta.id)} disabled={loading}>Recalcular OC</button>}
            <button className="btn-primary" onClick={handleExport}>Exportar CSV</button>
          </div>
        </div>

        {error && <div className="alert-box" style={{ background: '#ffebee', color: '#c62828', padding: 10 }}>{error}</div>}

        <div style={{ background: '#fff', padding: 20, borderRadius: 8, border: '1px solid #ddd', marginBottom: 20 }}>
          <h2 style={{ margin: '0 0 10px 0' }}>OC {meta.numero_oc}</h2>
          <div style={{ display: 'flex', gap: 30, fontSize: '0.95rem', color: '#555' }}>
            <span><strong>Fecha Emisión:</strong> {meta.fecha_emision}</span>
            <span><strong>Estado OC:</strong> {meta.estado_oc}</span>
            <span><strong>Estado Maquila:</strong> <span className="chip" style={{ background: '#e1f5fe' }}>{meta.estado_procesamiento}</span></span>
          </div>
          
          {isAdmin && (
            <div style={{ marginTop: 15 }}>
              <select 
                value={meta.estado_procesamiento} 
                onChange={(e) => updateEstado(meta.id, e.target.value)}
                style={{ padding: '6px 12px', borderRadius: 4, border: '1px solid #ccc' }}
                disabled={loading}
              >
                <option value="Pendiente">Pendiente</option>
                <option value="En preparación">En preparación</option>
                <option value="Preparada">Preparada</option>
                <option value="Bloqueada por faltantes">Bloqueada por faltantes</option>
                <option value="Cancelada">Cancelada</option>
              </select>
            </div>
          )}
        </div>

        <h3>1. Productos Maquilables ({maq.length})</h3>
        <table className="rrff-table" style={{ marginBottom: 20, width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc' }}>
              <th style={{ padding: '10px' }}>SKU Terminado</th>
              <th style={{ padding: '10px' }}>Producto</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Pedido</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Recibido</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Pendiente</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Stock Terminado</th>
              <th style={{ padding: '10px', textAlign: 'center', background: '#f5f5f5' }}>A Maquilar</th>
              <th style={{ padding: '10px', textAlign: 'center' }}>Estado</th>
            </tr>
          </thead>
          <tbody>
            {maq.map(m => (
              <tr key={m.sku} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '10px' }}><strong>{m.sku}</strong></td>
                <td style={{ padding: '10px' }}>{m.nombre_producto}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.cantidad_solicitada}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.cantidad_recibida}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.cantidad_pendiente}</td>
                <td style={{ padding: '10px', textAlign: 'center' }}>{m.stock_producto_terminado}</td>
                <td style={{ 
                  padding: '10px', 
                  textAlign: 'center', 
                  fontWeight: 'bold', 
                  background: '#f5f5f5',
                  color: m.cantidad_a_maquilar > 0 ? '#e65100' : '#388e3c' 
                }}>
                  {m.cantidad_a_maquilar > 0 ? m.cantidad_a_maquilar : "0 (Cubierto / No requiere)"}
                </td>
                <td style={{ padding: '10px', textAlign: 'center' }}>
                  <span className="chip" style={{ 
                    background: m.cantidad_a_maquilar > 0 ? '#fff3e0' : '#e8f5e9',
                    color: m.cantidad_a_maquilar > 0 ? '#e65100' : '#2e7d32',
                    border: '1px solid currentColor'
                  }}>
                    {m.estado_analisis}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        
        {maq.map(m => {
          if (m.cantidad_a_maquilar === 0) return null;
          return (
            <div key={`exp-${m.sku}`} style={{ marginBottom: 15, padding: 15, background: '#f5f5f5', borderLeft: '4px solid #1976d2', fontSize: '0.9rem' }}>
              <p style={{ margin: 0 }}>
                La OC {meta.numero_oc} solicita {m.cantidad_solicitada} unidades de <strong>{m.sku}</strong>. 
                Ya se recibieron {m.cantidad_recibida} y existen {m.stock_producto_terminado} unidades terminadas en stock. 
                Quedan {m.cantidad_pendiente} unidades pendientes, por lo que <strong>deben maquilarse {m.cantidad_a_maquilar} unidades.</strong>
              </p>
            </div>
          );
        })}

        <h3>2. Componentes Consolidados (Requerimientos)</h3>
        <table className="rrff-table" style={{ marginBottom: 20 }}>
          <thead>
            <tr>
              <th>SKU Componente</th>
              <th>Nombre</th>
              <th>Utilizado por</th>
              <th>Requerido Total</th>
              <th>Stock Actual</th>
              <th>Faltante Total</th>
            </tr>
          </thead>
          <tbody>
            {componentes.map(c => (
              <tr key={c.sku} style={{ background: c.faltante > 0 ? '#ffebee' : 'inherit' }}>
                <td><strong>{c.sku}</strong></td>
                <td>{c.nombre}</td>
                <td>{c.utilizado_por.join(', ')}</td>
                <td style={{ fontWeight: 'bold' }}>{c.requerido}</td>
                <td>{c.stock_actual}</td>
                <td style={{ fontWeight: 'bold', color: c.faltante > 0 ? '#c62828' : 'inherit' }}>{c.faltante}</td>
              </tr>
            ))}
            {componentes.length === 0 && (
              <tr><td colSpan="6" style={{ textAlign: 'center' }}>No hay componentes requeridos.</td></tr>
            )}
          </tbody>
        </table>

        {noMaq.length > 0 && (
          <>
            <h3>3. Productos No Maquilables ({noMaq.length})</h3>
            <table className="rrff-table" style={{ opacity: 0.8 }}>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Producto</th>
                  <th>Cantidad Pendiente</th>
                  <th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {noMaq.map(m => (
                  <tr key={m.sku}>
                    <td>{m.sku}</td>
                    <td>{m.nombre_producto}</td>
                    <td>{m.cantidad_pendiente}</td>
                    <td>Sin receta activa</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="ordenes-maquila">
      {view === 'list' && renderList()}
      {view === 'upload' && renderPreview()}
      {view === 'detail' && renderDetail()}
    </div>
  );
}
