# Reversible Search Research Paper Roadmap v1

> **Scope update (2026-07-11):** The primary paper line is now multi-agent capacity, coupling, and coordination. This document is retained as the memory-substrate and causal-audit foundation. The primary paper roadmap is [Multi-Agent Capacity–Coupling Paper Roadmap v1](multiagent_capacity_coupling_paper_roadmap_v1.md).

**目标：把当前 v1–v6 的结果收敛成一篇主张尖锐、机制闭环、经得住审稿人检查的 research paper。**

- 日期：2026-07-11
- 当前状态：研究路线已审计；不建议按现有证据直接投稿
- 推荐主线：**Capacity Before Capability — 从代数可逆、信息容量到因果搜索的完整闭环**
- 关键原则：不隐藏负结果，不把 proxy 当 downstream，不把 Python list 当 VSA register，不把 cap-matched 写成 exact-spend-matched

---

## 1. 一句话结论

现在最有价值的工作不是继续给 v6 增加更多 symbolic baseline，而是完成一个决定性的桥接实验：

> **在同一个 frozen-Qwen search loop 中，用真正可自解码、无 Python 栈旁路、资源完全审计的 VSA register 替换显式 list register，并验证其信息容量是否预测真实搜索成功边界。**

如果这个桥接成功，论文可以达到很强的完整性：

1. 为什么可逆 memory 能工作；
2. 它能装多少；
3. whitening 和 redundancy 如何改变可靠性；
4. 这些 memory-level 规律何时会转化成真实 frozen-LLM search gain；
5. 为什么简单 proxy transfer 会失败。

如果桥接失败，也能形成一个诚实但更窄的机制论文：**capacity is not capability**。

---

## 2. 推荐论文定位

### 2.1 首选标题

**Capacity Before Capability: Reversible External Memory for Frozen Language-Model Search**

其他候选：

1. **When Can a Frozen Language Model Backtrack? Capacity Laws for Reversible Search Memory**
2. **Reversible Search Memory for Frozen LMs: Geometry, Capacity, and Causal Use**
3. **From Reversible Storage to Search: Auditing External Memory for Frozen Language Models**

### 2.2 核心科学问题

> 对 frozen LLM 而言，一个固定宽度的外部可逆状态究竟能可靠保存多少搜索信息；该容量何时真正限制任务求解；memory-level gain 是否会转化为 causal search gain？

### 2.3 目标主张

只有在后续 hard gates 全部通过时，主文才使用下面的强主张：

> A self-decoding reversible register has a predictable geometry-dependent capacity, and that capacity predicts the success boundary of bounded-memory search driven by a frozen language model.

当前已经可以安全写的窄主张只有：

> With per-bundle whitening on sampled Qwen hidden states at fixed `K=9`, superposition memory exhibits a sharp empirical width transition that scales with hidden dimension, while independent replicas trade additional memory for improved retrieval reliability.

当前**不能**写：

- 已验证完整的 $D/(2\ln K)$ 定律；
- depth 在 autonomous search 中是 free 的；
- 多 agent 本身带来非平凡增益；
- D1 在 real-Qwen downstream 上击败 ToT/RAP；
- 当前 v6 是 real downstream negative result。

---

## 3. 当前证据必须拆成三层，不能混写

### 3.1 Layer A：代数可逆性

现有证据：

- supplied branch encoding 条件下，push 后再 pop 的数值误差在 depth 4000 时为 `1.33e-13`；
- 31 个 graph-coloring restore 事件在 native floor 内保持 decision agreement 1.0。

来源：

- [SPEC v2 summary](../results/capacity/SPEC_v2_run_summary_qwen3_fp32.md)
- [Structured register](../register/structured.py)

正确解释：

- **条件可逆性**成立：若 pop 时已知原始 branch encoding，则可以恢复前态。

不能推出：

- register 能从自身状态恢复 top item；
- register 是一个 autonomous stack；
- 深度信息被 register 单独保存。

