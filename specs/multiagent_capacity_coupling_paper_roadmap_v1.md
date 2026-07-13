# Multi-Agent Capacity–Coupling Paper Roadmap v1

> **Recurrent parallelism update (2026-07-12):** The forward research line is no longer another route heuristic or direct Qwen router. It is a fixed-state recurrent agent field: $M$ weight-tied local agents update in parallel for $T$ rounds under fixed $B=MT$, with coupling depth determining required recurrence. See [Recurrent Parallel Agent Reasoning](multiagent_recurrent_parallel_reasoning_v1.md).

> **Structural confirmation update (2026-07-11):** A new 200-instance one-shot confirmation rejected the current independent-factorization free-lunch candidate: `over_low` solve was 0.92 versus 1.00 for equal-memory controls, and failure-penalized work ratio was 1.551. Coupling boundary and coordination necessity passed, but route identifiability failed. Do not launch the planned Qwen confirmatory grid from the earlier development result. The authorized next line is [tail-risk-aware factorization](multiagent_tail_risk_factorization_contract_v1.md). Full closeout: [CLOSEOUT.md](../results/multiagent_structural_confirmatory/CLOSEOUT.md).

> **Cross-substrate update (2026-07-12):** Community SAT independently replicated the conditional-saving/tail-loss/coupling pattern. The strongest current paper line is now a symbolic resource-evaluation boundary—[When Factorized Agent Search Fails](../results/multiagent_cross_substrate_tail_risk/SUMMARY.md)—not a positive LLM-team advantage.

> **Route-confirmation update (2026-07-12):** The only secondary SAT route signal failed a preregistered 200-instance confirmation (`0.660` versus `0.620`, one-sided exact $p=0.225$; penalized-work ratio `0.972`, CI crossing one). `SAT_ROUTE_CONFIRMATION_NO_GO` supersedes the route-development suggestion. Do not launch Qwen target routing from the earlier development signal. See [route closeout](../results/multiagent_sat_route_confirmation/CLOSEOUT.md).

> **Capacity-valid routing update (2026-07-12):** The failed frozen deepest policy mixed target priority with out-of-window NACKs. A new matched-window policy—validity first, deepest priority second—passed an exposed-pool development gate and independently reproduced on 200 new SAT instances. It solved 0.975, used 0.339× the equal-memory monolith's penalized work, and reduced $q$ below $q^*$; however, the conservative solve-NI CP upper bound was 0.05184 > 0.05. The current result is a symbolic `SAT_MATCHED_ROUTE_CONFIRMATION_ONLY`, not an LLM headline. See [capacity-valid synthesis](../results/multiagent_capacity_valid_route_tail_control/SUMMARY.md).

> **Graph replication update (2026-07-12):** The same matched-window mechanism passed all eight gates on a new zero-overlap graph-color pool. Pooled-over solve was 0.990 for both proposed and equal-memory monolith, proposed work was 0.373× monolith, and the solve-NI CP upper bound was 0.0466. This yields `GRAPH_MATCHED_ROUTE_STRONG_CONFIRMATION` and a cross-substrate symbolic tail-control contribution. Qwen remains unnecessary and unauthorized. See [graph closeout](../results/multiagent_graph_matched_route_confirmation/CLOSEOUT.md).

**Primary paper line:** Multi-Agent Frozen-LLM Search

- 日期：2026-07-11
- 推荐标题：**When Do LLM Agent Teams Beat a Monolith? Capacity, Coupling, and Coordination in Bounded Search**
- 核心形式：理论 phase diagram + controlled distributed search + real frozen-Qwen paired validation
- 目标：解释 multi-agent gain 何时出现、来自哪里、何时消失，而不是笼统声称“更多 agents 更好”
- 技术基础：[Reversible-memory foundation roadmap](reversible_search_research_paper_roadmap_v1.md)
- 第一性原理解释：[Where Is the Multi-Agent Free Lunch?](multiagent_free_lunch_research_memo_v1.md)

> **Execution update:** The preregistered symbolic core 2×2 preflight is complete and GO. It supports distributed aggregate capacity against `monolith-R`, but team-CBJ exactly matches `monolith-MR` and `centralized-sharded-MR`. High coupling primarily increases coordination cost rather than immediately destroying solve rate. See [Core 2×2 Preflight Summary](../results/multiagent_core_2x2_preflight/PREFLIGHT_SUMMARY.md).

