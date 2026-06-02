from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("")
async def health_check():
    return {
        "success": True,
        "data": {"status": "ok", "version": "1.0.0", "hmm_loaded": True},
        "meta": {"timestamp": datetime.utcnow().isoformat() + "Z"},
        "errors": [],
    }
