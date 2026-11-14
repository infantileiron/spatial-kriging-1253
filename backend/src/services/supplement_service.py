import math,hashlib,json,tracemalloc
import numpy as np
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.run import KrigingRun
from ..models.supplement_plan import SupplementPlan
from .candidate_data import parse_candidates
from .ordinary_kriging import covariance

DEFAULT_BATCH_SIZE=2000
# 单次批次内最大常驻float64矩阵的元素数上限（距离/协方差等），配合DEFAULT_BATCH_SIZE控制新增内存。
BATCH_CELL_CAP=8_000_000

def _augmented(coords,sill,range_,nugget):
 distances=np.linalg.norm(coords[:,None,:]-coords[None,:,:],axis=2)
 C=covariance(distances,sill,range_,nugget)
 n=len(coords)
 return np.block([[C,np.ones((n,1))],[np.ones((1,n)),np.zeros((1,1))]])

def _variance(coords,query_coords,sill,range_,nugget):
 # 与 ordinary_kriging 同一协方差约定：C(h)=sill*exp(-h/range)+nugget*I(h=0)，C0=sill+nugget。
 A=_augmented(coords,sill,range_,nugget)
 d=np.linalg.norm(coords[:,None,:]-query_coords[None,:,:],axis=2)
 c=covariance(d,sill,range_,nugget)
 sol=np.linalg.solve(A,np.vstack([c,np.ones((1,len(query_coords)))]))
 w,mu=sol[:-1,:],sol[-1,:]
 C0=sill+nugget
 raw=C0-np.sum(c*w,axis=0)-mu
 return np.maximum(raw,0.0),raw,A

