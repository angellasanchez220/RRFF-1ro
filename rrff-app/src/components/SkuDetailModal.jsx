import React from 'react';

export default function SkuDetailModal({ skuData, onClose }) {
  if (!skuData) return null;

  const {
    sku,
    nombre_producto,
    stock_act,
    cantidad_transito,
    
    // Legacy
    sugerencia_compra_legacy,
    sugerencia_compra_inmediata_uds,
    explicacion_compra_legacy,
    explicacion_compra,
    duracion_fisica_solo,
    meses_cobertura_objetivo,
    ritmo_semanal_uds,
    total_4_sem_verificado,
    
    // Dinamico
    clasificacion_comportamiento,
    metodo_forecast,
    confianza_forecast,
    forecast_mes_1,
    forecast_mes_2,
    forecast_mes_3,
    forecast_mes_4,
    forecast_mes_5,
    forecast_mes_6,
    riesgo_stock,
    stock_seguridad_final,
    stock_seguridad_ajustado,
    fecha_estimada_llegada_oc,
    mes_llegada_oc,
    lead_time_dias,
    stock_fin_mes_1,
    stock_fin_mes_2,
    stock_fin_mes_3,
    stock_fin_mes_4,
    stock_fin_mes_5,
    stock_fin_mes_6,
    transito_confirmado,
    transito_estimado,
    transito_vencido,
    cobertura_proyectada_meses,
    estado_alerta,
    quiebre_antes_de_llegada,
    primer_mes_quiebre,
    sugerencia_compra_dinamica,
    accion_recomendada_dinamica,
    motivos_revision_manual_dinamica,
    explicacion_compra_dinamica,
    
    // Comparacion
    diferencia_compra_dinamica_legacy,
    diferencia_porcentual_dinamica_legacy,
    recomendacion_coincide
  } = skuData;

  const isDynamicAvailable = clasificacion_comportamiento != null;
  const sugLegacy = sugerencia_compra_legacy ?? sugerencia_compra_inmediata_uds ?? 0;
  const explLegacy = explicacion_compra_legacy ?? explicacion_compra ?? 'Sin explicacion';

  const purchaseFinal = sugerencia_compra_dinamica || 0;
  // Si no viene mes_llegada_oc, usamos 5 por default (Lead time)
  const mesLlegada = mes_llegada_oc || 5;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
      backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
    }}>
      <div style={{
        background: '#fff', borderRadius: '12px', width: '100%', maxWidth: '1100px', 
        maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 10px 25px rgba(0,0,0,0.2)'
      }}>
        {/* Header */}
        <div style={{ padding: '20px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', background: '#f8f9fa' }}>
          <div>
            <h2 style={{ margin: '0 0 5px 0', fontSize: '1.4rem' }}>{sku}</h2>
            <div style={{ color: '#555', fontSize: '0.95rem' }}>{nombre_producto}</div>
            <div style={{ display: 'flex', gap: '15px', marginTop: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ background: '#e3f2fd', padding: '4px 10px', borderRadius: '4px', fontSize: '0.85rem', fontWeight: 'bold' }}>
                Stock Actual: {stock_act || 0}
              </span>
              <div style={{ display: 'flex', gap: '5px' }}>
                <span style={{ background: '#f3e5f5', padding: '4px 10px', borderRadius: '4px', fontSize: '0.85rem', fontWeight: 'bold' }}>
                  Tránsito Total: {cantidad_transito || 0}
                </span>
                {(transito_confirmado > 0 || transito_estimado > 0 || transito_vencido > 0) && (
                  <div style={{ display: 'flex', gap: '5px', fontSize: '0.75rem', alignItems: 'center' }}>
                    {transito_confirmado > 0 && <span style={{ background: '#e8f5e9', color: '#2e7d32', padding: '2px 6px', borderRadius: '4px', border: '1px solid #c8e6c9' }}>Conf: {transito_confirmado}</span>}
                    {transito_estimado > 0 && <span style={{ background: '#e3f2fd', color: '#1565c0', padding: '2px 6px', borderRadius: '4px', border: '1px solid #bbdefb' }}>Est: {transito_estimado}</span>}
                    {transito_vencido > 0 && <span style={{ background: '#ffebee', color: '#c62828', padding: '2px 6px', borderRadius: '4px', border: '1px solid #ffcdd2' }}>Venc: {transito_vencido}</span>}
                  </div>
                )}
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#888'
          }}>✖</button>
        </div>

        {/* Warning Banner */}
        <div style={{ padding: '10px 20px', background: '#fff3cd', color: '#856404', fontSize: '0.85rem', borderBottom: '1px solid #ffeeba', textAlign: 'center' }}>
          <b>⚠️ Planificador Dinámico en modo experimental.</b> La recomendación operativa oficial sigue siendo la calculada por el modelo Legacy.
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', padding: '20px', gap: '20px' }}>
          
          {/* Panel Izquierdo: Legacy */}
          <div style={{ flex: '1 1 400px', background: '#fafafa', border: '1px solid #ddd', borderRadius: '8px', padding: '15px' }}>
            <h3 style={{ margin: '0 0 15px 0', color: '#2c3e50', fontSize: '1.1rem', borderBottom: '2px solid #ccc', paddingBottom: '5px' }}>
              Recomendación Oficial (Legacy)
            </h3>
            <table style={{ width: '100%', fontSize: '0.9rem', borderCollapse: 'collapse' }}>
              <tbody>
                <tr><td style={{ padding: '6px 0', color: '#666' }}>Ritmo Semanal Verificado</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{Number(skuData.ritmo_semanal_verificado||0).toFixed(1)} uds</td></tr>
                <tr><td style={{ padding: '6px 0', color: '#666' }}>Venta {skuData.cantidad_semanas_validas || 4} Semanas Válidas</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{Number(total_4_sem_verificado||0).toFixed(0)} uds</td></tr>
                <tr><td style={{ padding: '6px 0', color: '#666' }}>Ritmo Mensual Equivalente</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{Number(skuData.ritmo_mensual_verificado||0).toFixed(0)} uds</td></tr>
                <tr><td style={{ padding: '6px 0', color: '#666' }}>Cobertura Actual</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{Number(duracion_fisica_solo||0).toFixed(1)} meses</td></tr>
                <tr><td style={{ padding: '6px 0', color: '#666' }}>Cobertura Target</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{Number(meses_cobertura_objetivo||5)} meses</td></tr>
              </tbody>
            </table>
            <div style={{ marginTop: '20px', background: '#e8f5e9', padding: '15px', borderRadius: '6px', border: '1px solid #c8e6c9', textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', color: '#2e7d32', fontWeight: 'bold' }}>COMPRA SUGERIDA OFICIAL</div>
              <div style={{ fontSize: '2rem', color: '#1b5e20', fontWeight: '900', margin: '5px 0' }}>{Number(sugLegacy).toLocaleString('es-CL')}</div>
            </div>
            <div style={{ marginTop: '15px', fontSize: '0.85rem', color: '#444', lineHeight: '1.4' }}>
              <b>Explicación:</b> {explLegacy}
            </div>
          </div>

          {/* Panel Derecho: Dinamico */}
          <div style={{ flex: '1 1 500px', background: '#fff', border: '1px solid #2196f3', borderRadius: '8px', padding: '15px', boxShadow: '0 4px 6px rgba(33,150,243,0.1)' }}>
            <h3 style={{ margin: '0 0 15px 0', color: '#1976d2', fontSize: '1.1rem', borderBottom: '2px solid #90caf9', paddingBottom: '5px' }}>
              Análisis Dinámico (Experimental)
            </h3>
            
            {!isDynamicAvailable ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: '#777' }}>
                <div style={{ fontSize: '2rem', marginBottom: '10px' }}>📉</div>
                Historial o datos insuficientes para correr el modelo dinámico estadístico.
              </div>
            ) : (
              <>
                <table style={{ width: '100%', fontSize: '0.9rem', borderCollapse: 'collapse', marginBottom: '15px' }}>
                  <tbody>
                    <tr><td style={{ padding: '6px 0', color: '#666' }}>Clasificación</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{clasificacion_comportamiento}</td></tr>
                    <tr><td style={{ padding: '6px 0', color: '#666' }}>Riesgo de Stock</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{riesgo_stock}</td></tr>
                    <tr><td style={{ padding: '6px 0', color: '#666' }}>Estado Alerta</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{estado_alerta}</td></tr>
                    <tr><td style={{ padding: '6px 0', color: '#666' }}>Cobertura Proyectada</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{cobertura_proyectada_meses != null ? `${Number(cobertura_proyectada_meses).toFixed(1)} meses` : 'N/D'}</td></tr>
                    <tr><td style={{ padding: '6px 0', color: '#666' }}>Stock Seguridad</td><td style={{ textAlign: 'right', fontWeight: 'bold', color: '#e65100' }}>{stock_seguridad_final} uds</td></tr>
                    <tr><td style={{ padding: '6px 0', color: '#666' }}>Fecha Estimada OC</td><td style={{ textAlign: 'right', fontWeight: 'bold' }}>{fecha_estimada_llegada_oc || 'N/D'}</td></tr>
                  </tbody>
                </table>
                
                {quiebre_antes_de_llegada && (
                  <div style={{ padding: '10px', background: '#ffebee', color: '#c62828', borderRadius: '4px', fontSize: '0.8rem', border: '1px solid #ffcdd2', marginBottom: '15px' }}>
                    <b>⚠️ Alerta:</b> Una nueva compra con lead time normal de 5 meses no alcanzaría a llegar antes del quiebre proyectado (Mes {primer_mes_quiebre || '?'}). Se requiere revisar tránsito, traslado interno o acción logística urgente.
                  </div>
                )}
                
                <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse', marginBottom: '15px', textAlign: 'center' }}>
                  <thead>
                    <tr style={{ background: '#f5f5f5' }}>
                      <th style={{ padding: '4px', border: '1px solid #ddd' }}>Mes</th>
                      <th style={{ padding: '4px', border: '1px solid #ddd' }}>Forecast</th>
                      <th style={{ padding: '4px', border: '1px solid #ddd', color: '#d32f2f' }}>Stock sin OC</th>
                      <th style={{ padding: '4px', border: '1px solid #ddd', color: '#1976d2' }}>Stock con OC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { f: forecast_mes_1, s: stock_fin_mes_1 },
                      { f: forecast_mes_2, s: stock_fin_mes_2 },
                      { f: forecast_mes_3, s: stock_fin_mes_3 },
                      { f: forecast_mes_4, s: stock_fin_mes_4 },
                      { f: forecast_mes_5, s: stock_fin_mes_5 },
                      { f: forecast_mes_6, s: stock_fin_mes_6 },
                    ].map((m, i) => {
                      const simStock = m.s != null ? ((i + 1) >= mesLlegada ? m.s + purchaseFinal : m.s) : null;
                      return (
                        <tr key={i}>
                          <td style={{ padding: '4px', border: '1px solid #ddd', fontWeight: 'bold' }}>Mes {i + 1}</td>
                          <td style={{ padding: '4px', border: '1px solid #ddd' }}>{m.f != null ? Number(m.f).toFixed(0) : '—'}</td>
                          <td style={{ padding: '4px', border: '1px solid #ddd', fontWeight: 'bold', color: m.s < 0 ? '#d32f2f' : 'inherit' }}>{m.s != null ? Number(m.s).toFixed(0) : '—'}</td>
                          <td style={{ padding: '4px', border: '1px solid #ddd', fontWeight: 'bold', color: simStock < 0 ? '#d32f2f' : '#1976d2', background: (i + 1) >= mesLlegada ? '#e3f2fd' : 'transparent' }}>
                            {simStock != null ? Number(simStock).toFixed(0) : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                <div style={{ background: '#e3f2fd', padding: '15px', borderRadius: '6px', border: '1px solid #90caf9', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.85rem', color: '#1565c0', fontWeight: 'bold' }}>COMPRA SUGERIDA DINÁMICA</div>
                  <div style={{ fontSize: '2rem', color: '#0d47a1', fontWeight: '900', margin: '5px 0' }}>
                    {sugerencia_compra_dinamica != null ? Number(sugerencia_compra_dinamica).toLocaleString('es-CL') : 'N/D'}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#1976d2', fontWeight: 'bold', textTransform: 'uppercase' }}>
                    {accion_recomendada_dinamica}
                  </div>
                </div>
                
                <div style={{ marginTop: '15px', fontSize: '0.85rem', color: '#444', lineHeight: '1.4' }}>
                  <b>Motivo:</b> {explicacion_compra_dinamica || 'Sin detalle dinámico.'}
                </div>
                {motivos_revision_manual_dinamica && (
                  <div style={{ marginTop: '10px', fontSize: '0.8rem', color: '#c62828', background: '#ffebee', padding: '8px', borderRadius: '4px' }}>
                    ⚠️ {motivos_revision_manual_dinamica}
                  </div>
                )}
              </>
            )}
          </div>

        </div>

        {/* Footer Comparativo */}
        {isDynamicAvailable && (
          <div style={{ padding: '20px', borderTop: '1px solid #eee', background: '#f1f8e9' }}>
            <h4 style={{ margin: '0 0 10px 0', color: '#33691e', fontSize: '1rem' }}>Comparativa Directa</h4>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: '0.9rem', fontWeight: 'bold' }}>
                Veredicto: <span style={{ color: '#2e7d32', background: '#c8e6c9', padding: '4px 8px', borderRadius: '12px' }}>{recomendacion_coincide}</span>
              </div>
              <div style={{ display: 'flex', gap: '20px' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.75rem', color: '#555' }}>Diferencia (Uds)</div>
                  <div style={{ fontWeight: 'bold', color: diferencia_compra_dinamica_legacy > 0 ? '#d32f2f' : '#1976d2' }}>
                    {diferencia_compra_dinamica_legacy > 0 ? '+' : ''}{Number(diferencia_compra_dinamica_legacy || 0).toLocaleString('es-CL')}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.75rem', color: '#555' }}>Diferencia (%)</div>
                  <div style={{ fontWeight: 'bold', color: diferencia_porcentual_dinamica_legacy > 0.2 ? '#d32f2f' : '#f57f17' }}>
                    {Number((diferencia_porcentual_dinamica_legacy || 0) * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
