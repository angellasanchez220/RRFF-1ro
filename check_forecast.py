with open('src/forecast_sku.py', 'r', encoding='utf-8') as f: print('\n'.join([f'{i}: {line}' for i, line in enumerate(f) if 'descontinuado' in line]))
