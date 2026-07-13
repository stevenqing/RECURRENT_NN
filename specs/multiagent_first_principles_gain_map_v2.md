# Multi-Agent 的真实提升来自哪里？

## Independent Confirmation 失败后的第一性原理重构 v2

> **Execution update (2026-07-11):** The frozen static tail-risk preflight failed: grouped OOF AUROC 0.602, ECE 0.074, and selector/monolith work ratio 1.826. Static graph topology does not support the proposed risk selector. Per the frozen kill gate, do not escalate to online trace or Qwen risk prediction on the current graph-coloring substrate. See [static risk closeout](../results/multiagent_static_risk_preflight/CLOSEOUT.md).

> **Second-substrate update (2026-07-12):** Independent planted community 3-SAT reproduced the tail-risk pattern: jointly-solved work ratio 0.284, failure rate 0.160 above corrected break-even 0.067, penalized work ratio 2.231, and high/low coupling work ratio 2.001. The cross-substrate methodological result is now the strongest contribution candidate. See [cross-substrate synthesis](../results/multiagent_cross_substrate_tail_risk/SUMMARY.md).

> **Route-confirmation update (2026-07-12):** A preregistered 200-instance SAT-high study failed to reproduce the earlier secondary deepest-versus-random route effect: solve difference 0.040, one-sided exact $p=0.225$, and penalized-work ratio 0.972 with an interval crossing one. The frozen verdict is `SAT_ROUTE_CONFIRMATION_NO_GO`; Qwen target routing is not authorized. See [route closeout](../results/multiagent_sat_route_confirmation/CLOSEOUT.md).

> **Capacity-valid repair update (2026-07-12):** Post-hoc audit localized the failed route policy to priority-before-window-validity. A prospectively frozen validity-before-priority policy then passed development and reproduced on a new 200-instance pool: solve 0.975, $q=0.025<q^*=0.123$, and failure-penalized work 0.339× equal-memory monolith. The strict solve-NI CP bound was 0.05184 and failed the 0.05 gate, so this is `SAT_MATCHED_ROUTE_CONFIRMATION_ONLY`. See [capacity-valid synthesis](../results/multiagent_capacity_valid_route_tail_control/SUMMARY.md).

> **Cross-substrate confirmation update (2026-07-12):** A separately frozen graph-color replication passed all route, safety, repair, equal-memory solve, and expected-work gates. Pooled-over solve was 0.990 for both factorized and monolith arms; factorized penalized work was 0.373× monolith and $q=0.010<q^*=0.071$. The strongest contribution candidate is now capacity-valid-before-priority tail control across SAT and graph coloring, not Qwen routing. See [graph closeout](../results/multiagent_graph_matched_route_confirmation/CLOSEOUT.md).

> **Recoverability-observability audit (2026-07-12):** The matched policies obtain exact target-window validity by directly reading target private trails in shared memory. This is a perfect-directory factorized-search result, not a fully decentralized protocol. The higher-novelty direction is explicit proof-carrying rollback via owner-issued versioned capabilities, with query/lease/pinning cost charged. See [novelty strategy](multiagent_novelty_strategy_recovery_capabilities_v1.md).

- 日期：2026-07-11
- 当前证据：[Structural Contribution Closeout](../results/multiagent_structural_confirmatory/CLOSEOUT.md)
- 下一机制合同：[Tail-Risk-Aware Factorization](multiagent_tail_risk_factorization_contract_v1.md)
- 状态：research strategy；不是新的 confirmatory claim

---

## 1. 一句话结论

multi-agent 不会因为“agent 数量”本身产生普适 free lunch。

在相同信息、相同总 memory、相同 aggregate operations 下，一个 unrestricted centralized controller 可以逐步模拟所有 local agents 和 messages。因此真正可能的提升只能来自以下资源或约束差异：

1. **scale-out memory**：突破单设备/单 agent memory 上限；
2. **parallel critical path**：用更多硬件换更低 latency；
3. **context/attention factorization**：把一个长 context 的超线性 attention 分成多个短 context；
4. **speculative factorization**：大多数样本便宜求解，危险 tail 由风险策略回退；
5. **diversity/error coding**：低相关错误经 ensemble 降低失败率；
6. **data locality/privacy**：原始 local information 不能或不应集中化，只交换 sufficient messages。