### 3.2 Layer B：离线 associative retrieval capacity

现有证据：

- `W*=155`，first fail `W=156`；
- 4B-Instruct 五 seed 均值 `150.4`，95% CI `[144.0,156.8]`；
- Qwen3 `D={1024,2048,2560}` 上经验线性拟合 `R²=0.9994`；
- raw hidden 极端各向异性，whitening 是必要主效应；
- `N>=3` 独立 replicas 在 fixed per-register load 下提高 retrieval accuracy。

来源：

- [SPEC v4 summary](../results/capacity/SPEC_v4_run_summary_qwen3_fp32.md)
- [SPEC v5 summary](../results/capacity/SPEC_v5_run_summary_qwen3_fp32.md)

正确解释：

- 这是 **content-addressable retrieval** 的容量与可靠性结果。

不能推出：

- search stack 只存在于一个 D-dimensional state；
- 总 memory 已匹配；
- retrieval gain 会自动转化为 solve-rate gain。

### 3.3 Layer C：真实 frozen-Qwen bounded search

现有积极证据：

- Reasoning Gym graph_color，30 个需 backtracking 的实例；
- real Qwen3.5-4B，official scoring；
- 显式 bounded register view 的 solve rate 随 `R` 从 `0.00` 上升到 `0.83`。

来源：

- [Real-Qwen ceiling result](../results/externalization_validation_v0/graph_color_ceiling_llm.json)
- [Externalization execution contract](externalization_paper_full_execution_v1.md)

正确解释：

- bounded explicit history 对 frozen-Qwen-guided search 有价值；
- prompt view 可以限制在 current frontier、local constraints 和最近 R 条记录。

不能推出：

- 该 register 是 v4/v5 的 VSA register；
- dense latent capacity law解释了 `R` curve；
- external mutable memory 是 fixed-D；
- 已经击败 canonical ToT/RAP/best-of-N。

### 3.4 v6 的角色

来源：

- [SPEC v6 summary](../results/downstream/SPEC_v6_run_summary.md)

v6 应被写成：

- **engineering boundary / failed bridge prototype**；
- 它证明“把 v5 accuracy curve 注入 symbolic heuristic”并不能形成 downstream mechanism；
- 它不构成 real-Qwen 对 reversible search 的反证。

主文最多用一段或一张 appendix table；不要把 v6 proxy 放在 headline figure。

---

## 4. 当前实现中的一票否决问题

这些问题不修复，核心论文主张会被直接否决。

### 4.1 Python branch stack 旁路

当前 [SearchLoop](../controller/controller_head.py) 保存：

- `saved_partial`；
- `saved_hidden`；
- 完整 `branch_stack`。

因此真实搜索栈并不只在 register `h` 中。

**Hard rule P0.1：** headline arm 中禁止存在随 search depth 增长的 Python list、trail、saved partials、hidden checkpoints 或 cache checkpoints。

### 4.2 `pop()` 需要原始 branch encoding

当前接口：

$$
\text{pop}(h, e_t, t)
$$

其中 $e_t$ 就是需要恢复的原始 item。代数上可逆，但不是 self-decoding memory。

**Hard rule P0.2：** 主方法必须实现：

$$
\hat a_t=\operatorname{decode\_top}(h_t),\qquad
h_{t-1}=\operatorname{pop\_self}(h_t,\hat a_t,t)
$$

`pop_self()` 只能接收当前 register state、depth/key 和固定 codebook；不能接收外部保存的 item。

### 4.3 动态 codebook 的 memory 未计入

当前 associative register 还保存随 W 增长的：

- `value_codebook`；
- `key_codebook`。

二者规模均为 $O(WD)$。若不计入，它不是 fixed-memory claim。

**Hard rule P0.3：**

