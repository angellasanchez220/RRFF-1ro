// src/pages/Dashboard.jsx
import { useState, useEffect, useMemo } from 'react';
import { fetchSOP, downloadRrffExcel } from '../api';
import SkuCard from '../components/SkuCard';

const NIVELES = ['ROJO','NARANJA','AMARILLO','AZUL','MORADO','VERDE'];
const EMOJI = { ROJO:'🔴', NARANJA:'🟠', AMARILLO:'🟡', AZUL:'🔵', MORADO:'🟣', VERDE:'🟢' };

export default function Dashboard() {
  const [allData,   setAllData]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState('');
  const [lastFetch, setLastFetch] = useState(null);
  const [isDownloadingExcel, setIsDownloadingExcel] = useState(false);

  // Filtros — vacíos = sin restricción (muestra todos)
  const [fCat,     setFCat]     = useState('');
  const [fSub,     setFSub]     = useState('');
  const [fFmt,     setFFmt]     = useState('');
  const [fSku,     setFSku]     = useState('');
  const [fSearch,  setFSearch]  = useState('');
  const [fNiveles, setFNiveles] = useState(new Set());
  const [fMaquila, setFMaquila] = useState('');

  const loadData = async () => {
    setLoading(true); setError('');
    try {
      const res = await fetchSOP();
      setAllData(res.data || []);
      setLastFetch(new Date().toLocaleTimeString('es-CL'));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadData(); }, []);

  async function handleDownloadExcel() {
    if (isDownloadingExcel) return;
    setIsDownloadingExcel(true);
    try {
      const { blob, filename } = await downloadRrffExcel();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(err.message || 'No se pudo generar el Excel RRFF. Intenta nuevamente.');
    } finally {
      setIsDownloadingExcel(false);
    }
  }

  function clearFilters() {
    setFCat(''); setFSub(''); setFFmt(''); setFSku('');
    setFSearch(''); setFNiveles(new Set()); setFMaquila('');
  }

  const hasFilters = !!(fCat || fSub || fFmt || fSku || fSearch || fMaquila || fNiveles.size > 0);

  // ── Opciones derivadas del dataset ───────────────────────────────────────────
  const cats = useMemo(() =>
    [...new Set(allData.map(d => d.categoria).filter(Boolean))].sort(),
  [allData]);

  const subcats = useMemo(() => {
    const arr = allData
      .filter(d => !fCat || d.categoria === fCat)
      .map(d => d.subcategoria).filter(Boolean);
    return [...new Set(arr)].sort();
  }, [fCat, allData]);

  const formatos = useMemo(() => {
    const arr = allData
      .filter(d => (!fCat || d.categoria === fCat) && (!fSub || d.subcategoria === fSub))
      .map(d => d.formato).filter(Boolean);
    return [...new Set(arr)].sort();
  }, [fCat, fSub, allData]);

  const skusDisp = useMemo(() => {
    const arr = allData
      .filter(d =>
        (!fCat || d.categoria === fCat) &&
        (!fSub || d.subcategoria === fSub) &&
        (!fFmt || d.formato === fFmt)
      ).map(d => d.sku).filter(Boolean);
    return [...new Set(arr)].sort();
  }, [fCat, fSub, fFmt, allData]);

  // ── Datos filtrados ───────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const search = fSearch.toLowerCase().trim();
    return allData.filter(d => {
      // Compatibilidad con payloads nuevos y anteriores: un SKU pertenece a
      // maquila si el backend lo marca o si trae una familia real (>1 miembro).
      const esMaquila = d.es_maquilable === true ||
        (Array.isArray(d.familia_skus) && d.familia_skus.length > 1);
      if (fCat   && d.categoria    !== fCat) return false;
      if (fSub   && d.subcategoria !== fSub) return false;
      if (fFmt   && d.formato      !== fFmt) return false;
      if (fSku   && d.sku          !== fSku) return false;
      if (fMaquila === 'SI' && !esMaquila) return false;
      if (fMaquila === 'NO' && esMaquila) return false;
      if (search && !`${d.sku} ${d.nombre_producto} ${d.codigo_femaco}`.toLowerCase().includes(search)) return false;
      if (fNiveles.size > 0 && !fNiveles.has(d.nivel_alerta)) return false;
      return true;
    });
  }, [allData, fCat, fSub, fFmt, fSku, fSearch, fMaquila, fNiveles]);

  const alertCounts = useMemo(() => {
    const counts = {};
    NIVELES.forEach(n => { counts[n] = 0; });
    allData.forEach(d => { if (d.nivel_alerta) counts[d.nivel_alerta]++; });
    return counts;
  }, [allData]);

  function toggleNivel(n) {
    setFNiveles(prev => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n); else next.add(n);
      return next;
    });
  }

  return (
    <div className="content-area">
      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div>
          <div className="sidebar-section-title">Búsqueda</div>
          <div className="filter-group">
            <input
              type="text"
              placeholder="SKU, nombre, código…"
              value={fSearch}
              onChange={e => setFSearch(e.target.value)}
            />
          </div>
        </div>

        <div>
          <div className="sidebar-section-title">Filtros</div>
          <div className="filter-group">
            <label>Categoría</label>
            <select value={fCat} onChange={e => { setFCat(e.target.value); setFSub(''); setFFmt(''); setFSku(''); }}>
              <option value="">— Todas —</option>
              {cats.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            <label>Subcategoría</label>
            <select value={fSub} onChange={e => { setFSub(e.target.value); setFFmt(''); setFSku(''); }}>
              <option value="">— Todas —</option>
              {subcats.map(s => <option key={s} value={s}>{s}</option>)}
            </select>

            <label>Formato</label>
            <select value={fFmt} onChange={e => { setFFmt(e.target.value); setFSku(''); }}>
              <option value="">— Todos —</option>
              {formatos.map(f => <option key={f} value={f}>{f}</option>)}
            </select>

            <label>SKU Específico</label>
            <select value={fSku} onChange={e => setFSku(e.target.value)}>
              <option value="">— Todos —</option>
              {skusDisp.map(s => <option key={s} value={s}>{s}</option>)}
            </select>

            <label>Tipo (Maquila)</label>
            <select value={fMaquila} onChange={e => setFMaquila(e.target.value)}>
              <option value="">— Todos —</option>
              <option value="SI">Solo Maquila</option>
              <option value="NO">No Maquilables</option>
            </select>
          </div>
        </div>

        <div>
          <div className="sidebar-section-title">Semáforo de Alerta</div>
          <div className="semaforo-legend">
            {[
              { n: 'ROJO',    desc: 'Cobertura < 1 mes — CRÍTICO' },
              { n: 'NARANJA', desc: 'Cobertura < 2.5 meses' },
              { n: 'AMARILLO',desc: 'Cobertura < 4 meses' },
              { n: 'VERDE',   desc: 'Cobertura normal' },
              { n: 'MORADO',  desc: 'En tránsito activo' },
              { n: 'AZUL',    desc: 'Sobrestock > 10 meses' },
            ].map(({ n, desc }) => (
              <button
                key={n}
                className={`semaforo-row ${n} ${fNiveles.size > 0 && !fNiveles.has(n) ? 'inactive' : ''}`}
                onClick={() => toggleNivel(n)}
                title={desc}
              >
                <span className="sr-dot">{EMOJI[n]}</span>
                <span className="sr-label">{n}</span>
                <span className="sr-count">{alertCounts[n]}</span>
                <span className="sr-desc">{desc}</span>
              </button>
            ))}
          </div>
        </div>

        {hasFilters && (
          <button className="btn-clear-filters" onClick={clearFilters}>
            ✕ Limpiar filtros
          </button>
        )}

        <div>
          <div className="sidebar-section-title">Resumen</div>
          <div className="stat-pill">
            <span>Mostrando</span>
            <span className="count">{filtered.length} / {allData.length}</span>
          </div>
          {lastFetch && (
            <div style={{ fontSize: '0.7rem', color: 'var(--gray)', textAlign: 'center', marginTop: 6, marginBottom: 12 }}>
              Actualizado: {lastFetch}
            </div>
          )}
        </div>

        <button
          onClick={handleDownloadExcel}
          disabled={isDownloadingExcel}
          className="btn-primary"
          style={{ width: '100%', marginBottom: 10 }}
        >
          {isDownloadingExcel ? 'Generando Excel...' : 'Descargar Excel RRFF'}
        </button>

        <button
          onClick={loadData}
          style={{
            background: 'none', border: '1px solid var(--border)',
            borderRadius: 5, padding: '7px 12px', cursor: 'pointer',
            fontSize: '0.78rem', color: 'var(--mid)', fontFamily: 'inherit',
            width: '100%'
          }}
        >
          ↻ Recargar datos
        </button>
      </aside>

      {/* ── PANEL PRINCIPAL ── */}
      <main className="main-panel">
        {loading && (
          <div className="loader-wrap">
            <div className="spinner" />
            <span>Conectando a PostgreSQL…</span>
          </div>
        )}
        {error && (
          <div className="empty-state">
            <span style={{ color: 'var(--rojo)', fontSize: '1.5rem' }}>⚠️</span>
            <span>{error}</span>
            <button onClick={loadData} className="btn-primary" style={{ width: 'auto', padding: '8px 20px' }}>
              Reintentar
            </button>
          </div>
        )}
        {!loading && !error && allData.length === 0 && (
          <div className="empty-state">
            <span style={{ fontSize: '2.5rem' }}>📭</span>
            <span style={{ fontWeight: 700, fontSize: '1rem' }}>No hay datos de planificación cargados.</span>
            <span style={{ fontSize: '0.85rem', color: 'var(--gray)', textAlign: 'center', maxWidth: 360 }}>
              Ve al <strong>Panel de Control → Admin</strong> y presiona{' '}
              <strong>"Sincronizar Matrix"</strong> para descargar y procesar los datos,
              o <strong>"Ejecutar Pipeline"</strong> si ya tienes los archivos cargados.
            </span>
            <button onClick={loadData} className="btn-primary" style={{ width: 'auto', padding: '8px 20px', marginTop: 4 }}>
              ↻ Reintentar
            </button>
          </div>
        )}
        {!loading && !error && filtered.length === 0 && allData.length > 0 && (
          <div className="empty-state">
            <span style={{ fontSize: '2rem' }}>🔍</span>
            <span>Sin resultados para los filtros seleccionados.</span>
            <button className="btn-clear-filters" onClick={clearFilters} style={{ marginTop: 8 }}>
              ✕ Limpiar filtros
            </button>
          </div>
        )}
        {!loading && !error && filtered.map(p => (
          <SkuCard key={p.sku || p.codigo_femaco} product={p} />
        ))}
      </main>
    </div>
  );
}