结合当前数据，最值得追的不是 unconditional team，而是：

> **Risk-aware speculative factorization：把 multi-agent local search 当成一种便宜但有 tail risk 的 speculative execution mode，并在风险超过 break-even boundary 前切换到 equal-memory monolith。**

---

## 2. Central Simulation Lemma：为什么不存在“agent identity free lunch”

考虑一个 team：

- agents 有 local states $s_1,\ldots,s_M$；
- 每一步执行 local transition；
- 通过 messages 更新其他 local states；
- total mutable memory 为 $M_\Sigma$；
- aggregate work 为 $T_\Sigma$。

如果 centralized controller：

1. 能看到相同信息；
2. 拥有相同 total memory；
3. 能执行相同 local transition 和 message handler；

那么它可以顺序模拟整个 team：

$$
T_{central}\le T_{team}+O(\Gamma),
$$

其中 $\Gamma$ 是 message handling。

因此：

- team 不能在 aggregate algorithmic work 上普适击败最佳 centralized factorized solver；
- 若 team 胜普通 monolith，通常说明比较的是不同 search policy、representation 或 information constraint；
- `factorized_central_cbj` 与 independent arm 几乎相同，是这一点的实验证据；
- “decentralization”不是当前 work gain 的来源。

### 直接后果

最终论文不能把目标写成：

> 多 agent 天生比单 agent 推理更强。

应该写成：

> 在哪些 resource constraints 下，distributed execution 是更合适的系统实现；什么时候 factorized mode 的 frequent-case saving 足以覆盖其 failure tail 和 communication cost？

---

## 3. 必须使用的资源向量

定义：

$$
\mathbf C=(M_\Sigma,M_\infty,T_\Sigma,T_\infty,F_{attn},Q,\Gamma,R_f),
$$

其中：

- $M_\Sigma$：total mutable memory；
- $M_\infty$：peak per-agent/device memory；
- $T_\Sigma$：aggregate search work/tokens/FLOPs；
- $T_\infty$：critical-path latency；
- $F_{attn}$：transformer attention FLOPs；
- $Q$：LLM calls；
- $\Gamma$：communication tokens/messages；
- $R_f$：failure/tail risk。

任何“multi-agent improvement”都必须明确改善哪个分量、增加了哪个分量。

---

## 4. 六类真实可得的提升

## 4.1 Scale-out memory

### 原理

每个 agent 只有 memory $R$，但 team 总 memory 为 $MR$：

$$
M_\infty=R,\qquad M_\Sigma=MR.
$$

若 global recovery distance 超过 $R$，local recovery distances 不超过 $R$，team 可访问单 agent 无法访问的 state。

### 当前证据

这是最稳定的正结果：`monolith-R` 在 over cells 为 0，而 equal-total-memory controls 可以求解。

### 正确表述

- distributed aggregate capacity；
- horizontal memory scaling；
- per-device capacity relief。

### 不能写

- equal-resource free lunch；
- emergent collaboration。

### 论文价值

中等。它是真实 systems scaling，但需要清楚承认 total memory 增加。

---

## 4.2 Parallel critical path

### 原理

如果 local work 可并行：

$$
T_{\infty,team}\approx\max_i T_i+T_{sync},
$$

而 centralized sequential execution约为：

$$
T_{central}\approx\sum_iT_i.
$$

### 改善

- wall-clock latency；
- throughput；
- per-device memory。

### 代价

- M 份硬件；
- aggregate work不一定下降；
- synchronization 和 straggler。

### 当前证据

只有 simulated rounds，没有 measured wall-clock。因此尚未测。

### 必要控制

- actual concurrent execution；
- identical aggregate operations；
- hardware-seconds、energy、tokens 和 wall-clock 分开；
- centralized factorized sequential control。

### 论文价值

若效果强，可走 MLSys/systems 路线，而不是 reasoning free-lunch 路线。

---

## 4.3 Context/attention factorization

这是 LLM-specific、比普通 search factorization 更有潜力的机制。

### 原理

一个长度 $L$ 的 monolithic prompt，prefill attention 近似：

$$
F_{mono}\propto L^2.
$$

若分成 M 个大致均衡的 local prompts：

$$
F_{team}\propto\sum_{i=1}^{M}L_i^2
\approx M\left(\frac{L}{M}\right)^2
=\frac{L^2}{M}.
$$

