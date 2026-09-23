// src/components/SkuCard.jsx — v2.2
// Todo el data visible por defecto, expand = gráfico + desglose tránsito + por qué sugerencia
import { useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine
} from 'recharts';
import { fetchTransito, fetchObservacion, saveObservacion, fetchHoltWintersForecast, getPermisos } from '../api';

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
        {data.mom_growth_pct != null && (
          <div style={{ marginTop: 4, fontWeight: 'bold', color: data.mom_growth_pct > 0 ? '#1d6b3e' : data.mom_growth_pct < 0 ? '#b35f1a' : '#666' }}>
            Var. mes ant: {data.mom_growth_pct > 0 ? '▲' : data.mom_growth_pct < 0 ? '▼' : ''} {data.mom_growth_pct}%
          </div>
        )}
        {data.yoy_growth_pct != null && (
          <div style={{ marginTop: 2, fontWeight: 'bold', color: data.yoy_growth_pct > 0 ? '#1d6b3e' : data.yoy_growth_pct < 0 ? '#b35f1a' : '#666' }}>
            Var. año ant: {data.yoy_growth_pct > 0 ? '▲' : data.yoy_growth_pct < 0 ? '▼' : ''} {data.yoy_growth_pct}%
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

const MESES_ABREV = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
function fmtMonthLabel(monthStr) {
  if (!monthStr || typeof monthStr !== 'string') return monthStr || '';
  const parts = monthStr.split('-');
  if (parts.length === 2) {
    const yr = parts[0];
    const m = parseInt(parts[1], 10);
    if (m >= 1 && m <= 12) {
      return `${MESES_ABREV[m]} ${yr}`;
    }
  }
  return monthStr;
}


export default function SkuCard({ product, showDiscontinued = false }) {
  const [expanded,  setExpanded]  = useState(false);
  const [transito,  setTransito]  = useState(null);
  const [trLoad,    setTrLoad]    = useState(false);
  const [obs,       setObs]       = useState(null);
  const [obsEdit,   setObsEdit]   = useState('');
  const [obsSaving, setObsSaving] = useState(false);
  const [obsSaved,  setObsSaved]  = useState(false);
  const [hwData,    setHwData]    = useState(null);
  const [hwLoad,    setHwLoad]    = useState(false);
  const [showFullHistory, setShowFullHistory] = useState(false);

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
  const rawChartData = product.chart_24m || [];
  const firstDataIndex = rawChartData.findIndex(d => (d["Sell Out"] > 0 || d["Sell In"] > 0 || d["Sell Out Año Anterior"] > 0));
  const chartData = rawChartData.slice(firstDataIndex > -1 ? firstDataIndex : 0);
  
  const allFamilySkus = Array.isArray(product.familia_skus) ? product.familia_skus : [];
  const familySkus = showDiscontinued
    ? allFamilySkus
    : allFamilySkus.filter(member => member.descontinuado !== true);
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
      if (!hwData && !hwLoad && product.sku) {
        setHwLoad(true);
        try {
          const res = await fetchHoltWintersForecast(product.sku);
          setHwData(res);
        } catch {
          setHwData({ available: false, reason: 'error' });
        } finally {
          setHwLoad(false);
        }
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
            <span className="lbl-gr">Crecimiento</span>
          </div>
          {calendario.map((m, i) => {
            let growth = '-';
            let gClass = 'zero';
            if (m.growth_pct != null) {
              const diff = m.growth_pct;
              if (diff > 0) {
                growth = `↑ ${diff.toFixed(0)}%`;
                gClass = 'pos';
              } else if (diff < 0) {
                growth = `↓ ${Math.abs(diff).toFixed(0)}%`;
                gClass = 'neg';
              } else {
                growth = '0%';
              }
            }
            if (m.hist_val != null && m.hist_val > 0) {
               growth += ` (${fmt(m.hist_val)})`;
            }
            return (
            <div className="cal-col" key={i}>
              <div className={`cal-mes ${m.es_real ? 'real' : ''}`}>{m.label}</div>
              <div className={`cal-so ${m.sell_out === 0 ? 'zero' : ''}`}>{fmt(m.sell_out)}</div>
              <div className={`cal-si ${m.sell_in === 0 ? 'zero' : ''}`}>{fmt(m.sell_in)}</div>
              <div className={`cal-growth ${gClass}`}>{growth}</div>
            </div>
            );
          })}
        </div>
      </div>

      {/* ── MÉTRICAS (siempre visibles) ── */}
      <div className="metrics-row">
        <div className="metric-box">
          <div className="mb-lbl">📦 Stock Central</div>
          <div className="mb-val">{fmt(stockFemaco)} <small>unidades</small></div>
          <div className="mb-sub">{cajas} cajas · U/E {ueDisplay}</div>
        </div>

        {stockHC != null ? (
          <div className="metric-box">
            <div className="mb-lbl">🏪 Stock Tienda</div>
            <div className="mb-val">{fmt(stockHC)} <small>unidades</small></div>
            <div className="mb-sub">
              {hcCajas != null ? `${hcCajas} cajas` : 'Desde Matrix'}
              {product.alerta_sobrestock_tienda && <span style={{color: '#E65100', fontWeight: 'bold', marginLeft: '6px', fontSize: '0.75rem'}}>⚠️ Sobrestock en tienda: &gt; 2 meses</span>}
            </div>
            
            <div className="mb-lbl" style={{marginTop: '10px'}}>🌐 Stock Total Canal</div>
            <div className="mb-val" style={{fontSize: '1rem', color: '#3A86C8'}}>{fmt(stockFemaco + (stockHC || 0))} <small>unidades</small></div>
          </div>
        ) : (
          <div className="metric-box pending">
            <div className="mb-lbl">🏪 Stock Tienda</div>
            <div className="mb-val" style={{ fontSize: '0.78rem', color: '#888', fontStyle: 'italic' }}>⏳ Pendiente</div>
            
            <div className="mb-lbl" style={{marginTop: '10px'}}>🌐 Stock Total Canal</div>
            <div className="mb-val" style={{fontSize: '1rem', color: '#3A86C8'}}>{fmt(stockFemaco)} <small>unidades</small></div>
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
              <div className="mb-val">{durStr} <small style={{fontSize: '0.7rem', fontWeight: 400}}>ritmo 4 semanas</small></div>
              {product.duracion_4_meses != null && (
                <div style={{ fontSize: '0.85rem', marginTop: 2, color: '#333' }}>
                  {Number(product.duracion_4_meses).toFixed(1)} meses <small style={{fontSize: '0.7rem', fontWeight: 400}}>ritmo 4 meses</small>
                </div>
              )}
              <div className="mb-nivel" style={{marginTop: 4}}>
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
          {product.descuento_aplicado_por_decrecimiento && product.mom_sellout_pct != null && (
              <div style={{ fontSize: '0.75rem', color: '#E65100', marginTop: 4, fontWeight: 'bold' }}>
                ⚠️ Sugerencia reducida {Math.abs(product.mom_sellout_pct)}% por decrecimiento mensual
              </div>
          )}
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
                {familySkus.map(member => {
                  const ritmo = member.ritmo_mensual || 0;
                  const stockTotal = Number(member.stock_act || 0) + Number(member.cantidad_transito || 0);
                  const durMeses = ritmo > 0 ? stockTotal / ritmo : 999;
                  const durStr = durMeses >= 999 ? '∞' : `${durMeses.toFixed(1)} m`;

                  return (
                    <div
                      className={`family-stock-member ${String(member.codigo_femaco) === String(product.codigo_femaco) ? 'current' : ''}`}
                      key={member.codigo_femaco || member.sku}
                      title={member.nombre_producto || member.sku}
                    >
                      <span className="family-member-id">
                        {String(member.codigo_femaco) === String(product.codigo_femaco) && <span aria-label="Producto actual">● </span>}
                        CÓD. {member.codigo_femaco || '—'}
                      </span>
                      <span className="family-member-stock" style={{ minWidth: 200, textAlign: 'right' }}>
                        {fmt(member.stock_act)} uds | Vts: {fmt(ritmo)} | Dur: {durStr}
                      </span>
                      <span className="family-member-name">
                        SKU {member.sku || '—'} · {member.nombre_producto || 'Sin nombre'}
                      </span>
                      {member.no_transformable && <span className="family-member-locked">No transformable</span>}
                    </div>
                  );
                })}
                
                {/* Total Familia Bottom Center */}
                <div className="family-stock-member" style={{justifyContent: 'center', fontWeight: 'bold', borderTop: '2px solid #ccc', marginTop: '10px', paddingTop: '10px'}}>
                   <span className="family-member-stock" style={{ textAlign: 'center', width: '100%' }}>
                     {(() => {
                       const transformableSkus = familySkus.filter(m => !m.no_transformable);
                       const totalVts = transformableSkus.reduce((sum, m) => sum + Number(m.ritmo_mensual || 0), 0);
                       const duracion = totalVts > 0 ? (Number(familyStock) / totalVts).toFixed(1) + ' m' : '∞';
                       return `Total Familia: ${fmt(familyStock)} uds | Vts: ${fmt(totalVts)} | Dur: ${duracion}`;
                     })()}
                   </span>
                </div>
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
                    <Line type="monotone" dataKey="Sell Out Año Anterior" name="Referencia mismo período año anterior" stroke="#999" strokeWidth={1} strokeDasharray="3 3" dot={{ r: 2 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* GRÁFICO SEPARADO: PROYECCIÓN SELL OUT — HOLT-WINTERS */}
          <div className="exp-block">
            <div className="exp-title">📈 PROYECCIÓN SELL OUT — HOLT-WINTERS</div>
            {hwLoad && <div className="exp-loading">Calculando proyección Holt-Winters…</div>}
            {!hwLoad && hwData && !hwData.available && (
              <div className="exp-empty" style={{ fontStyle: 'italic', color: '#666', padding: '14px', textAlign: 'center', background: '#FDFDFD', borderRadius: 4, border: '1px dashed #DDD' }}>
                {hwData.reason === 'internal_gap_detected'
                  ? 'El historial contiene períodos sin información suficiente para generar la proyección.'
                  : hwData.reason === 'intermittent_demand'
                  ? 'La demanda de este producto es demasiado intermitente para aplicar este modelo.'
                  : 'No existe historial suficiente para generar una proyección confiable.'}
              </div>
            )}
            {!hwLoad && hwData && hwData.available && (() => {
              const histAll = hwData.history || [];
              // Limitar únicamente la visualización visual a los últimos 24 meses reales por defecto (sin recortar entrenamiento Holt-Winters)
              const visibleHistory = showFullHistory
                ? histAll
                : (histAll.length > 24 ? histAll.slice(histAll.length - 24) : histAll);
              const gaps = hwData.gap_estimates || [];
              const fc = hwData.forecast || [];
              const hwChartData = [];

              // 1. Sell Out Real (verde sólido)
              visibleHistory.forEach((item, idx) => {
                const isLastHist = idx === visibleHistory.length - 1;
                hwChartData.push({
                  name: fmtMonthLabel(item.month),
                  'Sell Out Real': item.value,
                  'Estimación Atraso': (isLastHist && gaps.length > 0) ? item.value : null,
                  'Proyección Futura': (isLastHist && gaps.length === 0) ? item.value : null
                });
              });

              // 2. Gap / Mes actual (gris punteado)
              gaps.forEach((item, idx) => {
                const isLastGap = idx === gaps.length - 1;
                hwChartData.push({
                  name: fmtMonthLabel(item.month),
                  'Sell Out Real': null,
                  'Estimación Atraso': item.value,
                  'Proyección Futura': isLastGap ? item.value : null
                });
              });

              // 3. Forecast Futuro 4 Meses (naranja punteado)
              fc.forEach((item) => {
                hwChartData.push({
                  name: fmtMonthLabel(item.month),
                  'Sell Out Real': null,
                  'Estimación Atraso': null,
                  'Proyección Futura': item.value
                });
              });

              const renderConfidenceBadge = (conf) => {
                if (conf === 'high' || conf === 'Alta') {
                  return <strong style={{ color: '#1d6b3e' }}>Alta</strong>;
                }
                if (conf === 'medium' || conf === 'Media') {
                  return <strong style={{ color: '#b35f1a' }}>Media</strong>;
                }
                return (
                  <strong style={{
                    color: '#c0392b',
                    background: '#FDE8E8',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    border: '1px solid #F8B4B4',
                    fontWeight: 'bold',
                    display: 'inline-block',
                    marginLeft: '2px'
                  }}>
                    Baja
                  </strong>
                );
              };

              return (
                <>
                  <div style={{ height: 210 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={hwChartData} margin={{ top: 5, right: 16, bottom: 0, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#EBEBEB" />
                        <XAxis dataKey="name" tick={{ fontSize: 9 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                        
                        <Line type="monotone" dataKey="Sell Out Real" stroke="#8DC63F" strokeWidth={2} dot={{ r: 3 }} />
                        {gaps.length > 0 && (
                          <Line type="monotone" dataKey="Estimación Atraso" stroke="#95A5A6" strokeWidth={1.5} strokeDasharray="3 3" dot={{ r: 2 }} />
                        )}
                        <Line type="monotone" dataKey="Proyección Futura" stroke="#E67E22" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 4 }} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                  <div style={{ fontSize: 11, color: '#444', marginTop: 8, textAlign: 'center', background: '#FAFAFA', padding: '6px 10px', borderRadius: 4, border: '1px solid #EAEAEA' }}>
                    {hwData.data_status === 'lagging' && (
                      <div style={{ color: '#b35f1a', fontWeight: 'bold', marginBottom: 4 }}>
                        ⚠️ Datos desactualizados: último mes cerrado observado {fmtMonthLabel(hwData.last_observed_month)}
                      </div>
                    )}
                    {hwData.method === 'holt_winters' ? (
                      <span>
                        <strong>Modelo:</strong> Holt-Winters
                        {' · '}
                        <strong>Histórico:</strong> {hwData.historical_months} meses
                        {histAll.length > 24 && (
                          <button
                            onClick={() => setShowFullHistory(!showFullHistory)}
                            style={{ background: 'none', border: 'none', color: '#1a6aa8', fontSize: 10, cursor: 'pointer', textDecoration: 'underline', marginLeft: 4, marginRight: 4 }}
                          >
                            ({showFullHistory ? 'ver 24m' : `ver ${histAll.length}m`})
                          </button>
                        )}
                        {hwData.validated ? (
                          <span> · <strong>WAPE histórico:</strong> {hwData.wape}%</span>
                        ) : (
                          <span> · <strong>WAPE:</strong> No validado</span>
                        )}
                        {' · '}
                        <strong>Confianza:</strong> {renderConfidenceBadge(hwData.confidence)}
                      </span>
                    ) : (
                      <span>
                        <strong>Modelo:</strong> Estacionalidad heredada
                        {' · '}
                        <strong>Referencia:</strong> {hwData.reference_level} — <em>{hwData.reference_value}</em>
                        {' · '}
                        <strong>SKUs de referencia:</strong> {hwData.reference_skus}
                        {' · '}
                        <strong>Confianza:</strong> {renderConfidenceBadge(hwData.confidence)}
                      </span>
                    )}
                  </div>
                </>
              );
            })()}
          </div>

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
