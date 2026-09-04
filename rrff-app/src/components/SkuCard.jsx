// src/components/SkuCard.jsx — v2.2
// Todo el data visible por defecto, expand = gráfico + desglose tránsito + por qué sugerencia
import { useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts';
import { fetchTransito, fetchObservacion, saveObservacion, getPermisos } from '../api';

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div style={{ background: '#fff', border: '1px solid #ccc', padding: '8px 12px', borderRadius: 6, fontSize: 11, boxShadow: '0 2px 5px rgba(0,0,0,0.1)' }}>
        <div style={{ fontWeight: 'bold', marginBottom: 4 }}>{label}</div>
        {payload.map((entry, index) => (
          <div key={index} style={{ color: entry.color, margin: '2px 0' }}>
            {entry.name}: {Number(entry.value).toLocaleString('es-CL')}
          </div>
        ))}
        {data.growth_pct != null && (
          <div style={{ marginTop: 4, fontWeight: 'bold', color: data.growth_pct > 0 ? '#1d6b3e' : data.growth_pct < 0 ? '#b35f1a' : '#666' }}>
            Var. vs mes ant: {data.growth_pct > 0 ? '▲' : data.growth_pct < 0 ? '▼' : ''} {data.growth_pct}%
          </div>
        )}
      </div>
    );
  }
  return null;
};

const COLORES = {
  ROJO:    { bg: '#FFEBEC', label: '🔴' },
  NARANJA: { bg: '#FFF3EB', label: '🟠' },
  AMARILLO:{ bg: '#FFFBE0', label: '🟡' },
  AZUL:    { bg: '#E8F2FB', label: '🔵' },
  MORADO:  { bg: '#F3EEF9', label: '🟣' },
  VERDE:   { bg: '#E7F7ED', label: '🟢' },
};

const ESTADO_STYLE = {
  EN_TRANSITO: { bg: '#E8F2FB', color: '#1a6aa8', label: '🚢 En tránsito' },
  EN_AFORO:    { bg: '#FFF3EB', color: '#b35f1a', label: '🛃 En aforo' },
  RETRASADO:   { bg: '#FFFBE0', color: '#8a7000', label: '⏱ Retrasado' },
  LLEGADO:     { bg: '#E7F7ED', color: '#1d6b3e', label: '✅ Llegado' },
};

function fmt(n) {
  if (n == null || n === '' || (typeof n === 'number' && isNaN(n))) return '—';
  return Number(n).toLocaleString('es-CL');
}
function fmtDate(s) {
  if (!s || s === '—' || s === 'None' || s === 'null') return '—';
  return String(s).slice(0, 10);
}