def build_supplement_plan(samples,queries,sill,range_,nugget,candidates,budget,min_spacing,
                          batch_size=DEFAULT_BATCH_SIZE,condition_limit=1e10,negative_tolerance=1e-10):
 """
 沿用已锁定的变异函数参数，按“每次补采后全体原待估点平均方差的降幅”贪心选点。
 仅使用坐标做条件方差更新；候选尚无现场读数，不编造任何 value。
 候选乱序不影响结果：输入先按 candidate_id 排序，收益并列也由最小点编号裁定。
 """
 if not (1<=budget<=20):raise ValueError("补采名额须在1–20之间")
 if not (0.<=min_spacing<=10000.):raise ValueError("最小间距须为0–10000米")
 if not (1<=batch_size<=10000):raise ValueError("批大小须在1–10000之间")
 if not math.isfinite(condition_limit) or condition_limit<=1:raise ValueError("条件数阈值无效")
 if not math.isfinite(negative_tolerance) or not 0.<negative_tolerance<=1e-8:raise ValueError("微负方差容差无效")
 if not samples or not queries:raise ValueError("缺少原采样点或待估点")
 if not candidates:raise ValueError("候选点为空")

 sample_coords=np.asarray([[p["x"],p["y"]] for p in samples],dtype=np.float64)
 query_coords=np.asarray([[p["x"],p["y"]] for p in queries],dtype=np.float64)
 C0=sill+nugget
 cutoff=negative_tolerance*max(1.,C0)

 # 候选乱序结果一致：按点编号排序后再进入全部计算。
 ordered=sorted(candidates,key=lambda r:r["candidate_id"])
 cand_ids=[r["candidate_id"] for r in ordered]
 cand_coords=np.asarray([[r["x"],r["y"]] for r in ordered],dtype=np.float64)
 if not np.isfinite(cand_coords).all():raise ValueError("候选坐标须有限")
 m=len(ordered)

 # 候选内部坐标去重：同坐标只保留编号最小者，其余整轮不可再选（不自动抖动或平均）。
 _,first_index=np.unique(cand_coords,axis=0,return_index=True)
 keep=np.zeros(m,dtype=bool);keep[first_index]=True
 duplicate_ids=[cand_ids[i] for i in range(m) if not keep[i]]
 active_index=np.where(keep)[0]

 spacing2=float(min_spacing)**2
 # 间距判定容差随坐标尺度缩放，避免平方比较的浮点误判；精确重合天然落在禁用侧。
 tol2=1e-12*max(1.0,float(np.max(sample_coords**2)))

 tracemalloc.start()
 try:
  variance,raw,A=_variance(sample_coords,query_coords,sill,range_,nugget)
  condition=float(np.linalg.cond(A))
  if not math.isfinite(condition) or condition>condition_limit:
   raise ValueError(f"锁定参数下克里金增广系统病态，条件数{condition:.3e}超阈值{condition_limit:.3e}")
  if np.min(raw)<-cutoff:
   raise ValueError("原运行方差复算出现严重负值，拒绝在该参数上制定补采方案")
  baseline=float(variance.mean())

  occupied=sample_coords.copy()                 # 已采样 + 已选补采点
  excluded=np.zeros(m,dtype=bool)              # 选中或违反间距后整轮禁用
  steps=[]
  stop_reason=None
  current_mean=baseline

  for step in range(1,budget+1):
   # 每轮重算资格：候选与“已有采样+已选点”保持指定间距，重合点不重复选。
   eligible=[]
   for idx in active_index:
    if excluded[idx]:continue
    d2=np.sum((occupied-cand_coords[idx])**2,axis=1)
    mind2=float(np.min(d2))
    # 重合点任何间距口径下都不重复选（相同浮点坐标距离恰为0；重复采样坐标会使增广系统不可识别）。
    if mind2==0.0:continue
    if mind2+tol2<spacing2:continue
    eligible.append(idx)
   if not eligible:
    stop_reason="no_eligible_candidate"
    break
   eligible=np.asarray(eligible,dtype=np.int64)

   # 分批评估：每批只实例化批大小对应的距离/协方差矩阵，控制新增内存。
   best_idx=-1;best_benefit=-np.inf
   for start in range(0,len(eligible),batch_size):
    batch=eligible[start:start+batch_size]
    b=len(batch);bc=cand_coords[batch]
    d_op=np.linalg.norm(occupied[:,None,:]-bc[None,:,:],axis=2)
    if d_op.size>BATCH_CELL_CAP:
     raise ValueError("单批矩阵规模超内存安全上限，请调小批大小")
    P=covariance(d_op,sill,range_,nugget)                          # (n,b)
    X=np.linalg.solve(A,np.vstack([P,np.ones((1,b))]))
    lam,alpha=X[:-1,:],X[-1,:]
    s=C0-np.sum(P*lam,axis=0)-alpha                                # 标量Schur项，必为正
    if not np.isfinite(s).all() or np.min(s)<=0.:
     raise ValueError("补采条件方差Schur项非正，增广系统不可识别")
    d_pq=np.linalg.norm(bc[:,None,:]-query_coords[None,:,:],axis=2)
    R=covariance(d_pq,sill,range_,nugget)                          # (b,q)
    d_oq=np.linalg.norm(occupied[:,None,:]-query_coords[None,:,:],axis=2)
    c=covariance(d_oq,sill,range_,nugget)                          # (n,q)
    r=R-lam.T@c-alpha[:,None]                                      # (b,q) 含普通克里金约束项
    reduction=r**2/s[:,None]                                       # 每个待估点的方差降幅
    benefit=reduction.mean(axis=1)                                 # 全体平均降幅
    # 编号已升序、批次保持该顺序，因此首个“非劣”候选即编号最小者。
    # 浮点近并列（对称布局下差异约机器精度）按并列处理，由点编号裁定，保证分批/乱序结果一致。
    local=int(np.argmax(benefit))
    if not math.isfinite(best_benefit) or benefit[local]>best_benefit+1e-12*max(1.0,abs(best_benefit)):
     best_benefit=float(benefit[local]);best_idx=int(batch[local])

   winner=best_idx
   # 依据实际选中后的增广系统重算条件方差（不依赖批量近似），并校验健康度。
   new_coords=np.vstack([occupied,cand_coords[winner]])
   new_variance,new_raw,new_A=_variance(new_coords,query_coords,sill,range_,nugget)
   new_condition=float(np.linalg.cond(new_A))
   if not math.isfinite(new_condition) or new_condition>condition_limit:
    raise ValueError(f"加入补采点后系统病态，条件数{new_condition:.3e}超阈值")
   if np.min(new_raw)<-cutoff:
    raise ValueError("补采后方差出现严重负值，拒绝继续")
   exact_benefit=current_mean-float(new_variance.mean())
   steps.append({
    "step":step,
    "candidate_id":cand_ids[winner],
    "x":float(cand_coords[winner,0]),
    "y":float(cand_coords[winner,1]),
    "mean_variance_before":current_mean,
    "mean_variance_after":float(new_variance.mean()),
    "variance_reduction":float(exact_benefit),
    "estimated_reduction":best_benefit,
    "condition_number":new_condition,
   })
   # 提交该点：更新占位点与增广系统，进入下一轮。
   occupied=new_coords;excluded[winner]=True
   A=new_A;current_mean=float(new_variance.mean())
  else:
   stop_reason="budget_exhausted"

  final_mean=current_mean
  _,peak=tracemalloc.get_traced_memory()
 finally:
  tracemalloc.stop()

 selected=[s["candidate_id"] for s in steps]
 fingerprint=hashlib.sha256(json.dumps({
  "sample_coords":sample_coords.tolist(),"query_coords":query_coords.tolist(),
  "candidates":ordered,"sill":sill,"range":range_,"nugget":nugget,
  "budget":budget,"min_spacing":min_spacing,
 },ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return {
  "locked_model":{"sill":float(sill),"range":float(range_),"nugget":float(nugget)},
  "budget":budget,"min_spacing":float(min_spacing),"batch_size":batch_size,
  "condition_limit":float(condition_limit),"negative_tolerance":float(negative_tolerance),
  "candidate_count":m,"unique_candidate_count":int(keep.sum()),
  "duplicate_candidate_ids":duplicate_ids,
  "baseline_mean_variance":baseline,
  "final_mean_variance":final_mean,
  "total_variance_reduction":baseline-final_mean,
  "baseline_condition_number":condition,
  "steps":steps,"selected_candidate_ids":selected,
  "stop_reason":stop_reason,
  "peak_memory_bytes":int(peak),
  "input_sha256":fingerprint,
  "no_reading_note":"补采方案只依据锁定协方差模型与坐标计算条件方差；候选点尚无现场读数，未编造任何新读数。",
 }

def create(db,body):
 run=db.get(KrigingRun,body.run_id)
 if run is None:raise HTTPException(404,"运行记录不存在")
 if run.status!="completed":raise HTTPException(422,"仅已完成运行可制定补采方案")
 result=run.result or {}
 try:
  samples=result["points"];queries=result["queries"];model=result["model"]
 except (KeyError,TypeError):raise HTTPException(422,"运行结果快照不完整，无法制定补采方案")
 try:candidates=parse_candidates(body.candidates_csv)
 except ValueError as e:raise HTTPException(422,str(e))
 # 用锁定参数与原输入复算基线条件方差，并与运行底稿留存的预测方差逐点核对，
 # 不一致说明快照被改动，拒绝在该运行上制定补采方案（原运行预测本身不被修改）。
 recorded={p["query_id"]:p["variance"] for p in result.get("kriging",{}).get("predictions",[])}
 if set(recorded)!={q["query_id"] for q in queries}:
  raise HTTPException(422,"运行预测快照与待估点不一致，无法复算条件方差")
 sample_coords=np.asarray([[p["x"],p["y"]] for p in samples],dtype=np.float64)
 query_coords=np.asarray([[p["x"],p["y"]] for p in queries],dtype=np.float64)
 condition_limit=result.get("config",{}).get("condition_limit",1e10)
 negative_tolerance=result.get("config",{}).get("negative_tolerance",1e-10)
 try:
  baseline_var,_,_=_variance(sample_coords,query_coords,model["sill"],model["range"],model["nugget"])
 except Exception as e:
  raise HTTPException(422,f"锁定参数下基线条件方差复算失败：{e}")
 recorded_mean=float(np.mean([recorded[q["query_id"]] for q in queries]))
 if abs(float(baseline_var.mean())-recorded_mean)>1e-10*max(1.,abs(recorded_mean)):
  raise HTTPException(422,"锁定参数复算的基线方差与运行底稿不一致，拒绝制定补采方案")
 try:
  plan=build_supplement_plan(
   samples,queries,model["sill"],model["range"],model["nugget"],candidates,
   body.budget,body.min_spacing,body.batch_size,
   condition_limit=condition_limit,negative_tolerance=negative_tolerance)
 except ValueError as e:
  raise HTTPException(422,str(e))
 row=SupplementPlan(
  id=str(uuid4()),run_id=run.id,budget=body.budget,min_spacing=body.min_spacing,
  candidate_count=plan["candidate_count"],selected_count=len(plan["steps"]),
  baseline_mean_variance=plan["baseline_mean_variance"],
  final_mean_variance=plan["final_mean_variance"],
  total_variance_reduction=plan["total_variance_reduction"],
  peak_memory_bytes=plan["peak_memory_bytes"],batch_size=body.batch_size,
  stop_reason=plan["stop_reason"],plan=plan)
 db.add(row);db.commit()
 return row

def list_for_run(db,run_id):
 if db.get(KrigingRun,run_id) is None:raise HTTPException(404,"运行记录不存在")
 rows=db.scalars(select(SupplementPlan).where(SupplementPlan.run_id==run_id)
                 .order_by(SupplementPlan.created_at.desc())).all()
 return [serialize_plan(r) for r in rows]

def detail(db,ident):
 row=db.get(SupplementPlan,ident)
 if row is None:raise HTTPException(404,"补采方案不存在")
 return serialize_plan(row)

def serialize_plan(row):
 from ..models.common import serialize
 return serialize(row)