> **Real-Qwen development update:** A 64-prompt Qwen3.5-4B decision gate passed after versioning a compact deepest-culprit route contract. In the subsequent 32-episode branch×route development run, symbolic-branch/Qwen-route solved 0.750 versus 0.625 for the all-symbolic policy, while Qwen-branch policies solved only 0.125–0.250 because of call-cap, exhaustion, and fail-closed branch errors. This is a development signal, not a confirmatory effect. The next work item is branch-policy/search-control repair, not the 50-instance-per-cell headline run. See [GPU4–7 Overnight Summary](../results/multiagent_overnight_gpu4_7/SUMMARY.md).

> **Free-lunch scope:** Current evidence confirms horizontal aggregate-capacity scaling only. It does not show an equal-total-resource architecture advantage. The strong research target is now independent local factorization plus event-triggered Qwen routing: reduce superlinear total search work and invoke the LLM only on sparse cross-agent conflicts. This requires replacing the current global-trail/global-suffix team loop before confirmatory evaluation.

---

## 1. 核心判断

同意把论文主线明确设为 **multi-agent**。

最强的科学问题不是：

> 多 agent 是否平均比单 agent 好？

而是：

> **在每个 agent 的 working memory 有容量上限时，问题的可分解性、跨分区 coupling 和协调策略如何共同决定 team 是否胜过 monolith？**

推荐中心结论：

> Multi-agent search gains arise from a capacity–coupling interaction: teams help when partitioning moves each local search below the per-agent memory wall while separator communication remains bounded; the advantage disappears when a monolith already fits, local subproblems overflow, or cross-agent coupling dominates.

这条主线能够统一当前所有结果：

1. v3–v5：给出单 register 容量和 reliability 基础；
2. Item076：bounded team 在容量交叉区胜过 monolith；
3. Item111：team 对 `monolith-R` 正向，对 `monolith-MR` mixed；
4. dense graph-color：CBJ 不产生统一 solve-rate gain，说明 coordination advantage 是 structure-dependent；
5. real-Qwen team pilot：当前 underpowered/negative，说明 end-to-end agent routing 是尚未完成的关键层；
6. v6 proxy：高 coupling 下没有 D1 优势，符合“coupling overload”边界，而不是 multi-agent 主线终止。

---

## 2. 推荐标题与一句话主张

### 2.1 首选标题

**When Do LLM Agent Teams Beat a Monolith? Capacity, Coupling, and Coordination in Bounded Search**

其他候选：

1. **The Capacity–Coupling Phase Diagram of Multi-Agent Language-Model Search**
2. **Beyond a Single Agent's Memory: Structure-Dependent Gains in Multi-Agent Search**
3. **Bounded Memory, Distributed Reasoning: When Agent Teams Outperform a Monolith**
4. **Multi-Agent Search Beyond the Monolithic Memory Wall**

### 2.2 目标 headline

只有 real-Qwen confirmatory gates 通过后才能使用：

> A bounded team of frozen language-model agents outperforms a monolithic agent only in a predictable phase: global search exceeds one agent's memory, every local partition remains below that memory wall, and separator communication remains within a bounded coordination channel.

### 2.3 保守 headline

如果 team 只胜过 `monolith-R`，但不能胜过 `monolith-MR`：

> Multi-agent partitioning scales aggregate bounded memory and preserves solve rate beyond a single agent's capacity, but does not provide an architectural advantage over a monolith with the same total memory.

### 2.4 强 headline

如果 team 在预注册 sweet spot 中显著胜过 `monolith-MR`：

> Structured decomposition provides an advantage beyond raw total memory: local memory reduces interference and sparse separator coordination is cheaper than centralized search.

---

## 3. 当前证据地图

## 3.1 Single-agent bounded-search positive

Real Qwen3.5-4B、Reasoning Gym official graph_color、30 个需 backtracking 实例：

| R | Solve rate |
|---:|---:|
| 0 | 0.000 |
| 2 | 0.167 |
| 4 | 0.600 |
| 8 | 0.767–0.800 |
| 16 | 0.833 |

来源：

- [Real-Qwen graph-color ceiling run](../results/externalization_validation_v0/graph_color_ceiling_llm.json)
- [Externalization execution contract](externalization_paper_full_execution_v1.md)

它证明：bounded recovery view 对 frozen-Qwen-guided search 有价值。

它不证明：