再加 separator communication：

$$
F_{total}\approx\sum_iL_i^2+F_{comm}(S,\rho).
$$

只要 communication 足够小，context sharding 可在 total tokens 相近时降低 attention FLOPs。

### 重要边界

- centralized-sharded sequential calls 同样能获得 aggregate FLOP gain；
- multi-agent 特有的是 parallel latency 和 distributed deployment，而不是 sharding algorithm 本身；
- KV cache、decode、batching 会改变常数，必须实测。

### 当前证据

尚未做 FLOP/KV/wall-clock matched profiling。

### 论文价值

高，且比“agents 会合作”更可证伪。推荐作为 systems mechanism 与 risk-aware search 结合。

---

## 4.4 Speculative factorization 与 tail-risk control

这是当前数据最直接支持的 research candidate。

### Frequent-case gain

在独立 `over_low` confirmation 中：

- jointly solved work ratio：约 `0.297`；
- 44/50 paired work wins；
- mean successful factorized work：$W_s\approx354.3$；
- mean monolith work：$W_m\approx1242.1$。

### Tail loss

- failure cost：$B=20{,}000$；
- factorized failure probability：$q=0.08$。

Expected work：

$$
E[W_f]=(1-q)W_s+qB.
$$

Break-even condition：

$$
q<q^*=\frac{W_m-W_s}{B-W_s}.
$$

当前：

$$
q^*\approx0.0452<0.08.
$$

所以 frequent-case gain 真实，但 expected-resource free lunch 不成立。

### Risk selector 的价值条件

令：

- $r$：unsafe trajectory recall，即被正确拦截的 failure fraction；
- $f$：safe trajectory false-positive rate；
- $P$：early probe cost。

Early-abort expected work：

$$
\begin{aligned}
E[W_R]=&(1-q)\left[(1-f)W_s+f(P+W_m)\right]\\
&+q\left[r(P+W_m)+(1-r)B\right].
\end{aligned}
$$

在当前数字下，击败 monolith 所需的 failure recall 大约为：

| Probe cost | Safe false positive | Required unsafe recall |
|---:|---:|---:|
| 0 | 0.00 | >0.456 |
| 0 | 0.10 | >0.510 |
| 100 | 0.00 | >0.458 |
| 100 | 0.10 | >0.519 |
| 100 | 0.20 | >0.580 |
| 250 | 0.10 | >0.533 |
| 250 | 0.20 | >0.603 |

这说明目标不是不现实的 perfect predictor。若 early signals 能捕获约一半危险轨迹，同时不过度拒绝 safe cases，就可能恢复 expected-work advantage。

### 真正贡献点

不是“加一个 classifier”，而是：

1. 给出可计算的 multi-agent tail-risk boundary；
2. 用 leakage-free online features 预测是否越界；
3. 在新数据上证明 selector 保持 equal-memory solve，同时降低 fully charged expected work；
4. 在第二 substrate 复现。

### 当前优先级

**最高。**

---

## 4.5 Diversity / error coding

### 原理

多个 agents 使用不同 partition、order、prompt 或 model，可以降低 shared failure。

独立误差下 majority/portfolio reliability 会提升；但实际关键是 error correlation：

$$
P(\text{all fail})
$$

只有在 failure correlation 足够低时才快速下降。

### 多样性来源

- different graph partitions；
- different variable orders；
- different search heuristics；
- different model checkpoints；
- different prompts/seeds。

### 代价

- 多倍 calls/tokens/memory；
- 与 best-of-N/self-consistency 强烈重叠；
- central portfolio 可以模拟。

### 必要控制

- same-total-token best-of-N monolith；
- sequential portfolio；
- random partition/order；
- pairwise failure correlation；
- gain per additional byte/FLOP。

### 当前证据

v5 仅确认 reliability-for-memory tradeoff；没有 same-total-resource coding advantage。

### 优先级

次要。除非能找到非常低相关且便宜的 local variants。

---

## 4.6 Data locality、privacy 与 communication compression

### 原理

若 raw local data：

- 不能集中；
- 太大而不适合全局 prompt；
- 有 privacy/ownership 约束；

则 centralized simulator 的前提不成立。Agents 交换 compact sufficient statistics/nogoods，而不是 raw history。

