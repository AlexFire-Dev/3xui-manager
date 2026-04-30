from fastapi import APIRouter, HTTPException

from app.schemas import VlessConvertRequest, VlessConvertResponse
from app.services.vless_converter import VlessConvertError, vless_url_to_sing_box_outbound

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/vless-to-outbound", response_model=VlessConvertResponse)
def convert_vless_to_outbound(payload: VlessConvertRequest):
    try:
        outbound = vless_url_to_sing_box_outbound(payload.url)
    except VlessConvertError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VlessConvertResponse(outbound=outbound)
