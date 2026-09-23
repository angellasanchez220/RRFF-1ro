"""
api/routes/forecast.py — Endpoint de Forecast Sell Out con Holt-Winters
========================================================================
Expone el endpoint independiente GET /api/sop/forecast-holtwinters/{sku}
Totalmente desacoplado de la lógica S&OP y sugerencia de compra.
"""

from fastapi import APIRouter, HTTPException
from api.db import engine
from src.services.holt_winters_service import get_holt_winters_forecast

router = APIRouter()

@router.get("/forecast-holtwinters/{sku}")
def get_forecast(sku: str):
    """
    Obtiene la proyección analítica de Sell Out usando Holt-Winters o Estacionalidad de Familia.
    """
    if not sku or not sku.strip():
        raise HTTPException(status_code=400, detail="SKU no proporcionado")
    
    try:
        res = get_holt_winters_forecast(sku.strip(), engine=engine)
        return res
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando forecast Holt-Winters: {str(exc)}")