- multi-agent team 胜过 monolith；
- list register 等于 latent VSA；
- total-token efficiency 已完成；
- agent routing 是 autonomous。

## 3.2 No-LLM capacity-intersection positive

Item076 的最终 capacity intersection：

- intersection size：768；
- team solve rate：0.9948；
- monolith-R solve rate：0.0；
- same R、same official-scored instances；
- 但样本条件是 monolith-fail 且 static-team-feasible intersection。

来源：

- [Multi-agent closeout](../results/rung1_multiagent_solvability/closeout.json)
- [Item076 contract](../results/experiment_items/item_076_rung1_multiagent_solvability.json)

正确解释：

- **存在可分解的容量区间**，team 可以把 global load 分解到 local registers 中。

不能作为最终 headline 的原因：

- 条件化选择了 monolith-fail/team-feasible intersection；
- no-LLM；
- 未匹配 `monolith-MR` 总 memory；
- 不能估计自然分布上的无条件 effect。

## 3.3 Coordination is structure-dependent

Item076 dense graph_color：

- complete CBJ 与 complete chronological 在所有预算均 solve rate 1.0；
- work slopes 接近；
- 最终 verdict：`structure_dependent_scoping`。

这不是坏结果。它给出非常重要的边界：

> CBJ/agent coordination 不应在 dense, short-distance conflicts 上产生统一优势；其收益应集中在 sparse separators 和 distant cross-block culprits。

## 3.4 K=2 structural multi-agent result

Item111：

- team-CBJ 胜 `monolith-R`：4/4 cells；
- team-CBJ 对 `monolith-KR`：3/4 cells match/beat，`v16,R2` 小幅失败；
- CBJ 的 cross-block messages 和 retractions 在所有 symbolic cells 低于 chronological；
- autonomous model route parse/valid 高，但 exact route 仅约 0.32–0.51；
- real generated route 仍是 secondary gap。

来源：

- [Item111 K=2 structural result](../results/experiment_items/item_111_kvcache_multiagent_structural_k2.json)

正确解释：

- per-agent capacity scaling有信号；
- coordination-cost advantage比 solve-rate advantage更稳定；
- equal-total-memory advantage尚未稳定；
- agent-generated routing是主要瓶颈。

## 3.5 Real-Qwen team pilot

当前 pilot：

- `K=2`；
- 每个 arm 只有 1 个实例；
- team 失败，`monolith-R` 和 `monolith-KR` 成功；
- 明确标记为 underpowered/harness pilot。

来源：

- [Real-LLM multi-agent pilot](../results/externalization_validation_v0/multiagent_real_llm_v1_pilot.json)

该结果不能用于正负 headline，只能用于定位：

- cross-block recovery；
- route quality；
- call cap；
- partition quality；
- centralized controller dependence。

## 3.6 v5 redundancy 与 v6 proxy

- v5：同负载 replicas 提升 retrieval reliability，但使用了 N 倍 memory；
- v6：proxy D1 无 Holm win，高 coupling 无优势。

在 multi-agent 论文中：

- redundancy 是 secondary mechanism；
- v6 是 coupling-overload / failed-proxy boundary；
- 两者都不是主 headline。

来源：

- [SPEC v5](../results/capacity/SPEC_v5_run_summary_qwen3_fp32.md)
- [SPEC v6](../results/downstream/SPEC_v6_run_summary.md)

---

## 4. Multi-agent gain 必须分解成四种机制

论文不能把所有提升统称为“collaboration”。必须逐一隔离。

### 4.1 Capacity aggregation

M 个 agents、每个 register R，总 memory 约为 MR。

比较：

- team-M×R vs `monolith-R`：测试 aggregate capacity；
- team-M×R vs `monolith-MR`：测试 architecture advantage beyond total memory。

如果只通过第一项，正确措辞是：

> distributed aggregate capacity

而不是：

> emergent collaboration

### 4.2 Load splitting / decomposition

将 global search load $L_G$ 分成 local loads $L_1,\ldots,L_M$。

收益条件：

$$
\max_i L_i<C_{\mathrm{agent}}.
$$

需要 `centralized-sharded` control：

- 一个 monolithic Qwen；
- 同样的 M 个 local views；
- 同样的 M 个 local registers；
- 顺序处理所有 blocks。

若 team 与 centralized-sharded 相同，收益来自 decomposition，不来自 agent identity。

### 4.3 Coordination

比较：

