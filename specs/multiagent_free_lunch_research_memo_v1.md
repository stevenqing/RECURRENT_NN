# Where Is the Multi-Agent Free Lunch?

## A First-Principles Research Memo Grounded in All Current Results

> **Confirmation update (2026-07-11):** The proposed independent-local mechanism failed a new 200-instance, hash-locked symbolic confirmation. In `over_low`, solve was 0.92 versus 1.00 for equal-memory controls and failure-penalized work ratio was 1.551. The strong structural free-lunch hypothesis is rejected for this mechanism. The retained research target is tail-risk-aware selective factorization, not unconditional local factorization or immediate Qwen scaling. See [confirmatory closeout](../results/multiagent_structural_confirmatory/CLOSEOUT.md).

- 日期：2026-07-11
- 主线：Multi-Agent Frozen-LLM Search
- 推荐论文题目：**Where Is the Multi-Agent Free Lunch? Factorized Search with Sparse LLM Coordination**
- 当前结论：horizontal aggregate capacity 与 coupling cost boundary 成立；当前 independent factorization 的 strong free lunch 已被独立确认否决
- 证据边界：200-instance symbolic confirmation + 8-instance real-Qwen development；无 headline-grade real-Qwen 或 equal-resource positive

---

## 1. 一句话答案

multi-agent 的 free lunch 不是：

> 多复制几个相同 LLM，就免费得到更强 reasoning。

而可能是：

> **当原问题的搜索复杂度是超线性的、可被 separator 分解，而跨分区冲突足够稀疏时，多个 bounded local solvers 可以把一次昂贵的 global search 变成若干更小的并行 local searches；LLM 只在少量高价值 cross-block recovery events 上做 routing。**

这个收益成立的三个必要条件是：

1. global search 已超过单体 memory/search capacity；
2. 每个 local subproblem 仍低于单 agent capacity；
3. separator coordination 的总代价小于 factorization 节省的搜索代价。

如果任一条件不满足，multi-agent 不仅没有 free lunch，还会付出 communication、synchronization 和重复计算成本。

---

## 2. 先严格定义“free lunch”

没有资源定义的 “multi-agent 更好” 没有科学意义。

定义一个系统的资源向量：

$$
\mathbf C=(M_\Sigma,M_\infty,T_\Sigma,T_\infty,Q,\Gamma),
$$

其中：

- $M_\Sigma$：total mutable memory；
- $M_\infty$：peak per-agent memory；
- $T_\Sigma$：aggregate tokens/FLOPs/work；
- $T_\infty$：critical-path latency/parallel rounds；
- $Q$：LLM calls；
- $\Gamma$：communication tokens/messages。

令 $S$ 为 solve probability。

### 2.1 Strong free lunch

Team 相对 equal-resource monolith 满足：

$$
S_{team}\ge S_{mono},\qquad
\mathbf C_{team}\preceq\mathbf C_{mono},
$$

并且至少一个维度严格改善。

当前证据：**没有观察到。**

在 core 2×2 symbolic preflight 中：

- `team-CBJ = monolith-MR = centralized-sharded-MR`；
- equal-total-memory solve gap 为 0。

来源：[Core 2×2 preflight](../results/multiagent_core_2x2_preflight/PREFLIGHT_SUMMARY.md)

### 2.2 Horizontal capacity scaling

固定每个 agent 的 resource，而允许 total resource 随 M 增长：

$$
M_\infty=R,\qquad M_\Sigma=MR.
$$

Team 胜 `monolith-R`。

当前证据：**已确认。**

- over/low：team `1.0`，monolith-R `0.0`；
- over/high：team `0.9375`，monolith-R `0.0`。

但这不是 global-resource free lunch，因为买入了 M 倍 aggregate memory。

正确名称：

> distributed aggregate capacity / horizontal scaling

### 2.3 Parallel-latency lunch

允许 M 份硬件并行，关注 critical path：

$$
T_\infty^{team}<T_\infty^{mono},
$$

即使 aggregate work 不下降。

当前证据：**未测。** 现有 team loop 仍是串行 global trail，不能支持 parallel latency 主张。

### 2.4 Structural/factorization free lunch

在 equal total memory/compute 下，由问题分解降低总搜索复杂度：

$$
T_\Sigma^{team}<T_\Sigma^{mono},
$$

