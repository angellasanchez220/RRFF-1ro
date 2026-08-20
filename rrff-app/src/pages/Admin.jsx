// src/pages/Admin.jsx
import { useState, useRef, useEffect } from 'react';
import {
  fetchEmbarques, marcarAforo, cambiarEta, confirmarLlegada, deleteOc,
  marcarAforoOc, cambiarEtaOc, confirmarLlegadaOc,
  fetchUsuarios, createUsuario, updateUsuario, deleteUsuario,
  getPermisos, extractShinyapps, uploadFile, uploadTransito, reprocess
} from '../api';

const PERMS_LIST = [
  { key: 'can_upload_maestro',    label: 'Subir Maestra' },
  { key: 'can_upload_inventario', label: 'Subir Inventario' },
  { key: 'can_upload_transito',   label: 'Subir OC/Tránsito' },
  { key: 'can_edit_obs',          label: 'Editar Observaciones' },
  { key: 'can_manage_oc',         label: 'Gestionar Embarques' },
  { key: 'can_manage_users',      label: 'Gestionar Usuarios' },
];

const ESTADO_STYLE = {
  EN_TRANSITO: { bg: '#E8F2FB', color: '#1a6aa8', label: '🚢 En tránsito' },
  EN_AFORO:    { bg: '#FFF3EB', color: '#b35f1a', label: '🛃 En aforo' },
  RETRASADO:   { bg: '#FFFBE0', color: '#8a7000', label: '⏱ Retrasado' },
  LLEGADO:     { bg: '#E7F7ED', color: '#1d6b3e', label: '✅ Llegado' },
};