- no coordination；
- broadcast；
- chronological rollback；
- conflict-directed backjumping；
- oracle route；
- model-generated route。

稳定指标优先级：

1. solve rate；
2. cross-block messages；
3. total retractions；
4. communication tokens；
5. synchronization rounds。

### 4.4 Redundancy

replicated agents处理同一 local load，用于降低 decision/retrieval error。

这与 partition team 不同：

- partition 增加 aggregate capacity；
- replication 增加 reliability；
- 两者 resource scaling 不同。

建议作为 secondary section，不要与主 capacity-decomposition claim 混在一个变量中。

---

## 5. Capacity–Coupling Phase Diagram

## 5.1 变量定义

使用 M 表示 agent 数，避免与 action branching factor K 混淆。

- $C$：单 agent register capacity；
- $L_G$：global/monolithic live search load；
- $L_i$：agent i 的 local live load；
- $S$：separator/boundary state complexity；
- $C_{\mathrm{comm}}$：共享 coordination channel capacity；
- $\rho$：cross-partition coupling ratio；
- $B$：total operator budget；
- $R$：显式 register entries 或经校准的 fixed-memory capacity。

定义三个无量纲 stress axes：

$$
\alpha=\frac{L_G}{C},\qquad
\beta=\frac{\max_iL_i}{C},\qquad
\gamma=\frac{S}{C_{\mathrm{comm}}}.
$$

## 5.2 预测区域

### Region A：Monolith-sufficient

$$
\alpha<1.
$$

单 agent 已经能装下 global load。team 不应产生 solve advantage，额外 communication 可能有害。

### Region B：Distributed sweet spot

$$
\alpha>1,\qquad \beta<1,\qquad \gamma<1.
$$

这是主论文期待的 team advantage 区域：

- monolith-R 超容量；
- 每个 local agent 未超容量；
- separator 可用 bounded messages 协调。

### Region C：Local overflow

$$
\beta>1.
$$

分区后 local task 仍超过单 agent capacity，team 与 monolith 都会失败，除非增加 R 或 agent 数。

### Region D：Coordination overload

$$
\gamma>1.
$$

跨分区 coupling 太强；communication、rollback cascade 和 inconsistent commitments 主导，team 可能低于 monolith-MR。

v6 的高-rho负结果应该放在这个区域解释。

## 5.3 Headline phase condition

最简单可检验预测：

$$
\Delta_{\mathrm{team-monoR}}>0
\quad\text{iff approximately}\quad
\alpha>1,\ \beta<1,\ \gamma<1.
$$

更强预测：

$$
\Delta_{\mathrm{team-monoMR}}>0
$$

只在 decomposition 降低 interference/branching 且 coordination cost 足够小的区域出现。

## 5.4 Cost model

Aggregate compute：

$$
T_{\mathrm{team,total}}=\sum_{i=1}^{M}T_i+T_{\mathrm{comm}}.
$$

Parallel latency：

$$
T_{\mathrm{team,parallel}}\approx \max_iT_i+T_{\mathrm{sync}}.
$$

必须分别报告：

- total tokens；
- max per-agent tokens；
- total LLM calls；
- parallel rounds；
- communication tokens；
- total mutable memory；
- peak per-agent memory。

不能用 parallel latency 掩盖 M 倍 aggregate compute。

---

## 6. 论文方法：Bounded Multi-Agent Backjumping Search

### 6.1 Agent contract

每个 agent 仅看到：

- local block frontier；
- local constraints；
- boundary assignments；
- bounded local register R；
- bounded incoming nogoods/messages。

每个 agent 输出：

- branch value；
- local rollback target；
- optional cross-block culprit/message。

### 6.2 Coordinator contract

必须明确 autonomy level。

| Tier | Controller owns | Agent owns | 论文用途 |
|---|---|---|---|
| T0 | 所有 branch/route/search | 无 | symbolic ceiling |
| T1 | propagation、conflict detection、undo | branch + local route | 当前 real-Qwen主可行层 |
| T2 | message delivery + official validation | branch、local conflict、route | 强 multi-agent evidence |
| T3 | 仅 environment transitions | 全部 reasoning/coordination | 长期目标 |

当前代码属于 T1，不得写成 fully autonomous decentralized agents。

### 6.3 Route-source × branch-source factorial

必须把 agent failure 拆开：