同时 solve 不下降。

这是最有科学价值的 strong candidate，但当前 harness 尚未真正实现独立 local search，因此仍未测到。

### 2.5 Coordination-specialization lunch

只在高价值 coordination events 调用 LLM，而不是每个 branch step 都调用：

$$
Q_{route-only}\ll Q_{LLM-every-step}.
$$

如果 solve 还更高，则形成 Pareto improvement。

GPU4–7 development 结果：

| Policy | Solve | LLM calls | Total tokens |
|---|---:|---:|---:|
| Qwen branch + Qwen route | 0.125 | 929 | 346218 |
| Qwen branch + symbolic route | 0.250 | 874 | 293237 |
| symbolic branch + Qwen route | **0.750** | **265** | **187019** |
| symbolic branch + symbolic route | 0.625 | 0 | 0 |

来源：[GPU4–7 Overnight Summary](../results/multiagent_overnight_gpu4_7/SUMMARY.md)

因此 route-only 相对 full-Qwen 在当前 dev sample 上同时：

- solve 更高；
- calls 更少；
- tokens 更少。

这是当前最强的 **conditional Pareto signal**，但只有 8 个 development instances，不能作为论文结论。

---

## 3. 从第一性原理推导 multi-agent 的结构收益

## 3.1 Monolithic search

令 $F(x)$ 表示 effective search width/depth 为 x 时的工作量。

对于 combinatorial search，$F$ 通常是凸或指数型：

$$
F(x)\approx b^x,
$$

其中 b 是 effective branching factor。

Monolith：

$$
W_{mono}=F(L_G),
$$

$L_G$ 是 global effective search load。

## 3.2 Factorized team search

把问题分成 M 个 local subproblems，local loads 为 $L_1,\ldots,L_M$，separator complexity 为 S：

$$
W_{team}=\sum_{i=1}^{M}F(L_i)+G(S,\rho)+Q_{coord}c_Q.
$$

- $G(S,\rho)$：message passing、boundary consistency、rollback cascade；
- $Q_{coord}$：需要 LLM coordination 的 event 数；
- $c_Q$：一次 route call 的代价。

强 structural lunch 的条件：

$$
\sum_i F(L_i)+G(S,\rho)+Q_{coord}c_Q<F(L_G).
$$

若分割大致均衡：

$$
L_i\approx\frac{L_G}{M},
$$

则：

$$
M F(L_G/M)+G(S,\rho)+Q_{coord}c_Q<F(L_G).
$$

当 $F$ 是指数函数时，左侧 local search 的节省可能非常大；这是真正可能覆盖 communication overhead 的地方。

## 3.3 Capacity feasibility

单 agent memory capacity 为 C。

Team 能解决、单 R monolith 失败的区域：

$$
L_G>C,\qquad \max_i L_i\le C.
$$

这正是 core preflight 的 over/local-fit strata：

- global recovery distance：9–21；
- local recovery distance：2–6；
- $R=8$。

来源：[Core 2×2 Preflight](../results/multiagent_core_2x2_preflight/PREFLIGHT_SUMMARY.md)

## 3.4 Coupling feasibility

separator channel capacity 为 $C_{comm}$。

额外条件：

$$
S\le C_{comm},
$$

且：

$$
G(S,\rho)<F(L_G)-\sum_iF(L_i).
$$

当前 fixed-density preflight 中，rho 从约 0.109 增至 0.380 时：

- steps：`403 → 875`；
- cross-block messages：`42 → 168`；
- communication tokens：`886 → 4619`；
- retractions：`296 → 654`。

也就是说，coupling 的第一影响是 cost explosion，不一定立即表现为 solve collapse。

## 3.5 Phase regions

定义：

$$
\alpha=\frac{L_G}{C},\qquad
\beta=\frac{\max_iL_i}{C},\qquad
\gamma=\frac{G(S,\rho)}{F(L_G)-\sum_iF(L_i)}.
$$

与之前用未校准 communication capacity 定义 gamma 相比，这个定义更直接：gamma 是 coordination cost 与 factorization saving 的比值。

### Region A — Monolith fits

$$
\alpha\le1.
$$

预测：team 没有 solve gain，只有 overhead。

现有结果：under cells 中 team 与 monolith-R 均为 1.0。

