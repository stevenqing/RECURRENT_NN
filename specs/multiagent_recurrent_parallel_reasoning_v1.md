# Recurrent Parallel Agent Reasoning

> **SPEC v7-RPD preflight update (2026-07-12):** A fixed-density exact-diameter graph environment with decoupled rollback noise passed all CPU harness gates. Exact one-hit rollback is an asset at $\eta=0$, while frozen two-hit confirmation becomes preferable under false positives. No $\delta$ shift can yet be claimed; the next required component is the synchronous parallel recurrent engine and fixed $B=MT$ sweep. See [v7 closeout](../results/recurrent_signal_phase_v7_preflight/CLOSEOUT.md).

> **Synchronous RPD P0 update (2026-07-12):** A 17-agent Jacobi engine completed 960 development rows with immutable snapshots and one-round-delayed messages. Correct recurrent messages raised pooled long-diameter solve from 0 at T=1/no-message/shuffled controls to 1.0 at T=32; T≥0.90 increased from 4 rounds at $\delta\in\{2,4\}$ to 16 rounds at $\delta\in\{8,16\}$. Persistent candidate state was not identified because state-reset also solved 1.0. Verdict: `RPD_MESSAGE_RECURRENCE_ONLY`. See [P0 closeout](../results/recurrent_parallel_engine_p0/CLOSEOUT.md).

> **Fixed-$B=MT$ update (2026-07-12):** A 320-row width/depth sweep passed all frozen gates. At $B=136$, $M=8,T=17$ solved 1.000 with mean idealized path 5.62, while $M=1$ solved 1.000 at path 16.06 and $M=17,T=8$ fell to 0.844 from recurrence starvation. At $B=272$, $M=17,T=16$ recovered solve 1.000. Verdict: `RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE`. This is symbolic development, not actual timing. See [fixed-budget closeout](../results/recurrent_parallel_fixed_budget/CLOSEOUT.md).

> **Compressed-message state update (2026-07-12):** With one boundary fact per edge/round, compressed persistent recurrence retains solve 1.000 using 0.553× the full-message facts; all-state reset, shuffled, and no-message controls solve 0. However, newest-fragment-only cache also solves 1.000, so explicit message-cache necessity fails even though persistent candidate state is necessary. Verdict: `RPD_COMPRESSED_MESSAGE_RECURRENCE_ONLY`; learned-state training is not authorized. See [compressed-state closeout](../results/recurrent_parallel_compressed_state/CLOSEOUT.md).

> **Recurrent signal graph confirmation (2026-07-12):** A locked 3,600-row independent graph study confirms that recurrent correction noise interacts with diameter. The one-hit/two-hit work crossing is 0.10 at $\delta=2$, 0.05 at $\delta=4$, and 0.02 at $\delta=8,16$; all gates pass. This is the first independent RPD phase result, but it remains graph-only and symbolic. See [graph signal closeout](../results/recurrent_parallel_signal_graph_confirmation/CLOSEOUT.md).

> **SAT replication boundary (2026-07-12):** A 576-row long-diameter SAT development study confirms recurrent one-hit hazard but rejects fixed two-hit robustness at large diameter. Independent SAT confirmation is blocked. The next hypothesis must scale verification depth with recurrent exposure, while the current paper claim remains graph-specific. See [SAT signal closeout](../results/recurrent_parallel_signal_sat_development/CLOSEOUT.md).

> **Exposure-calibrated guard update (2026-07-12):** An analytically frozen $k(\eta,\delta)$ policy repairs the SAT two-hit failures and passes a locked 4,800-row independent confirmation. The same formula is robust on graph but fails a strict every-cell hazard-dominance gate, so no universal adaptive-policy claim is made. The evidence supports substrate-dependent allocation of verification depth under a common recurrent hazard law. See [SAT adaptive closeout](../results/recurrent_parallel_adaptive_guard_sat_confirmation/CLOSEOUT.md) and [graph adaptive closeout](../results/recurrent_parallel_adaptive_guard_graph/CLOSEOUT.md).

> **Cost-sensitive policy confirmation (2026-07-12):** Replacing the survival-only schedule with a common expected-cost objective yields substrate-specific schedules from frozen eta=0 exposure calibration. New graph and SAT pools jointly pass robustness, perfect-signal, high-exposure value, schedule, and signal-necessity gates. A replay helper metadata mismatch is corrected by an erratum without rerunning raw rows. The confirmed object is a recurrent verification resource-allocation law, not a fixed universal $k$. See [joint closeout](../results/recurrent_parallel_cost_sensitive_confirmation/CLOSEOUT.md).

