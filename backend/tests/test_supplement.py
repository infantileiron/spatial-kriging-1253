import math
import numpy as np
import pytest
from src.services.ordinary_kriging import ordinary_kriging,covariance
from src.services.supplement_service import build_supplement_plan
from src.services.candidate_data import parse_candidates

SILL,RANGE,NUGGET=8.0,55.0,0.2

@pytest.fixture(scope="module")
def scene():
 rng=np.random.default_rng(20261114)
 coords=rng.uniform(0,160,(18,2))
 d=np.linalg.norm(coords[:,None]-coords[None],axis=2)
 C=covariance(d,SILL,RANGE,NUGGET)
 values=30+rng.multivariate_normal(np.zeros(18),C)
 samples=[{"point_id":f"S{i+1:02}","x":float(coords[i,0]),"y":float(coords[i,1]),"value":float(values[i])} for i in range(18)]
 qc=rng.uniform(0,160,(10,2))
 queries=[{"query_id":f"Q{j+1:02}","x":float(qc[j,0]),"y":float(qc[j,1])} for j in range(10)]
 return samples,queries

def ok_variances(samples,queries,extra=()):
 points=list(samples)+[{"point_id":f"X{k}","x":float(x),"y":float(y),"value":0.0} for k,(x,y) in enumerate(extra)]
 out=ordinary_kriging(points,queries,SILL,RANGE,NUGGET)
 return np.array([p["variance"] for p in out["predictions"]])

def make_candidates(n,seed=3,start=200.0):
 rng=np.random.default_rng(seed)
 coords=rng.uniform(0,170,(n,2))
 return [{"candidate_id":f"C{i+1:05}","x":float(coords[i,0]),"y":float(coords[i,1])} for i in range(n)],coords

def test_variance_matches_full_kriging_each_step(scene):
 samples,queries=scene
 candidates,_=make_candidates(40)
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=5,min_spacing=0.0)
 # 用 ordinary_kriging 对“原采样+逐步已选点”整体重算，方案记录的均值必须一致。
 chosen=[(s["x"],s["y"]) for s in plan["steps"]]
 base=ok_variances(samples,queries).mean()
 assert plan["baseline_mean_variance"]==pytest.approx(base,abs=1e-12)
 running=[]
 for k in range(1,len(chosen)+1):
  running.append(ok_variances(samples,queries,chosen[:k]).mean())
 for step,mean_after in zip(plan["steps"],running):
  assert step["mean_variance_after"]==pytest.approx(mean_after,abs=1e-12)
  assert step["variance_reduction"]==pytest.approx(step["mean_variance_before"]-mean_after,abs=1e-12)
  assert step["variance_reduction"]>=-1e-12

def test_greedy_matches_bruteforce(scene):
 samples,queries=scene
 candidates,coords=make_candidates(12,seed=11)
 budget=4
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=budget,min_spacing=0.0)
 # 暴力枚举：每轮对每个候选整体重算平均方差，取降幅最大者。
 added=[];pool=list(range(len(candidates)));brute=[]
 v=ok_variances(samples,queries)
 for _ in range(budget):
  gains=[]
  for i in pool:
   vt=ok_variances(samples,queries,added+[(float(coords[i,0]),float(coords[i,1]))])
   gains.append(v.mean()-vt.mean())
  k=pool[int(np.argmax(gains))];brute.append(candidates[k]["candidate_id"])
  added.append((float(coords[k,0]),float(coords[k,1])));pool.remove(k)
  v=ok_variances(samples,queries,added)
 assert [s["candidate_id"] for s in plan["steps"]]==brute

def test_shuffled_candidates_identical_result(scene):
 samples,queries=scene
 candidates,_=make_candidates(120,seed=5)
 shuffled=list(candidates);np.random.default_rng(99).shuffle(shuffled)
 a=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=8,min_spacing=2.0)
 b=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,shuffled,budget=8,min_spacing=2.0)
 assert a["steps"]==b["steps"]
 assert a["input_sha256"]==b["input_sha256"]

def test_tie_broken_by_candidate_id():
 # 构造关于中心完全对称的采样与待估布局：镜像两个候选的收益逐位相同。
 rng=np.random.default_rng(31)
 half=rng.uniform(5,80,(9,2));coords=np.vstack([half,-half])+100.0
 d=np.linalg.norm(coords[:,None]-coords[None],axis=2)
 C=covariance(d,SILL,RANGE,NUGGET)
 values=30+rng.multivariate_normal(np.zeros(18),C)
 samples=[{"point_id":f"S{i+1:02}","x":float(coords[i,0]),"y":float(coords[i,1]),"value":float(values[i])} for i in range(18)]
 qh=rng.uniform(5,70,(5,2));qc=np.vstack([qh,-qh])+100.0
 queries=[{"query_id":f"Q{j+1:02}","x":float(qc[j,0]),"y":float(qc[j,1])} for j in range(10)]
 c1={"candidate_id":"C-B","x":130.0,"y":100.0}
 c2={"candidate_id":"C-A","x":70.0,"y":100.0}                 # 关于中心(100,100)镜像
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[c1,c2],budget=1,min_spacing=0.0)
 assert plan["steps"][0]["candidate_id"]=="C-A"
 plan2=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[c2,c1],budget=1,min_spacing=0.0)
 assert plan2["steps"][0]["candidate_id"]=="C-A"
 # 跨批次并列：批大小=1时两个候选落在不同批次，仍由编号裁定。
 plan3=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[c1,c2],budget=1,min_spacing=0.0,batch_size=1)
 assert plan3["steps"][0]["candidate_id"]=="C-A"
 # 分批只影响内存与浮点末位，不影响选择与按重算口径记录的收益。
 assert [s["candidate_id"] for s in plan3["steps"]]==[s["candidate_id"] for s in plan["steps"]]
 assert plan3["steps"][0]["variance_reduction"]==pytest.approx(plan["steps"][0]["variance_reduction"],abs=1e-14)

