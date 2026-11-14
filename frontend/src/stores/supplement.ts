import {ref} from 'vue';
import {fetchPlansByRun,createSupplementPlan,type SupplementPlan} from '../api/supplement';
export function supplementStore(){
 const items=ref<SupplementPlan[]>([]);const error=ref('');const busy=ref(false);
 async function load(runId:string){busy.value=true;try{items.value=await fetchPlansByRun(runId);error.value=''}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
 async function create(body:unknown){const row=await createSupplementPlan(body);return row}
 return {items,error,busy,load,create};
}