## Spatial Agents × Temporal Recurrence Research Strategy v1

- 日期：2026-07-12
- 状态：主线 research strategy；不是新实验结果
- 目标：构造真正 recurrently updated、空间并行的 multi-agent reasoning system
- 当前 empirical foundation：[capacity-valid cross-substrate result](../results/multiagent_capacity_valid_route_tail_control/SUMMARY.md)

---

## 1. 方向修正

上一版把下一步集中在 rollback capability protocol。它解决的是 fully decentralized correctness，但不是最终研究主线。

新的主线应是：

> **把 multi-agent reasoning 建模为一个二维 recurrent computation：agent 轴提供空间并行，round 轴提供时间递归；多个 weight-tied local reasoners 在固定大小 state 上并行更新，通过稀疏 residual messages 逐轮收敛。**

Rollback capability、versioning 和 no-free-read 仍然重要，但它们降级为 message layer 的 correctness constraint，而不是论文 headline。

---

## 2. 一句话 architecture

建议名称：

- **Recurrent Parallel Deliberation (RPD)**；
- **Spatial–Temporal Agent Recurrence (STAR)**；
- 或 **Recurrent Agent Field (RAF)**。

首选暂定：**Recurrent Parallel Deliberation (RPD)**。

系统包含 $M$ 个 weight-tied agents。每个 agent $i$ 有：

- local immutable input $x_i$；
- fixed-size recurrent latent state $h_i^t\in\mathbb R^d$；
- bounded explicit register $r_i^t$；
- incoming message state $\bar m_i^t$；
- local proposal $y_i^t$；
- verifier residual $e_i^t$。

在 round $t$，所有 agents 基于同一个 round-$t$ snapshot 并行更新：

$$
q_i^t=O_\theta(x_i,h_i^t,r_i^t,\bar m_i^t),
$$

$$
(h_i^{t+1},r_i^{t+1},y_i^t,m_i^t,c_i^t)
=F_\phi(h_i^t,q_i^t,r_i^t,\bar m_i^t,e_i^t),
$$

其中：

- $O_\theta$ 可以是 symbolic local operator、轻量 recurrent operator 或 frozen Qwen；
- $F_\phi$ 是跨 agents、跨 rounds weight-tied 的 recurrent update cell；
- $m_i^t$ 是固定 bandwidth message；
- $c_i^t$ 是 local confidence/halting gate。

所有 $y_i^t$ 在 barrier 处一起验证和 commit：

$$
(a^{t+1},e^{t+1})=V(a^t,\{y_i^t\}_{i=1}^M).
$$

然后 messages 被交付给下一 round：

$$
\bar m_i^{t+1}=\operatorname{Agg}\{m_j^t:j\in\mathcal N_t(i)\}.
$$

这是真正的 recurrent update：

- weights 在时间上共享；
- state 不随 transcript 无限增长；
- 每一轮都可以修正上一轮；
- agent 间信息传播需要多个 rounds；
- $T$ 是 test-time recurrence budget。

---

## 3. 为什么要用 synchronous snapshot / Jacobi update？

每个 recurrent round 使用 round 开始时的 frozen snapshot：

1. 所有 agents 同时读取 $a^t,h^t,m^{t-1}$；
2. 所有 local updates 独立执行；
3. 同一 round 内不能读取其他 agent 刚写出的 $h_j^{t+1}$；
4. barrier 后统一 commit；
5. messages 在 $t+1$ 才可见。

这对应 Jacobi-style parallel update，而不是当前 Python loop 的 Gauss–Seidel sequential update。

价值：

- 可以真实 batch/parallelize；
- critical path 是 recurrent rounds，不是 agent activations 总和；
- 避免隐式 agent-order advantage；
- 允许严格比较 parallel versus centralized-sequential execution；
- 信息每轮最多传播一跳，产生可测的 communication-depth law。

---

## 4. 真正的研究对象：$M\times T$ reasoning geometry

传统 test-time compute 通常只报告 scalar budget $B$。

这里把 compute 分成：

- 空间宽度 $M$：并行 agents；
- 时间深度 $T$：recurrent rounds；
- 总 agent updates $B=M T$。

在固定 $B$ 下：

- $M=1,T=B$：单 agent 深度 recurrence；
- $M=B,T=1$：one-shot ensemble/decomposition；
- $1<M<B$：parallel recurrent team。