| Branch source | Route source | 作用 |
|---|---|---|
| symbolic | symbolic | algorithm/partition ceiling |
| Qwen | symbolic | branch-quality isolation |
| symbolic | Qwen | coordination-quality isolation |
| Qwen | Qwen | end-to-end multi-agent |

禁止 silent oracle fallback。parse/invalid route 必须成为显式 failure status。

### 6.4 Register substrate

主论文可以先使用 audited explicit bounded lists，因为 multi-agent 是主线。

但必须准确写：

- bounded per-agent visible/recovery window；
- central symbolic state仍存在；
- 不是 fully latent fixed-D stack。

Self-decoding VSA register 是增强项：

- 若 bridge 通过，可加入 compressed-memory section；
- 若不通过，不阻塞 multi-agent phase-diagram paper；
- 不得把 list R 与 VSA W 直接等同。

---

## 7. 公平性控制：论文成败的中心

### 7.1 三个 monolith controls

1. **monolith-R**：与每个 agent 相同的 memory；测试 aggregate capacity scaling。
2. **monolith-MR**：与 team 相同的 total memory；测试 decomposition beyond raw capacity。
3. **centralized-sharded-MR**：一个 Qwen 使用与 team 相同的 M local views/registers；测试 agent architecture beyond partitioning。

### 7.2 Information parity

- team 与 centralized control 看到相同 constraints、boundary assignments 和 local state；
- monolith-global 看到 full current assignment，但不能看到额外 oracle culprit；
- 所有 arms 使用相同 official instance；
- hidden fallback、oracle target、full trail exposure 必须逐字段审计。

### 7.3 Compute parity

报告 anytime/Pareto curves，而非只选一个 cap：

- solve vs total tokens；
- solve vs total calls；
- solve vs node budget；
- solve vs communication tokens；
- solve vs wall-clock parallel rounds。

允许 solved arm 提前停止，不做虚假 padding；使用 AUC 和 budget-to-solve 比较。

### 7.4 Selection discipline

最终 confirmatory pool 禁止条件化于：

- monolith fail；
- team feasible；
- team solve；
- large CBJ gain。

正确流程：

1. calibration split 定义 $\alpha,\beta,\gamma$ bins；
2. freeze generator/config；
3. 在 independent test split 无条件读取 arm differences。

Item076 intersection positive保留为 mechanism existence proof，不作为 population headline。

---

## 8. Controlled Benchmark 设计

## 8.1 正交轴

需要独立控制：

- M：`{1,2,4,6}` agents；
- per-agent R：`{2,4,8,16}`；
- global load/depth；
- local load；
- separator size；
- cross-edge ratio $\rho$；
- total edge density；
- node/call/token budget。

### Hard generation rules

- 同 seed 跨 rho 保持 total edges 不变；
- global depth 与 separator size 的相关性低；
- local load 与 rho 不共线；
- 每个主 cell 都能在无 arm 信息时生成；
- report correlations/VIF；
- official global scoring。

已有可复用基础：

- [Separator scaling harness](../results/rung1_separator_scaling/results.json)
- [Fixed-density coupled-coloring harness](../experiments/downstream/dist_coloring.py)

## 8.2 Core 2×2 confirmatory design

第一版 real-Qwen 不要直接跑巨大 grid。先做：

- Capacity stress：monolith under-capacity vs over-capacity/local-fit；
- Coupling：low separator vs high coupling。

固定：

- `M=4`；
- `R=8`；
- same task size family；
- 50 paired test instances/cell；
- 同一个 frozen Qwen backend。

四个 cells：

| Cell | Capacity | Coupling | Prediction |
|---|---|---|---|
| A | monolith fits | low | no team gain |
| B | global exceeds R, locals fit | low | maximal team gain |
| C | global exceeds R, locals fit | high | gain shrinks/reverses |
| D | locals exceed R | low/high | team also collapses |

## 8.3 Arms in core design

Primary：

1. team-CBJ；
2. team-chronological；
3. monolith-R；
4. monolith-MR；
5. centralized-sharded-MR。

Secondary：

6. team-no-coordination；
7. team-broadcast；
8. symbolic-route ceiling；
9. Qwen-route end-to-end。

---

## 9. Real-Qwen 执行计划

## Phase 0：No-LLM phase-map calibration

目标：只确定 bins，不读取 headline arm。

必须 PASS：

- fixed density；
- axis independence；
- monolith under/over capacity cells都存在；
- local-fit 与 local-overflow cells都存在；
- low/high coupling separation明确；
- CBJ/chrono reference completeness。

