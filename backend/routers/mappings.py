from fastapi import APIRouter, HTTPException

import database
from backend.schemas import AddMappingRequest

router = APIRouter(tags=["mappings"])


@router.get("/mappings")
def mappings():
    return database.get_mappings()


@router.post("/mappings")
def add_mapping(body: AddMappingRequest):
    try:
        database.add_mapping(body.label, body.sheet_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