核心问题是：

> 在 fixed total operator calls、total recurrent state 和 total memory 下，最优 reasoning compute 应如何在 spatial agents 与 temporal recurrence 之间分配？

### 预测

设：

- $D_{local}(M)$：最大 local reasoning depth；
- $D_{comm}(M,\rho)$：跨 partition dependency propagation depth；
- $C$：local recurrent-state capacity；
- $S$：message bandwidth；
- $\delta(G_P)$：partition graph diameter。

parallel recurrent system 至少需要：

$$
T\ge D_{comm}(M,\rho)\gtrsim\delta(G_P),
$$

且：

$$
L_{local}^{\max}(M)\le C.
$$

固定 $B=MT$ 时，过大的 $M$ 会导致：

$$
T=B/M<D_{comm},
$$

信息来不及跨 blocks 传播；过小的 $M$ 会导致 local state/context overflow。

因此预期存在 interior optimum：

$$
1<M^*<B,
$$

而不是“agents 越多越好”或“rounds 越多越好”。

这可以形成新的 **spatial–temporal reasoning phase diagram**。

### Noisy-feedback refinement

SPEC v7 加入一个关键反作用：每个 recurrent correction round 也是一次接触错误 rollback signal 的机会。若 harmful live-state exposures 为 $L(M,T,\delta)$，则 exact policy 不发生 harmful false positive 的概率近似：

$$
P_{survive}=(1-\eta_{fp})^{L(M,T,\delta)}.
$$

所以 recurrence 同时：

- 增加 dependency propagation depth；
- 增加 signal-noise exposure；
- 增加 synchronization cost。

真正的规律不再只是 $T\ge\delta$，而是存在：

$$
T^*(\eta,\delta),
$$

它在 under-propagation 与 recurrent hazard accumulation 之间取得平衡。联合设计见 [SPEC v7-RPD](recurrent_parallel_signal_phase_v7.md)。

---

## 5. Parallel free lunch 应该定义在哪里？

不再追求 unrestricted centralized simulation 无法解释的 aggregate-work miracle。

真正可证伪的收益是：

### 5.1 Critical-path latency

如果 agents 同步并行：

$$
T_\infty^{team}
\approx
T\cdot\max_i C_i + T_{sync},
$$

而 sequential sharded control：

$$
T_\infty^{seq}
\approx
T\cdot\sum_i C_i.
$$

### 5.2 Context/attention factorization

local context 长度为 $L_i$，固定 recurrent state/message 长度为 $K+S_i$：

$$
F_{team}^{round}
\propto
\sum_i(L_i+K+S_i)^2.
$$

若 balanced partition 且 $L_i\approx L/M$：

$$
F_{team}^{round}
\approx
\frac{L^2}{M}+2L(K+\bar S)+M(K+\bar S)^2.
$$

monolithic recurrence 约为：

$$
F_{mono}^{round}\propto(L+MK)^2.
$$

在 messages/state 足够小的区域，local recurrent contexts 可以降低 attention FLOPs，同时 agent calls 可以并行。

### 5.3 State amortization

local problem prefix 只 encode 一次；每轮只更新：

- fixed $K$ state tokens；
- sparse boundary messages；
- changed local assignments。

静态 local prefix KV 可以复用，避免每轮重新 encode global prompt。

---

## 6. Repository-native model

### 6.1 Local recurrent state

复用：

- [Structured register](../register/structured.py)；
- [GRU baseline/register](../register/gru_baseline.py)；
- [Weight-tied recurrent operator](../experiments/train_recurrent_operator.py)；
- [Controller head](../controller/controller_head.py)；
- [Verifier head](../controller/verifier_head.py)。

每个 agent state：

$$
s_i^t=(h_i^t,r_i^t,a_i^t,e_i^t,\mathcal M_i^t).
$$

推荐初始配置：

- $d=128$ lightweight recurrent state；
- structured register dimension $D=256$；
- message bottleneck $p=32$；
- $M\in\{1,2,4,8\}$；
- $T\in\{1,2,4,8,16,32\}$。

### 6.2 Frozen Qwen integration

复用 [Frozen Qwen operator](../llm_operator/wrapper.py)，但不应每轮把完整 transcript 重新 prompt。

建议：

1. local static problem prefix 产生 cache；
2. $h_i^t$ 投影成固定 $K$ 个 soft state tokens；
3. incoming messages 投影成固定 $S$ 个 message tokens；
4. Qwen 对 `[cached local prefix; state tokens; message tokens]` 做 local update/readout；
5. 最后一层 hidden state 输入 weight-tied recurrent adapter；
6. Qwen weights frozen，只训练 adapter/message encoder/controller。

