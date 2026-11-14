from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user
from ..schemas.supplement import SupplementCreate
from ..controllers import supplement_controller as controller
router=APIRouter(prefix="/supplement-plans",tags=["supplement-plans"])
@router.get("/by-run/{run_id}")
def listing(run_id:str,db=Depends(get_db),user=Depends(current)):return controller.list_for_run(db,run_id)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.post("",status_code=201)
def create(body:SupplementCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body)
