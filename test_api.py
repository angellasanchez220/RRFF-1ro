import urllib.request
import json
try:
    resp = urllib.request.urlopen('http://localhost:5001/api/sop')
    data = json.loads(resp.read().decode('utf-8'))
    families = [p for p in data if len(p.get('familia_skus', [])) > 1]
    if not families:
        print("NO FAMILIES FOUND IN API RESPONSE")
    else:
        print("FOUND", len(families), "FAMILIES")
        f = families[0]
        print("SKU:", f['sku'], "FAMILIA_SKUS:", f['familia_skus'])
except Exception as e:
    print("ERROR:", e)