形式：

$$
z_i^t=\operatorname{Qwen}_\theta
(x_i, P_hh_i^t,P_m\bar m_i^t),
$$

$$
h_i^{t+1}=\operatorname{GRU}_\phi
(h_i^t,[z_i^t,e_i^t]).
$$

所有 agents 在同一 round 打包成 batch，实际并行执行。

### 6.3 Active-set recurrence

不是每轮所有 agents 都必须调用重 operator。

定义：

$$
a_i^t=\mathbb 1[e_i^t>\epsilon
\lor\Delta\bar m_i^t\ne0
\lor c_i^t<\tau].
$$

只有 active agents 更新；已收敛 agent 保持 state，但新 boundary residual 可重新激活。

这使 recurrence 具有：

- event-triggered sparsity；
- adaptive computation；
- local convergence；
- coupling-dependent active width。

---

## 7. 它与现有方法有什么区别？

### 已有直接邻居

- CommNet：可微 multi-agent communication；
- DIAL：learned inter-agent messages；
- recurrent GNN/message passing：并行迭代传播；
- Universal Transformer / ACT：weight-tied recurrent depth；
- Deep Equilibrium Models：fixed-point computation；
- Recurrent Independent Mechanisms：稀疏交互的 recurrent modules；
- multi-agent debate：多轮语言交互；
- neural algorithmic reasoning：weight-tied processor/message passing。

因此以下都不新：

- recurrent updates；
- parallel message passing；
- shared weights；
- learned communication；
- iterative refinement；
- adaptive halting。

### Potential novelty 必须来自组合后的明确问题

1. **固定总 compute 下的 spatial-agent × temporal-recurrence allocation law**；
2. **bounded fixed-size agent state，而不是增长的 conversation transcript**；
3. **actual critical-path 与 attention-FLOP accounting，而不是只看 accuracy**；
4. **one-shot ensemble、single recurrent agent、sequential sharded recurrence、GNN/CommNet controls 全部 matched**；
5. **coupling diameter 决定所需 recurrent rounds 的 phase law**；
6. **frozen local LLM prefix/cache + small recurrent state tokens 的 amortized execution**；
7. **cross-substrate confirmation and real parallel hardware measurement**。

最有机会的新贡献不是“发明 recurrent agents”，而是：

> **给出并验证 reasoning compute 在空间宽度与时间递归深度之间的资源分配规律。**

## 8. Real-Agent Instantiation: EBW / Proof-Carrying Actions

AppWorld Evidence-Bound Writes (EBW) 是当前最贴近真实 agent 应用的 RPD 落点。这里的 agent 不是在玩抽象 voting game，而是在执行有副作用的工具写操作：移动文件、发消息、写数据库字段、使用 prior API effects。系统允许多个 agents 并行提出 action proof sketch，但 barrier 只在唯一候选被 deterministic verifier 证明时 commit。

这条线把 RPD 的 recurrent state 从 hidden conversation 变成 typed verifier residual：

$$
e_i^t=(role,slot,predicate,counterexample,missing\ evidence,ambiguity,unsafe\ reason).
$$

下一轮不是让 agent “再想想”，而是把 residual 当作 text-gradient 编译回 proof frontier：

1. `VerifierAgent` 对每个 proposal 产生 typed residual；
2. `RepairAgent` 只允许基于 residual 修改 proof sketch 或申请新增 proof grammar；
3. `MetaVerifier` 检查新增 grammar 是否只是 prompt shortcut，还是能在 adversarial candidates 下保持唯一有效性；
4. 通过后，frontier 进入下一轮，并在 sealed/opened split 上重新 gate。

EBW Track A v8/v9/v10 已经给出一个具体例子：full-v8 的 derived-path unsafe 不是模型随机错误，而是 `projection_loss` residual；v9 增加 `path_pair_transform_binding` 后，120 个直接覆盖的 unsafe rows 在 deterministic gate 与 model-facing Qwen gate 中都变成 `commit_live` 且 0 unsafe。v10 进一步把剩余 36 个 mismatch 归因到 path literal canonicalization residual，并在 CPU-only deterministic gate 中覆盖全部 156 个 full-v8 derived unsafe rows。v11 residual taxonomy 显示下一组 post-v10 residual 不是 safety failure，而是可分解的 abstain/coverage frontier gaps，其中最大 post-v10 类是 65 个 `title_slug_export_path_binding_missing`。这个结果应作为 RPD 的 real-agent proof-carrying action substrate，而不是孤立工程 patch。

