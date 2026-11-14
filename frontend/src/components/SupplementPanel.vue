<script setup lang="ts">
import {ref,onMounted,watch} from 'vue';
import {supplementStore} from '../stores/supplement';
import {canWrite} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import {fixed,scientific} from '../utils/format';
import Notice from './common/Notice.vue';
const props=defineProps<{runId:string}>();
const store=supplementStore();
const candidatesCsv=ref('candidate_id,x,y\n'),budget=ref(8),minSpacing=ref(5),batchSize=ref(2000);
const {error,busy,act}=useTask();
onMounted(()=>store.load(props.runId));
watch(()=>props.runId,id=>store.load(id));
const stopLabels:Record<string,string>={
 budget_exhausted:'补采名额已用完（达到预算上限）',
 no_eligible_candidate:'没有满足间距要求的可选候选点，剩余额度保留'
};
async function file(e:Event){const f=(e.target as HTMLInputElement).files?.[0];if(f)candidatesCsv.value=await f.text()}
function submit(){act(async()=>{
 await store.create({run_id:props.runId,candidates_csv:candidatesCsv.value,budget:Number(budget.value),min_spacing:Number(minSpacing.value),batch_size:Number(batchSize.value)});
 await store.load(props.runId);
})}
const mb=(b:number)=>fixed(b/1048576,2);
</script>
<template>
 <section class="supplement-panel">
  <div class="section-heading">
   <h2>补采方案 · 条件方差贪心选点</h2>
  </div>
  <p class="method-note">沿用本运行锁定的变异函数参数，按“每次补采后全体原待估点平均方差的降幅”逐个选择；仅用候选坐标做条件方差更新，候选尚无现场读数，不编造新读数。候选与已有采样、已选点保持指定间距，重合点不重复选；收益并列按点编号裁定，候选乱序结果一致。原运行预测不变。</p>
  <Notice :message="error||store.error.value"/>
  <form v-if="canWrite()" class="supplement-form" @submit.prevent="submit">
   <label>补采候选CSV（candidate_id,x,y，最多10000点，不含读数列）
    <input type="file" accept=".csv" @change="file">
    <textarea v-model="candidatesCsv" rows="6" required></textarea>
   </label>
   <div class="form-pair">
    <label>补采名额预算（1–20）<input v-model.number="budget" type="number" min="1" max="20" required></label>
    <label>最小间距 / 米（0–10000）<input v-model.number="minSpacing" type="number" min="0" max="10000" step="0.1" required></label>
   </div>
   <div class="form-pair">
    <label>分批评估批大小（1–10000）<input v-model.number="batchSize" type="number" min="1" max="10000" required></label>
   </div>
   <button :disabled="busy">计算补采方案</button>
  </form>
  <article v-for="plan in store.items.value" :key="plan.id" class="plan-card">
   <p class="eyebrow">SUPPLEMENT PLAN · {{plan.id.slice(0,8)}}</p>
   <div class="plan-summary">
    <div><small>候选 / 去重后 / 已选</small><strong>{{plan.candidate_count}} / {{plan.plan.unique_candidate_count}} / {{plan.selected_count}}</strong></div>
    <div><small>预算名额</small><strong>{{plan.budget}}</strong></div>
    <div><small>最小间距(米)</small><strong>{{fixed(plan.min_spacing,2)}}</strong></div>
    <div><small>批大小</small><strong>{{plan.batch_size}}</strong></div>
    <div><small>新增内存峰值(MB)</small><strong>{{mb(plan.peak_memory_bytes)}}</strong><span>上限128MB</span></div>
    <div><small>终止原因</small><strong :class="plan.stop_reason==='no_eligible_candidate'?'stop-warn':''">{{stopLabels[plan.stop_reason]||plan.stop_reason}}</strong></div>
   </div>
   <div class="plan-summary">
    <div><small>补采前平均方差(pp²)</small><strong>{{fixed(plan.baseline_mean_variance,6)}}</strong></div>
    <div><small>补采后平均方差(pp²)</small><strong>{{fixed(plan.final_mean_variance,6)}}</strong></div>
    <div><small>累计平均降幅(pp²)</small><strong>{{fixed(plan.total_variance_reduction,6)}}</strong></div>
    <div><small>锁定 sill/range/nugget</small><strong>{{fixed(plan.plan.locked_model.sill,4)}} / {{fixed(plan.plan.locked_model.range,4)}} / {{fixed(plan.plan.locked_model.nugget,4)}}</strong></div>
   </div>
   <p v-if="plan.plan.duplicate_candidate_ids.length" class="method-note">同坐标重复候选仅保留编号最小者，未参与选择：{{plan.plan.duplicate_candidate_ids.join('、')}}</p>
   <div class="table-wrap">
    <table>
     <thead><tr><th>选择顺序</th><th>候选点编号</th><th>x 米</th><th>y 米</th><th>步前方差均值</th><th>步后方差均值</th><th>本步收益(降幅)</th><th>选后条件数</th></tr></thead>
     <tbody>
      <tr v-for="s in plan.plan.steps" :key="s.step">
       <td>{{s.step}}</td><td>{{s.candidate_id}}</td><td>{{fixed(s.x,2)}}</td><td>{{fixed(s.y,2)}}</td>
       <td>{{fixed(s.mean_variance_before,6)}}</td><td>{{fixed(s.mean_variance_after,6)}}</td>
       <td>{{fixed(s.variance_reduction,6)}}</td><td>{{scientific(s.condition_number)}}</td>
      </tr>
      <tr v-if="!plan.plan.steps.length"><td colspan="8">无可选点，未选择任何补采点，剩余额度保留。</td></tr>
     </tbody>
    </table>
   </div>
   <p class="hash-note">输入SHA256 {{plan.plan.input_sha256}} · {{plan.plan.no_reading_note}}</p>
  </article>
  <p v-if="!store.items.value.length&&!busy" class="method-note">本运行暂无补采方案。</p>
 </section>
</template>
