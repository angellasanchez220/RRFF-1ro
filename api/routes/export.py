from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, validator
from typing import List

from src.services.excel_export_service import generate_excel_for_sku, generar_excel_skus, generar_excel_todos_skus

router = APIRouter()

class MultiSkuRequest(BaseModel):
    skus: List[str] = Field(..., min_items=1)
    
    @validator("skus")
    def clean_skus(cls, v):
        # Eliminar espacios vacios y strings vacios
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("La lista debe contener al menos 1 SKU v\u00e1lido")
        # Eliminar duplicados conservando el orden
        seen = set()
        return [x for x in cleaned if not (x in seen or seen.add(x))]

@router.get("/rrff/excel/{sku}")
def export_sku_excel(sku: str):
    try:
        excel_bytes = generate_excel_for_sku(sku)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando exportaci\u00f3n: {str(e)}")

    headers = {
        "Content-Disposition": f'attachment; filename="RRFF_{sku}.xlsx"'
    }
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router.post("/rrff/excel")
def export_multi_sku_excel(request: MultiSkuRequest):
    try:
        excel_bytes = generar_excel_skus(request.skus)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"message": "Uno o m\u00e1s SKU no existen", "skus": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando exportaci\u00f3n m\u00faltiple: {str(e)}")

    headers = {
        "Content-Disposition": 'attachment; filename="RRFF_export.xlsx"'
    }
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router.get("/rrff/completo/excel")
def export_all_sku_excel():
    try:
        excel_bytes = generar_excel_todos_skus()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando exportaci\u00f3n completa: {str(e)}")

    headers = {
        "Content-Disposition": 'attachment; filename="RRFF_completo.xlsx"'
    }
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