### 8.1 EBW 中的 parallel free lunch

free lunch 不来自多数投票，而来自 proof search factorization：

- filesystem path agent 只搜索 path/date/directory binding；
- literal intent agent 只搜索 task-span binding；
- ordered-role agent 只搜索 ordinal/source-read binding；
- prior-effect agent 只搜索 previous-write membership；
- barrier 把所有候选压成唯一有效性判定。

在固定 wall-clock critical path 下，多个 proof-family agents 可以并行搜索不同 obligation；deterministic verifier 阻止错误写入；typed residual 把失败留下来作为下一轮 recurrent update 的可复用状态。

### 8.2 Required EBW controls

EBW 线必须报告：

- `single_agent_all_obligations`：一个 agent 串行处理所有 proof families；
- `parallel_family_agents`：每个 proof family 一个并行 agent；
- `parallel_same_family_resampling`：同一 proof family 的独立重采样，排除普通 ensemble；
- `repair_agent_without_metaverifier`：证明 grammar patch 需要 verifier gate；
- `residual_shuffled`：打乱 typed residual 到错误 family，验证 recurrence signal 必须匹配；
- `candidate_frontier_oracle` 与 deterministic frontier 分开报告。

主要指标不是 raw task accuracy，而是：safe commit recovery、unsafe unique-wrong、parse rate、frontier coverage、residual-to-grammar repair yield、repair rounds、critical-path latency、sealed split safety。

### 8.3 v11 RepairAgent benchmark

下一步不应继续 chase v10 分数，而应把 v9/v10 人工 repair 过程变成可证伪 benchmark。当前 preregistered target 是 `title_slug_export_path_binding`：Simple Note title evidence 通过 whitespace-to-underscore transform、task literal backup directory、`.md` extension 证明 filesystem write path。

R1 CPU feasibility 已通过：65/65 target rows 在 corrected frontier 下 `commit_live`，0 unsafe。关键细节是 source binding 必须使用 latest matching pre-write `show_note` read；content-only matching 会因为 habit tracker 内容重复而绑定错 title。这个失败再修复的过程本身就是 typed residual 作为 text-gradient 的例子。

R3 model-facing gate 的第一版暴露了 output-contract residual：Qwen 在 60/65 rows 输出有效 `title_slug_export_path_binding`，另外 5 个把 output key 写成 `required_obligation` 或漏掉 `obligation`。v11b 不放宽 parser，只强化 response contract，并只 rerun 5 个失败行，得到 5/5 commit。合并后 title-slug target 65/65 commit、0 unsafe；full executable compositional rescore 提升到 822 commit、25 abstain、0 unsafe。这里的 lesson 是：MetaVerifier/strict parser 应继续把 contract leakage 作为 typed residual，而不是容忍解析。

v12 CPU-only MetaVerifier preflight 已完成：两个正确 repair proposals 被接受（latest-`show_note` frontier、`obligation` output contract），四个 shortcut controls 被拒（content-only binding、residual-shuffled、parser relaxation、prompt-only）。这还不是 autonomous RepairAgent，但它把 evaluator 固定住了：下一步只替换 proposal source，让 model/agent 从 typed residual text 生成 patch JSON，MetaVerifier 保持不变。

v14 answer-blinded RepairAgent attempt 是当前 autonomous proposal 的 no-go：Qwen 输出 2/2 parseable patch JSON，但 MetaVerifier 0/2 接受。失败原因正是我们希望 evaluator 抓住的 shortcut：title-slug repair 回到 content-only binding，contract repair 把 `required_obligation` 误当 required key。这个 negative result 支持方法论边界：MetaVerifier 已就绪，但 RepairAgent proposal policy 还不够强。

v15 structured repair policy 通过 CPU gate：给定 typed residual packets、primitive library 和 deterministic compiler，系统能选择 latest-`show_note` frontier 与 strict `obligation` contract，MetaVerifier 接受 2/2；同一组 shortcut controls 继续被拒。下一步的模型贡献应收窄为 primitive selection，而不是 free-form patch JSON generation。

