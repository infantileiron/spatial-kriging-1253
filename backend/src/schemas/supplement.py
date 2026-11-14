from pydantic import BaseModel,Field
class SupplementCreate(BaseModel):
 run_id:str
 candidates_csv:str=Field(min_length=8,max_length=2_000_000)
 budget:int=Field(ge=1,le=20)
 min_spacing:float=Field(ge=0.,le=10000.)
 batch_size:int=Field(default=2000,ge=1,le=10000)
