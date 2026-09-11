with open('api/routes/sop.py', 'r', encoding='utf-8') as f: print('\n'.join([f'{i}: {line}' for i, line in enumerate(f) if 'include_discontinued' in line]))