v16/v16b model-in-the-loop primitive selection 已通过：Qwen 首轮正确选择 title-slug primitives，但在 output-contract residual 漏选 `parser_policy.strict`；v16b 只 retry 该 compile failure，并通过 slot-completeness instruction 补齐。合并后 Qwen-selected primitives 2/2 被 deterministic compiler + unchanged MetaVerifier 接受。这是当前第一个 agent-in-the-loop repair success，但 scope 仍限于已定义 primitive vocabulary。

v17 已把下一类 post-v11b abstain `directory_basename_archive_path_binding_missing` 打开：9/9 vacation-directory compression rows 可由 immutable directory-list evidence 的 basename、task literal archive template 和 extension 证明，0 unsafe。随后 strict grammar/prompt/runner integration 与 9-row model-facing target 均通过，Qwen 9/9 commit、parse 1.0；full executable compositional rescore 提升到 831 commit、16 abstain、0 unsafe。下一步是把 archive-path 纳入 structured RepairAgent primitive selection，而不是继续人工扩 grammar。

v18 archive structured policy 已通过 CPU gate：archive-path 被纳入 primitive selection action space，正确 primitives 被 MetaVerifier 接受，generic basename projection、wrong template、wrong transform、wrong extension、parser relaxation、prompt-only 六个 shortcut controls 被拒。下一步是单 residual packet 的 model-in-the-loop primitive selection。

v19 archive model-in-the-loop primitive selection 已通过：Qwen 在 answer-blinded archive residual packet 上选择完整 primitive set，deterministic compiler + unchanged archive MetaVerifier 接受 1/1。这把 model-in-loop RepairAgent 从 title-slug/output-contract 扩展到第三个 proof family。下一步应重新做剩余 16 个 safe abstentions 的 residual taxonomy。

v20 residual taxonomy 已完成：剩余 16 个 safe abstentions 分为 7 个 prior-effect playlist、5 个 source-path identity、2 个 literal export path、2 个 ordered note identity。下一步 CPU-first target 是 `source_path_identity_binding`，因为它是 path-pair destination proof 的自然补全：证明 `move_file.source_file_path` 本身来自 immutable source path evidence。

v21 source-path identity CPU feasibility 已通过：5 个 `move_file.source_file_path` residual 全部被 exact `response.path` identity proof 覆盖，5/5 commit-live，0 unsafe。下一步不是直接 Qwen，而是把 `source_path_identity_binding` 接进 strict parser、prompt manifest builder、runner/rescorer 和 tests，再做 CPU compositional rescore。

v22-v28 deterministic frontier closure 已完成：v22 source-path identity 把 full executable gate 推到 836/11/0，v24 literal export path 到 838/9/0，v26 ordered note title identity 到 840/7/0，v28 prior-effect playlist 到 847/0/0。这里的 claim 是 recurrent typed residual -> deterministic proof-frontier closure，不是新的 Qwen synthesis。下一步应把这些 residual packets 编成 RepairAgent primitive-selection benchmark，让 Qwen 只选 primitives，由 deterministic compiler + unchanged MetaVerifier 验证。

v29/v29b model-in-the-loop primitive selection 已完成：把 v21-v28 closure 编成 4 个 residual packets + primitive library 后，Qwen 首轮接受 3/4，唯一失败是把 `parser_policy.strict` 写成语义值 `parser_policy.strict_json_no_regex_repair`；v29b targeted retry 修复这个 slot，merged eval 4/4 被 deterministic compiler + unchanged MetaVerifier 接受。这是当前最强的 multi-family RepairAgent 结果。

v30 test-time compute protocol 已冻结并开始执行：冻结 parser/verifier/rescorer/v29 primitive library/compiler/MetaVerifier 后，先做 opened-data retrospective replay，只验证 mechanics：round0 v17 是 831 commit / 16 abstain / 0 unsafe；round1 parallel v29b repair 用 5 个记录的 model calls 达到 847 commit / 0 abstain / 0 unsafe。这个结果不能写成 held-out test-time compute claim；真正的下一步是 prospective held-out TTC，在看到 held-out outcomes 之后不允许新增 primitives、proof families、parser edits 或人工 residual taxonomy。

v31-v33 prospective held-out TTC first pass 已完成：fresh variations 10-12 在 v30 freeze 后打开，v31 value-free preflight 得到 24 个 fresh tasks / 169 target instances；v32 no-repair held-out baseline 在 65 个可执行 prompts 上得到 62 commit / 3 abstain / 0 unsafe；v33 只用 frozen v29 primitive library 形成 1 个 `literal_export_path_binding_missing` residual packet，Qwen 选中 quoted task path primitives，MetaVerifier 接受 3/3 target rows，merged rescore 到 65 commit / 0 abstain / 0 unsafe。下一步必须跑 controls，而不是继续加 frontier。

