import os

files_to_update = [
    'src/services/maquila_service.py',
    'src/planner.py',
    'src/forecast_sku.py',
    'src/calculate_safety_stock.py',
    'src/calculate_purchase_suggestion.py',
    'src/validate_sku_history.py',
    'api/routes/sop.py',
    'api/routes/maquila.py',
    'src/services/excel_export_service.py'
]

replacements = [
    (
        "'DESCONTINUADO', 'INACTIVO', 'BLOQUEADO', 'BLOQUEADOS'",
        "'DESCONTINUADO', 'DESCONTINUADOS', 'INACTIVO', 'BLOQUEADO', 'BLOQUEADOS'"
    ),
    (
        "'descontinuado', 'inactivo', 'bloqueado', 'bloqueados'",
        "'descontinuado', 'descontinuados', 'inactivo', 'bloqueado', 'bloqueados'"
    ),
    (
        '{"DESCONTINUADO", "INACTIVO", "BLOQUEADO", "BLOQUEADOS"}',
        '{"DESCONTINUADO", "DESCONTINUADOS", "INACTIVO", "BLOQUEADO", "BLOQUEADOS"}'
    ),
    (
        '["DESCONTINUADO", "INACTIVO", "BLOQUEADO", "BLOQUEADOS"]',
        '["DESCONTINUADO", "DESCONTINUADOS", "INACTIVO", "BLOQUEADO", "BLOQUEADOS"]'
    ),
    (
        "['descontinuado', 'desconocido']",
        "['descontinuado', 'descontinuados', 'desconocido']"
    ),
    (
        "== 'descontinuado'",
        "in ['descontinuado', 'descontinuados']"
    ),
    (
        '== "DESCONTINUADO"',
        'in ["DESCONTINUADO", "DESCONTINUADOS"]'
    )
]

for filepath in files_to_update:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        orig_content = content
        for old, new in replacements:
            content = content.replace(old, new)
            
        if content != orig_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Updated {filepath}')