若 separator state entropy 小：

$$
\Gamma\ll\sum_i |D_i|,
$$

distributed architecture 可以降低 data movement 和 prompt exposure。

### 当前 harness 的问题

成功机制仍共享 current global assignment visibility，因此尚未证明真实 information decentralization。

### 必要实验

- boundary-only information；
- explicit byte/token audit；
- centralized raw-data arm；
- centralized same-summary arm；
- privacy/no-centralization constraint 明确写入 problem definition。

### 论文价值

若任务天然分布式，可成为真正 multi-agent systems contribution；在当前 graph-color harness 中尚未成立。

---

## 5. 当前证据支持什么

| Mechanism | Current evidence | Verdict |
|---|---|---|
| Aggregate capacity | team/equal-memory controls solve，monolith-R失败 | Confirmed but buys memory |
| Frequent-case factorization | jointly-solved work约0.30× | Confirmed conditional gain |
| Expected-resource free lunch | penalized ratio 1.551 | Rejected |
| Coupling boundary | work 2.516×；solve 0.92→0.78 | Confirmed on graph coloring |
| Coordination necessity | no-cross大幅下降 | Confirmed |
| Deepest route advantage | deepest≈random-valid | Not identified |
| Algorithm novelty | classical DisCSP/DCOP precedents | Not supported |
| Parallel wall-clock | only simulated rounds | Untested |
| Attention FLOP gain | no real profiling | Untested |
| Qwen route contribution | small development signal only | Not authorized |
| Risk-aware selector | analytical feasibility only | Best next candidate |

---

## 6. LLM 应该扮演什么角色

当前结果表明，LLM 不应优先用于每一步 branch 或在等价 route 中做微选择。

## 6.1 不推荐：micro-branching

已有 overnight 中 Qwen branching 导致 trajectory explosion、call-cap 和 exhaustion。局部 valid 不等于序列策略正确。

## 6.2 暂停：rollback route choice

新 confirmation 中 deepest 与 random-valid 在 over-low solve 都是 0.92，S1失败。没有 route-sensitive substrate，就没有 LLM route contribution。

## 6.3 推荐候选：meta-risk / architecture selection

LLM 可能更适合判断：

- 当前 partition 是否 unsafe；
- observed NACK/window-rejection pattern 是否预示 tail failure；
- 应继续 local factorization 还是切换 monolith；
- 哪个 partition/order 更可能安全。

但必须先让 symbolic risk model 建立 strong baseline。Qwen 只有在 matched tokens 下显著增加 out-of-sample predictive value，才有 LLM contribution。

## 6.4 另一候选：message compression

LLM 将 local conflict trace 压成 compact nogood/message，可能减少 communication tokens。但必须与 deterministic symbolic compression 和 same-summary centralized control 比较。

---

## 7. 推荐主线：Conditional Multi-Agent Execution

新主张不应是：

> Teams beat monoliths.

而应是：

> **Factorized agent search is a speculative mode with large conditional savings and a quantifiable catastrophic tail. A calibrated architecture policy should invoke it only when predicted failure risk lies below the resource-dependent break-even boundary.**

中文：

> multi-agent 不是默认更优的 solver，而是一种 conditional execution mode。只有当 decomposition saving 大于 coordination 与 tail risk 时才应启用。

这个故事有三个层次：

1. **law**：$q^*$ 由 monolith cost、success cost 和 failure cost 决定；
2. **mechanism**：coupling、window rejection、NACK、progress imbalance 驱动 $q$；
3. **policy**：risk-aware static/early-abort selector 使系统停留在 $q<q^*$ 区域。

---

## 8. 可形成 research contribution 的实验计划

## Phase A — Development instrumentation

只使用已暴露的 64+200 development pools。

在冻结 early horizons，例如：

$$
h\in\{32,64,128,256\}\text{ activations},
$$

记录：

- assignment progress；
- branch/retraction slope；
- request rate；
- NACK rate；
- window-rejection rate；
- repeated-target count；
- per-agent progress imbalance；
- local-window occupancy；
- state revisit sketch。

禁止使用 final status 后的 features 或 unlimited-reference metrics 作为 deployment input。

## Phase B — Grouped development validation

按 generator seed/batch 分组交叉验证，避免相邻生成样本泄漏。