v34 held-out best-of-N no-repair control 已完成：对 v32 的 3 个 held-out abstains，每个额外采样 8 个 proof sketches，不调用 RepairAgent，不新增 frontier。24/24 samples 仍为 abstain，row-level 仍是 3 abstain / 0 unsafe。这支持 v33 的解释：收益来自 typed residual -> frozen primitive selection -> MetaVerifier，而不是普通 test-time 多采样。

v35-v37 held-out controls 已完成：free-form RepairAgent patch JSON 1/1 parse，但因为把 `span_source` 写成 `derived_path_binding` 被 MetaVerifier 拒绝；structured without MetaVerifier 的 compiler-only path 接受 3/3，其中 2 个是 bad controls（wrong span source 和 parser relaxation）。v37 control summary 因此支持当前机制 claim：held-out gain 需要 typed residual、frozen primitive selection、deterministic compiler 和 MetaVerifier，不能简化为多采样或无约束 patch。

v38 no-typed-residual ablation 已完成并改变 claim 边界：隐藏 `residual_class`、`typed_reason`、`failed_frontier`、`counterexample_summary` 后，模型仍然能从 untyped API/field failure metadata 和 frozen primitive library 中选出 literal export path repair，merged rescore 仍为 65/0/0。因此当前 held-out slice 证明的是 structured primitive selection + MetaVerifier 的必要性，而不是 typed residual label 的必要性。typed residual 是否必要需要在更难的 source-path、ordered-note、prior-effect 等 held-out residual 上继续测。

这组 benchmark 的 research value 在于：

- residual 是 typed abstain frontier gap，不是模型随机错误；
- proof schema 必须通过 MetaVerifier adversarial uniqueness；
- `prompt_only_repair`、`residual_shuffled`、`repairagent_without_metaverifier` 都能作为反证 control；
- 成功后可以报告 residual-to-grammar repair yield，而不是只报告 commit 数。

具体 gate ladder 见 [EBW RepairAgent Benchmark v11](recurrent_parallel_ebw_repairagent_benchmark_v11.md)。

---

## 9. 必须使用的 controls

### Architecture controls

1. `single_recurrent_monolith`：$M=1,T=B$；
2. `parallel_one_shot`：$M=B,T=1$；
3. `parallel_recurrent_agents`：$1<M<B$；
4. `centralized_sharded_sequential`：相同 local cells/messages，逐 agent 顺序执行；
5. `parallel_no_message`：隔离 recurrence 与 communication；
6. `parallel_frozen_state`：agent 不 recurrent update；
7. `CommNet_or_GNN_processor`：证明不是普通 message passing baseline；
8. `monolithic_transformer_context`：相同 total token/FLOP budget；
9. `oracle_partition` 与 frozen non-oracle partition 分开。

### Resource matching

必须分别报告：

- model weights 是否共享；
- total mutable state $M d$；
- total explicit register memory $MR$；
- operator calls $MT$；
- prompt/decode tokens；
- attention FLOPs；
- message bytes/tokens；
- actual GPU-seconds；
- wall-clock critical path；
- peak per-device memory；
- synchronization time。

不能用 $M$ 倍硬件产生的 latency gain冒充 aggregate compute gain。

---

## 10. 第一组关键实验：fixed $B=MT$

选取固定 operator-update budgets：

$$
B\in\{16,32,64,128\}.
$$

对每个 $B$ sweep：

$$
(M,T)\in
\{(1,B),(2,B/2),(4,B/4),(8,B/8),(B,1)\}.
$$

在 low/high coupling、under/over local capacity 上测：

- solve；
- failure-penalized work；
- recurrent rounds to convergence；
- active-agent fraction；
- residual decay；
- message volume；
- actual and idealized critical path。

### 主要 prediction

- low coupling：增加 $M$、减少 $T$ 可降低 latency，直到 $T$ 接近 dependency diameter；
- high coupling：需要更多 recurrent rounds，过宽 one-shot team 失败；
- local capacity overflow：$M=1$ 失败，适中 $M$ 成功；
- 极大 $M$：message/diameter overhead 主导；
- 存在随 coupling 移动的 interior $(M^*,T^*)$。

这比“team 平均是否更强”更像一个真实 research law。

---

## 11. 第二组实验：recurrence necessity

冻结 $M$，比较：