### Region B — Factorization sweet spot

$$
\alpha>1,\qquad\beta\le1,\qquad\gamma<1.
$$

预测：team 有可能在 equal total resources 下形成 structural lunch。

当前只验证了 aggregate capacity；尚未实现独立 local loops，因此不能读取 strong lunch。

### Region C — Local overflow

$$
\beta>1.
$$

预测：每个 agent 也超容量，增加 agents 或 R 前 team 仍失败。

当前尚未正式生成该 confirmatory cell。

### Region D — Coordination overload

$$
\gamma\ge1.
$$

预测：coupling cost 吃掉 factorization saving；team 可能低于 centralized/monolith-MR。

v6 high-rho proxy negative 与 preflight cost escalation 都指向这个边界。

---

## 4. 所有历史结果对 free lunch 的约束

## 4.1 v3–v5 capacity results

支持：

- 单 register 有明确容量墙；
- whitening 对真实 hidden geometry 很重要；
- replication 可提高 retrieval reliability。

不支持：

- multi-agent architecture advantage；
- equal-total-memory gain；
- downstream transfer。

作用：给每个 agent 的 local memory capacity C 提供 mechanism motivation。

来源：

- [SPEC v4](../results/capacity/SPEC_v4_run_summary_qwen3_fp32.md)
- [SPEC v5](../results/capacity/SPEC_v5_run_summary_qwen3_fp32.md)

## 4.2 Item076

支持：

- 在 monolith-fail/team-feasible intersection 上，team capacity positive；
- dense graph 上 CBJ≈chronological；
- coordination advantage 是 structure-dependent。

限制：

- outcome-conditioned intersection；
- no-LLM；
- 未匹配 monolith-MR。

来源：[Item076 closeout](../results/rung1_multiagent_solvability/closeout.json)

## 4.3 Item111

支持：

- team 胜 monolith-R；
- CBJ messages/retractions 较少；
- team 对 monolith-KR 为 mixed；
- model route 是主要 gap。

来源：[Item111](../results/experiment_items/item_111_kvcache_multiagent_structural_k2.json)

## 4.4 Core 2×2 preflight

支持：

- fixed-density capacity/coupling cells可生成；
- team 解除单 R capacity failure；
- high coupling 大幅提升 coordination cost。

反证：

- team 未超过 monolith-MR；
- team 未超过 centralized-sharded；
- 当前实现的 agent identity 没有额外价值。

## 4.5 v6 proxy

支持：

- 简单 reliability injection 不能产生 multi-agent downstream advantage；
- high coupling 不会自动激活 agent gain。

它是 failed bridge，不是 real-Qwen反证。

来源：[SPEC v6](../results/downstream/SPEC_v6_run_summary.md)

## 4.6 GPU4–7 real-Qwen development

Decision gate：

- branch parse/valid/exact：1.0；
- route parse/valid：1.0；
- route exact：29/32 = 0.90625。

End-to-end：

- Qwen route 在 symbolic branches 上 aggregate route valid 0.996，route exact 0.860；
- full-Qwen branch valid 0.993，但 branch exact 0.698；
- locally valid branch choices仍造成 combinatorial trajectory explosion。

关键发现：

> Local validity is not sequential policy quality.

LLM 更适合受约束的高层 recovery routing，而不是每个 micro-branch decision。

---

## 5. 当前最强 research idea

## 5.1 推荐方法

**Factorized Search with Event-Triggered LLM Coordination**

核心结构：

1. 每个 agent 独立维护 local search loop 和 bounded local memory；
2. local propagation/branching 使用便宜、稳定、可验证的 solver policy；
3. 只有跨块 conflict 或 ambiguous recovery 时触发 frozen LLM；
4. LLM 从显式枚举的 valid cross-agent targets 中选择 route；
5. agents 只交换 boundary assignments、compact nogoods 和 recovery messages；
6. 不使用单一 global suffix rollback 作为执行主干。

### 为什么这比当前架构更“multi-agent”

当前 core solver 有一个 global order、global trail 和 global suffix rollback，因此：

$$
team=centralized\text{-}sharded=monolith\text{-}MR.
$$

真正的 multi-agent factorization 必须：

- local loops 独立推进；
- local failures 不自动撤销无关 blocks；
- only dependency-connected agents rollback；
- boundary protocol 决定同步范围；
- 可并行执行并测 critical path。