Gates 已在 [tail-risk contract](multiagent_tail_risk_factorization_contract_v1.md) 中冻结：

- AUROC ≥0.80；
- Brier优于 prevalence；
- calibration error ≤0.05；
- solve within 0.05 of monolith；
- fully charged work 至少降低10%；
- 胜 matched random selector 与 unconditional restart。

任何一项失败，停止该线。

## Phase C — New graph-color confirmation

只有 development gates PASS 后：

1. freeze horizon、features、model、threshold、code hashes；
2. generate untouched manifest；
3. compare always-monolith、always-factorized、static selector、early-abort、random selector、restart；
4. primary metrics：solve non-inferiority、penalized work、tail bound。

## Phase D — 第二 substrate

推荐 **community-structured SAT**：

- variables分区；
- local clauses 与 cross-community clauses独立控制；
- fixed clause count/density；
- local/global backjump distance可测；
- separator/coupling定义自然；
- official SAT validation明确。

只有 graph coloring 与 SAT 同方向，才可写一般性 bounded-memory factorization law。

## Phase E — Real Qwen meta-control

在 symbolic risk gate 和第二 substrate之后，比较：

1. symbolic calibrated risk model；
2. Qwen risk prediction；
3. symbolic+Qwen hybrid；
4. random/static threshold；
5. always-factorized/always-monolith。

报告 total calls、tokens、attention FLOPs、fallback work 和 wall-clock。

---

## 9. 可选 systems 分支：Attention-Sharded Agents

如果 risk predictor不够强，但 real Qwen local prompts显著降低 FLOPs/latency，可转 systems paper：

> **Sharding long-context search across bounded agents reduces prefill attention and per-device KV memory, while a risk-aware fallback controls rare global-consistency failures.**

需要主图：

1. solve vs total attention FLOPs；
2. solve vs wall-clock；
3. peak per-GPU KV bytes；
4. communication tokens；
5. fallback rate；
6. centralized-sharded sequential control。

这是合理的 multi-agent systems contribution，即使 aggregate symbolic search work不形成 free lunch。

---

## 10. 明确停止的方向

当前不要继续：

1. 直接扩大 Qwen branch×route confirmatory；
2. 把 16-instance development positive 当 paper result；
3. 调 penalty/cap 让 C2变正；
4. 挑掉四个 tail failures；
5. 声称 local rollback/CBJ/request-ack 是新算法；
6. 只报 solved-only work，不报 failure-penalized work；
7. 用 simulated rounds 写 wall-clock speedup。

---

## 11. 最终优先级

### Priority 1 — Risk-aware speculative factorization

- 最强数据支撑；
- 有明确数学 threshold；
- 约一半 unsafe recall 可能已足够恢复 expected-work gain；
- 可严格证伪。

### Priority 2 — Attention/context sharding systems study

- LLM-specific；
- 有 $L^2/M$ 的明确机制；
- 需要真实 Qwen FLOP/KV/wall-clock profiling。

### Priority 3 — Low-correlation partition portfolio

- 可能降低 tail risk；
- 但需匹配 total compute，容易退化为 best-of-N。

### 暂停 — LLM micro-routing

- route identifiability没有通过；
- 无 substrate-level effect 时，LLM 不可能形成可信 contribution。

---

## 12. 推荐论文定位

若 risk-aware + second substrate 通过：

**When Should Agents Factorize Search? Tail Risk and Resource-Aware Execution in Bounded Multi-Agent Systems**

贡献可以写成：

1. 证明 agent identity 不产生 aggregate free lunch，给出 resource-conditioned simulation boundary；
2. 定义 factorized search 的 tail-risk break-even law；
3. 提出并独立验证 leakage-free architecture selector；
4. 区分 scale-out memory、parallel latency、attention FLOPs 与 expected work；
5. 在 graph coloring 和 community SAT 上复现 holds-here/not-there boundary；
6. 可选地证明 Qwen 仅在 meta-risk role 上提供增量价值。

若 selector失败：

论文应收窄为 negative/evaluation：

**When Factorized Agent Search Fails: Tail Risk, Coupling, and Equal-Resource Controls**

这仍可能是诚实的 research contribution，但需要第二 substrate 和真实 LLM/system measurement，不能仅依赖当前 symbolic graph-color结果。