def test_spacing_and_overlap_constraints(scene):
 samples,queries=scene
 sx,sy=samples[0]["x"],samples[0]["y"]
 overlap={"candidate_id":"C-OV","x":sx,"y":sy}                 # 与已采样重合
 near={"candidate_id":"C-NEAR","x":sx+1.0,"y":sy}              # 间距不足
 far={"candidate_id":"C-FAR","x":sx+40.0,"y":sy+40.0}
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[overlap,near,far],budget=3,min_spacing=10.0)
 ids=[s["candidate_id"] for s in plan["steps"]]
 assert "C-OV" not in ids and "C-NEAR" not in ids
 assert ids==["C-FAR"]
 assert plan["stop_reason"]=="no_eligible_candidate"
 # 最小间距为0时，重合点仍不允许重复选，非重合点正常可选。
 plan0=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[overlap,near,far],budget=3,min_spacing=0.0)
 ids0=[s["candidate_id"] for s in plan0["steps"]]
 assert "C-OV" not in ids0 and set(ids0)=={"C-NEAR","C-FAR"}
 # 与上一轮已选点间距不足的候选在后续轮次被排除（每轮对“采样+已选点”重算资格）。
 near_far={"candidate_id":"C-NF","x":sx+45.0,"y":sy+40.0}        # 距 C-FAR 仅5米
 plan2=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[far,near_far],budget=2,min_spacing=10.0)
 ids2=[s["candidate_id"] for s in plan2["steps"]]
 assert ids2==["C-FAR"] and plan2["stop_reason"]=="no_eligible_candidate"

def test_duplicate_candidate_coords_kept_once(scene):
 samples,queries=scene
 c1={"candidate_id":"C-001","x":12.5,"y":77.5}
 c2={"candidate_id":"C-002","x":12.5,"y":77.5}                 # 同坐标不同编号
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[c1,c2],budget=2,min_spacing=0.0)
 assert plan["duplicate_candidate_ids"]==["C-002"]
 assert plan["unique_candidate_count"]==1
 assert [s["candidate_id"] for s in plan["steps"]]==["C-001"]
 assert plan["stop_reason"]=="no_eligible_candidate"

def test_budget_exhausted_reason(scene):
 samples,queries=scene
 candidates,_=make_candidates(30,seed=13)
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=3,min_spacing=0.0)
 assert len(plan["steps"])==3
 assert plan["stop_reason"]=="budget_exhausted"

def test_no_fabricated_readings(scene):
 samples,queries=scene
 candidates,_=make_candidates(10)
 plan=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=2,min_spacing=0.0)
 text=str(plan)
 assert "value" not in plan["no_reading_note"].lower() or "未编造" in plan["no_reading_note"]
 for step in plan["steps"]:assert "value" not in step

def test_parser_rejects_bad_rows():
 with pytest.raises(ValueError):parse_candidates("id,x,y\nC1,1,2")               # 缺candidate_id列
 good=parse_candidates("candidate_id,x,y\nC1,1,2\nC2,3,4")
 assert good==[{"candidate_id":"C1","x":1.0,"y":2.0},{"candidate_id":"C2","x":3.0,"y":4.0}]
 with pytest.raises(ValueError):parse_candidates("candidate_id,x,y\nC1,1,nan") # 非有限
 with pytest.raises(ValueError):parse_candidates("candidate_id,x,y\nC1,1\nC2,2,3")  # 缺列
 with pytest.raises(ValueError):parse_candidates("candidate_id,x,y\nC1,1,2\nC1,3,4") # 重复ID
 # 任何读数/含水率列一律拒绝：补采方案不接受、更不编造新读数。
 with pytest.raises(ValueError):parse_candidates("candidate_id,x,y,value\nC1,1,2,30.5")
 with pytest.raises(ValueError):parse_candidates("candidate_id,x,y,含水率\nC1,1,2,30.5")

def test_invalid_arguments(scene):
 samples,queries=scene
 candidates,_=make_candidates(5)
 with pytest.raises(ValueError):build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=0,min_spacing=0.0)
 with pytest.raises(ValueError):build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=21,min_spacing=0.0)
 with pytest.raises(ValueError):build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=2,min_spacing=-1.0)
 with pytest.raises(ValueError):build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,[],budget=2,min_spacing=0.0)

def test_large_scale_memory_and_batching(scene):
 samples,queries=scene
 candidates,coords=make_candidates(10000,seed=21)
 # 小批与大批结果必须一致（分批评估只改变内存占用，不改变选择）。
 small=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=20,min_spacing=5.0,batch_size=128)
 large=build_supplement_plan(samples,queries,SILL,RANGE,NUGGET,candidates,budget=20,min_spacing=5.0,batch_size=2000)
 assert [s["candidate_id"] for s in small["steps"]]==[s["candidate_id"] for s in large["steps"]]
 assert small["stop_reason"]==large["stop_reason"]
 # 新增内存峰值不超过128MB（tracemalloc口径，仅计Python/NumPy跟踪分配）。
 assert small["peak_memory_bytes"]<=128*1024*1024
 assert large["peak_memory_bytes"]<=128*1024*1024
 assert len(small["steps"])<=20

def test_parser_cap():
 rows="\n".join(f"C{i:05},{i*0.1},{i*0.2}" for i in range(10001))
 with pytest.raises(ValueError):parse_candidates("candidate_id,x,y\n"+rows)