## Phase 1：Endpoint and route-quality gates

在少量 dev instances 上测：

- parse rate；
- valid branch rate；
- valid route rate；
- exact route vs symbolic reference；
- no oracle fallback；
- T1 controller state exposure audit；
- aggregate token logging。

Gate：

- parse ≥0.95；
- valid ≥0.90；
- route exactness达到预注册最低线，或明确将 symbolic route 设为主 method、Qwen route 作为 secondary gap。

## Phase 2：Core 2×2 confirmatory

- 4 cells；
- 50 paired instances/cell；
- 5 primary arms；
- temperature 0；
- official scoring；
- aggregate total-token accounting；
- complete failure taxonomy。

这是论文最重要的一次 run。

## Phase 3：Scaling only after interaction passes

扩展：

- `M={2,4,6}`；
- `R={4,8,16}`；
- more rho/separator points；
- capacity phase boundary；
- second Qwen scale。

若 Phase 2 不出现 capacity × coupling interaction，不启动大 scaling。

## Phase 4：External validity

优先顺序：

1. Reasoning Gym graph_color；
2. AgentsNet direct formula graph coloring；
3. distributed CSP/Sudoku 或 zebra（只有 adapter 与 power gate 完成后）。

至少两个 substrate 才能使用一般性 multi-agent headline。

---

## 10. 统计计划

## 10.1 Primary family

建议只预注册四个 primary hypotheses：

### H1 — Single-agent capacity relief

在 low-coupling capacity-gap cell：

$$
\text{team-CBJ}>\text{monolith-R}.
$$

解释：aggregate distributed capacity。

### H2 — Beyond total memory

同 cell：

$$
\text{team-CBJ}>\text{monolith-MR}.
$$

解释：decomposition/locality beyond raw memory。

### H3 — Capacity × coupling interaction

$$
(\Delta_{\mathrm{team-monoMR}})_{\mathrm{low\ coupling}}
>
(\Delta_{\mathrm{team-monoMR}})_{\mathrm{high\ coupling}}.
$$

这是论文核心机制检验。

### H4 — Coordination efficiency

在 both-solve 或 censor-aware analysis 中：

$$
\text{CBJ messages/retractions}<\text{chronological}.
$$

四个 primary tests 做 Holm correction。

## 10.2 Tests

- solve：paired exact McNemar；
- capacity×coupling：paired interaction/randomization test 或 mixed-effects logistic model；
- tokens/messages/retractions：paired bootstrap + permutation test；
- time-to-solve：survival analysis，unsolved 作为 right-censored；
- models/tasks：hierarchical random effects；
- 同时报告 risk difference、odds ratio、95% CI。

## 10.3 Power

- 每 primary cell 至少 50 paired instances；
- run 前基于 discordant-pair effect 做 exact power simulation；
- 不再依赖 8-instance、56-family 设计；
- confirmatory test 只读一次。

---

## 11. Kill Gates 与诚实分叉

### G0 — Generator validity

- axes独立；
- density fixed；
- bins可分；
- 不按 arm outcome选实例。

FAIL：停止 real-Qwen。

### G1 — Capacity existence

- monolith-R 在 capacity-gap cell 明显下降；
- team local loads 确实低于 R；
- local-overflow cell team也下降。

FAIL：当前任务没有能力检验 capacity claim，重新校准但不得看 confirmatory outcomes。

### G2 — Team vs monolith-R

PASS：可声称 distributed aggregate capacity。

FAIL：multi-agent capacity headline终止。

### G3 — Team vs monolith-MR

PASS：可声称 decomposition beyond total memory。

FAIL：必须收窄为 aggregate capacity；不能写 emergent collaboration。

### G4 — Coupling interaction

PASS：phase-diagram thesis成立。

FAIL：只能报告 task-specific team result，不能声称 structure-dependent law。

### G5 — Real-Qwen end-to-end

- Qwen branch + Qwen route；
- no oracle fallback；
- n≥50/cell；
- route validity gate通过。

FAIL：论文只能是 symbolic/mechanism paper，不能以 LLM multi-agent 为 headline。

### G6 — External validity

第二 substrate 复现方向。

FAIL：scope 到 graph coloring。

---

## 12. v5 redundancy 在 multi-agent 论文中的位置

建议增加一个窄 secondary section：

