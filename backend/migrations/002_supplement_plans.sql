-- 补采方案聚合：对已完成克里金运行制定条件方差贪心补采计划，不修改原运行预测。
-- 方案明细（选择顺序、每步收益、终止原因、锁定参数快照）存入 JSON；汇总指标另开 DOUBLE/INTEGER 列。
CREATE TABLE IF NOT EXISTS supplement_plans (
 id VARCHAR(36) NOT NULL PRIMARY KEY,
 created_at DATETIME NOT NULL,
 run_id VARCHAR(36) NOT NULL,
 budget INTEGER NOT NULL,
 min_spacing DOUBLE NOT NULL,
 candidate_count INTEGER NOT NULL,
 selected_count INTEGER NOT NULL,
 baseline_mean_variance DOUBLE NOT NULL,
 final_mean_variance DOUBLE NOT NULL,
 total_variance_reduction DOUBLE NOT NULL,
 peak_memory_bytes INTEGER NOT NULL,
 batch_size INTEGER NOT NULL,
 stop_reason VARCHAR(40) NOT NULL,
 plan JSON NOT NULL,
 CONSTRAINT fk_supplement_plans_run FOREIGN KEY (run_id) REFERENCES runs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
