import os

for filepath in ['src/forecast_sku.py', 'src/validate_sku_history.py']:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace("str.lower() in ['descontinuado', 'descontinuados']", "str.lower().isin(['descontinuado', 'descontinuados'])")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Fixed {filepath}')