- keys 必须由 depth/action id 程序化生成；
- value codebook 必须是固定 action vocabulary，或其 bytes 必须计入 memory；
- headline memory audit 必须统计所有 mutable tensors、Python containers、KV caches 和 lookup tables。

### 4.4 当前 whitening 是 transductive

现有 `_whiten_values()` 在被评估的整组 states 上重新计算 mean/SVD。它看到了当前 test bundle。

**Hard rule P0.4：**

- whitening 仅在独立 calibration split 上拟合；
- 之后冻结；
- test instances、tasks、models 不得参与变换估计；
- per-instance whitening 只能作为 oracle upper bound。

### 4.5 redundancy 没有匹配总 memory

v5 的 N replicas 每个都是 full-D，因而总 memory 和编码成本约增加 N 倍。

这不是“free multi-agent effect”，而是 reliability-resource tradeoff。

**Hard rule P0.5：** 同时报告：

1. N 个 full-D replicas；
2. 单个 ND register；
3. N 个 D/N registers；
4. 同总 bytes 下的 error-correcting code；
5. accuracy–memory–compute Pareto frontier。

建议从标题和主张中移除 “multi-agent”，改称 **redundant coding / replicated memory**。

### 4.6 K-law 尚未被验证

现有 cross-model scaling 固定 `K=9`。因此只支持经验 $W^*(D)$，不支持完整 $D/(2\ln K)$。

**Hard rule P0.6：** 必须做 `D × K` factorial，至少：

- `D={256,512,1024,2048,4096}`；
- `K={3,9,27,81}`；
- 多 seed；
- held-out whitening；
- 自主 self-pop sequence recovery，而不只是 supplied-item pop。

### 4.7 depth 与 live width 被混在一起

- 代数实验测 depth；
- capacity 实验测 live bundle width W；
- downstream proxy 测 search frontier。

它们不是同一个量。

**Hard rule P0.7：** 论文分别定义并测量：

- stack depth $L$；
- live frontier width $W$；
- action alphabet $K$；
- total mutable memory $M$；
- operator compute budget $B$。

### 4.8 Real-Qwen positive 使用 explicit list，而不是 VSA

现有 R curve 是重要证据，但它证明的是 bounded explicit history，而非 dense reversible latent memory。

**Hard rule P0.8：** 同一个 instance、同一个 Qwen、同一个 controller policy 下进行：

- explicit list register；
- self-decoding VSA register；
- GRU fixed-state register；
- no-memory；
- full-history prompt。

---

## 5. 建议的新方法：Causal Reversible Search Memory（CRSM）

### 5.1 设计目标

CRSM 必须同时满足：

1. **Self-decoding**：能从当前 state 解出 top action；
2. **No bypass**：无外部 depth-growing trail；
3. **Bounded mutable memory**：memory bytes 与 search depth 无关；
4. **Causal use**：每次 REVERT 真正调用 decode/pop；
5. **Frozen operator**：Qwen 参数不更新；
6. **Auditable**：所有状态、tokens、forwards、bytes 都可计数。

### 5.2 推荐存储对象

不要直接试图无损保存任意 2560-D hidden sequence。信息论上这不可能在 fixed D 内无限完成。

主 register 应存储有限 action alphabet：

$$
a_t=(\text{branch value},\text{optional target class},\text{control flag})\in\{1,\ldots,K\}.
$$

- variable selection由固定 MRV/degree policy 决定；
- LLM 只选择 branch value 和 bounded backtrack target；
- action codebook 固定，不随 depth 增长；
- operator hidden state用于决策，但不是隐藏的 unbounded stack。

### 5.3 自解码 push/pop

建议状态更新：

$$
h_{t+1}=P_t h_t+c(a_t),
$$

其中 $P_t$ 是由 depth seed 程序化生成的 signed permutation，$c(a_t)$ 是固定 action code。

Top decode：

$$
\hat a_t=\arg\max_{a\in[K]}\langle h_t,c(a)\rangle.
$$