export default function SkuCard({ product }) {
  const [expanded,  setExpanded]  = useState(false);
  const [transito,  setTransito]  = useState(null);
  const [trLoad,    setTrLoad]    = useState(false);
  const [obs,       setObs]       = useState(null);
  const [obsEdit,   setObsEdit]   = useState('');
  const [obsSaving, setObsSaving] = useState(false);
  const [obsSaved,  setObsSaved]  = useState(false);

  const alerta    = product.nivel_alerta || 'VERDE';
  const colorInfo = COLORES[alerta] || COLORES.VERDE;
  const permisos  = getPermisos();
  const role      = localStorage.getItem('rrff_role');
  const canEditObs = role === 'admin' || permisos.can_edit_obs || false;

  const ump         = product.ump ?? 0;
  const ueDisplay   = ump > 0 ? Math.round(ump) : '—';
  const stockFemaco = product.stock_act ?? 0;
  const stockHC     = product.stock_fisico_matrix ?? product.stock_hc ?? null;
  const cantTr      = product.cantidad_transito ?? 0;
  const eta         = fmtDate(product.eta_proxima);
  const durMeses    = product.duracion_meses ?? 0;
  const durStr      = durMeses >= 999 ? '∞' : `${Number(durMeses).toFixed(1)} m`;

  const durFisica   = product.duracion_fisica_solo ?? 0;
  const durFisicaStr = durFisica >= 999 ? '∞' : `${Number(durFisica).toFixed(1)} m`;
  const sug         = product.sugerencia_compra_inmediata_uds ?? 0;
  const cajas       = ump > 0 ? Math.floor(stockFemaco / ump) : 0;
  const hcCajas     = ump > 0 && stockHC ? Math.floor(stockHC / ump) : null;
  const condicion   = product.condicion || product.estado || '';
  const esNuevo     = !product.sku || String(product.sku).trim() === '';
  const calendario  = product.calendario || [];
  const chartData = product.chart_12m || [];
  
  const familySkus = Array.isArray(product.familia_skus) ? product.familia_skus : [];
  const isFamilyMember = familySkus.length > 1;
  const isMaquilable = product.es_maquilable === true || isFamilyMember;
  const familyName = product.nombre_familia_maquila || 'Familia de reemplazo';
  const familyStock = product.stock_bruto_familia ??
    familySkus.reduce((sum, member) => sum + Number(member.stock_act || 0), 0);
  const usesFamilyStockForPurchase = product.sug_usa_stock_familia === true;
  const stockUsedForPurchase = product.sug_stock_actual ??
    (usesFamilyStockForPurchase ? familyStock : stockFemaco);
  const familyAdditionalStock = Math.max(0, Number(familyStock) - Number(stockFemaco));

  const sem1 = product.sem1_uds ?? 0;
  const sem2 = product.sem2_uds ?? 0;
  const sem3 = product.sem3_uds ?? 0;
  const sem4 = product.sem4_uds ?? 0;
  const total4 = product.total_4_sem_verificado ?? (sem1 + sem2 + sem3 + sem4);
  const objetivo = product.objetivo ?? 0;

  async function toggleExpanded() {
    const opening = !expanded;
    setExpanded(opening);
    if (opening) {
      if (!transito) {
        setTrLoad(true);
        try { const d = await fetchTransito(product.sku); setTransito(d.ordenes || []); }
        catch { setTransito([]); }
        finally { setTrLoad(false); }
      }
      if (obs === null) {
        try {
          const d = await fetchObservacion(product.sku);
          setObs(d); setObsEdit(d.observacion || '');
        } catch { setObs({ observacion: '' }); }
      }
    }
  }

  async function handleSaveObs() {
    setObsSaving(true);
    try {
      await saveObservacion(product.sku, obsEdit);
      setObsSaved(true);
      setTimeout(() => setObsSaved(false), 3000);
    } catch (e) { alert(e.message); }
    finally { setObsSaving(false); }
  }

  return (
    <div className={`sku-card ${isMaquilable ? 'sku-card-maquilable' : ''}`}>

      {/* ── CABECERA ── */}
      <div className="card-header" onClick={toggleExpanded} style={{ cursor: 'pointer' }}>
        <span className="ch-item"><b>SKU</b> {product.sku || 'NUEVO'}</span>
        <span className="ch-item"><b>CÓD.</b> {product.codigo_femaco || '—'}</span>
        <span className="ch-desc">{product.nombre_producto || '—'}</span>
        {condicion && <span className={`ch-badge ${esNuevo ? 'nuevo' : ''}`}>{condicion}</span>}
        {esNuevo && <span className="ch-badge nuevo">PRODUCTO NUEVO</span>}
        {isMaquilable && <span className="ch-badge maquila-badge" title={`Familia: ${familyName}`}>🏭 Maquila</span>}
        <span className="ch-item"><b>Formato</b> {product.formato || '—'}</span>
        <span className="ch-item"><b>U/E</b> {ueDisplay}</span>
        <span className="expand-chevron">{expanded ? '▾' : '▸'}</span>
      </div>

      {/* ── CALENDARIO 12 MESES ── */}
      <div className="cal-wrap">
        <div className="cal-grid">
          <div className="cal-label-col">
            <span className="lbl-so">Sell Out</span>
            <span className="lbl-si">Sell In</span>
          </div>
          {calendario.map((m, i) => (
            <div className="cal-col" key={i}>
              <div className={`cal-mes ${m.es_real ? 'real' : ''}`}>{m.label}</div>
              <div className={`cal-so ${m.sell_out === 0 ? 'zero' : ''}`}>{fmt(m.sell_out)}</div>
              <div className={`cal-si ${m.sell_in === 0 ? 'zero' : ''}`}>{fmt(m.sell_in)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── MÉTRICAS (siempre visibles) ── */}
      <div className="metrics-row">
        <div className="metric-box">
          <div className="mb-lbl">📦 Stock Físico (Femaco)</div>
          <div className="mb-val">{fmt(stockFemaco)} <small>unidades</small></div>
          <div className="mb-sub">{cajas} cajas · U/E {ueDisplay}</div>
        </div>

        {stockHC != null && stockHC > 0 ? (
          <div className="metric-box">
            <div className="mb-lbl">🏪 Stock HC (Tiendas)</div>
            <div className="mb-val">{fmt(stockHC)} <small>unidades</small></div>
            <div className="mb-sub">{hcCajas != null ? `${hcCajas} cajas` : 'Desde Matrix'}</div>
          </div>
        ) : (
          <div className="metric-box pending">
            <div className="mb-lbl">🏪 Stock HC (Tiendas)</div>
            <div className="mb-val" style={{ fontSize: '0.78rem', color: '#888', fontStyle: 'italic' }}>⏳ Pendiente</div>
          </div>
        )}

        <div className="metric-box">
          <div className="mb-lbl">🚢 Tránsito Total</div>
          <div className="mb-val">{fmt(cantTr)} <small>unidades</small></div>
          <div className="mb-sub">ETA: {eta}</div>
        </div>

        <div className="alert-box" style={{ background: colorInfo.bg }}>
          <div className="mb-lbl">Duración &amp; Estado</div>
          {alerta === 'MORADO' ? (
            <>
              {/* Gran número: Duración física */}
              <div className="mb-val">{durFisicaStr} <small style={{fontSize:'0.7rem', fontWeight:400}}>físico</small></div>
              <div className="mb-nivel">
                {/* Texto abajo: Duración total c/tránsito */}
                <div style={{ fontSize: '0.85rem', fontWeight: 'bold', marginBottom: 2 }}>{durStr} <small>total c/tránsito</small></div>
                <span className="semaforo-dot">{colorInfo.label}</span> {alerta}
              </div>
            </>
          ) : (
            <>
              <div className="mb-val">{durStr}</div>
              <div className="mb-nivel">
                <span className="semaforo-dot">{colorInfo.label}</span> {alerta}
              </div>
            </>
          )}
        </div>

        <div className="metric-box sug">
          <div className="mb-lbl">🛒 Sugerencia Compra</div>
          <div className="mb-val green">{fmt(sug)} <small>unidades</small></div>
          <div className="mb-sub">
            {usesFamilyStockForPurchase
              ? `Calculada con ${fmt(stockUsedForPurchase)} uds de la familia`
              : (ump > 0 ? `${Math.ceil(sug / ump)} cajas` : '')}
          </div>
        </div>
      </div>

      {/* ── SEMANAS + OBJETIVO ── */}
      <div className="sem-row">
        <div className="sem-row-label">Últimas<br />4 Sem.</div>
        {[
          { l: 'Sem 1', v: sem1 },
          { l: 'Sem 2', v: sem2 },
          { l: 'Sem 3', v: sem3 },
          { l: 'Sem 4', v: sem4 },
          { l: 'Total 4S', v: total4 },
        ].map((s, i) => (
          <div className="sem-box" key={i}>
            <div className="sb-lbl">{s.l}</div>
            <div className="sb-val">{fmt(s.v)}</div>
          </div>
        ))}
        <div className="ritmo-box">
          <div className="sb-lbl">Objetivo</div>
          <div className="sb-val">{fmt(objetivo)}</div>
        </div>
      </div>

      {/* ── OBSERVACIÓN (siempre visible si existe) ── */}
      {obs && obs.observacion && (
        <div style={{ padding: '6px 14px', background: '#FFFDE7', borderTop: '1px solid var(--border)', fontSize: '0.8rem', color: '#5a4000' }}>
          📝 {obs.observacion}
          {obs.usuario && <small style={{ marginLeft: 8, color: '#999' }}>{obs.usuario} · {obs.fecha}</small>}
        </div>
      )}

      {/* ── SECCIÓN EXPANDIDA ── */}
      {expanded && (
        <div className="expanded-section">

          {/* FAMILIA ACTIVA Y STOCK USADO PARA LA COMPRA */}
          {isFamilyMember && (
            <div className="exp-block family-stock-summary">
              <div className="family-stock-header">
                <span className="family-stock-title">🏭 Familia activa: {familyName}</span>
                <span className="family-stock-total">
                  Stock total familia: <strong>{fmt(familyStock)} unidades</strong>
                </span>
              </div>
              <div className="family-stock-calculation-note">
                {usesFamilyStockForPurchase ? (
                  <>
                    Para calcular la sugerencia, el stock individual de <b>{fmt(stockFemaco)} uds</b>
                    {' '}se reemplaza por el total familiar de <b>{fmt(stockUsedForPurchase)} uds</b>
                    {' '}({fmt(familyAdditionalStock)} uds aportadas por los otros integrantes).
                  </>
                ) : (
                  <>La familia está identificada, pero falta recalcular la planificación para aplicar su stock a la sugerencia.</>
                )}
              </div>
              <div className="family-stock-members">
                {familySkus.map(member => (
                  <div
                    className={`family-stock-member ${String(member.codigo_femaco) === String(product.codigo_femaco) ? 'current' : ''}`}
                    key={member.codigo_femaco || member.sku}
                    title={member.nombre_producto || member.sku}
                  >
                    <span className="family-member-id">
                      {String(member.codigo_femaco) === String(product.codigo_femaco) && <span aria-label="Producto actual">● </span>}
                      CÓD. {member.codigo_femaco || '—'}
                    </span>
                    <span className="family-member-stock">{fmt(member.stock_act)} uds</span>
                    <span className="family-member-name">
                      SKU {member.sku || '—'} · {member.nombre_producto || 'Sin nombre'}
                    </span>
                    {member.no_transformable && <span className="family-member-locked">No transformable</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* GRÁFICO 12 MESES */}
          {chartData.length > 0 && (
            <div className="exp-block">
              <div className="exp-title">📊 Sell-Out vs Sell-In — Últimos 12 Meses</div>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 5, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#EBEBEB" />
                    <XAxis dataKey="name" tick={{ fontSize: 9 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                    
                    <Area type="monotone" dataKey="Sell Out" fill="#8DC63F" stroke="#8DC63F" fillOpacity={0.3} />
                    <Line type="monotone" dataKey="Sell In" stroke="#3A86C8" strokeWidth={2} dot={{ r: 3 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* DESGLOSE TRÁNSITO */}
          <div className="exp-block">
            <div className="exp-title">🚢 Desglose de OCs en Tránsito</div>
            {trLoad && <div className="exp-loading">Cargando OCs…</div>}
            {!trLoad && transito && transito.length === 0 && (
              <div className="exp-empty">Sin OCs registradas en tránsito activo</div>
            )}
            {!trLoad && transito && transito.length > 0 && (
              <table className="tr-table">
                <thead>
                  <tr>
                    <th>OC</th><th>Cant.</th><th>ETA orig.</th>
                    <th>Disponible</th><th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {transito.map((oc, i) => {
                    const st = ESTADO_STYLE[oc.estado] || ESTADO_STYLE.EN_TRANSITO;
                    return (
                      <tr key={i}>
                        <td><b>{oc.oc}</b></td>
                        <td>{fmt(oc.cantidad)}</td>
                        <td>{fmtDate(oc.eta)}</td>
                        <td>{fmtDate(oc.disponible)}</td>
                        <td>
                          <span className="estado-badge" style={{ background: st.bg, color: st.color }}>
                            {st.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* DESGLOSE SUGERENCIA (Modelo de Cobertura a 5 Meses) */}
          <div className="exp-block">
            <div className="exp-title">🛒 Por qué esta Sugerencia de Compra</div>
            <div className="sug-desglose">
              <div className="sd-row" style={{ color: '#666' }}><span>1. Ritmo Venta Pasado (últimas 4 sem)</span><span>{fmt(product.sug_ritmo_pasado ?? 0)} uds/mes</span></div>
              <div className="sd-row" style={{ color: '#666' }}><span>2. Ritmo Venta Futuro (próx 4 meses)</span><span>{fmt(product.sug_ritmo_futuro ?? 0)} uds/mes</span></div>
              <div className="sd-row" style={{ color: '#000' }}><span><b>3. Ritmo Consolidado (Máximo)</b></span><span><b>{fmt(product.sug_ritmo_mensual ?? 0)} uds/mes</b></span></div>
              
              <div className="sd-row" style={{ color: '#3A86C8', borderTop: '1px solid #eee', paddingTop: 6, marginTop: 6 }}>
                <span><b>4. Target Stock a {product.sug_target_meses ?? 5} Meses</b> <small>(Ritmo Consolidado × {product.sug_target_meses ?? 5})</small></span>
                <span><b>{fmt(product.sug_target_uds ?? 0)} unidades</b></span>
              </div>
              
              <div className="sd-row" style={{ color: cantTr > 0 ? '#3A86C8' : 'inherit', marginTop: 6 }}>
                <span>5. Tránsito activo descontado</span><span>- {fmt(product.sug_cantidad_transito ?? cantTr)} unidades</span>
              </div>
              <div className="sd-row" style={{ color: '#E65100' }}>
                <span>
                  6. {usesFamilyStockForPurchase ? 'Stock total de familia descontado' : 'Stock actual físico descontado'}
                  {usesFamilyStockForPurchase && <small> (stock individual {fmt(stockFemaco)} + otros {fmt(familyAdditionalStock)})</small>}
                </span>
                <span>- {fmt(stockUsedForPurchase)} unidades</span>
              </div>
              
              <div className="sd-row result" style={{ marginTop: 8 }}>
                <span><b>COMPRA SUGERIDA</b></span>
                <span><b>{fmt(sug)}</b> unidades {ump > 0 && <small>= {Math.ceil(sug / ump)} cajas × {ump} unidades</small>}</span>
              </div>
            </div>
          </div>

          {/* OBSERVACIONES */}
          <div className="exp-block">
            <div className="exp-title">📝 Observaciones</div>
            {canEditObs ? (
              <div className="obs-edit">
                <textarea
                  className="obs-textarea"
                  value={obsEdit}
                  onChange={e => setObsEdit(e.target.value)}
                  placeholder="Escribe una observación sobre este SKU…"
                  rows={3}
                />
                <div className="obs-actions">
                  {obs && obs.usuario && (
                    <span className="obs-meta">Última edición: {obs.usuario} · {obs.fecha || '—'}</span>
                  )}
                  <button
                    className={`obs-save-btn ${obsSaved ? 'saved' : ''}`}
                    onClick={handleSaveObs}
                    disabled={obsSaving}
                  >
                    {obsSaving ? 'Guardando…' : obsSaved ? '✓ Guardado' : '💾 Guardar'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="obs-readonly">
                {obs && obs.observacion
                  ? <p>{obs.observacion}</p>
                  : <span className="exp-empty">Sin observaciones</span>
                }
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
