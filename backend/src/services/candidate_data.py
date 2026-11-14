import csv,io,math

MAX_CANDIDATES=10000
# 补采候选只有点位坐标；外业读数尚未采集，系统不编造任何 value 字段。
def parse_candidates(text):
 rows=list(csv.DictReader(io.StringIO(text)))
 if not rows or not {"candidate_id","x","y"}.issubset(rows[0]):
  raise ValueError("候选CSV列不完整，需要candidate_id,x,y（不含读数列）")
 # 补采读数只能来自现场实测；上传阶段禁止携带任何读数列，避免被误用为编造读数。
 if any((k or "").strip().lower() in {"value","reading","观测值","读数","含水率"} for k in rows[0].keys()):
  raise ValueError("候选点CSV不得包含读数/含水率列；补采方案只接受坐标，读数须现场采集后另行入库")
 if len(rows)>MAX_CANDIDATES:
  raise ValueError(f"候选点上限{MAX_CANDIDATES}个，当前{len(rows)}个，请分批或精简候选")
 result=[];ids=set()
 for row in rows:
  ident=(row.get("candidate_id") or "").strip()
  if not ident or len(ident)>80 or ident in ids:
   raise ValueError("候选点ID为空、过长或重复")
  values={}
  for field in ["x","y"]:
   try:value=float(row.get(field))
   except Exception:raise ValueError("候选坐标须为数值")
   if not math.isfinite(value):raise ValueError("候选坐标须有限")
   if abs(value)>10000:raise ValueError("局部平面坐标绝对值须≤10000米")
   values[field]=value
  ids.add(ident);result.append({"candidate_id":ident,"x":values["x"],"y":values["y"]})
 return result