Self-pop：

$$
h_{t-1}=P_t^{-1}(h_t-c(\hat a_t)).
$$

headline 指标不是 supplied-item algebraic error，而是：

- top-action accuracy；
- full-sequence self-pop recovery；
- first-error depth；
- conditional numerical error given correct decode；
- catastrophic error propagation after one wrong pop。

### 5.4 当前 assignment 如何处理

允许环境保存：

- immutable task；
- current assignment，大小由 task size 决定；
- fixed-size tried-value bitmap，大小 $O(nK)$。

不允许环境保存：

- history of assignments；
- undo trail；
- saved hidden states；
- per-depth KV caches；
- branch stack。

Chronological revert：decode top action、撤销当前 variable、self-pop。

Bounded backjump：在 register 的临时副本上连续 self-pop，读取最近 R 条 action，选择 target 后在主 state 上执行对应次数的 pop。临时副本也是一个 D-vector，不随 depth 增长。

### 5.5 KV cache 的正确角色

不要把每个 branch 的完整 KV cache 当成 core stack。那会让 memory 随 depth 增长并破坏核心主张。

分成两个清晰 arm：

- **CRSM-Recompute（core claim）**：revert 后重新渲染 bounded current-node prompt；不保存 per-depth cache。
- **CRSM-KV(R)（systems extension）**：只保留最多 R 个 cache checkpoints，完整统计 bytes；这是显式 bounded-cache baseline，不是 fixed-D theorem arm。

---

## 6. 理论部分应该怎样做

### 6.1 条件可逆性 theorem

证明：若 top action 被正确解码，则 signed permutation update 的 pop 在 exact arithmetic 中恢复前态；浮点误差只按 operation count 累积。

这比“depth free”更准确：

> Numerical reversibility is conditional on correct symbol recovery; information errors, not algebraic drift, set the autonomous depth limit.

### 6.2 容量近似

展开 nested state：

$$
h_L=\sum_{t=1}^{L}P_LP_{L-1}\cdots P_{t+1}c(a_t).
$$

在近似 isotropic、independent code 假设下：

- true action score包含 unit signal；
- 前序 actions 形成方差约 $(L-1)/D$ 的 interference；
- K 个候选的 extreme-value penalty 约为 $\sqrt{2\log K}$。

因此产生可检验的 collapse variable：

$$
\xi=\frac{L\log K}{D}.
$$

目标不是先验强行宣称常数就是 $1/2$，而是测试不同 D、K、model/task 后曲线是否在 $\xi$ 上 collapse。

### 6.3 各向异性修正

对真实 hidden-derived code，理论需加入 covariance：

$$
D_{\mathrm{iso}}=\frac{(\operatorname{tr}\Sigma)^2}{\operatorname{tr}(\Sigma^2)}.
$$

比较：

- raw；
- globally centered；
- frozen ZCA/PCA whitening；
- per-instance whitening upper bound。

目标是解释何时 nominal D、何时 effective geometry 控制 capacity，而不是只报告一条拟合直线。

### 6.4 redundancy 理论

若单 register error rate 为 p 且 replicas 独立，majority error 为：

$$
p_N=\sum_{j=\lceil N/2\rceil}^{N}\binom Njp^j(1-p)^{N-j}.
$$

真实 replicas 不是独立的，因此必须测：

- pairwise error correlation；
- shared-failure rate；
- beta-binomial 或 correlated-binomial fit；
- accuracy gain per additional byte/forward。

---

## 7. 决定性实验矩阵

## Phase 0：Causal Memory Audit（零号硬门）

目标：证明 headline arm 没有隐藏 history。

必须自动检查：

