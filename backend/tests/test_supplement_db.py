import copy
import pytest
from sqlalchemy import select
from src.config.database import Session,initialize
from src import models
from src.services.run_service import compute
from src.services import supplement_service
from src.schemas.supplement import SupplementCreate
from src.services.candidate_data import parse_candidates

@pytest.fixture(scope="module")
def seeded():
 initialize()
 with Session() as db:
  if not db.get(models.SpatialDataset,"t-dataset"):
   db.add(models.SpatialDataset(id="t-dataset",name="补采测试批次",coordinate_system="local_meters",description=""))
   db.flush()
   pts=[("S01",0.,0.,26.1),("S02",30.,0.,27.4),("S03",0.,30.,28.9),("S04",30.,30.,30.2),
        ("S05",70.,10.,25.7),("S06",90.,80.,33.1),("S07",20.,90.,31.4),("S08",100.,100.,29.8)]
   for pid,x,y,v in pts:db.add(models.SamplingPoint(id="sp-"+pid,dataset_id="t-dataset",point_id=pid,x=x,y=y,value=v))
   db.add(models.VariogramSpec(id="t-spec",name="固定口径",mode="fixed",n_bins=6,min_pairs=2,max_distance=160.,
     nugget=.2,fixed_sill=8.,fixed_range=55.,sill_min=.1,sill_max=50.,range_min=5.,range_max=300.,
     condition_limit=1e10,negative_tolerance=1e-10))
   db.add(models.KrigingStudy(id="t-study",name="补采测试研究",dataset_id="t-dataset",spec_id="t-spec",query_coordinate_system="local_meters"))
   db.flush()
   for j,(x,y) in enumerate([(20.,20.),(60.,60.),(110.,110.)],start=1):
    db.add(models.QueryPoint(id=f"tq{j}",study_id="t-study",query_id=f"Q{j:02}",x=x,y=y))
   db.add(models.KrigingRun(id="t-run",study_id="t-study",status="queued",result={},error=""))
   db.commit()
   compute(db,"t-run")
  run=db.get(models.KrigingRun,"t-run")
  assert run.status=="completed"
  return run.id

def csv_of(rows):return "candidate_id,x,y\n"+"\n".join(f"{r['candidate_id']},{r['x']},{r['y']}" for r in rows)

@pytest.fixture()
def candidates():
 return [{"candidate_id":f"C{i+1:03}","x":15.0+i*9.0,"y":55.0+(i%4)*12.0} for i in range(60)]

def test_create_persists_plan_and_keeps_run_untouched(seeded,candidates):
 with Session() as db:
  run_before=db.get(models.KrigingRun,seeded)
  snapshot=copy.deepcopy(run_before.result)
  body=SupplementCreate(run_id=seeded,candidates_csv=csv_of(candidates),budget=5,min_spacing=8.0,batch_size=16)
  row=supplement_service.create(db,body)
  assert row.selected_count==len(row.plan["steps"])<=5
  run_after=db.get(models.KrigingRun,seeded)
  # 原运行预测、参数与状态完全不变。
  assert run_after.result==snapshot
  assert run_after.model_sill==snapshot["model"]["sill"]
  assert run_after.status=="completed"
  # 列表与详情可读回。
  listing=supplement_service.list_for_run(db,seeded)
  assert any(r["id"]==row.id for r in listing)
  assert supplement_service.detail(db,row.id)["plan"]["steps"]==row.plan["steps"]

def test_remaining_budget_retained_when_no_candidates(seeded):
 with Session() as db:
  sample=db.scalars(select(models.SamplingPoint).limit(1)).first()
  overlap=[{"candidate_id":"C-OV","x":sample.x,"y":sample.y}]
  body=SupplementCreate(run_id=seeded,candidates_csv=csv_of(overlap),budget=4,min_spacing=10.0)
  row=supplement_service.create(db,body)
  assert row.selected_count==0
  assert row.stop_reason=="no_eligible_candidate"
  assert row.plan["steps"]==[]
  assert row.plan["final_mean_variance"]==row.plan["baseline_mean_variance"]

def test_rejects_non_completed_run(seeded,candidates):
 with Session() as db:
  db.add(models.KrigingRun(id="t-queued",study_id="t-study",status="queued",result={},error=""))
  db.commit()
  with pytest.raises(Exception) as ei:
   supplement_service.create(db,SupplementCreate(run_id="t-queued",candidates_csv=csv_of(candidates),budget=2,min_spacing=0.))
  assert ei.value.status_code==422

def test_rejects_bad_csv(seeded):
 with Session() as db:
  with pytest.raises(Exception) as ei:
   supplement_service.create(db,SupplementCreate(run_id=seeded,candidates_csv="point_id,x,y,value\nA,1,2,3",budget=2,min_spacing=0.))
  assert ei.value.status_code==422

def test_rejects_tampered_run_snapshot(seeded,candidates):
 with Session() as db:
  run=db.get(models.KrigingRun,seeded)
  original=copy.deepcopy(run.result)
  run.result["kriging"]["predictions"][0]["variance"]+=1.0          # 篡改底稿方差
  db.commit()
  try:
   with pytest.raises(Exception) as ei:
    supplement_service.create(db,SupplementCreate(run_id=seeded,candidates_csv=csv_of(candidates),budget=2,min_spacing=0.))
   assert ei.value.status_code==422
  finally:
   run=db.get(models.KrigingRun,seeded);run.result=original;db.commit()  # 还原，避免污染其他用例

def test_http_routes_registered():
 from src.main import app
 paths={r.path for r in app.routes}
 assert "/supplement-plans" in paths
 assert "/supplement-plans/by-run/{run_id}" in paths
 assert "/supplement-plans/{ident}" in paths
