import React, { useState, useEffect } from 'react';
import { fetchSOP, fetchMrpMateriales, generarPoProveedor } from '../api';
import * as XLSX from 'xlsx';
import SkuDetailModal from '../components/SkuDetailModal';

// Helper: Obtener número de semana (ISO)
function getWeekNumber(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return { year: date.getUTCFullYear(), week: weekNo };
}

// Helper: Obtener rango de fechas de la semana (Lunes a Domingo)
function getWeekDateRange(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diffToMonday = date.getDate() - day + (day === 0 ? -6 : 1);
  const start = new Date(date.setDate(diffToMonday));
  const end = new Date(start.getTime());
  end.setDate(end.getDate() + 6);
  
  const getDayMonth = (dateObj) => {
    const months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    return `${dateObj.getDate()} de ${months[dateObj.getMonth()]}`;
  };
  
  return `semana del ${getDayMonth(start)} al ${getDayMonth(end)}`;
}

// Helper: Obtener nombre de mes formateado
const MESES_ES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
];

function getMonthLabel(d) {
  return `📅 ${MESES_ES[d.getMonth()]} ${d.getFullYear()}`;
}

export default function Compras() {
  const [activeTab, setActiveTab] = useState('SOP'); // 'SOP' | 'MRP'
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [filterAlert, setFilterAlert] = useState('ALL');
  const [filterTransit, setFilterTransit] = useState('ALL');
  const [filterComparacion, setFilterComparacion] = useState('ALL');
  const [filterCrecimiento, setFilterCrecimiento] = useState('ALL');
  const [filterCNY, setFilterCNY] = useState(false);
  const [filterExcluirMaquila, setFilterExcluirMaquila] = useState(true);
  const [groupBy, setGroupBy] = useState('MONTH'); // 'MONTH' | 'WEEK'
  const [selectedSku, setSelectedSku] = useState(null);

  // Estados para Emisión Directa de Orden de Compra (PO)
  const [selectedSkusForPo, setSelectedSkusForPo] = useState(new Set());
  const [showPoModal, setShowPoModal] = useState(false);
  const [poForm, setPoForm] = useState({
    numero_oc: '',
    proveedor: 'PROVEEDOR PRINCIPAL',
    fecha_pedido: new Date().toISOString().split('T')[0],
    fecha_eta: '',
    lead_time_dias: 120,
    observacion: '',
    items: []
  });
  const [submittingPo, setSubmittingPo] = useState(false);

  // Estados para MRP de Insumos de Maquila
  const [mrpData, setMrpData] = useState([]);
  const [mrpResumen, setMrpResumen] = useState(null);
  const [mrpLoading, setMrpLoading] = useState(false);
  const [mrpFilter, setMrpFilter] = useState('ALL'); // 'ALL' | 'CRITICO' | 'ALERTA'

  const LEAD_TIME_DAYS = 120; // Lead time operativo vigente

  const loadSopData = async () => {
    setLoading(true);
    try {
      const sopData = await fetchSOP();
      setData(Array.isArray(sopData?.data) ? sopData.data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadMrpData = async () => {
    setMrpLoading(true);
    try {
      const res = await fetchMrpMateriales();
      if (res && res.ok) {
        setMrpData(res.data || []);
        setMrpResumen(res.resumen || null);
      }
    } catch (err) {
      console.error("Error cargando MRP de insumos:", err);
    } finally {
      setMrpLoading(false);
    }
  };

  useEffect(() => {
    loadSopData();
    loadMrpData();
  }, []);

  // ── APLICAR FILTROS GLOBALES ──
  let filteredData = Array.isArray(data) ? data : [];
  if (filterAlert !== 'ALL') {
    filteredData = filteredData.filter(s => s.nivel_alerta === filterAlert);
  }
  if (filterTransit === 'WITH') {
    filteredData = filteredData.filter(s => (s.cantidad_transito || 0) > 0);
  } else if (filterTransit === 'WITHOUT') {
    filteredData = filteredData.filter(s => (s.cantidad_transito || 0) === 0);
  }
  if (filterComparacion !== 'ALL') {
    if (filterComparacion === '>20%') {
      filteredData = filteredData.filter(s => (s.diferencia_porcentual_dinamica_legacy || 0) > 0.2);
    } else if (filterComparacion === 'SOLO_LEGACY') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'Legacy compra / Dinamica no compra');
    } else if (filterComparacion === 'SOLO_DINAMICA') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'Dinamica compra / Legacy no compra');
    } else if (filterComparacion === 'AMBAS') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'Ambas recomiendan comprar' || s.recomendacion_coincide === 'Ambas compran con diferencia superior al 20%');
    } else if (filterComparacion === 'SIN_ANALISIS') {
      filteredData = filteredData.filter(s => s.recomendacion_coincide === 'No comparable por falta de datos' || !s.recomendacion_coincide);
    }
  }
  if (filterCrecimiento !== 'ALL') {
    filteredData = filteredData.filter(s => {
      const chart = s.chart_24m;
      if (!chart || chart.length < 2) return false;
      const last = chart[chart.length - 1];
      const prev = chart[chart.length - 2];
      const m1 = last.mom_growth_pct || 0;
      const m2 = prev.mom_growth_pct || 0;

      if (filterCrecimiento === 'NEG_2M') {
        return m1 < 0 && m2 < 0;
      }
      if (filterCrecimiento === 'HIGH_50_2M') {
        return m1 > 50 && m2 > 50;
      }
      if (filterCrecimiento === 'ANOMALIES') {
        return (m1 < 0 && m2 < 0) || (m1 > 50 && m2 > 50);
      }
      return true;
    });
  }

  // Filtro específico para Compra Masiva Año Nuevo Chino
  if (filterCNY) {
    filteredData = filteredData.filter(s => (s.compra_masiva_cny_uds || 0) > 0);
  }

  // Productos cubiertos por Maquila familiar
  const maquilaCubiertos = (Array.isArray(data) ? data : []).filter(s => 
    s.sug_usa_stock_familia && (Number(s.sug_stock_familia) >= Number(s.sug_target_uds) || (Number(s.sugerencia_compra_inmediata_uds) === 0))
  );

  // Regla: Los productos maquilables con stock familiar suficiente se gestionan en Maquila
  if (filterExcluirMaquila) {
    filteredData = filteredData.filter(s => {
      if (s.sug_usa_stock_familia) {
        const stockFam = Number(s.sug_stock_familia) || 0;
        const targetFam = Number(s.sug_target_uds) || 0;
        if (stockFam >= targetFam) return false;
      }
      return true;
    });
  }

  const totalCNYUds = (Array.isArray(data) ? data : []).reduce(
    (acc, curr) => acc + (Number(curr.compra_masiva_cny_uds) || 0), 0
  );

  // ── 1. PROCESAR SUGERENCIAS AUTOMÁTICAS ──
  const sugList = filteredData.filter(s => (s.sugerencia_compra_inmediata_uds || 0) > 0 || (s.sugerencia_compra_dinamica || 0) > 0 || (filterCNY && (s.compra_masiva_cny_uds || 0) > 0));
  
  // ── PROCESAR REVISIONES (EXCEPCIONES) ──
  const revisionList = filteredData.filter(s => s.requiere_revision);
  
  const groupedSug = {};
  sugList.forEach(s => {
    // duracion_fisica_solo son MESES. 1 mes ~= 30.4 días.
    const daysToStockout = (s.duracion_fisica_solo || 0) * 30.4;
    const stockoutDate = new Date();
    stockoutDate.setDate(stockoutDate.getDate() + daysToStockout);
    
    const idealDate = new Date(stockoutDate);
    idealDate.setDate(idealDate.getDate() - LEAD_TIME_DAYS);
    
    s.idealDateObj = idealDate;
    
    // Si la fecha ideal ya pasó, la agrupamos como "URGENTE / ATRASADA"
    const hoy = new Date();
    let groupKey = '';
    let groupLabel = '';
    
    if (idealDate < hoy) {
      groupKey = '0000-URGENTE';
      groupLabel = '🚨 PEDIDOS ATRASADOS (Emitir YA)';
    } else if (groupBy === 'MONTH') {
      const year = idealDate.getFullYear();
      const monthNum = (idealDate.getMonth() + 1).toString().padStart(2, '0');
      groupKey = `${year}-${monthNum}`;
      groupLabel = getMonthLabel(idealDate);
    } else {
      const wk = getWeekNumber(idealDate);
      groupKey = `${wk.year}-W${wk.week.toString().padStart(2, '0')}`;
      groupLabel = `📅 ${getWeekDateRange(idealDate)}`;
    }

    if (!groupedSug[groupKey]) groupedSug[groupKey] = { label: groupLabel, items: [] };
    groupedSug[groupKey].items.push(s);
  });

  // ── 2. PROCESAR OBSERVACIONES HUMANAS ──
  // Regex para atrapar "comprar", "compra" + [palabras opcionales] + NUMERO
  const regexNum = /compr(?:ar|a)\s*(?:unas?\s+|unos?\s+|cajas?\s+|uds?\s*)?(\d+)/i;
  const obsList = [];
  
  (Array.isArray(data) ? data : []).forEach(s => {
    if (s.observacion && s.observacion.toLowerCase().includes('compra')) {
      const match = s.observacion.match(regexNum);
      const extraido = match ? match[1] : '';
      obsList.push({ ...s, extraido });
    }
  });

  // Ordenar grupos de sugerencias cronológicamente
  const sortedGroupKeys = Object.keys(groupedSug).sort();

    const handleExportExcel = (onlyUrgentes = false) => {
    // Hoja 1: Sugerencias Automáticas
    const wsSugData = [];
    const keysToExport = onlyUrgentes ? sortedGroupKeys.filter(k => k === '0000-URGENTE') : sortedGroupKeys;
    
    keysToExport.forEach(key => {
      const group = groupedSug[key];

      // Ordenar para el Excel: Categoria -> Familia Maquila -> Fecha
      const sortedItems = [...group.items].sort((a, b) => {
        const catA = a.categoria || '';
        const catB = b.categoria || '';
        if (catA < catB) return -1;
        if (catA > catB) return 1;
        
        const fListA = a.familia_skus || a.familia_maquila || [];
        const fListB = b.familia_skus || b.familia_maquila || [];
        const famA = fListA.length > 1 ? fListA.map(c => c.sku).sort().join('-') : '';
        const famB = fListB.length > 1 ? fListB.map(c => c.sku).sort().join('-') : '';
        if (famA && !famB) return -1;
        if (!famA && famB) return 1;
        if (famA && famB && famA !== famB) return famA.localeCompare(famB);

        return a.idealDateObj - b.idealDateObj;
      });

      sortedItems.forEach(s => {
        const fList = s.familia_skus || s.familia_maquila || [];
        const isMaq = s.es_maquilable === true || fList.length > 1;
        const esMaquilable = isMaq ? 'Sí' : 'No';
        const stockFamilia = isMaq && s.stock_bruto_familia != null ? s.stock_bruto_familia : (s.stock_act || 0);
        const familiaStr = fList.length > 1
          ? fList.map(c => `${c.sku || c.codigo_femaco} (Stk: ${c.stock_act || 0})`).join(' | ')
          : '';
        
        wsSugData.push({
          'Grupo': group.label,
          'SKU': s.sku,
          'Código Femaco': s.codigo_femaco || '',
          'Nombre de Producto': s.nombre_producto,
          'Es Maquilable': esMaquilable,
          'Stock Total Familia Maquila': stockFamilia,
          'Hermanos (Componentes)': familiaStr,
          'Formato': s.formato_compra || 'LINEAL',
          'Ventas 4 sem': s.total_4_sem_verificado || 0,
          'Stock': s.stock_act || 0,
          'Demanda espera 4 meses': s.demanda_espera_4_meses || 0,
          'Maquila recibida': s.maquila_recibida_4_meses || 0,
          'Maquila destinada': s.maquila_destinada_4_meses || 0,
          'Stock estimado llegada': s.stock_estimado_llegada || 0,
          'Cobertura objetivo meses': s.meses_cobertura_objetivo || 5.4,
          'Stock objetivo': s.stock_objetivo || 0,
          'Sugerencia bruta': s.sugerencia_bruta || 0,
          'Total compra familia': s.familia_compra_total || 0,
          'Duración': Number(s.duracion_fisica_solo || 0).toFixed(1),
          'Sugerido (Uds)': s.sugerencia_compra_inmediata_uds || 0,
          'Compra Masiva Año Nuevo Chino (Feb-Abr)': s.compra_masiva_cny_uds || 0
        });
      });
    });
    
    // Hoja 2: Observaciones Manuales
    const wsObsData = obsList.map(s => {
      const fList = s.familia_skus || s.familia_maquila || [];
      const isMaq = s.es_maquilable === true || fList.length > 1;
      const esMaquilable = isMaq ? 'Sí' : 'No';
      const stockFamilia = isMaq && s.stock_bruto_familia != null ? s.stock_bruto_familia : (s.stock_act || 0);
      const familiaStr = fList.length > 1
          ? fList.map(c => `${c.sku || c.codigo_femaco} (Stock: ${c.stock_act || 0}, Venta/mes: ${c.ritmo_mensual || 0})`).join(', ')
          : '';
      return {
        'SKU': s.sku,
        'Código Femaco': s.codigo_femaco || '',
        'Nombre de Producto': s.nombre_producto,
        'Es Maquilable': esMaquilable,
        'Stock Total Familia Maquila': stockFamilia,
        'U/E': s.ump || '',
        'Ventas 4 sem': s.total_4_sem_verificado || 0,
        'Stock': s.stock_act || 0,
        'Duración': Number(s.duracion_fisica_solo || 0).toFixed(1),
        'Observación Original': s.observacion || '',
        'Detalle Hermanos': familiaStr,
        'Extracción (Uds)': s.extraido || '?'
      };
    });

    // Hoja 3: Resumen
    const wsResumenData = [];
    keysToExport.forEach(key => {
      const group = groupedSug[key];
      const sortedItems = [...group.items].sort((a, b) => {
        const fListA = a.familia_skus || a.familia_maquila || [];
        const fListB = b.familia_skus || b.familia_maquila || [];
        const famA = fListA.length > 1 ? 'A' : 'B';
        const famB = fListB.length > 1 ? 'A' : 'B';
        if (famA !== famB) return famA.localeCompare(famB);
        return a.sku.localeCompare(b.sku);
      });

      sortedItems.forEach(s => {
        const sugerido = s.sugerencia_compra_inmediata_uds || 0;
        const dinamico = s.sugerencia_compra_dinamica || 0;
        const diferencia = dinamico - sugerido;
        const fList = s.familia_skus || s.familia_maquila || [];
        const isMaq = s.es_maquilable === true || fList.length > 1;
        const esMaquilable = isMaq ? 'Sí' : 'No';
        const stockFamilia = isMaq && s.stock_bruto_familia != null ? s.stock_bruto_familia : (s.stock_act || 0);
        wsResumenData.push({
          'SKU': s.sku,
          'Código Femaco': s.codigo_femaco || '',
          'Grupo': group.label,
          'Es Maquilable': esMaquilable,
          'Stock Total Familia Maquila': stockFamilia,
          'Formato': s.formato_compra || 'LINEAL',
          'Ventas 4 sem': s.total_4_sem_verificado || 0,
          'Stock': s.stock_act || 0,
          'Demanda espera 4 meses': s.demanda_espera_4_meses || 0,
          'Maquila recibida': s.maquila_recibida_4_meses || 0,
          'Maquila destinada': s.maquila_destinada_4_meses || 0,
          'Stock estimado llegada': s.stock_estimado_llegada || 0,
          'Cobertura objetivo meses': s.meses_cobertura_objetivo || 5.4,
          'Stock objetivo': s.stock_objetivo || 0,
          'Sugerencia bruta': s.sugerencia_bruta || 0,
          'Total compra familia': s.familia_compra_total || 0,
          'Duración': Number(s.duracion_fisica_solo || 0).toFixed(1),
          'Sugerido (Uds)': sugerido,
          'Sugerido Dinámico (Uds)': dinamico,
          'Diferencia (Dinámico - Sugerido)': diferencia,
          'Compra Masiva Año Nuevo Chino (Feb-Abr)': s.compra_masiva_cny_uds || 0
        });
      });
    });

    const wb = XLSX.utils.book_new();
    
    if (wsSugData.length > 0) {
      const wsSug = XLSX.utils.json_to_sheet(wsSugData);
      XLSX.utils.book_append_sheet(wb, wsSug, 'Sugerencias Automáticas');
    }
    
    if (wsObsData.length > 0) {
      const wsObs = XLSX.utils.json_to_sheet(wsObsData);
      XLSX.utils.book_append_sheet(wb, wsObs, 'Notas Manuales');
    }

    if (wsResumenData.length > 0) {
      const wsResumen = XLSX.utils.json_to_sheet(wsResumenData);
      XLSX.utils.book_append_sheet(wb, wsResumen, 'Resumen');
    }

    if (wsSugData.length === 0 && wsObsData.length === 0) {
      alert("No hay datos para exportar.");
      return;
    }

    XLSX.writeFile(wb, 'Plan_de_Compras.xlsx');
  };

  const handleOpenPoModal = (customItems = null) => {
    let itemsToInclude = [];
    if (customItems && customItems.length > 0) {
      itemsToInclude = customItems;
    } else if (selectedSkusForPo.size > 0) {
      itemsToInclude = filteredData.filter(s => selectedSkusForPo.has(s.sku));
    } else {
      const urgentes = groupedSug['0000-URGENTE'] ? groupedSug['0000-URGENTE'].items : [];
      if (urgentes.length === 0 && sugList.length === 0) {
        alert("Selecciona al menos un SKU marcando su casilla para emitir una Orden de Compra.");
        return;
      }
      itemsToInclude = urgentes.length > 0 ? urgentes : sugList.slice(0, 10);
    }

    const defaultEta = new Date();
    defaultEta.setDate(defaultEta.getDate() + LEAD_TIME_DAYS);
    const etaStr = defaultEta.toISOString().split('T')[0];
    const poNum = `PO-${new Date().getFullYear()}${String(new Date().getMonth()+1).padStart(2,'0')}-${Math.floor(100 + Math.random() * 900)}`;

    const itemsFormatted = itemsToInclude.map(s => {
      const sug = Number(s.sugerencia_compra_inmediata_uds || s.compra_masiva_cny_uds || 100);
      const moq = Number(s.moq || 1);
      const roundedQty = moq > 1 ? Math.ceil(sug / moq) * moq : sug;
      return {
        sku: s.sku,
        codigo_femaco: s.codigo_femaco || s.sku,
        nombre_producto: s.nombre_producto || '',
        cantidad: roundedQty > 0 ? roundedQty : 100,
        moq: moq,
        costo_unitario: Number(s.costo_compra || 0),
        subtotal: (roundedQty > 0 ? roundedQty : 100) * Number(s.costo_compra || 0)
      };
    });

    setPoForm({
      numero_oc: poNum,
      proveedor: 'PROVEEDOR PRINCIPAL',
      fecha_pedido: new Date().toISOString().split('T')[0],
      fecha_eta: etaStr,
      lead_time_dias: LEAD_TIME_DAYS,
      observacion: 'Emisión automática generada desde Plan de Compras S&OP',
      items: itemsFormatted
    });
    setShowPoModal(true);
  };

  const handleUpdatePoItemQty = (index, newQty) => {
    const val = Math.max(0, parseInt(newQty) || 0);
    setPoForm(prev => {
      const newItems = [...prev.items];
      newItems[index] = {
        ...newItems[index],
        cantidad: val,
        subtotal: val * (newItems[index].costo_unitario || 0)
      };
      return { ...prev, items: newItems };
    });
  };

  const handleUpdatePoItemCosto = (index, newCosto) => {
    const val = Math.max(0, parseFloat(newCosto) || 0);
    setPoForm(prev => {
      const newItems = [...prev.items];
      newItems[index] = {
        ...newItems[index],
        costo_unitario: val,
        subtotal: (newItems[index].cantidad || 0) * val
      };
      return { ...prev, items: newItems };
    });
  };

  const handleRemovePoItem = (index) => {
    setPoForm(prev => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index)
    }));
  };

  const handleConfirmSubmitPo = async (e) => {
    e.preventDefault();
    if (!poForm.numero_oc.trim()) {
      alert("Por favor ingresa un código / número de Orden de Compra (PO).");
      return;
    }
    if (!poForm.items || poForm.items.length === 0) {
      alert("No hay ítems en la orden de compra.");
      return;
    }
    setSubmittingPo(true);
    try {
      const res = await generarPoProveedor(poForm);
      alert(`✅ ${res.mensaje || 'Orden de Compra emitida con éxito e inyectada a Tránsito.'}`);
      setShowPoModal(false);
      setSelectedSkusForPo(new Set());
      loadSopData();
    } catch (err) {
      alert("Error al emitir orden de compra: " + err.message);
    } finally {
      setSubmittingPo(false);
    }
  };

  const toggleSkuSelection = (sku) => {
    setSelectedSkusForPo(prev => {
      const next = new Set(prev);
      if (next.has(sku)) next.delete(sku);
      else next.add(sku);
      return next;
    });
  };

  const toggleGroupSelection = (groupItems) => {
    setSelectedSkusForPo(prev => {
      const next = new Set(prev);
      const allSelected = groupItems.every(it => next.has(it.sku));
      if (allSelected) {
        groupItems.forEach(it => next.delete(it.sku));
      } else {
        groupItems.forEach(it => next.add(it.sku));
      }
      return next;
    });
  };

  return (
    <div className="content-area">
      <main className="main-panel" style={{ maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>🛒 Plan de Compras</h1>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ fontSize: '0.85rem', color: '#666', background: '#fff', padding: '6px 12px', borderRadius: 20, border: '1px solid #ddd', display: 'flex', flexDirection: 'column' }}>
              <span>⏱ Lead time estándar de reposición: <b>120 días</b></span>
              <span style={{ fontSize: '0.75rem', fontStyle: 'italic', marginTop: '2px' }}>Valor operativo provisional. Las ETA reales tienen prioridad cuando están disponibles.</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button
                onClick={() => handleOpenPoModal()}
                style={{
                  padding: '8px 16px', background: '#2563eb', color: '#fff', border: 'none',
                  borderRadius: 8, cursor: 'pointer', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 8,
                  boxShadow: '0 2px 4px rgba(37,99,235,0.25)'
                }}
                title="Generar Orden de Compra formal para inyectar a Tránsito">
                <span>📝 Emitir PO</span>
                {selectedSkusForPo.size > 0 && (
                  <span style={{ background: '#fff', color: '#2563eb', padding: '1px 7px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 800 }}>
                    {selectedSkusForPo.size}
                  </span>
                )}
              </button>
              <button 
                onClick={() => handleExportExcel(false)}
                style={{ padding: '8px 16px', background: '#1d6b3e', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                📥 Excel (Todo)
              </button>
              <button 
                onClick={() => handleExportExcel(true)}
                style={{ padding: '8px 16px', background: '#d32f2f', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                📥 Excel (Urgentes)
              </button>
            </div>
          </div>
        </div>

        {/* ── NAVEGACIÓN DE PESTAÑAS S&OP vs MRP ── */}
        <div style={{ display: 'flex', gap: 12, borderBottom: '2px solid #e2e8f0', marginBottom: 20 }}>
          <button
            onClick={() => setActiveTab('SOP')}
            style={{
              background: 'none', border: 'none', padding: '10px 18px', cursor: 'pointer',
              fontSize: '1rem', fontWeight: 700,
              color: activeTab === 'SOP' ? '#1d6b3e' : '#64748b',
              borderBottom: activeTab === 'SOP' ? '3px solid #1d6b3e' : 'none'
            }}>
            🛒 Abastecimiento S&OP (Productos)
          </button>
          <button
            onClick={() => {
              setActiveTab('MRP');
              if (mrpData.length === 0) loadMrpData();
            }}
            style={{
              background: 'none', border: 'none', padding: '10px 18px', cursor: 'pointer',
              fontSize: '1rem', fontWeight: 700,
              color: activeTab === 'MRP' ? '#9333ea' : '#64748b',
              borderBottom: activeTab === 'MRP' ? '3px solid #9333ea' : 'none',
              display: 'flex', alignItems: 'center', gap: 6
            }}>
            <span>📦 MRP Insumos de Maquila</span>
            {mrpResumen && mrpResumen.criticos > 0 && (
              <span style={{ background: '#ef4444', color: '#fff', padding: '1px 6px', borderRadius: 10, fontSize: '0.7rem', fontWeight: 800 }}>
                {mrpResumen.criticos} críticos
              </span>
            )}
          </button>
        </div>

        {/* ── CONTENIDO PRINCIPAL: S&OP vs MRP ── */}
        {activeTab === 'SOP' ? (
          <>
            {/* ── ADVERTENCIA DE REGLAS ── */}
            <div style={{ backgroundColor: '#fff3cd', border: '1px solid #ffeeba', color: '#856404', padding: '15px 20px', borderRadius: '8px', marginBottom: '25px', fontSize: '0.9rem', lineHeight: '1.5' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                ⚠️ Precaución: Reglas de Cálculo del Motor
              </h4>
          <p style={{ margin: '0 0 8px 0' }}>Estas sugerencias de compra se generan de forma automática basándose en las siguientes reglas:</p>
          <ul style={{ margin: 0, paddingLeft: '20px' }}>
            <li><b>Target de Cobertura:</b> Las sugerencias cubren como mínimo <b>5,4 meses</b>. Si el crecimiento mensual del SKU es igual o superior al <b>5%</b>, se agrega <b>1 mes extra</b> (6,4 meses en total).</li>
            <li><b>Lead Time (Tránsito):</b> Se asume que los pedidos tardan <b>{LEAD_TIME_DAYS} días</b> en llegar.</li>
            <li><b>Ritmo de Venta:</b> El consumo mensual estimado se calcula en base al pico máximo histórico mensual del SKU.</li>
            <li><b>Filtro de Tránsito:</b> Si un SKU tiene al menos 1 unidad ya en tránsito (estado Morado), <b>NO</b> se sugiere volver a comprar.</li>
            <li><b>Disparador (Trigger):</b> Solo se sugiere comprar cuando el stock proyectado cae por debajo de 4 meses (Amarillo, Naranja o Rojo).</li>
          </ul>
        </div>

        {/* ── BANNER GESTIÓN POR MAQUILA ── */}
        <div style={{ backgroundColor: '#ebf8ff', border: '1px solid #90cdf4', color: '#2b6cb0', padding: '15px 20px', borderRadius: '8px', marginBottom: '25px', fontSize: '0.9rem', lineHeight: '1.5' }}>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🏭 Gestión y Transformación en Maquila: Exclusión de Productos Cubiertos por Familia
          </h4>
          <p style={{ margin: '0 0 6px 0' }}>
            Todo producto que sea maquilable (pertenece a una familia de reemplazo) se abastece mediante la redistribución homogénea de su grupo familiar en <b>Maquila</b> y no se lista para compra si su familia tiene unidades suficientes. Solo pasan a compra aquellos con déficit neto familiar.
          </p>
          <div style={{ display: 'flex', gap: 15, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
            <span style={{ background: '#2b6cb0', color: '#fff', padding: '4px 12px', borderRadius: 20, fontWeight: 'bold', fontSize: '0.85rem' }}>
              {maquilaCubiertos.length} productos cubiertos por Maquila (0 compra)
            </span>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600, color: '#2b6cb0' }}>
              <input
                type="checkbox"
                checked={filterExcluirMaquila}
                onChange={e => setFilterExcluirMaquila(e.target.checked)}
              />
              Ocultar cubiertos por Maquila (Activo por regla de negocio)
            </label>
          </div>
        </div>

        {/* ── BANNER AÑO NUEVO CHINO (FEBRERO) ── */}
        <div style={{ backgroundColor: '#fff5f5', border: '1px solid #feb2b2', color: '#9b2c2c', padding: '15px 20px', borderRadius: '8px', marginBottom: '25px', fontSize: '0.9rem', lineHeight: '1.5' }}>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🏮 Recomendación Estratégica: Compra Masiva por Año Nuevo Chino (Febrero)
          </h4>
          <p style={{ margin: '0 0 6px 0' }}>
            Las fábricas y puertos en China cierran durante semanas en febrero. Con el lead time de importación de <b>120 días</b>, los pedidos que deban arribar en <b>Febrero, Marzo y Abril</b> deben ordenarse anticipadamente en una sola <b>Compra Masiva Proyectada</b>.
          </p>
          <div style={{ display: 'flex', gap: 15, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
            <span style={{ background: '#c53030', color: '#fff', padding: '4px 12px', borderRadius: 20, fontWeight: 'bold', fontSize: '0.85rem' }}>
              Volumen Consolidado Sugerido (Feb-Abr): {Number(totalCNYUds).toLocaleString('es-CL')} uds
            </span>
            <button
              onClick={() => setFilterCNY(!filterCNY)}
              style={{ padding: '6px 12px', background: filterCNY ? '#742a2a' : '#fff', color: filterCNY ? '#fff' : '#c53030', border: '1px solid #c53030', borderRadius: 6, cursor: 'pointer', fontWeight: 'bold', fontSize: '0.8rem' }}>
              {filterCNY ? '✓ Mostrando solo compras CNY' : '🏮 Filtrar solo SKUs con compra CNY'}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="loader-wrap"><div className="spinner" /></div>
        ) : error ? (
          <div className="upload-result err">❌ {error}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 30 }}>
            
            {/* ── FILTROS ── */}
            <div style={{ display: 'flex', gap: 15, background: '#fff', padding: 15, borderRadius: 8, border: '1px solid #ddd' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Nivel Alerta</label>
                <select value={filterAlert} onChange={e => setFilterAlert(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}>
                  <option value="ALL">Todas</option>
                  <option value="ROJO">🔴 Rojo</option>
                  <option value="NARANJA">🟠 Naranja</option>
                  <option value="AMARILLO">🟡 Amarillo</option>
                  <option value="MORADO">🟣 Morado</option>
                  <option value="VERDE">🟢 Verde</option>
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Tránsito</label>
                <select value={filterTransit} onChange={e => setFilterTransit(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}>
                  <option value="ALL">Todos</option>
                  <option value="WITH">Con Tránsito (&gt;0)</option>
                  <option value="WITHOUT">Sin Tránsito (0)</option>
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Comparación Modelos</label>
                <select value={filterComparacion} onChange={e => setFilterComparacion(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc', background: '#e3f2fd' }}>
                  <option value="ALL">Todas</option>
                  <option value=">20%">Diferencia &gt;20%</option>
                  <option value="AMBAS">Ambos sugieren comprar</option>
                  <option value="SOLO_LEGACY">Solo Oficial (Legacy) compra</option>
                  <option value="SOLO_DINAMICA">Solo Dinámico compra</option>
                  <option value="SIN_ANALISIS">Sin análisis dinámico</option>
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Crecimiento 2M</label>
                <select value={filterCrecimiento} onChange={e => setFilterCrecimiento(e.target.value)} style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}>
                  <option value="ALL">Todos</option>
                  <option value="ANOMALIES">Anomalías (Negativo o &gt;50%)</option>
                  <option value="NEG_2M">Crecimiento Negativo (2M)</option>
                  <option value="HIGH_50_2M">Crecimiento &gt;50% (2M)</option>
                </select>
              </div>

              {/* Selector de Agrupación (Mes / Semana) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#555' }}>Agrupación</label>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    type="button"
                    onClick={() => setGroupBy('MONTH')}
                    style={{
                      padding: '6px 12px',
                      borderRadius: 4,
                      border: '1.5px solid ' + (groupBy === 'MONTH' ? '#1d6b3e' : '#cbd5e1'),
                      background: groupBy === 'MONTH' ? '#1d6b3e' : '#ffffff',
                      color: groupBy === 'MONTH' ? '#ffffff' : '#475569',
                      fontWeight: 700,
                      fontSize: '0.8rem',
                      cursor: 'pointer'
                    }}
                    title="Agrupar compras por Mes calendario"
                  >
                    📅 Por Mes
                  </button>
                  <button
                    type="button"
                    onClick={() => setGroupBy('WEEK')}
                    style={{
                      padding: '6px 12px',
                      borderRadius: 4,
                      border: '1.5px solid ' + (groupBy === 'WEEK' ? '#1d6b3e' : '#cbd5e1'),
                      background: groupBy === 'WEEK' ? '#1d6b3e' : '#ffffff',
                      color: groupBy === 'WEEK' ? '#ffffff' : '#475569',
                      fontWeight: 700,
                      fontSize: '0.8rem',
                      cursor: 'pointer'
                    }}
                    title="Agrupar compras por Semana ISO"
                  >
                    📆 Por Semana
                  </button>
                </div>
              </div>
            </div>

            {/* ── SECCIÓN 1: SUGERENCIAS AUTOMÁTICAS ── */}
            <section>
              <h2 style={{ fontSize: '1.2rem', color: '#1d6b3e', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                🤖 Sugerencias del Motor
              </h2>
              
              {sortedGroupKeys.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', background: '#f9f9f9', borderRadius: 8, color: '#888' }}>
                  No hay sugerencias de compra automáticas activas en este momento.
                </div>
              ) : (
                sortedGroupKeys.map(key => {
                  const group = groupedSug[key];
                  // Ordenar ítems dentro del grupo: Categoría -> Familia Maquila -> Fecha ideal
                  group.items.sort((a, b) => {
                    const catA = a.categoria || '';
                    const catB = b.categoria || '';
                    if (catA < catB) return -1;
                    if (catA > catB) return 1;
                    
                    const famA = a.nombre_familia_maquila || (a.familia_skus && a.familia_skus.length > 1 ? (a.familia_skus[0].codigo_femaco || a.familia_skus[0].sku) : '');
                    const famB = b.nombre_familia_maquila || (b.familia_skus && b.familia_skus.length > 1 ? (b.familia_skus[0].codigo_femaco || b.familia_skus[0].sku) : '');
                    if (famA && !famB) return -1;
                    if (!famA && famB) return 1;
                    if (famA && famB && famA !== famB) return famA.localeCompare(famB);

                    return a.idealDateObj - b.idealDateObj;
                  });
                  
                  const isUrgente = key === '0000-URGENTE';
                  
                  return (
                    <details key={key} open={isUrgente} style={{ marginBottom: 12, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: '#fff' }}>
                      <summary style={{ padding: '12px 16px', background: isUrgente ? '#FFEBEC' : '#f9f9f9', cursor: 'pointer', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ color: isUrgente ? '#E63946' : '#333' }}>
                          {group.label} 
                          <span style={{ marginLeft: 16, fontSize: '0.85rem', fontWeight: 'normal', color: 'var(--gray)' }}>
                            ({group.items.length} SKUs sugeridos)
                          </span>
                        </div>
                      </summary>
                      <div style={{ overflowX: 'auto', borderTop: '1px solid var(--border)' }}>
                        <table className="preview-table" style={{ margin: 0, border: 'none', borderRadius: 0 }}>
                          <thead>
                            <tr>
                              <th style={{ width: 36, textAlign: 'center' }}>
                                <input
                                  type="checkbox"
                                  title="Seleccionar todo el grupo"
                                  checked={group.items.length > 0 && group.items.every(it => selectedSkusForPo.has(it.sku))}
                                  onChange={() => toggleGroupSelection(group.items)}
                                />
                              </th>
                              <th>SKU / Cód. Femaco</th>
                              <th>Categoría</th>
                              <th>Estado & Maquila</th>
                              <th>Cobertura</th>
                              <th>Tránsito</th>
                              <th>Proyeccion 4 meses</th>
                              <th style={{ background: '#e8f5e9', borderLeft: '2px solid #a5d6a7', color: '#1b5e20' }}>Compra proyectada</th>
                              <th style={{ background: '#ffebee', color: '#b71c1c', borderLeft: '2px solid #ef9a9a' }}>🏮 Masiva CNY (Feb-Abr)</th>
                              <th style={{ background: '#e3f2fd', color: '#0d47a1' }}>Dinámico (Exp.)</th>
                              <th style={{ background: '#f5f5f5', color: '#333' }}>Comparativa</th>
                              <th>Detalle</th>
                            </tr>
                          </thead>
                          <tbody>
                            {group.items.map(s => {
                              const stockoutDate = new Date(s.idealDateObj);
                              stockoutDate.setDate(stockoutDate.getDate() + LEAD_TIME_DAYS);
                              const isMaq = Boolean(s.es_maquilable || (s.familia_skus && s.familia_skus.length > 1));
                              const movimientoMaquila = Number(s.maquila_recibida_4_meses || 0) > 0 || Number(s.maquila_destinada_4_meses || 0) > 0;
                              
                              return (
                                <tr key={s.sku} style={isMaq ? { background: '#fdfbfe' } : {}}>
                                  <td style={{ textAlign: 'center' }}>
                                    <input
                                      type="checkbox"
                                      checked={selectedSkusForPo.has(s.sku)}
                                      onChange={() => toggleSkuSelection(s.sku)}
                                    />
                                  </td>
                                  <td style={isMaq ? { borderLeft: '3px solid #9333ea' } : {}}>
                                    <div>
                                      <b>{s.sku}</b>
                                      {s.codigo_femaco && s.codigo_femaco !== s.sku && (
                                        <span style={{ marginLeft: 6, fontSize: '0.75rem', color: '#0369a1', fontWeight: 700 }}>
                                          [{s.codigo_femaco}]
                                        </span>
                                      )}
                                    </div>
                                    <div style={{ marginTop: 3, fontSize: '0.7rem', fontWeight: 800, color: '#475569' }}>
                                      FORMATO: {s.formato_compra || 'LINEAL'}
                                    </div>
                                    <div style={{ fontSize: '0.75rem', color: '#666', maxWidth: 180, whiteSpace: 'normal' }}>{s.nombre_producto}</div>
                                    {isMaq && (
                                      <div style={{ marginTop: 4, display: 'inline-flex', alignItems: 'center', gap: 4, background: '#f3e8ff', padding: '1px 6px', borderRadius: 4, fontSize: '0.68rem', color: '#6b21a8', fontWeight: 600, border: '1px solid #d8b4fe' }}>
                                        🧩 {s.nombre_familia_maquila || 'Familia Maquila'} ({s.familia_skus?.length || 1} SKUs)
                                      </div>
                                    )}
                                  </td>
                                  <td style={{ fontSize: '0.8rem', maxWidth: 120 }}>{s.categoria || '—'}</td>
                                  <td style={{ verticalAlign: 'top' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                        <span style={{ 
                                          padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold', width: 'fit-content',
                                          background: s.nivel_alerta === 'ROJO' ? '#ffebee' : s.nivel_alerta === 'NARANJA' ? '#fff3e0' : s.nivel_alerta === 'AMARILLO' ? '#fffde7' : s.nivel_alerta === 'MORADO' ? '#f3e5f5' : '#e8f5e9',
                                          color: s.nivel_alerta === 'ROJO' ? '#c62828' : s.nivel_alerta === 'NARANJA' ? '#ef6c00' : s.nivel_alerta === 'AMARILLO' ? '#f57f17' : s.nivel_alerta === 'MORADO' ? '#6a1b9a' : '#2e7d32'
                                        }}>
                                          {s.nivel_alerta}
                                        </span>

                                        {s.estado && (s.estado.includes('BLOQUE') || s.condicion?.includes('BLOQUE')) && (
                                          <span style={{ padding: '2px 6px', borderRadius: 4, fontSize: '0.68rem', fontWeight: 'bold', background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' }}>
                                            BLOQUEADO
                                          </span>
                                        )}

                                        {s.estado && (s.estado.includes('DESCONTINUA') || s.condicion?.includes('DESCONTINUA')) && (
                                          <span style={{ padding: '2px 6px', borderRadius: 4, fontSize: '0.68rem', fontWeight: 'bold', background: '#fee2e2', color: '#991b1b', border: '1px solid #fca5a5' }}>
                                            DESCONTINUADO
                                          </span>
                                        )}
                                      </div>

                                      {/* Estado de Maquila Familiar */}
                                      {isMaq && (
                                        movimientoMaquila ? (
                                          <span title={`Recibe ${Number(s.maquila_recibida_4_meses || 0).toLocaleString('es-CL')} y destina ${Number(s.maquila_destinada_4_meses || 0).toLocaleString('es-CL')} unidades durante la espera.`} style={{ background: '#e0f2fe', color: '#0369a1', padding: '2px 6px', borderRadius: 4, fontSize: '0.68rem', fontWeight: 700, border: '1px solid #bae6fd', width: 'fit-content' }}>
                                            MAQUILA PROYECTADA
                                          </span>
                                        ) : (
                                          <span title={`Compra total de la familia: ${Number(s.familia_compra_total || 0).toLocaleString('es-CL')} unidades, desglosada por SKU.`} style={{ background: '#faf5ff', color: '#7e22ce', padding: '2px 6px', borderRadius: 4, fontSize: '0.68rem', fontWeight: 700, border: '1px solid #d8b4fe', width: 'fit-content' }}>
                                            🔄 FAMILIA MAQUILA
                                          </span>
                                        )
                                      )}

                                      {s.excepciones && s.excepciones.length > 0 && s.excepciones.map((ex, i) => (
                                        <span key={ex} title={s.explicacion_excepcion?.[i] || ex} style={{ background: '#FFF3EB', color: '#b35f1a', padding: '2px 6px', borderRadius: 4, fontSize: '0.65rem', border: '1px solid #F4864A', cursor: 'help', width: 'fit-content' }}>
                                          {ex.replace(/_/g, ' ')}
                                        </span>
                                      ))}
                                    </div>
                                  </td>
                                  <td>{Number(s.duracion_fisica_solo || 0).toFixed(1)} m</td>
                                  <td>{Number(s.cantidad_transito || 0).toLocaleString('es-CL')}</td>
                                  <td style={{ minWidth: 190, fontSize: '0.74rem', lineHeight: 1.45 }}>
                                    <div>Stock actual: <b>{Number(s.stock_act || 0).toLocaleString('es-CL')}</b></div>
                                    <div>Venta 4 sem.: <b>{Number(s.total_4_sem_verificado || 0).toLocaleString('es-CL')}</b></div>
                                    <div>Demanda espera: <b>{Number(s.demanda_espera_4_meses || 0).toLocaleString('es-CL')}</b></div>
                                    <div>Maquila recibida / destinada: <b>{Number(s.maquila_recibida_4_meses || 0).toLocaleString('es-CL')} / {Number(s.maquila_destinada_4_meses || 0).toLocaleString('es-CL')}</b></div>
                                    <div>Stock llegada: <b>{Number(s.stock_estimado_llegada || 0).toLocaleString('es-CL')}</b></div>
                                    <div>Objetivo ({Number(s.meses_cobertura_objetivo || 5.4).toFixed(1)} m): <b>{Number(s.stock_objetivo || 0).toLocaleString('es-CL')}</b></div>
                                    {Number(s.deficit_espera_4_meses || 0) > 0 && (
                                      <div style={{ color: '#b91c1c' }}>Deficit espera: <b>{Number(s.deficit_espera_4_meses).toLocaleString('es-CL')}</b></div>
                                    )}
                                    {s.ambiguedad_maquila && (
                                      <div style={{ color: '#b45309' }}>Revisar prioridad de maquila</div>
                                    )}
                                  </td>
                                  
                                  <td style={{ fontWeight: 'bold', background: '#E7F7ED', color: '#1d6b3e', borderLeft: '2px solid #a5d6a7' }}>
                                    {Number(s.sugerencia_compra_inmediata_uds || 0).toLocaleString('es-CL')}
                                  </td>

                                  <td style={{ fontWeight: 'bold', background: '#FFF5F5', color: '#B71C1C', borderLeft: '2px solid #EF9A9A', textAlign: 'center' }}>
                                    {Number(s.compra_masiva_cny_uds || 0).toLocaleString('es-CL')}
                                  </td>
                                  
                                  <td style={{ background: '#e3f2fd', color: '#0d47a1', fontSize: '0.8rem', verticalAlign: 'top' }}>
                                    <div style={{ marginBottom: '4px' }}>
                                      <span style={{ color: '#555' }}>Compra dinámica:</span>{' '}
                                      <b>{s.sugerencia_compra_dinamica != null ? Number(s.sugerencia_compra_dinamica).toLocaleString('es-CL') : 'No disponible'}</b>
                                    </div>
                                    <div style={{ marginBottom: '4px' }}>
                                      <span style={{ color: '#555' }}>Cobertura:</span>{' '}
                                      <b>{s.cobertura_proyectada_meses != null ? `${Number(s.cobertura_proyectada_meses).toFixed(1)} meses` : 'No disponible'}</b>
                                    </div>
                                    <div>
                                      <span style={{ color: '#555' }}>Estado:</span>{' '}
                                      {s.estado_alerta ? (
                                        <span style={{
                                          padding: '2px 6px',
                                          borderRadius: '4px',
                                          display: 'inline-block',
                                          marginTop: '2px',
                                          fontWeight: 'bold',
                                          fontSize: '0.75rem'
                                        }} className={`dynamic-status-${s.estado_alerta.toLowerCase().replace(/ /g, '-')}`}>
                                          {s.estado_alerta}
                                        </span>
                                      ) : (
                                        <span style={{
                                          padding: '2px 6px',
                                          borderRadius: '4px',
                                          display: 'inline-block',
                                          marginTop: '2px',
                                          fontWeight: 'bold',
                                          fontSize: '0.75rem'
                                        }} className="dynamic-status-sin-analisis">
                                          Sin análisis
                                        </span>
                                      )}
                                    </div>
                                  </td>
                                  
                                  <td style={{ background: '#f5f5f5', fontSize: '0.8rem' }}>
                                    {s.recomendacion_coincide === 'No comparable por falta de datos' || !s.recomendacion_coincide ? (
                                      <span style={{ color: '#888' }}>Sin Análisis</span>
                                    ) : (
                                      <div>
                                        <div style={{ fontWeight: 'bold', color: (s.diferencia_porcentual_dinamica_legacy || 0) > 0.2 ? '#d32f2f' : '#2e7d32' }}>
                                          Dif: {s.diferencia_compra_dinamica_legacy > 0 ? '+' : ''}{Number(s.diferencia_compra_dinamica_legacy || 0).toLocaleString('es-CL')} 
                                          ({Number((s.diferencia_porcentual_dinamica_legacy || 0) * 100).toFixed(0)}%)
                                        </div>
                                        <div style={{ color: '#555', fontSize: '0.75rem', marginTop: 2 }}>{s.recomendacion_coincide}</div>
                                      </div>
                                    )}
                                  </td>
                                  
                                  <td>
                                    <button onClick={() => setSelectedSku(s)} style={{ padding: '4px 8px', background: '#2196f3', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.8rem' }}>
                                      Ver Detalle
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  );
                })
              )}
            </section>

            <hr style={{ border: 'none', borderTop: '2px dashed #eee' }} />

            {/* ── SECCIÓN 2: REQUIERE REVISIÓN ── */}
            <section>
              <h2 style={{ fontSize: '1.2rem', color: '#b35f1a', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                ⚠️ Requiere Revisión (Excepciones)
              </h2>
              
              {revisionList.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', background: '#f9f9f9', borderRadius: 8, color: '#888' }}>
                  No hay productos que requieran revisión actualmente.
                </div>
              ) : (
                <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <table className="preview-table" style={{ margin: 0, border: 'none' }}>
                          <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Nombre de Producto</th>
                              <th>Categoría</th>
                              <th>Stock Físico</th>
                              <th>Excepciones</th>
                              <th>Estado Compra</th>
                            </tr>
                          </thead>
                    <tbody>
                      {revisionList.map(s => (
                        <tr key={s.sku}>
                          <td><b>{s.sku}</b></td>
                          <td style={{ fontSize: '0.8rem', maxWidth: 200 }}>{s.nombre_producto}</td>
                          <td>{s.categoria || '—'}</td>
                          <td>{Number(s.stock_act || 0).toLocaleString('es-CL')}</td>
                          <td>
                            {s.excepciones && s.excepciones.length > 0 && (
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                {s.excepciones.map((ex, i) => (
                                  <span key={ex} title={s.explicacion_excepcion?.[i] || ex} style={{ background: '#FFF3EB', color: '#b35f1a', padding: '4px 8px', borderRadius: 4, fontSize: '0.75rem', border: '1px solid #F4864A', cursor: 'help' }}>
                                    {ex.replace(/_/g, ' ')}
                                  </span>
                                ))}
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: 'center', fontWeight: 'bold', color: s.bloquea_compra_automatica ? '#E63946' : '#888' }}>
                            {s.bloquea_compra_automatica ? 'BLOQUEADA' : 'NO'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <hr style={{ border: 'none', borderTop: '2px dashed #eee' }} />

            {/* ── SECCIÓN 2: OBSERVACIONES HUMANAS ── */}
            <section>
              <h2 style={{ fontSize: '1.2rem', color: '#3A86C8', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                ✍️ Notas de Compra Manuales (Humano)
              </h2>
              
              {obsList.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', background: '#f9f9f9', borderRadius: 8, color: '#888' }}>
                  No se encontraron notas que contengan la palabra "comprar".
                </div>
              ) : (
                <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <table className="preview-table" style={{ margin: 0, border: 'none' }}>
                            <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Nombre de Producto</th>
                              <th>Categoría</th>
                              <th>U/E</th>
                              <th>Stock Físico</th>
                              <th>Observación Original</th>
                              <th>Extracción (Uds)</th>
                            </tr>
                          </thead>
                    <tbody>
                      {obsList.map(s => (
                        <tr key={s.sku}>
                          <td><b>{s.sku}</b></td>
                          <td style={{ fontSize: '0.8rem', maxWidth: 200 }}>{s.nombre_producto}</td>
                          <td>{s.categoria || '—'}</td>
                          <td>{s.ump || '—'}</td>
                          <td>{Number(s.stock_act || 0).toLocaleString('es-CL')}</td>
                          <td style={{ fontSize: '0.8rem', fontStyle: 'italic', color: '#555', maxWidth: 300 }}>
                            "{s.observacion}"
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {s.extraido ? (
                              <span style={{ background: '#E8F2FB', color: '#1a6aa8', padding: '4px 10px', borderRadius: 12, fontWeight: 'bold' }}>
                                {Number(s.extraido).toLocaleString('es-CL')}
                              </span>
                            ) : (
                              <span style={{ color: '#ccc' }}>?</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

          </div>
        )}
        </>
      ) : (
        /* ── VISTA MRP DE INSUMOS DE MAQUILA ── */
        <div>
          {/* KPI CARDS */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #9333ea', background: '#fff' }}>
              <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Total Insumos</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#9333ea' }}>
                {mrpResumen?.total_materiales || mrpData.length}
              </div>
              <span style={{ fontSize: '0.8rem', color: '#666' }}>Etiquetas, mangas, cajas, insumos</span>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #ef4444', background: '#fff' }}>
              <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Déficit Crítico 🔴</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#ef4444' }}>
                {mrpResumen?.criticos || mrpData.filter(m => m.urgencia === 'CRITICO').length}
              </div>
              <span style={{ fontSize: '0.8rem', color: '#dc2626' }}>Stock insuficiente vs órdenes activas</span>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #f59e0b', background: '#fff' }}>
              <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Alerta de Stock 🟡</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#f59e0b' }}>
                {mrpResumen?.alertas || mrpData.filter(m => m.urgencia === 'ALERTA').length}
              </div>
              <span style={{ fontSize: '0.8rem', color: '#b45309' }}>Bajo stock mínimo de seguridad</span>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #10b981', background: '#fff' }}>
              <span style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', fontWeight: 600 }}>Presupuesto Reposición</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, margin: '6px 0', color: '#10b981' }}>
                ${Number(mrpResumen?.presupuesto_reposicion_total || 0).toLocaleString('es-CL')}
              </div>
              <span style={{ fontSize: '0.8rem', color: '#047857' }}>Para cubrir órdenes y stock mín.</span>
            </div>
          </div>

          {/* TOOLBAR */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setMrpFilter('ALL')}
                style={{
                  padding: '6px 14px', borderRadius: 6, border: '1px solid #cbd5e1', cursor: 'pointer',
                  background: mrpFilter === 'ALL' ? '#9333ea' : '#fff', color: mrpFilter === 'ALL' ? '#fff' : '#475569',
                  fontWeight: 600, fontSize: '0.85rem'
                }}>
                Todos ({mrpData.length})
              </button>
              <button
                onClick={() => setMrpFilter('CRITICO')}
                style={{
                  padding: '6px 14px', borderRadius: 6, border: '1px solid #fca5a5', cursor: 'pointer',
                  background: mrpFilter === 'CRITICO' ? '#ef4444' : '#fff', color: mrpFilter === 'CRITICO' ? '#fff' : '#dc2626',
                  fontWeight: 600, fontSize: '0.85rem'
                }}>
                🔴 Críticos ({mrpData.filter(m => m.urgencia === 'CRITICO').length})
              </button>
              <button
                onClick={() => setMrpFilter('ALERTA')}
                style={{
                  padding: '6px 14px', borderRadius: 6, border: '1px solid #fde68a', cursor: 'pointer',
                  background: mrpFilter === 'ALERTA' ? '#f59e0b' : '#fff', color: mrpFilter === 'ALERTA' ? '#fff' : '#b45309',
                  fontWeight: 600, fontSize: '0.85rem'
                }}>
                🟡 Alertas ({mrpData.filter(m => m.urgencia === 'ALERTA').length})
              </button>
            </div>

            <button
              onClick={loadMrpData}
              style={{ padding: '6px 14px', background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer', fontSize: '0.85rem', color: '#475569', fontWeight: 600 }}>
              ↻ Actualizar Necesidades MRP
            </button>
          </div>

          {/* TABLA MRP */}
          {mrpLoading ? (
            <div className="loader-wrap"><div className="spinner" /></div>
          ) : mrpData.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', background: '#fff', borderRadius: 8, color: '#888', border: '1px solid var(--border)' }}>
              No hay materiales registrados en el módulo de Maquila.
            </div>
          ) : (
            <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid var(--border)', borderRadius: 8 }}>
              <table className="preview-table" style={{ margin: 0, border: 'none' }}>
                <thead>
                  <tr>
                    <th>SKU / Insumo</th>
                    <th>Categoría</th>
                    <th>Stock Físico</th>
                    <th style={{ background: '#fef2f2', color: '#991b1b' }}>Comprometido en Maquilas</th>
                    <th style={{ background: '#f8fafc' }}>Balance Proyectado</th>
                    <th>Stock Mínimo</th>
                    <th style={{ background: '#eff6ff', color: '#1e40af' }}>Sugerencia Reorden</th>
                    <th>Costo Unitario</th>
                    <th>Costo Estimado</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {mrpData
                    .filter(m => mrpFilter === 'ALL' || m.urgencia === mrpFilter)
                    .map(m => (
                      <tr key={m.sku}>
                        <td>
                          <div><b>{m.sku}</b></div>
                          <div style={{ fontSize: '0.78rem', color: '#64748b' }}>{m.nombre}</div>
                        </td>
                        <td><span style={{ fontSize: '0.75rem', background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>{m.categoria}</span></td>
                        <td><b>{Number(m.stock_actual).toLocaleString('es-CL')}</b> {m.unidad_medida}</td>
                        <td style={{ background: '#fef2f2', color: '#991b1b' }}>
                          <b>{Number(m.comprometido_ordenes).toLocaleString('es-CL')}</b> {m.unidad_medida}
                          {m.ordenes_pendientes > 0 && (
                            <div style={{ fontSize: '0.72rem', color: '#b91c1c' }}>
                              en {m.ordenes_pendientes} orden(es)
                            </div>
                          )}
                        </td>
                        <td style={{ background: '#f8fafc', fontWeight: 'bold', color: m.balance_proyectado < 0 ? '#dc2626' : '#1e293b' }}>
                          {Number(m.balance_proyectado).toLocaleString('es-CL')} {m.unidad_medida}
                        </td>
                        <td>{Number(m.stock_minimo).toLocaleString('es-CL')} {m.unidad_medida}</td>
                        <td style={{ background: '#eff6ff', fontWeight: 'bold', color: '#1d4ed8' }}>
                          {m.sugerencia_compra > 0 ? `${Number(m.sugerencia_compra).toLocaleString('es-CL')} ${m.unidad_medida}` : '—'}
                        </td>
                        <td>${Number(m.costo_unitario).toLocaleString('es-CL')}</td>
                        <td>${Number(m.costo_estimado_compra).toLocaleString('es-CL')}</td>
                        <td>
                          <span style={{
                            padding: '3px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold',
                            background: m.urgencia === 'CRITICO' ? '#fee2e2' : m.urgencia === 'ALERTA' ? '#fef3c7' : '#dcfce7',
                            color: m.urgencia === 'CRITICO' ? '#b91c1c' : m.urgencia === 'ALERTA' ? '#b45309' : '#15803d'
                          }}>
                            {m.urgencia === 'CRITICO' ? '🔴 CRÍTICO' : m.urgencia === 'ALERTA' ? '🟡 ALERTA' : '🟢 OK'}
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

      {/* ── MODAL: GENERADOR DIRECTO DE ORDEN DE COMPRA (PO) ── */}
      {showPoModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(15,23,42,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1200, padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 12, maxWidth: 960, width: '100%', maxHeight: '90vh', overflowY: 'auto', padding: 24, boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, borderBottom: '1px solid #e2e8f0', paddingBottom: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.3rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
                  📝 Emisión Directa de Orden de Compra (PO)
                </h2>
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  Inyecta automáticamente los ítems a Control de Embarques (Tránsito) y al Kardex
                </span>
              </div>
              <button onClick={() => setShowPoModal(false)} style={{ background: 'none', border: 'none', fontSize: '1.3rem', cursor: 'pointer', color: '#64748b' }}>✕</button>
            </div>

            <form onSubmit={handleConfirmSubmitPo}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14, marginBottom: 16 }}>
                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: 4 }}>
                    Código / N° de PO *
                  </label>
                  <input
                    type="text"
                    required
                    value={poForm.numero_oc}
                    onChange={e => setPoForm({ ...poForm, numero_oc: e.target.value.toUpperCase() })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cbd5e1', fontWeight: 700, boxSizing: 'border-box' }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: 4 }}>
                    Proveedor
                  </label>
                  <input
                    type="text"
                    value={poForm.proveedor}
                    onChange={e => setPoForm({ ...poForm, proveedor: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: 4 }}>
                    Fecha Estimada Arribo (ETA)
                  </label>
                  <input
                    type="date"
                    value={poForm.fecha_eta}
                    onChange={e => setPoForm({ ...poForm, fecha_eta: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569', display: 'block', marginBottom: 4 }}>
                  Observaciones / Notas
                </label>
                <input
                  type="text"
                  value={poForm.observacion}
                  onChange={e => setPoForm({ ...poForm, observacion: e.target.value })}
                  placeholder="Ej: Despacho marítimo, contenedor 40ft..."
                  style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}
                />
              </div>

              {/* TABLA ITEMS */}
              <div style={{ marginBottom: 16, border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                <table className="preview-table" style={{ margin: 0, width: '100%' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th>SKU</th>
                      <th>Producto</th>
                      <th style={{ width: 140 }}>Cantidad a Pedir</th>
                      <th>MOQ / Caja</th>
                      <th style={{ width: 120 }}>Costo Unit. ($)</th>
                      <th>Subtotal</th>
                      <th style={{ width: 40 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {poForm.items.map((it, idx) => (
                      <tr key={it.sku}>
                        <td><b>{it.sku}</b></td>
                        <td style={{ fontSize: '0.8rem', maxWidth: 220 }}>{it.nombre_producto}</td>
                        <td>
                          <input
                            type="number"
                            min="1"
                            value={it.cantidad}
                            onChange={e => handleUpdatePoItemQty(idx, e.target.value)}
                            style={{ width: '100%', padding: '4px 8px', borderRadius: 4, border: '1px solid #94a3b8', fontWeight: 700, boxSizing: 'border-box' }}
                          />
                        </td>
                        <td style={{ fontSize: '0.8rem', color: '#64748b' }}>
                          {it.moq > 1 ? `${it.moq} uds/caja` : '—'}
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={it.costo_unitario}
                            onChange={e => handleUpdatePoItemCosto(idx, e.target.value)}
                            style={{ width: '100%', padding: '4px 8px', borderRadius: 4, border: '1px solid #94a3b8', boxSizing: 'border-box' }}
                          />
                        </td>
                        <td style={{ fontWeight: 700 }}>
                          ${Number(it.subtotal || 0).toLocaleString('es-CL')}
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={() => handleRemovePoItem(idx)}
                            style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 'bold' }}>
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* TOTALES */}
              <div style={{ background: '#f1f5f9', padding: '12px 16px', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <span style={{ fontSize: '0.9rem', color: '#475569' }}>
                  Total Ítems: <b>{poForm.items.length} SKUs</b> | Unidades Totales:{' '}
                  <b>{poForm.items.reduce((acc, it) => acc + (Number(it.cantidad) || 0), 0).toLocaleString('es-CL')} uds</b>
                </span>
                <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#1e293b' }}>
                  Monto Total: ${poForm.items.reduce((acc, it) => acc + (Number(it.subtotal) || 0), 0).toLocaleString('es-CL')}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
                <button
                  type="button"
                  onClick={() => setShowPoModal(false)}
                  style={{ padding: '9px 18px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}>
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={submittingPo}
                  style={{ padding: '9px 22px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 700 }}>
                  {submittingPo ? 'Inyectando a Tránsito...' : '🚀 Confirmar y Emitir a Tránsito'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      </main>
      {selectedSku && <SkuDetailModal skuData={selectedSku} onClose={() => setSelectedSku(null)} allProducts={data} />}
    </div>
  );
}