| 检查 | PASS 条件 |
|---|---|
| Python container growth | mutable container size 不随 L 增长 |
| Tensor memory growth | 除 current state 外，bytes 对 L 的 slope≈0 |
| `pop_self` API | 不接收 saved item/hidden/partial/cache |
| Codebook accounting | 动态 codebook 不存在或计入总 bytes |
| KV checkpoints | core arm 为 0；systems arm ≤R |
| Causal usage | 每个真实 REVERT 都调用 self-decode + self-pop |
| No-revert ablation | backtracking-required tasks 降到 forward-only floor |

**Kill rule：任何一项失败，停止 downstream headline run。**

## Phase 1：Synthetic Theory Grid

- `D={256,512,1024,2048,4096}`
- `K={3,9,27,81}`
- depth adaptive grid around predicted transition
- seeds ≥20
- fp32、bf16
- structured signed permutation、GRU、random overwrite controls

Primary outputs：

1. full-sequence recovery vs $L$；
2. collapse vs $L\log K/D$；
3. observed $L^*(D,K)$；
4. leave-one-D-out / leave-one-K-out prediction；
5. numerical error conditional on correct decode。

Gate T1：normalized curves collapse substantially better on $L\log K/D$ than on L alone。

Gate T2：held-out D/K transition prediction error低于预注册阈值，例如 median relative error <20%。

## Phase 2：Held-Out Real Hidden Geometry

Models：

- Qwen3-0.6B；
- Qwen3-1.7B；
- Qwen3-4B；
- 至少一个更大 Qwen checkpoint；
- 若资源允许，再加一个非 Qwen family。

Axes：

- layers：25%、50%、75%、final；
- tasks：graph_color、general SAT、sudoku；
- train/calibration instances 与 test instances 严格分离；
- raw/global whitening/per-instance upper bound。

Gate G1：frozen whitening 在 held-out instances 上保留显著 gain。

Gate G2：D scaling 不能只依赖三个同 family 点；至少需要 4 个 D 点或 2 个 model families。

## Phase 3：Memory-Matched Redundancy

Conditions：

1. `1 × D`；
2. `N × D` replicas；
3. `1 × ND`；
4. `N × (D/N)`；
5. same-byte ECC/control；
6. random replica selection；
7. confidence selection；
8. majority vote。

报告三维 Pareto：

$$
(\text{accuracy},\text{mutable bytes},\text{encoder/decoder FLOPs}).
$$

Gate R1：只有在 same-total-memory 控制下仍存在 gain，才可称“coding advantage”；否则只称“replication reliability tradeoff”。

## Phase 4：Causal Bridge on Real Frozen Qwen

使用现有 Reasoning Gym harness，但替换 memory substrate。

同一实例、同一 Qwen、同一 branch policy、同一 budget 下比较：

| Arm | Memory |
|---|---|
| F0 | forward-only，无 recovery |
| L-R | explicit bounded list，R entries |
| VSA-1 | self-decoding CRSM，one register |
| VSA-3 | three replicated CRSM registers |
| GRU-D | fixed-D learned recurrent memory |
| Full-history | append-only history / prompt memory |
| No-revert | register存在但禁止 causal pop |

先做 controlled CSP：

- propagation-only；
- backtracking-required；
- depth bins around predicted $L^*$；
- 同 task size、不同 required backtrack depth。

再做 external tasks：

- Reasoning Gym graph_color；
- Sudoku 或 general SAT 至少一个；
- official scoring。

Gate C1：VSA-1 在 below-capacity bin 接近 explicit list，above-capacity 按 theory collapse。

Gate C2：No-revert 在 backtracking bin 明显失败，但 propagation-only 不受影响。

Gate C3：VSA-3 的 gain 与 offline correlated-redundancy prediction一致。

这是整篇论文最重要的 figure。

## Phase 5：Canonical Baselines and Efficiency

同一个 frozen model backend 上运行：

- one-shot vanilla；
- one-shot thinking；
- best-of-N；
- self-verification；
- ToT；
- RAP；
- explicit list search；
- CRSM。

不要只做单一 cap。报告 anytime curves：

