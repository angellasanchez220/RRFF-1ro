with open('src/services/maquila_service.py', 'r', encoding='utf-8') as f: print('\n'.join([line for line in f if 'is_discontinued' in line or 'DESCONTINUADO' in line]))
