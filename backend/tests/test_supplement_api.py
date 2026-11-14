import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from src.config.database import Session,initialize
from src import models
from src.services.run_service import compute
from src.main import app
from src.utils.security import hash_password

@pytest.fixture(scope="module")
def client_and_run():
 initialize()
 with Session() as db:
  if not db.get(models.User,"u-admin"):
   db.add(models.User(id="u-admin",email="admin@t.local",role="admin",password_hash=hash_password("Passw0rd!")))
   db.add(models.User(id="u-viewer",email="viewer@t.local",role="viewer",password_hash=hash_password("Passw0rd!")))
  if not db.get(models.SpatialDataset,"a-dataset"):
   db.add(models.SpatialDataset(id="a-dataset",name="接口测试批次",coordinate_system="local_meters",description=""))
   db.flush()
   pts=[("S01",0.,0.,26.1),("S02",30.,0.,27.4),("S03",0.,30.,28.9),("S04",30.,30.,30.2),
        ("S05",70.,10.,25.7),("S06",90.,80.,33.1),("S07",20.,90.,31.4),("S08",100.,100.,29.8)]
   for pid,x,y,v in pts:db.add(models.SamplingPoint(id="ap-"+pid,dataset_id="a-dataset",point_id=pid,x=x,y=y,value=v))
   db.add(models.VariogramSpec(id="a-spec",name="固定口径A",mode="fixed",n_bins=6,min_pairs=2,max_distance=160.,
     nugget=.2,fixed_sill=8.,fixed_range=55.,sill_min=.1,sill_max=50.,range_min=5.,range_max=300.,
     condition_limit=1e10,negative_tolerance=1e-10))
   db.add(models.KrigingStudy(id="a-study",name="接口测试研究",dataset_id="a-dataset",spec_id="a-spec",query_coordinate_system="local_meters"))
   db.flush()
   for j,(x,y) in enumerate([(20.,20.),(60.,60.),(110.,110.)],start=1):
    db.add(models.QueryPoint(id=f"aq{j}",study_id="a-study",query_id=f"Q{j:02}",x=x,y=y))
   db.add(models.KrigingRun(id="a-run",study_id="a-study",status="queued",result={},error=""))
   db.commit();compute(db,"a-run")
 return TestClient(app),"a-run"

def token(client,email):
 r=client.post("/auth/login",json={"email":email,"password":"Passw0rd!"});assert r.status_code==200
 return r.json()["token"]

def test_supplement_api_flow(client_and_run):
 client,run_id=client_and_run
 admin=token(client,"admin@t.local");viewer=token(client,"viewer@t.local")
 csv="candidate_id,x,y\n"+"\n".join(f"C{i:03},{10+i*8},{50+(i%5)*10}" for i in range(40))
 # viewer 只读，禁止创建
 r=client.post("/supplement-plans",headers={"Authorization":f"Bearer {viewer}"},
   json={"run_id":run_id,"candidates_csv":csv,"budget":4,"min_spacing":6,"batch_size":32})
 assert r.status_code==403
 # analyst/admin 可创建
 r=client.post("/supplement-plans",headers={"Authorization":f"Bearer {admin}"},
   json={"run_id":run_id,"candidates_csv":csv,"budget":4,"min_spacing":6,"batch_size":32})
 assert r.status_code==201,r.text
 plan=r.json();assert plan["selected_count"]==len(plan["plan"]["steps"])<=4
 assert plan["stop_reason"] in ("budget_exhausted","no_eligible_candidate")
 assert all(set(s)=={"step","candidate_id","x","y","mean_variance_before","mean_variance_after",
                     "variance_reduction","estimated_reduction","condition_number"} for s in plan["plan"]["steps"])
 # 按运行列出
 r=client.get(f"/supplement-plans/by-run/{run_id}",headers={"Authorization":f"Bearer {admin}"})
 assert r.status_code==200 and any(p["id"]==plan["id"] for p in r.json())
 # 详情
 r=client.get(f"/supplement-plans/{plan['id']}",headers={"Authorization":f"Bearer {admin}"})
 assert r.status_code==200 and r.json()["id"]==plan["id"]
 # 未认证401
 assert client.get(f"/supplement-plans/{plan['id']}").status_code==401
 # 不存在的运行404
 assert client.get("/supplement-plans/by-run/missing",headers={"Authorization":f"Bearer {admin}"}).status_code==404

def test_supplement_api_validation(client_and_run):
 client,run_id=client_and_run
 admin=token(client,"admin@t.local")
 bad="point_id,x,y,value\nA,1,2,3"
 r=client.post("/supplement-plans",headers={"Authorization":f"Bearer {admin}"},
   json={"run_id":run_id,"candidates_csv":bad,"budget":4,"min_spacing":6})
 assert r.status_code==422
 r=client.post("/supplement-plans",headers={"Authorization":f"Bearer {admin}"},
   json={"run_id":run_id,"candidates_csv":"candidate_id,x,y\nC1,1,2","budget":21,"min_spacing":6})
 assert r.status_code==422
