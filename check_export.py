with open('rrff-app/src/pages/Dashboard.jsx', 'r', encoding='utf-8') as f: print('\n'.join([line for line in f if 'excel' in line.lower() or 'export' in line.lower()]))