### LLM 的正确角色

不是：

- 每个 vertex 都调用一次 LLM 选 color。

而是：

- 在 sparse, high-impact coordination events 上选择 culprit/target/message。

这与 overnight 结果一致：route-only 相对 full-Qwen 是当前唯一的 Pareto candidate。

---

## 6. Multi-agent free lunch taxonomy

| 类型 | 资源是否真的免费 | 当前证据 | 论文措辞 |
|---|---|---|---|
| Aggregate capacity | total memory 增加 M 倍 | 已确认 | horizontal scaling |
| Replication reliability | memory/compute 增加 | v5确认 retrieval | reliability tradeoff |
| Parallel latency | 硬件增加 | 未测 | systems speedup |
| Structural factorization | 可能降低 total work | 未实现/未测 | strong free-lunch candidate |
| Sparse LLM coordination | 相对 LLM-every-step可能 Pareto 改善 | n=8 dev signal | event-triggered specialization |
| Agent identity/diversity | 无证据 | team=centralized | 不主张 |
| Equal-memory architecture | 当前为 0 | preflight null | 不主张 |

---

## 7. 决定性下一步实验

## Phase 1 — Independent Local Loops

实现真正的 local search agents：

- 每个 block 独立 cursor、trail、register、tried values；
- boundary blackboard只保存当前 commitments/nogoods；
- conflict dependency graph决定 rollback recipients；
- 不相关 blocks不做 global suffix rollback；
- 记录 total work 与 critical-path rounds。

Primary controls：

1. monolith-R；
2. monolith-MR；
3. centralized-sharded-MR；
4. current global-trail team；
5. independent-local team。

Strong factorization gate：

$$
S_{local\ team}\ge S_{monoMR}
$$

且：

$$
T_{\Sigma,local\ team}<T_{\Sigma,monoMR}
$$

或：

$$
T_{\infty,local\ team}<T_{\infty,central\ sharded}.
$$

## Phase 2 — Route Policy Confirmatory

先不让 Qwen 做 branch。

Independent manifest：50 instances/cell，四 cells，共 200 instances。

Route policies：

1. deepest conflict target；
2. chronological target；
3. uniformly random valid target；
4. Qwen valid-target route；
5. oracle budget-optimal target upper bound。

注意：当前 all-symbolic route 不是 random；不能把 0.625 写成 random baseline。

Primary test：

$$
S_{Qwen\ route}>S_{random\ valid\ route}
$$

且比较 Qwen vs deepest deterministic。

四个 primary tests做 Holm；solve使用 paired McNemar，cost使用 paired bootstrap。

## Phase 3 — Event-Triggered vs LLM-Every-Step

在相同 total token/call caps 下比较：

- event-triggered Qwen route；
- Qwen every branch + symbolic route；
- full Qwen branch + route；
- best-of-N branch attempts；
- symbolic-only。

Primary Pareto hypothesis：

> route-only 的 solve 不低于 full-Qwen，同时 calls/tokens 显著更少。

当前 dev effect：

- solve：0.750 vs 0.125；
- calls：265 vs 929；
- tokens：187019 vs 346218。

必须在新 manifest confirm。

## Phase 4 — Coupling Boundary

固定 capacity stratum：

$$
L_G>R,\quad\max_iL_i\le R.
$$

扫 separator/coupling，使 communication cost连续变化。

测：

- solve；
- total work；
- route events；
- messages；
- communication tokens；
- parallel rounds。

不要预设任意 gamma threshold；从 calibration split 拟合，confirmatory split 只测试预测的 boundary。

## Phase 5 — External Validity

至少第二个 substrate：

- distributed SAT；或
- Sudoku block/subgrid agents；或
- AgentsNet direct scoring。

只有方向复现后才能写一般性 multi-agent law。

---

## 8. 最关键的公平性控制

### 8.1 Total resources

必须同时报告：

- aggregate tokens；
- aggregate calls；
- total mutable bytes；
- peak per-agent memory；
- wall-clock；
- parallel critical path；
- communication overhead。

### 8.2 Centralization controls

- monolith-global；
- monolith-MR；
- centralized-sharded-MR；
- independent multi-agent。

若 independent team 只等于 centralized-sharded，则收益来自 factorization，不来自 decentralized agency。