**Two ways teams scale bounded memory**

1. **Partitioning**：不同 agents 存不同 search state，扩大 aggregate capacity；
2. **Replication**：不同 agents 存相同 state，提高 reliability。

但必须做 total-memory controls：

- M×D replicated team；
- one MD monolith；
- M×D/M replicas；
- majority/random/confidence aggregation。

若 same-total-memory 后没有 gain：

- replication 是 reliability-for-memory tradeoff；
- 不作为独立 multi-agent novelty。

---

## 13. 论文主图

### Figure 1 — Capacity–Coupling Phase Diagram

横轴 $\alpha=L_G/C$，纵轴 coupling/separator stress $\gamma$，颜色表示 team-minus-monolith solve gap。

标出：

- monolith-sufficient；
- distributed sweet spot；
- local overflow；
- coordination overload。

### Figure 2 — Fair Capacity Controls

同一 cells 比较：

- team-M×R；
- monolith-R；
- monolith-MR；
- centralized-sharded-MR。

这是判断“更多 memory”还是“架构优势”的核心图。

### Figure 3 — Coupling Sweep

固定 density，画 team gap vs rho/separator size；叠加 messages/retractions。

### Figure 4 — Coordination Mechanisms

CBJ、chrono、broadcast、no-coordination 的：

- solve rate；
- messages；
- retractions；
- total tokens。

### Figure 5 — Branch × Route Factorial

symbolic/Qwen branch × symbolic/Qwen route，显示失败来自 decision 还是 coordination。

### Figure 6 — Real-Qwen Anytime Curves

team 与三个 monolith controls 的 solve-vs-total-token、solve-vs-calls、solve-vs-parallel-round curves。

### Figure 7 — Holds-Here / Not-There Map

- sparse separator：coordination gain；
- dense graph：CBJ≈chrono；
- high coupling：team loses；
- capacity gap：team beats monolith-R；
- equal total memory：mixed/conditional。

负结果成为 phase diagram 的边界，而不是被隐藏。

---

## 14. 推荐论文结构

1. **Introduction**
   - multi-agent gains缺乏资源与结构解释；
   - 提出 capacity–coupling thesis。
2. **Problem Definition**
   - per-agent capacity、local/global load、separator、communication、fairness。
3. **Theory: Capacity–Coupling Phase Diagram**
   - sweet spot 与 failure regions；
   - aggregate vs equal-total-memory predictions。
4. **Bounded Multi-Agent Search Architecture**
   - agent views、registers、CBJ messages、autonomy tiers。
5. **Controlled Symbolic Validation**
   - orthogonal axes；
   - team/monolith controls；
   - holds-here/not-there map。
6. **Real Frozen-Qwen Validation**
   - branch×route factorial；
   - core 2×2；
   - official scoring。
7. **Efficiency and Fairness**
   - total tokens、parallel latency、memory、communication。
8. **Redundancy as a Secondary Scaling Mechanism**
9. **Limitations**
   - symbolic coordinator；
   - graph-color scope；
   - explicit registers vs dense VSA。
10. **Conclusion**

---

## 15. 审稿人质疑与预先防御

| 质疑 | 必须提供的证据 |
|---|---|
| team只是用了 M 倍 memory | `monolith-MR` control |
| team只是看了更小 prompt | `centralized-sharded-MR` control |
| team只是并行用了 M 倍 compute | aggregate tokens/calls 与 parallel latency 分开 |
| 你挑了 monolith fail 的实例 | independent unconditioned confirmatory pool |
| coordinator 才是真正 solver | autonomy tier + branch×route factorial |
| route 使用 oracle fallback | fail-closed parsing，无 silent fallback |
| CBJ 不是普遍更好 | dense negative明确写入 phase map |
| rho 改变了密度 | fixed-density generator audit |
| multi-agent 是同一个模型重复调用 | 明确 system architecture claim，不声称 cognitive diversity |
| equal-total-memory 下无优势 | scope 为 distributed aggregate capacity，不写 collaboration advantage |
| real-Qwen pilot失败 | pilot underpowered；full preregistered n≥50 read 决定 headline |

---

## 16. 投稿分叉

### Strong path：G2–G6 全通过

标题使用 capacity–coupling phase diagram；目标 ICLR/NeurIPS/ICML 风格主会。

主张：

- team advantage可预测；
- 超越 `monolith-MR`；
- real Qwen；
- 两 substrate；
- coordination cost有机制解释。

