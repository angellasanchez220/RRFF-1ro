from api.routes.sop import get_sop
try:
    res = get_sop(include_discontinued=True)
    if 'data' in res:
        print("Success, found", len(res['data']), "items")
        for item in res['data'][:5]:
            if len(item.get('familia_skus', [])) > 1:
                print("Item with family:", item['sku'])
    else:
        print("Error:", res)
except Exception as e:
    import traceback
    traceback.print_exc()