- solve rate vs forwards；
- solve rate vs total tokens；
- solve rate vs mutable external bytes；
- time-to-solve；
- AUC over predeclared budget range；
- unsolved censoring。

主 fairness 是多轴 Pareto，不通过 padding 强行制造 identical realized spend。

---

## 8. 数据与统计设计

### 8.1 数据切分

至少四个互不重叠 split：

1. whitening calibration；
2. difficulty calibration；
3. development/smoke；
4. frozen confirmatory test。

禁止：

- 用 test states 重新拟合 whitening；
- 根据 headline arm 的失败情况挑实例；
- 在 confirmatory run 后改变 primary family。

### 8.2 Primary contrasts

不要再声明 56 个同等 primary tests。建议只预注册四个：

1. CRSM vs forward-only on backtracking-required bin；
2. CRSM vs explicit list at same memory budget；
3. no-revert interaction：backtracking minus propagation；
4. replicated CRSM vs one CRSM at matched total memory。

对四个 primary contrasts 做 Holm；其他 W/rho/N/model curves 是 secondary/exploratory。

### 8.3 样本量

- 每个 primary downstream task 至少 50 个 paired confirmatory instances；
- 至少 3 个独立 instance seeds/splits；
- exact McNemar 用于 solve；
- paired bootstrap 用于 token/forward/AUC；
- hierarchical logistic model 汇总 task/model heterogeneity；
- run 前用预期 discordant counts 做 exact power simulation。

### 8.4 Effect size

所有 p-value 同时报告：

- paired solve-rate difference；
- odds ratio；
- 95% CI；
- median token/forward difference；
- memory bytes ratio；
- failure status decomposition。

---

## 9. 推荐 baseline 层次

### Mechanism baselines

- raw vs frozen-whitened；
- supplied-item pop vs self-pop；
- structured VSA vs GRU；
- N=1 vs memory-matched N replicas；
- explicit list vs dense register。

### Search baselines

- no-memory forward；
- explicit bounded list；
- chronological DFS；
- conflict-directed backjumping；
- full-history prompt；
- one-shot thinking；
- best-of-N；
- ToT/RAP。

### Upper/lower bounds

- symbolic oracle search：ceiling/context，不是 target to beat；
- random branch/target：floor；
- oracle target with learned branch；
- learned target with oracle branch。

branch-source × target-source 2×2 是判断 LLM 到底贡献在哪里的必要实验。

---

## 10. 论文主图设计

### Figure 1 — Three properties are not equivalent

概念图：

- algebraic reversibility；
- information capacity；
- causal search utility。

用 v6 说明前两者不自动推出第三者。

### Figure 2 — Theory collapse

`D × K × L` self-pop recovery curves，对横轴 $L\log K/D$ collapse。

### Figure 3 — Geometry and frozen whitening

- raw covariance spectrum；
- frozen whitening held-out gain；
- per-instance whitening upper bound；
- across layers/models/tasks。

### Figure 4 — Memory reliability Pareto

accuracy vs total mutable bytes，比较：

- one D；
- N×D；
- one ND；
- N×D/N；
- GRU。

### Figure 5 — Causal bridge

solve rate vs required depth：

- explicit list；
- CRSM；
- no-revert；
- GRU；
- forward-only。

同时画 predicted capacity boundary。

### Figure 6 — Real-Qwen anytime efficiency

solve rate vs tokens/forwards/memory bytes，在 graph_color 和第二任务上比较 CRSM、thinking、ToT/RAP、best-of-N。

### Figure 7 — Failure map

按 below-capacity、near-wall、above-capacity 分解：

- decode error；
- controller error；
- verifier error；
- budget exhaustion；
- no recovery target。

---

## 11. 推荐论文结构

1. **Introduction**
   - token history 是可增长 memory；latent/external fixed memory 的限制未被清楚测量；
   - 提出 algebraic / capacity / causal 三层审计。
