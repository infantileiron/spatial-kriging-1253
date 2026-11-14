from ..services import supplement_service
def list_for_run(db,run_id):return supplement_service.list_for_run(db,run_id)
def detail(db,ident):return supplement_service.detail(db,ident)
def create(db,body):return supplement_service.serialize_plan(supplement_service.create(db,body))