### Moderate path：胜 monolith-R，但不胜 monolith-MR

主张收窄：

> Multi-agent systems scale bounded working memory through partitioned capacity, but do not exhibit an advantage beyond equal total memory.

仍可能成为一篇好的 honest empirical paper，尤其若 phase boundary 与 real-Qwen curves清晰。

### Mechanism-only path：real-Qwen G5 FAIL

写 symbolic capacity/separator paper；不要把 LLM 放 headline。

### Systems path

若最强结果是 parallel latency/communication efficiency，则转向 MLSys 风格，弱化 cognitive claim。

---

## 17. 最小执行顺序

### Step 1 — 冻结论文问题

- 主问题：team vs monolith 的 capacity×coupling interaction；
- 不再扩展 15 个 heterogeneous baselines；
- 不把 multi-agent 与 redundancy 混为一谈。

### Step 2 — 统一 generator

合并：

- separator scaling 的 `d_global × boundary` axes；
- v6 fixed-density rho generator；
- Reasoning Gym official scoring。

输出一个 frozen instance manifest，confirmatory 时只读。

### Step 3 — 增加公平 arms

必须先实现：

1. `monolith-R`；
2. `monolith-MR`；
3. `centralized-sharded-MR`；
4. `team-CBJ`；
5. `team-chrono`。

### Step 4 — 跑 no-LLM phase-map

只用于选 bins 与验证 axes，不读取最终 headline。

### Step 5 — 跑 branch×route dev gates

确认 Qwen endpoint、parse、route、token accounting 和 no-fallback。

### Step 6 — 跑 4-cell × 5-arm × 50-instance real-Qwen confirmatory

这是下一次真正值得花 GPU 的 run。

### Step 7 — 根据 G2/G3/G4 决定是否扩大 M/R/rho/model grid

不在核心 interaction 失败后继续 goalpost hunting。

---

## 18. 当前文件的角色分配

### 主论文基础

- [Multi-agent real-LLM spec](multiagent_real_llm_internalization_v1.md)
- [Item076 capacity/structure closeout](../results/rung1_multiagent_solvability/closeout.json)
- [Item111 K=2 structural result](../results/experiment_items/item_111_kvcache_multiagent_structural_k2.json)
- [Real-Qwen single-agent bounded search](../results/externalization_validation_v0/graph_color_ceiling_llm.json)

### Controlled generator / accounting

- [Separator scaling](../results/rung1_separator_scaling/results.json)
- [Fixed-density coupling harness](../experiments/downstream/dist_coloring.py)
- [Honest token accounting correction](../results/externalization_validation_v0/honest_token_accounting_addendum.json)

### Secondary mechanism

- [SPEC v5 redundancy](../results/capacity/SPEC_v5_run_summary_qwen3_fp32.md)
- [Reversible-memory technical roadmap](reversible_search_research_paper_roadmap_v1.md)

### Boundary / appendix

- [SPEC v6 proxy negative](../results/downstream/SPEC_v6_run_summary.md)
- [Underpowered real team pilot](../results/externalization_validation_v0/multiagent_real_llm_v1_pilot.json)

---

## 19. 最终建议

论文真正有力量的表述不是：

> Multi-agent LLMs are better than single agents.

而是：

> We identify the phase in which bounded-memory LLM agent teams outperform a monolith. The gain appears when decomposition moves local search below each agent's memory wall and separator coordination remains bounded; it vanishes when the monolith already fits, local agents overflow, or coupling overwhelms communication. Equal-total-memory and centralized-sharding controls distinguish aggregate capacity from genuine architectural advantage.

这条主线：

1. 是明确的 multi-agent research；
2. 能容纳正结果与负结果；
3. 理论变量可控；
4. 公平性可审计；
5. 能自然解释 Item076、Item111、real pilot 和 v6；
6. 不依赖“15 个 proxy baseline 中必须赢”。

### 下一件应做的事

实现并冻结一个 **Multi-Agent Core 2×2 preregistration**：

- capacity under/over × coupling low/high；
- team-CBJ、team-chrono、monolith-R、monolith-MR、centralized-sharded-MR；
- 50 paired instances/cell；
- branch×route dev gate；
- four-test Holm family；
- total-token / total-memory / parallel-latency accounting。

这比继续扩展 v6 proxy 更直接地通向一篇高质量 multi-agent 论文。