2. **Problem Definition**
   - 定义 L、W、K、D、mutable bytes、operator budget；
   - 明确 environment state 与 search history 的边界。
3. **Causal Reversible Search Memory**
   - self-decoding push/pop；
   - no-bypass contract；
   - memory accounting。
4. **Capacity Theory**
   - conditional exactness；
   - $L\log K/D$；
   - anisotropy；
   - correlated redundancy。
5. **Controlled Memory Experiments**
   - D×K；
   - held-out whitening；
   - memory-matched redundancy。
6. **Frozen-LM Search Experiments**
   - controlled depth bins；
   - Reasoning Gym tasks；
   - causal ablations。
7. **Baselines and Efficiency**
   - canonical methods；
   - anytime/Pareto curves。
8. **Transfer Boundary**
   - v6 proxy 为什么失败；
   - capacity 不等于 capability。
9. **Limitations and Ethics**
10. **Conclusion**

---

## 12. 审稿人最可能的质疑与预先回答

| 质疑 | 必须提供的回答 |
|---|---|
| 你只是把 stack 放在 Python list | no-bypass memory audit + self-pop API |
| pop 时已经给了正确 item，结果是 tautology | autonomous full-sequence self-pop |
| codebook 本身比 register 更大 | complete mutable-byte accounting |
| whitening 看到了 test bundle | frozen calibration transform |
| N replicas 只是用了 N 倍 memory | same-total-memory controls |
| $D/(2\ln K)$ 没测 K | full D×K grid + held-out prediction |
| W wall 与 search depth无关 | separate L/W experiments + causal bridge |
| symbolic engine 才是 solver | branch-source × target-source factorial；明确 scope 是 LLM-guided search |
| baseline 不公平 | same backend、same instances、anytime curves、memory axis |
| 只在一个 synthetic task 上有效 | ≥2 tasks、≥2 model scales；official scoring |
| v6 已经失败 | v6 是 proxy bridge failure，不是 real causal CRSM test |

---

## 13. Go / No-Go 决策树

### G0：定义完整性

- no bypass；
- self-pop；
- memory accounting；
- frozen whitening。

**若 FAIL：停止论文 headline，先修方法。**

### G1：理论与容量

- D×K collapse；
- held-out prediction；
- below/above wall transition。

**若 FAIL：删除 capacity-law 主张，只保留经验 memory study。**

### G2：memory-matched redundancy

- same-total-memory 后仍有 gain：称 coding advantage；
- 否则：称 replication tradeoff，不使用 multi-agent novelty。

### G3：causal bridge

- CRSM 在 below-wall 接近 explicit list；
- above-wall 按预测 collapse；
- no-revert interaction 成立。

**若 FAIL：机制论文和 externalization 论文拆开。**

### G4：real-Qwen downstream

- 至少两任务；
- 至少一个 primary Holm contrast 正向；
- efficiency Pareto 不被 canonical baseline 完全支配。

**若 PASS：主会级完整论文。**

**若 FAIL：写 “Capacity Before Capability” 边界论文，但不声称 downstream advantage。**

---

## 14. 投稿策略

### 路线 A：强单篇论文（推荐，前提是 G3/G4 PASS）

内容：theory + no-bypass method + real-Qwen causal bridge + canonical baselines。

适合：ICLR / NeurIPS / ICML 风格主会。

### 路线 B：拆成两篇（G3 或 G4 FAIL 时）

**Paper A — Mechanism**

- self-decoding reversible memory；
- D×K scaling；
- held-out geometry；
- memory-matched redundancy。

适合：TMLR 或主会的机制型投稿。

**Paper B — Externalization**

- explicit bounded list；
- real Qwen3.5；
- Reasoning Gym；
- thinking/ToT/best-of-N efficiency；
- multi-agent separator line单独处理。

沿用：

- [Externalization full execution spec](externalization_paper_full_execution_v1.md)

