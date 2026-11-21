const normalizeLabel = (value) => String(value ?? '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .trim()
  .toUpperCase();

const normalizeId = (value) => normalizeLabel(value).replace(/\s+/g, '');

export function normalizePiCode(value) {
  const code = normalizeId(value);
  return /^CL\d{5}$/.test(code) ? `19${code}` : code;
}

export function parsePositiveNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? Math.max(0, value) : 0;
  const text = String(value ?? '').trim().replace(/\s/g, '');
  if (!text) return 0;

  let normalized;
  if (text.includes('.') && text.includes(',')) {
    normalized = text.lastIndexOf(',') > text.lastIndexOf('.')
      ? text.replace(/\./g, '').replace(',', '.')
      : text.replace(/,/g, '');
  } else if (/^\d{1,3}(\.\d{3})+$/.test(text)) {
    normalized = text.replace(/\./g, '');
  } else if (/^\d{1,3}(,\d{3})+$/.test(text)) {
    normalized = text.replace(/,/g, '');
  } else {
    normalized = text.replace(',', '.');
  }

  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

export function calculateBoxes(quantity, unitsPerBox) {
  const units = parsePositiveNumber(quantity);
  const pack = parsePositiveNumber(unitsPerBox) || 1;
  return Math.round((units / pack) * 1000) / 1000;
}

function rowToObject(headers, row) {
  return headers.reduce((result, header, index) => {
    if (header) result[header] = row[index];
    return result;
  }, {});
}

function firstValue(record, keys) {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null && record[key] !== '') {
      return record[key];
    }
  }
  return '';
}

function parseTabularSheet(rows, sheetName) {
  const headerIndex = rows.findIndex(row => {
    const labels = row.map(normalizeLabel);
    return labels.includes('CANTIDAD')
      && (labels.includes('SKU') || labels.includes('COD INTERNO') || labels.includes('CODIGO FEMACO'));
  });
  if (headerIndex < 0) return [];

  const headers = rows[headerIndex].map(normalizeLabel);
  const parsed = [];
  for (const row of rows.slice(headerIndex + 1)) {
    const record = rowToObject(headers, row);
    const sku = String(firstValue(record, ['SKU']) || '').trim();
    const internalCode = String(firstValue(record, ['COD INTERNO', 'CODIGO FEMACO', 'CODIGO INTERNO']) || '').trim();
    const unitsPerBox = parsePositiveNumber(firstValue(record, [
      'QTTY (UNIDAD EMPAQUE)', 'U/E', 'UE', 'UNIDAD EMPAQUE', 'UNIDADES POR CAJA'
    ]));
    const boxes = parsePositiveNumber(firstValue(record, ['CAJAS']));
    const enteredQuantity = parsePositiveNumber(firstValue(record, ['CANTIDAD', 'UNIDADES', 'CANTIDAD A PEDIR']));
    const quantity = enteredQuantity || (boxes * unitsPerBox);
    if ((!sku && !internalCode) || quantity <= 0) continue;

    parsed.push({
      source: 'TABULAR',
      sheetName,
      piCode: normalizePiCode(firstValue(record, ['NUMERO PI', 'NRO PI', 'PI'])),
      originalPiCode: String(firstValue(record, ['NUMERO PI', 'NRO PI', 'PI']) || '').trim(),
      sku,
      codigo_femaco: internalCode,
      nombre_producto: String(firstValue(record, ['DESCRIPCION (ESPANOL)', 'NOMBRE DE PRODUCTO', 'PRODUCTO']) || '').trim(),
      descripcion_ingles: String(firstValue(record, ['DESCRIPTION (ENGLISH)', 'DESCRIPCION INGLES']) || '').trim(),
      cantidad: Math.round(quantity),
      qtty: unitsPerBox || 0,
      cajas: boxes || calculateBoxes(quantity, unitsPerBox),
    });
  }
  return parsed;
}

function parseRrffSheet(rows, sheetName) {
  const parsed = [];
  rows.forEach((row, rowIndex) => {
    if (normalizeLabel(row[4]) !== 'ENVIO PI') return;
    const header = rows[rowIndex - 5] || [];
    const piCodeRaw = row[5];
    const quantityRow = rows[rowIndex + 1] || [];
    const quantity = parsePositiveNumber(quantityRow[5]);
    const sku = String(header[1] ?? '').trim();
    const internalCode = String(header[2] ?? '').trim();
    if ((!sku && !internalCode) || !piCodeRaw || quantity <= 0) return;

    const unitsPerBox = parsePositiveNumber(header[8]);
    parsed.push({
      source: 'RRFF',
      sheetName,
      sourceRow: rowIndex + 1,
      piCode: normalizePiCode(piCodeRaw),
      originalPiCode: String(piCodeRaw).trim(),
      sku,
      codigo_femaco: internalCode,
      nombre_producto: String(header[3] ?? '').trim(),
      descripcion_ingles: '',
      cantidad: Math.round(quantity),
      qtty: unitsPerBox || 0,
      cajas: calculateBoxes(quantity, unitsPerBox),
    });
  });
  return parsed;
}

function deduplicateItems(items) {
  const unique = new Map();
  items.forEach(item => {
    const key = normalizeId(item.sku) || `COD:${normalizeId(item.codigo_femaco)}`;
    if (key) unique.set(key, item);
  });
  return [...unique.values()];
}