### 8.3 Route controls

- random valid；
- latest valid；
- deepest valid；
- Qwen；
- oracle optimal。

否则无法判断 LLM routing 的真实价值。

### 8.4 Selection discipline

confirmatory instances 禁止按以下条件筛选：

- monolith failure；
- team success；
- Qwen route correctness；
- large coupling effect。

只能按 frozen structural strata 生成。

---

## 9. 推荐论文故事

### 标题

**Where Is the Multi-Agent Free Lunch? Factorized Search with Sparse LLM Coordination**

### 核心主张

如果未来 gates 通过：

> Multi-agent systems do not gain from multiplicity alone. Their conditional advantage comes from factorizing superlinear search into bounded local processes and invoking language models only for sparse cross-agent coordination. The gain disappears when local problems overflow or separator communication dominates.

### Contributions

1. 定义 multi-agent free lunch 的资源向量和 Pareto标准；
2. 给出 factorization-vs-coordination cost model；
3. 建立 capacity × coupling phase map；
4. 提出 independent local loops + event-triggered LLM routing；
5. 用 equal-memory、centralized-sharded、random/deepest route controls隔离机制；
6. 报告 holds-here/not-there boundary，而不是只展示正例。

### v6 的位置

v6 是一个重要 negative：

- 仅注入 capacity/reliability proxy 不会产生 agent gain；
- high coupling 不会自动让 multi-agent 更好。

放在 mechanism boundary/appendix，不做 headline。

---

## 10. 安全主张与禁止主张

### 当前可以写

- Partitioned R-windows relieve a single R-window capacity failure on controlled instances.
- This gain vanishes against an equal-total-memory monolith in the current symbolic loop.
- Coupling increases coordination cost sharply.
- Qwen routing from bounded valid targets is substantially more reliable than Qwen micro-branch control in development.
- Event-triggered Qwen routing is a candidate Pareto improvement over invoking Qwen at every branch.

### 当前不能写

- Multi-agent teams beat equal-resource monoliths.
- Multi-agent is universally better.
- Qwen route has a confirmed solve advantage.
- 0.750 vs 0.625 is statistically established。
- The symbolic route baseline is random。
- Current team is fully decentralized。
- Current VSA capacity law explains the real-Qwen route result。

---

## 11. Go / No-Go

### G1 — Independent local factorization

若 independent local team 在 equal total memory 下不能降低 total work/latency：

- 删除 strong free-lunch claim；
- 保留 horizontal capacity scaling。

### G2 — Qwen route confirmatory

若 Qwen route 不胜 random/deepest controls：

- 删除 LLM coordination novelty；
- 保留 symbolic distributed-search paper。

### G3 — Event-triggered Pareto

若 route-only 不再 dominate full-Qwen：

- 不写 specialization free lunch；
- 分析 dev overfit。

### G4 — Coupling boundary

若 cost/solve 不随 separator stress系统变化：

- 删除 phase-law主张；
- scope到特定 generator。

### G5 — Second substrate

若第二任务不复现：

- 标题和 abstract 明确 graph-coloring scope。

---

## 12. 最终判断

从所有结果出发，multi-agent 的 free lunch 目前有两层：

### 已确认的弱版本

> **Horizontal capacity scaling:** 多个 bounded agents 的 aggregate memory 能覆盖单 R monolith 无法访问的 recovery target。

它真实，但不是 global-resource free lunch。

### 最值得追的强版本

> **Structural + specialization free lunch:** 独立 local search 利用问题 factorization 降低超线性搜索工作；LLM 只处理稀疏 cross-agent routing，从而相对 LLM-every-step 同时提高 solve、减少 calls/tokens，并在 equal total memory 下保持优势。

当前 overnight 结果为这个方向提供了第一个 development signal，但尚未 confirm。

因此下一步不应继续优化 Qwen 每步 branch，也不应直接扩大现有 global-trail team。应该：

1. 实现独立 local loops；
2. 以 symbolic branching + Qwen routing 为 primary architecture；
3. 增加 random/deepest/oracle route controls；
4. 用新 50/cell manifest 验证 equal-resource Pareto 和 coupling boundary。

这才是从第一性原理出发、最可能形成高质量 multi-agent research paper 的 free-lunch 主线。