// ── Upload Tab ────────────────────────────────────────────────────────────────
function UploadTab({ tab }) {
  const [file, setFile]       = useState(null);
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [drag, setDrag]       = useState(false);
  // Campos extra para tránsito
  const [nombrePedido, setNombrePedido] = useState('');
  const [etaFecha, setEtaFecha]         = useState('');
  const inputRef = useRef();

  const isTransito = tab.id === 'transito';

  const handleFile = f => {
    if (f && (f.name.endsWith('.xlsx') || f.name.endsWith('.xls'))) {
      setFile(f); setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    if (isTransito && !nombrePedido.trim()) {
      alert('Debes ingresar el nombre del pedido antes de subir.');
      return;
    }
    setLoading(true); setResult(null);
    try {
      let data;
      if (isTransito) {
        data = await uploadTransito(file, nombrePedido.trim(), etaFecha);
      } else {
        data = await uploadFile(tab.endpoint, file);
      }
      setResult({ ok: true, data });
    } catch (e) { setResult({ ok: false, msg: e.message }); }
    finally { setLoading(false); }
  };

  return (
    <div>
      {/* Campos extra para OC / Tránsito */}
      {isTransito && (
        <div className="transito-meta">
          <div className="filter-group" style={{ marginBottom: 14 }}>
            <label>📦 Nombre del Pedido / OC <span style={{ color: 'var(--rojo)' }}>*</span></label>
            <input
              type="text"
              placeholder="Ej: OC-2026-048 / Contenedor Mayo"
              value={nombrePedido}
              onChange={e => setNombrePedido(e.target.value)}
            />
          </div>
          <div className="filter-group" style={{ marginBottom: 14 }}>
            <label>📅 ETA estimada (fecha de llegada)</label>
            <input
              type="date"
              value={etaFecha}
              onChange={e => setEtaFecha(e.target.value)}
            />
          </div>
        </div>
      )}

      <div
        className={`upload-zone ${drag ? 'drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); }}
      >
        <input ref={inputRef} type="file" accept=".xlsx,.xls" onChange={e => handleFile(e.target.files[0])} />
        <div className="upload-icon">📁</div>
        <p>Arrastra el archivo aquí o haz clic para seleccionar</p>
        <p style={{ marginTop: 4, fontSize: '0.75rem', color: '#aaa' }}>Solo archivos Excel (.xlsx, .xls)</p>
        {file && <div className="file-name">✅ {file.name}</div>}
      </div>
      <button className="btn-upload" onClick={handleUpload} disabled={!file || loading}>
        {loading ? 'Subiendo…' : `Subir ${tab.label}`}
      </button>
      {result && (
        <div className={`upload-result ${result.ok ? 'ok' : 'err'}`}>
          {result.ok
            ? <>{`✅ Procesado. `}
                {result.data.actualizados != null && `${result.data.actualizados} actualizados, ${result.data.insertados ?? 0} nuevos.`}
                {result.data.insertadas   != null && `${result.data.insertadas} OCs insertadas.`}
                {result.data.nombre_pedido && ` Pedido: "${result.data.nombre_pedido}"`}
              </>
            : <>❌ {result.msg}</>}
        </div>
      )}
      {result?.ok && result.data.preview && (
        <div style={{ marginTop: 16, overflowX: 'auto' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: 6 }}>Preview ({result.data.preview.length} filas):</div>
          <table className="preview-table">
            <thead><tr>{Object.keys(result.data.preview[0]).map(k => <th key={k}>{k}</th>)}</tr></thead>
            <tbody>{result.data.preview.map((row, i) => (
              <tr key={i}>{Object.values(row).map((v, j) => <td key={j}>{v == null ? '—' : String(v)}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Panel Embarques ───────────────────────────────────────────────────────────
function EmbarquesTab() {
  const [embarques, setEmbarques] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [msg, setMsg]             = useState(null);
  const [etaModal, setEtaModal]   = useState(null); // id del item
  const [ocEtaModal, setOcEtaModal] = useState(null); // nombre de la OC
  const [newEta, setNewEta]       = useState('');
  const [motivo, setMotivo]       = useState('');
  const [filtro, setFiltro]       = useState('ACTIVAS'); // ACTIVAS, AFORO, TRANSITO, LLEGADAS, TODAS

  const load = async () => {
    setLoading(true);
    try { const d = await fetchEmbarques(); setEmbarques(d.embarques || []); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const doAction = async (fn, label) => {
    try {
      const r = await fn();
      setMsg({ ok: r.ok !== false, text: r.msg || r.alerta_msg || label + ' OK', alerta: r.alerta });
      load();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  };

  const doEta = async () => {
    if (!newEta) return;
    try {
      const r = await cambiarEta(etaModal, newEta, motivo);
      setMsg({ ok: true, text: `ETA cambiada → ${r.nueva_eta}` });
      setEtaModal(null); setNewEta(''); setMotivo('');
      load();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  };

  const doEtaOc = async () => {
    if (!newEta) return;
    try {
      const r = await cambiarEtaOc(ocEtaModal, newEta, motivo);
      setMsg({ ok: true, text: r.msg || `ETA cambiada para OC ${ocEtaModal}` });
      setOcEtaModal(null); setNewEta(''); setMotivo('');
      load();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  };

  const doDeleteOc = async (ocName) => {
    if (!confirm(`⚠️ ¿Estás seguro de que quieres borrar TODA la Orden de Compra "${ocName}"?\nEsta acción eliminará todos los SKUs asociados a esta OC y no se puede deshacer.`)) return;
    try {
      const r = await deleteOc(ocName);
      setMsg({ ok: true, text: r.msg || `OC ${ocName} eliminada` });
      load();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  };

  const embarquesFiltrados = embarques.filter(e => {
    if (filtro === 'ACTIVAS') return e.estado !== 'LLEGADO';
    if (filtro === 'TRANSITO') return e.estado === 'EN_TRANSITO' || e.estado === 'RETRASADO';
    if (filtro === 'AFORO') return e.estado === 'EN_AFORO';
    if (filtro === 'LLEGADAS') return e.estado === 'LLEGADO';
    return true; // TODAS
  });

  const gruposOc = {};
  embarquesFiltrados.forEach(e => {
    const oc = e.nombre_pedido || e.codigo_envio || 'Sin OC';
    if (!gruposOc[oc]) gruposOc[oc] = [];
    gruposOc[oc].push(e);
  });

  return (
    <div>
      {msg && (
        <div className={`upload-result ${msg.ok ? (msg.alerta ? '' : 'ok') : 'err'}`}
          style={msg.alerta ? { background: '#FFF3EB', color: '#b35f1a', border: '1px solid #F4864A' } : {}}
        >
          {msg.alerta ? '⚠️' : msg.ok ? '✅' : '❌'} {msg.text}
          <button onClick={() => setMsg(null)} style={{ marginLeft: 12, background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}>×</button>
        </div>
      )}

      {/* Modal ETA */}
      {etaModal && (
        <div className="modal-overlay">
          <div className="modal-box">
            <div className="modal-title">⏱ Cambiar ETA — ID #{etaModal}</div>
            <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Nueva fecha ETA</label>
            <input type="date" value={newEta} onChange={e => setNewEta(e.target.value)} className="modal-input" />
            <label style={{ fontSize: '0.82rem', fontWeight: 600, marginTop: 10 }}>Motivo (opcional)</label>
            <input type="text" value={motivo} onChange={e => setMotivo(e.target.value)} className="modal-input" placeholder="Ej: atraso en origen" />
            <div className="modal-actions">
              <button className="btn-upload" onClick={doEta} style={{ margin: 0 }}>Guardar</button>
              <button className="btn-reprocess" onClick={() => setEtaModal(null)} style={{ margin: 0 }}>Cancelar</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal ETA Masiva */}
      {ocEtaModal && (
        <div className="modal-overlay">
          <div className="modal-box">
            <div className="modal-title">⏱ Cambiar ETA Masiva — OC: {ocEtaModal}</div>
            <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Nueva fecha ETA (aplica a todos los ítems no llegados)</label>
            <input type="date" value={newEta} onChange={e => setNewEta(e.target.value)} className="modal-input" />
            <label style={{ fontSize: '0.82rem', fontWeight: 600, marginTop: 10 }}>Motivo (opcional)</label>
            <input type="text" value={motivo} onChange={e => setMotivo(e.target.value)} className="modal-input" placeholder="Ej: atraso contenedor" />
            <div className="modal-actions">
              <button className="btn-upload" onClick={doEtaOc} style={{ margin: 0 }}>Guardar</button>
              <button className="btn-reprocess" onClick={() => setOcEtaModal(null)} style={{ margin: 0 }}>Cancelar</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 16 }}>
        <div className="filter-group">
          <label style={{ marginRight: 8, fontWeight: 600 }}>Filtro de Estado:</label>
          <select value={filtro} onChange={e => setFiltro(e.target.value)}>
            <option value="ACTIVAS">🚢 Todas las Activas</option>
            <option value="TRANSITO">🌊 En Tránsito / Retrasado</option>
            <option value="AFORO">🛃 En Aforo</option>
            <option value="LLEGADAS">✅ Historial de Llegadas</option>
            <option value="TODAS">Ver Todas</option>
          </select>
        </div>
        <button onClick={load} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 5, padding: '6px 14px', cursor: 'pointer', fontSize: '0.78rem' }}>
          ↻ Actualizar
        </button>
      </div>

      {loading ? <div className="loader-wrap"><div className="spinner" /></div> : (
        <>
          <div style={{ fontWeight: 700, marginBottom: 12 }}>📋 Órdenes de Compra ({Object.keys(gruposOc).length})</div>
          {Object.keys(gruposOc).length === 0 && <div style={{ textAlign: 'center', padding: 20, color: '#aaa', border: '1px dashed var(--border)', borderRadius: 8 }}>No hay OCs para mostrar en este filtro</div>}
          
          {Object.entries(gruposOc).map(([ocName, items]) => {
            const totalQty = items.reduce((sum, item) => sum + (Number(item.cantidad) || 0), 0);
            const isLlegado = items.every(i => i.estado === 'LLEGADO');
            return (
              <details key={ocName} open={!isLlegado} style={{ marginBottom: 16, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                <summary style={{ padding: '12px 16px', background: isLlegado ? '#f3f9f5' : '#f9f9f9', cursor: 'pointer', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    📦 OC: <span style={{ color: 'var(--primary)', marginLeft: 6 }}>{ocName}</span> 
                    <span style={{ marginLeft: 16, fontSize: '0.85rem', color: 'var(--gray)', fontWeight: 'normal' }}>
                      ({items.length} SKUs — {totalQty.toLocaleString('es-CL')} uds)
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="oc-btn aforo" style={{ margin: 0, padding: '6px 10px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6 }} 
                            onClick={(e) => { e.preventDefault(); doAction(() => marcarAforoOc(ocName), `Aforo marcado para OC ${ocName}`); }} title="Aforo a toda la OC">
                      🛃 <span style={{ fontWeight: 600 }}>Aforo OC</span>
                    </button>
                    <button className="oc-btn eta" style={{ margin: 0, padding: '6px 10px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6 }} 
                            onClick={(e) => { e.preventDefault(); setOcEtaModal(ocName); setNewEta(''); }} title="Cambiar ETA a toda la OC">
                      📅 <span style={{ fontWeight: 600 }}>ETA OC</span>
                    </button>
                    <button className="oc-btn llego" style={{ margin: 0, padding: '6px 10px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6 }} 
                            onClick={(e) => { e.preventDefault(); doAction(() => confirmarLlegadaOc(ocName), `Llegada confirmada para OC ${ocName}`); }} title="Confirmar Llegada a toda la OC">
                      ✅ <span style={{ fontWeight: 600 }}>Llegada OC</span>
                    </button>
                    <button className="oc-btn" style={{ background: '#FFEBEC', color: '#E63946', margin: 0, padding: '6px 10px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6 }} 
                            onClick={(e) => { e.preventDefault(); doDeleteOc(ocName); }} title="Borrar toda la OC">
                      🗑️ <span style={{ fontWeight: 600 }}>Borrar OC</span>
                    </button>
                  </div>
                </summary>
                
                <div style={{ overflowX: 'auto', borderTop: '1px solid var(--border)' }}>
                  <table className="preview-table embarques-table" style={{ margin: 0, border: 'none', borderRadius: 0 }}>
                    <thead><tr>
                      <th style={{ background: '#fff' }}>SKU</th>
                      <th style={{ background: '#fff' }}>Producto</th>
                      <th style={{ background: '#fff' }}>Cantidad</th>
                      <th style={{ background: '#fff' }}>ETA</th>
                      <th style={{ background: '#fff' }}>Disponible</th>
                      <th style={{ background: '#fff' }}>Estado</th>
                      <th style={{ background: '#fff' }}>Acciones</th>
                    </tr></thead>
                    <tbody>
                      {items.map(e => {
                        const st = ESTADO_STYLE[e.estado] || ESTADO_STYLE.EN_TRANSITO;
                        return (
                          <tr key={e.id} style={e.estado === 'LLEGADO' ? { opacity: 0.6 } : {}}>
                            <td><b>{e.sku || '—'}</b></td>
                            <td style={{ maxWidth: 200, fontSize: '0.78rem' }}>{e.nombre_producto || '—'}</td>
                            <td>{Number(e.cantidad || 0).toLocaleString('es-CL')}</td>
                            <td>{e.eta_ajustada || e.fecha_eta || '—'}</td>
                            <td>{e.eta_efectiva || e.fecha_disponibilidad_real || e.fecha_llegada_real || '—'}</td>
                            <td><span className="estado-badge" style={{ background: st.bg, color: st.color }}>{st.label}</span></td>
                            <td>
                              <div className="oc-actions">
                                {e.estado !== 'LLEGADO' && (
                                  <>
                                    <button className="oc-btn aforo" onClick={() => doAction(() => marcarAforo(e.id), 'Aforo marcado')} title="Marcar en Aforo">🛃</button>
                                    <button className="oc-btn eta"   onClick={() => { setEtaModal(e.id); setNewEta(''); }} title="Cambiar ETA">📅</button>
                                    <button className="oc-btn llego" onClick={() => doAction(() => confirmarLlegada(e.id), 'Llegada confirmada')} title="Confirmar Llegada">✅</button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </details>
            );
          })}
        </>
      )}
    </div>
  );
}

// ── Panel Usuarios ────────────────────────────────────────────────────────────
function UsuariosTab() {
  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [msg, setMsg]           = useState(null);
  const [form, setForm]         = useState(null); // null | { mode: 'new'|'edit', data }

  const load = async () => {
    setLoading(true);
    try { setUsuarios(await fetchUsuarios()); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const emptyForm = () => ({
    username: '', password: '', role: 'viewer', activo: true,
    permisos: Object.fromEntries(PERMS_LIST.map(p => [p.key, false])),
  });

  const handleSave = async () => {
    const d = form.data;
    if (!d.username) return setMsg({ ok: false, text: 'El usuario no puede estar vacío' });
    try {
      if (form.mode === 'new') {
        if (!d.password) return setMsg({ ok: false, text: 'La contraseña es requerida' });
        await createUsuario({ username: d.username, password: d.password, role: d.role, permisos: d.permisos });
        setMsg({ ok: true, text: `Usuario ${d.username} creado` });
      } else {
        const upd = { role: d.role, permisos: d.permisos, activo: d.activo };
        if (d.password) upd.password = d.password;
        await updateUsuario(d.username, upd);
        setMsg({ ok: true, text: `Usuario ${d.username} actualizado` });
      }
      setForm(null); load();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  };

  const handleDelete = async (username) => {
    if (!confirm(`¿Eliminar usuario "${username}"?`)) return;
    try { await deleteUsuario(username); setMsg({ ok: true, text: `Usuario ${username} eliminado` }); load(); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  };

  return (
    <div>
      {msg && (
        <div className={`upload-result ${msg.ok ? 'ok' : 'err'}`}>
          {msg.ok ? '✅' : '❌'} {msg.text}
          <button onClick={() => setMsg(null)} style={{ marginLeft: 12, background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}>×</button>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn-upload" style={{ marginTop: 0 }} onClick={() => setForm({ mode: 'new', data: emptyForm() })}>
          + Nuevo Usuario
        </button>
      </div>

      {/* Formulario inline */}
      {form && (
        <div className="user-form-box">
          <div style={{ fontWeight: 700, marginBottom: 12 }}>
            {form.mode === 'new' ? '➕ Crear Usuario' : `✏️ Editar: ${form.data.username}`}
          </div>
          <div className="user-form-grid">
            {form.mode === 'new' && (
              <div className="form-field">
                <label>Nombre de usuario</label>
                <input value={form.data.username} onChange={e => setForm(f => ({ ...f, data: { ...f.data, username: e.target.value } }))} />
              </div>
            )}
            <div className="form-field">
              <label>Contraseña {form.mode === 'edit' && '(dejar vacío = no cambiar)'}</label>
              <input type="password" value={form.data.password} onChange={e => setForm(f => ({ ...f, data: { ...f.data, password: e.target.value } }))} />
            </div>
            <div className="form-field">
              <label>Rol</label>
              <select value={form.data.role} onChange={e => setForm(f => ({ ...f, data: { ...f.data, role: e.target.value } }))}>
                <option value="viewer">viewer</option>
                <option value="admin">admin</option>
                <option value="custom">custom</option>
              </select>
            </div>
            {form.mode === 'edit' && (
              <div className="form-field">
                <label>Estado</label>
                <select value={form.data.activo ? 'activo' : 'inactivo'} onChange={e => setForm(f => ({ ...f, data: { ...f.data, activo: e.target.value === 'activo' } }))}>
                  <option value="activo">Activo</option>
                  <option value="inactivo">Inactivo</option>
                </select>
              </div>
            )}
          </div>

          {form.data.role !== 'admin' && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, marginBottom: 8 }}>Permisos</div>
              <div className="perms-grid">
                {PERMS_LIST.map(p => (
                  <label key={p.key} className="perm-check">
                    <input
                      type="checkbox"
                      checked={!!form.data.permisos[p.key]}
                      onChange={e => setForm(f => ({ ...f, data: { ...f.data, permisos: { ...f.data.permisos, [p.key]: e.target.checked } } }))}
                    />
                    {p.label}
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="modal-actions" style={{ marginTop: 16 }}>
            <button className="btn-upload" style={{ marginTop: 0 }} onClick={handleSave}>💾 Guardar</button>
            <button className="btn-reprocess" style={{ marginTop: 0 }} onClick={() => setForm(null)}>Cancelar</button>
          </div>
        </div>
      )}

      {loading ? <div className="loader-wrap"><div className="spinner" /></div> : (
        <table className="preview-table">
          <thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th><th>Permisos</th><th>Acciones</th></tr></thead>
          <tbody>
            {usuarios.map(u => (
              <tr key={u.username} style={{ opacity: u.activo ? 1 : 0.5 }}>
                <td><b>{u.username}</b></td>
                <td><span className={`badge-role ${u.role}`}>{u.role}</span></td>
                <td>{u.activo ? '✅ Activo' : '🔴 Inactivo'}</td>
                <td style={{ fontSize: '0.72rem' }}>
                  {u.role === 'admin'
                    ? <span style={{ color: 'var(--verde)' }}>Todos los permisos</span>
                    : PERMS_LIST.filter(p => u.permisos[p.key]).map(p => p.label).join(', ') || 'Sin permisos'}
                </td>
                <td>
                  <div className="oc-actions">
                    <button className="oc-btn eta" onClick={() => setForm({ mode: 'edit', data: { ...u, password: '', permisos: { ...Object.fromEntries(PERMS_LIST.map(p => [p.key, false])), ...u.permisos } } })}>✏️</button>
                    <button className="oc-btn" style={{ background: '#FFEBEC', color: '#E63946' }} onClick={() => handleDelete(u.username)}>🗑</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Main Admin ────────────────────────────────────────────────────────────────
const UPLOAD_TABS = [
  { id: 'maestro',    label: '📋 Maestra',          endpoint: 'maestro' },
  { id: 'inventario', label: '📦 Inventario Femaco', endpoint: 'inventario' },
  { id: 'transito',   label: '🚢 OC / Tránsito',    endpoint: 'transito' },
];

const ALL_TABS = [
  ...UPLOAD_TABS,
  { id: 'embarques', label: '⚓ Gestión Embarques' },
  { id: 'usuarios',  label: '👥 Usuarios' },
];

export default function Admin() {
  const [activeTab, setActiveTab]             = useState('maestro');
  const [reprocessing, setReprocessing]       = useState(false);
  const [reprocessResult, setReprocessResult] = useState(null);
  const [extracting, setExtracting]           = useState(false);
  const [extractResult, setExtractResult]     = useState(null);

  const handleExtract = async () => {
    setExtracting(true); setExtractResult(null);
    try {
      const d = await extractShinyapps();
      const logs = d.logs || {};
      const extOk = logs.extractor?.code === 0;
      const pipeOk = d.ok;
      let msg;
      if (pipeOk) {
        msg = '✅ Sincronización completa: Matrix descargado + Pipeline ejecutado. Recarga el dashboard.';
      } else if (extOk) {
        msg = '⚠️ Matrix descargado pero el pipeline tuvo errores. Intenta "Ejecutar Pipeline" manualmente.';
      } else {
        msg = `❌ Error en extracción: ${logs.extractor?.err || 'Sin conexión a Matrix'}. Intenta "Ejecutar Pipeline" con los datos existentes.`;
      }
      setExtractResult({ ok: pipeOk, msg });
    } catch (e) { setExtractResult({ ok: false, msg: e.message }); }
    finally { setExtracting(false); }
  };

  const handleReprocess = async () => {
    setReprocessing(true); setReprocessResult(null);
    try {
      const d = await reprocess();
      setReprocessResult({ ok: d.ok, msg: d.ok ? 'Pipeline ejecutado correctamente.' : 'Error en pipeline.' });
    } catch (e) { setReprocessResult({ ok: false, msg: e.message }); }
    finally { setReprocessing(false); }
  };

  const uploadTab = UPLOAD_TABS.find(t => t.id === activeTab);

  return (
    <div className="main-panel">
      <div className="admin-page">
        <h1>⚙️ Panel de Administración</h1>
        <p style={{ color: 'var(--gray)', marginBottom: 20, fontSize: '0.85rem' }}>
          Gestión de datos, embarques y usuarios.
        </p>

        <div className="tabs">
          {ALL_TABS.map(t => (
            <button key={t.id} className={`tab-btn ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        {uploadTab && <UploadTab key={activeTab} tab={uploadTab} />}
        {activeTab === 'embarques' && <EmbarquesTab />}
        {activeTab === 'usuarios'  && <UsuariosTab />}

        {activeTab !== 'embarques' && activeTab !== 'usuarios' && (
          <>
            <hr style={{ margin: '24px 0', borderColor: 'var(--border)', borderStyle: 'dashed' }} />
            <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 300px' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>📥 Sincronizar Matrix (Shinyapps)</div>
                <p style={{ fontSize: '0.82rem', color: 'var(--gray)', marginBottom: 10 }}>
                  Descarga automáticamente los reportes de Sell In y Sell Out más recientes desde Matrix.
                </p>
                <button className="btn-upload" onClick={handleExtract} disabled={extracting}>
                  {extracting ? 'Sincronizando…' : '⬇ Sincronizar Matrix'}
                </button>
                {extractResult && (
                  <div className={`upload-result ${extractResult.ok ? 'ok' : 'err'}`} style={{ marginTop: 12 }}>
                    {extractResult.ok ? `✅ ${extractResult.msg}` : `❌ ${extractResult.msg}`}
                  </div>
                )}
              </div>
              <div style={{ flex: '1 1 300px' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>🔄 Reprocesar Pipeline Completo</div>
                <p style={{ fontSize: '0.82rem', color: 'var(--gray)', marginBottom: 10 }}>
                  Ejecuta Transformer → Planner para recalcular la planificación con los datos actuales.
                </p>
                <button className="btn-reprocess" onClick={handleReprocess} disabled={reprocessing}>
                  {reprocessing ? 'Procesando…' : '▶ Ejecutar Pipeline'}
                </button>
                {reprocessResult && (
                  <div className={`upload-result ${reprocessResult.ok ? 'ok' : 'err'}`} style={{ marginTop: 12 }}>
                    {reprocessResult.ok ? `✅ ${reprocessResult.msg}` : `❌ ${reprocessResult.msg}`}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