export function parsePiWorkbook(workbook, xlsx, targetPiCode) {
  const tabularItems = [];
  const rrffItems = [];

  workbook.SheetNames.forEach(sheetName => {
    const rows = xlsx.utils.sheet_to_json(workbook.Sheets[sheetName], {
      header: 1,
      raw: true,
      defval: null,
      blankrows: true,
    });
    tabularItems.push(...parseTabularSheet(rows, sheetName));
    rrffItems.push(...parseRrffSheet(rows, sheetName));
  });

  const target = normalizePiCode(targetPiCode);
  const availablePiCodes = [...new Set(rrffItems.map(item => item.piCode).filter(Boolean))].sort();
  let selected = rrffItems.filter(item => item.piCode === target);
  let format = 'RRFF';

  if (selected.length === 0 && tabularItems.length > 0) {
    const withMatchingPi = tabularItems.filter(item => !item.piCode || item.piCode === target);
    selected = withMatchingPi;
    format = 'TABULAR';
  }

  if (selected.length === 0) {
    const suffix = availablePiCodes.length
      ? ` Se encontraron estas PI: ${availablePiCodes.join(', ')}.`
      : '';
    throw new Error(`El archivo no contiene productos para la PI ${targetPiCode}.${suffix}`);
  }

  return {
    format,
    targetPiCode: target,
    availablePiCodes,
    items: deduplicateItems(selected),
  };
}

function findByProduct(items, target) {
  const sku = normalizeId(target.sku);
  const code = normalizeId(target.codigo_femaco);
  return items.findIndex(item => (
    (sku && normalizeId(item.sku) === sku)
    || (code && normalizeId(item.codigo_femaco) === code)
  ));
}

function formatImportedItem(imported, catalogItem = {}) {
  const qtty = parsePositiveNumber(imported.qtty)
    || parsePositiveNumber(catalogItem.qtty)
    || parsePositiveNumber(catalogItem.ump)
    || 1;
  const quantity = Math.round(parsePositiveNumber(imported.cantidad));
  const catalogQtty = parsePositiveNumber(catalogItem.qtty)
    || parsePositiveNumber(catalogItem.ump)
    || qtty;
  return {
    sku: imported.sku || catalogItem.sku || '',
    codigo_femaco: imported.codigo_femaco || catalogItem.codigo_femaco || imported.sku || '',
    nombre_producto: imported.nombre_producto || catalogItem.nombre_producto || '',
    descripcion_ingles: imported.descripcion_ingles || catalogItem.descripcion_ingles || '',
    categoria: catalogItem.categoria || '',
    subcategoria: catalogItem.subcategoria || '',
    formato_compra: catalogItem.formato_compra || 'LINEAL',
    clave_familia_compra: catalogItem.clave_familia_compra || '',
    nombre_familia_maquila: catalogItem.nombre_familia_maquila || '',
    familia_skus: catalogItem.familia_skus || [],
    unidades_sugeridas: Math.round(parsePositiveNumber(
      catalogItem.sugerencia_compra_inmediata_uds || catalogItem.compra_masiva_cny_uds
    )),
    cantidad: quantity,
    qtty,
    cajas: calculateBoxes(quantity, qtty),
    importedFromExcel: true,
    qttyOriginal: catalogQtty,
    qttyChanged: qtty !== catalogQtty,
  };
}

export function reconcilePiItems(currentItems, importedItems, catalogItems = []) {
  const items = currentItems.map(item => ({
    ...item,
    qtty: parsePositiveNumber(item.qtty) || 1,
    cajas: calculateBoxes(item.cantidad, item.qtty),
  }));
  const conflicts = [];
  let unchanged = 0;
  let added = 0;

  importedItems.forEach(imported => {
    const currentIndex = findByProduct(items, imported);
    const catalogIndex = findByProduct(catalogItems, imported);
    const catalogItem = catalogIndex >= 0 ? catalogItems[catalogIndex] : {};
    const importedItem = formatImportedItem(imported, catalogItem);

    if (currentIndex < 0) {
      items.push(importedItem);
      added += 1;
      return;
    }

    const currentItem = items[currentIndex];
    const importedQtty = parsePositiveNumber(imported.qtty) || currentItem.qtty;
    importedItem.qtty = importedQtty;
    importedItem.cajas = calculateBoxes(importedItem.cantidad, importedQtty);
    importedItem.qttyOriginal = currentItem.qtty;
    importedItem.qttyChanged = importedQtty !== currentItem.qtty;

    const quantityChanged = importedItem.cantidad !== Number(currentItem.cantidad || 0);
    const qttyChanged = importedItem.qttyChanged;
    if (!quantityChanged && !qttyChanged) {
      unchanged += 1;
      return;
    }

    conflicts.push({
      key: normalizeId(currentItem.sku) || normalizeId(currentItem.codigo_femaco),
      itemIndex: currentIndex,
      quantityChanged,
      qttyChanged,
      current: currentItem,
      imported: { ...currentItem, ...importedItem },
      choice: '',
    });
  });

  return { items, conflicts, added, unchanged, imported: importedItems.length };
}