- $T=1$ one-shot；
- $T>1$ recurrent；
- recurrent but messages shuffled；
- recurrent but hidden state reset each round；
- recurrent with no residual reactivation。

要证明的不是更多 calls 有用，而是：

1. state persistence 必须；
2. correct cross-agent messages 必须；
3. 多轮传播必须；
4. 增益出现在 dependency distance $>1$ 的实例；
5. 同样 calls 的 independent resampling/ensemble 不能替代 recurrence。

---

## 12. 第三组实验：real parallelism

只有 symbolic/lightweight gate 通过后才使用 GPU 2、3。

### 两卡执行方式

- GPU 2：agents 0…$M/2-1$；
- GPU 3：agents $M/2$…$M-1$；
- 每轮各卡内部 batch local agents；
- barrier 后只交换 fixed-size messages；
- 相同 cells 在单卡 sequential 模式运行 control。

### 必须测

- true wall-clock per round；
- synchronization overhead；
- GPU utilization；
- aggregate GPU-seconds；
- prefix-cache hit rate；
- dynamic-state token cost；
- sequential-sharded versus parallel-sharded latency；
- strong scaling 与 weak scaling。

这才是“parallel reasoning”的直接 evidence。

---

## 13. Preregistered gate ladder

### P0 — Symbolic recurrent semantics

- round snapshot immutable；
- no same-round cross-agent reads；
- message delivery only at barrier；
- deterministic replay；
- official scoring；
- no hidden global rollback。

### P1 — Recurrence necessity

在 dependency-distance $>1$ 的 development slice：

- recurrent policy solve 比 matched one-shot 高至少 0.15；
- 比 state-reset control 高至少 0.10；
- shuffled-message control 明显下降。

否则 recurrent mechanism 不成立。

### P2 — Fixed-budget interior optimum

至少两个 $B$ 和两个 coupling levels 上：

- 存在 $1<M^*<B$；
- interior point 在 solve–critical-path Pareto frontier；
- 不是由更多 total calls/state/memory 解释。

### P3 — Attention/latency value

相对 monolithic recurrence：

- solve non-inferior；
- measured attention FLOPs 或 actual wall-clock 至少下降 20%；
- aggregate GPU-seconds完整报告；
- sequential sharded control 排除纯 decomposition confound。

### P4 — Cross-substrate confirmation

- graph coloring + community SAT；
- new zero-overlap pools；
- spatial–temporal optimum 随 coupling/dependency depth 方向一致；
- failure-penalized expected work 与 solve 同时报。

### P5 — Frozen-Qwen extension

只有 P0–P4 通过：

- local Qwen prefix fixed；
- recurrent state/message tokens fixed-size；
- no growing transcript；
- compare lightweight recurrent operator；
- token/FLOP/wall-clock matched；
- Qwen 不胜 symbolic/lightweight control 则删除 LLM contribution。

---

## 14. 当前已有结果在新主线中的位置

当前 capacity-valid tail-control 结果不是被丢弃，而是变成：

1. recurrent agent message layer 的 failure-recovery primitive；
2. high-residual round 的 targeted correction mechanism；
3. bounded local register 的 safety invariant；
4. coupling/communication phase map 的先验证据；
5. one-shot/failure-tail baseline。

但论文 headline 从：

> rollback routing 更好

提升为：

> reasoning compute 应如何在 parallel agent width 与 recurrent communication depth 之间分配？

---

## 15. 推荐标题

### 最强目标

**Reasoning in Space and Time: Recurrent Parallel Agent Dynamics under Fixed Compute**

### 更 systems-oriented

**Recurrent Parallel Deliberation: Trading Agent Width for Communication Depth**

### 更 LLM-oriented

**Beyond Multi-Agent Debate: Fixed-State Recurrent Parallel Reasoning with Frozen Language Models**

---

## 16. 单一下一步

不要直接启动 Qwen。

先冻结并实现 **P0 symbolic recurrent parallel engine**：

1. $M$ local agent states；
2. synchronous immutable snapshots；
3. all-agent parallel proposal phase；
4. barrier verification/commit；
5. messages visible only next round；
6. fixed-size state/register；
7. explicit $M\times T$ accounting；
8. fixed $B=MT$ sweep；
9. one-shot/state-reset/shuffled-message/sequential-sharded controls。

P1 recurrence-necessity gate 通过后，才训练 lightweight recurrent cell；P2–P4 通过后，GPU 2、3 才用于真实 parallel Qwen experiment。
