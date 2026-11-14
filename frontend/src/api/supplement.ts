import {request} from "./client";
export interface SupplementStep{
 step:number;candidate_id:string;x:number;y:number;
 mean_variance_before:number;mean_variance_after:number;
 variance_reduction:number;estimated_reduction:number;condition_number:number
}
export interface SupplementPlan{
 id:string;run_id:string;budget:number;min_spacing:number;batch_size:number;
 candidate_count:number;selected_count:number;baseline_mean_variance:number;
 final_mean_variance:number;total_variance_reduction:number;peak_memory_bytes:number;
 stop_reason:string;created_at:string;
 plan:{locked_model:{sill:number;range:number;nugget:number};
  unique_candidate_count:number;duplicate_candidate_ids:string[];
  baseline_condition_number:number;steps:SupplementStep[];selected_candidate_ids:string[];
  input_sha256:string;no_reading_note:string}
}
export const fetchPlansByRun=(runId:string)=>request<SupplementPlan[]>(`/supplement-plans/by-run/${runId}`);
export const createSupplementPlan=(body:unknown)=>request<SupplementPlan>("/supplement-plans","POST",body);
