from sqlalchemy import String,Text,JSON,Integer,Double,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class SupplementPlan(RecordMixin,Base):
 __tablename__="supplement_plans"
 run_id:Mapped[str]=mapped_column(ForeignKey("runs.id"))
 budget:Mapped[int]=mapped_column(Integer)
 min_spacing:Mapped[float]=mapped_column(Double)
 candidate_count:Mapped[int]=mapped_column(Integer)
 selected_count:Mapped[int]=mapped_column(Integer)
 baseline_mean_variance:Mapped[float]=mapped_column(Double)
 final_mean_variance:Mapped[float]=mapped_column(Double)
 total_variance_reduction:Mapped[float]=mapped_column(Double)
 peak_memory_bytes:Mapped[int]=mapped_column(Integer)
 batch_size:Mapped[int]=mapped_column(Integer)
 stop_reason:Mapped[str]=mapped_column(String(40))
 plan:Mapped[dict]=mapped_column(JSON,default=dict)