不要把 multi-agent separator、latent VSA capacity、real-Qwen bounded list、KV-cache systems 全部塞进同一篇；这会让主线失焦。

### 路线 C：MLSys 版本

仅当 KV-cache bounded checkpoint 和 wall-time/memory savings成为最强结果时采用；此时核心指标是 system efficiency，不是 cognitive capacity。

---

## 15. 最小执行顺序

### Step 0 — 先修定义，不跑大模型

1. 实现 `SelfDecodingRegister`；
2. 移除 headline loop 的 `branch_stack`；
3. 建立 mutable-memory auditor；
4. 建立 frozen whitening split；
5. 写 Phase 0 kill tests。

### Step 1 — 理论 grid

1. D×K×L；
2. self-pop sequence；
3. dtype；
4. curve collapse；
5. memory-matched redundancy。

### Step 2 — 复用现有 real hidden states

1. 对现有 state shards 做 train/test split；
2. 冻结 whitening；
3. 重新测 held-out W*；
4. 判断 v4/v5 effect 是否 survives。

### Step 3 — 接到现有 Reasoning Gym loop

1. explicit list 保留为 gold systems baseline；
2. 新增 CRSM substrate；
3. 同实例 paired smoke；
4. controlled depth bins；
5. no-revert/GRU controls。

### Step 4 — 只在 gates 通过后跑 full Qwen grid

1. graph_color；
2. sudoku 或 SAT；
3. thinking/best-of-N/ToT/RAP；
4. 第二 model scale；
5. confirmatory statistics。

### Step 5 — 最后才决定论文标题与 headline

不要在 G3/G4 之前承诺“beats baselines”。

---

## 16. 现有 artifact 如何使用

### 主文可复用为 pilot / motivation

- [SPEC v2](../results/capacity/SPEC_v2_run_summary_qwen3_fp32.md)：conditional algebraic exactness；
- [SPEC v4](../results/capacity/SPEC_v4_run_summary_qwen3_fp32.md)：pilot D scaling 与 whitening；
- [SPEC v5](../results/capacity/SPEC_v5_run_summary_qwen3_fp32.md)：replication reliability pilot；
- [Real-Qwen graph-color](../results/externalization_validation_v0/graph_color_ceiling_llm.json)：explicit bounded-list search positive；
- [Token accounting correction](../results/externalization_validation_v0/honest_token_accounting_addendum.json)：honesty precedent。

### Appendix / negative boundary

- [SPEC v6](../results/downstream/SPEC_v6_run_summary.md)：proxy transfer failure。

### 不能直接合并

- 不同实例/预算的 ToT/RAP artifacts；
- symbolic multi-agent 与 real-Qwen monolith；
- list-register R 与 VSA W；
- per-instance whitening 与 deployable frozen whitening。

---

## 17. 最终建议

### 最强故事

不是：

> 我们做了一个 multi-agent reversible method，并在所有 baseline 上更好。

而是：

> We separate three properties that are often conflated in external-memory reasoning—algebraic reversibility, information capacity, and causal utility. We derive and test the capacity of a self-decoding reversible memory, show how hidden-state geometry and redundancy control reliability, and identify the exact capacity boundary at which a frozen language-model search loop succeeds or fails.

这条故事有四个优点：

1. v6 负结果不是尴尬，而是论文动机；
2. 理论、机制和 downstream 构成因果闭环；
3. 审稿人最容易攻击的旁路、codebook、whitening 和 memory fairness 都被前置解决；
4. 即使 downstream 不胜 baseline，也能留下清楚且可复现的 capacity boundary。

### 现在最应该做的下一件事

**不是继续跑 v7 大 grid。**

先完成一个小而严格的 Phase 0 artifact：

> `SelfDecodingRegister + no-bypass SearchLoop + mutable-memory audit + supplied-pop/self-pop comparison`。

只有它通过，当前研究才真正拥有一篇好论文所需要的“方法对象”。
