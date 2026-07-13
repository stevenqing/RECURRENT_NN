# 从 Capacity-Valid Routing 到 Proof-Carrying Rollback

> **Direction update (2026-07-12):** Proof-Carrying Rollback is retained as a decentralized message-safety sublayer, not the main research narrative. The primary target is now spatially parallel agents with temporally recurrent, fixed-state updates under fixed compute. See [Recurrent Parallel Agent Reasoning](multiagent_recurrent_parallel_reasoning_v1.md).

## Multi-Agent Novelty Strategy v1

- 日期：2026-07-12
- 状态：research strategy；不是新实验结果或 novelty claim
- 当前主结果：[Capacity-valid cross-substrate synthesis](../results/multiagent_capacity_valid_route_tail_control/SUMMARY.md)
- 既有文献审计：[Literature audit](../results/multiagent_structural_confirmatory/LITERATURE_AUDIT.md)

---

## 1. 当前 research contribution 到底是什么？

当前最强证据是：

**`CROSS_SUBSTRATE_CAPACITY_VALID_TAIL_CONTROL_CONFIRMATION`**

在 community SAT 和 graph coloring 两个独立 symbolic substrates 中，我们都观察到：

1. owner-local factorization 在成功轨迹上很便宜；
2. priority-before-capacity-validity 会反复请求 target owner 已无法恢复的 checkpoint；
3. 这些请求形成 NACK/window-rejection cascade，并把少量轨迹推到 activation cap；
4. 先限制到 target owner 当前 $R$-window 中仍可执行的 targets，再使用 deepest conflict priority，可以把失败率压到 break-even boundary 以下；
5. graph coloring 通过 equal-memory solve NI 和 expected-work 两类强 gate；SAT 通过 expected-work，但保守 solve-NI CP 上界为 0.051843，略高于冻结门槛 0.05。

### 当前可以安全声称

> 在带有精确 recovery-validity directory 的 bounded factorized search 中，rollback priority 必须在 executor capacity feasibility 之后应用。Validity-before-priority 可以消除 NACK cascade，并在两个 symbolic substrates 上将 completion risk 移到 measured break-even boundary 以下。

### 当前不能声称

- 新的 CSP、DisCSP、CBJ 或 backtracking 算法；
- fully decentralized multi-agent protocol；
- universal equal-resource free lunch；
- Qwen/LLM contribution；
- wall-clock、energy 或 hardware speedup。

---

## 2. Novelty 的诚实评级

| 组件 | 当前证据 | Novelty 评级 | 原因 |
|---|---|---:|---|
| Equal-total-memory controls | 两基质、独立 pools | 中 | 在 LLM-agent evaluation 中少见，但不是新算法 |
| Failure-penalized expected work | cross-substrate | 中 | 评价纪律有价值，代数本身基础 |
| Break-even law $q^*$ | 两基质验证 | 低–中 | 公式简单，价值来自 operationalization |
| Capacity-valid-before-priority | SAT + graph 独立确认 | 中 | 机制清晰且可复现，但 feasibility filtering 本身直观 |
| Owner-local CBJ/messages | 完整协议审计 | 低 | DisCSP/ABT/DCOP/CBJ 有直接先例 |
| 当前 matched-window implementation | 强 empirical result | 低于表面值 | 使用共享内存读取 target agent 的实时 trail |
| 真正 decentralized recoverability protocol | 尚未实现 | 潜在高 | 需要消除 free global reads、处理 staleness、pinning 和通信成本 |

因此，当前工作已经从“只有负结果”上升为一个扎实的 empirical systems/evaluation contribution，但若目标是更高 novelty，必须解决 **recoverability observability**，不能继续微调 route heuristic。

---

## 3. 当前机制的隐藏假设

SAT 中的 `target_window_valid()` 和 graph 中的 `target_is_window_valid()` 都直接执行：

1. 从全局 `agents` dictionary 取得 target owner's state；
2. 搜索 target owner's private trail；
3. 读取 trail length 与 target index；
4. 零延迟、零 token、零 message 地判断 target 是否仍在 $R$-window。

相关实现：

- [SAT factorized solver](../experiments/multiagent_community_sat.py)
- [Graph factorization controls](../experiments/multiagent_factorization_controls.py)
- [SAT matched control](../experiments/multiagent_community_sat_route_controls.py)
- [Graph matched control](../experiments/multiagent_graph_route_controls.py)

这意味着当前结果依赖一个 **perfect shared recovery directory**：

- source 能看到 target 的实时 private trail；
- read 与 target mutation 之间隐含原子 snapshot；
- 没有 query/response latency；
- validity read 没有计入 communication；
- single-process scheduler 保证读取期间没有并发 mutation。

`no_direct_cross_agent_mutation` 只证明 source 没有直接修改 target state，并不证明 source 没有直接读取 target private state。

此外，当前 engines 还共享 global assignment/metadata。Boundary messages 被计数，但 local replicas、delivery delay 和 coherence 并未完整模拟。因此，当前结果最准确的名字是：

> **bounded factorized search with a perfect validity directory**

而不是 fully decentralized autonomous agents。

---

## 4. 第一性原理：为什么这是新的核心问题？

设 source agent $i$ 需要把 conflict route 到 owner $j$ 的 checkpoint $x$。

source 本地知道：

- $x$ 是一个 blocker；
- $x$ 在全局 priority order 中的位置；
- $x$ 的 owner 是 $j$。

source 本地不知道：

- $x$ 是否仍在 $j$ 的 bounded trail；
- $x$ 距离 $j$ 的 eviction boundary 有多少 slack；
- 在 request 到达前 $j$ 是否会本地 rollback 或追加 state；
- request 执行时 $x$ 的版本是否仍等于 source 观察到的版本。

### Indistinguishability lower bound

构造两个对 source $i$ 完全相同的 local transcripts：

- execution A：$x$ 仍位于 owner $j$ 的最后 $R$ 个 checkpoints；
- execution B：$x$ 已被 $j$ eviction，但 source 尚未收到任何信息。

任何只依赖 source-local state 的 deterministic route policy 在 A/B 中必须做同一选择。因此它不可能同时保证：

1. 在 A 中利用 $x$；
2. 在 B 中永不产生 invalid rollback。

所以 exact capacity-valid routing 必须至少使用以下一种额外资源：

- shared memory/directory；
- explicit query；
- owner advertisement；
- versioned capability/lease；
- conservative refusal。

这给出比“deepest 是否优于 random”更基础的研究问题：

> **在没有 free global reads 的独立 agents 中，recoverability 如何被观测、证明和保持？**

---

## 5. 最值得追的 novel idea：Proof-Carrying Rollback

建议名称：

- **Proof-Carrying Rollback (PCR)**；
- 或 **Rollback Capability Leases (RCL)**；
- 或 **Recovery Capability Protocol (RCP)**。

### 核心对象

Target owner $j$ 为当前可恢复 checkpoint $x$ 发行 capability：

$$
\kappa=(j,x,v,s,e),
$$

其中：

- $j$：owner；
- $x$：checkpoint/variable；
- $v$：assignment version；
- $s$：owner-local slot generation；
- $e$：lease expiry round。

capability 的语义不是“我曾经看见过 $x$”，而是：

> 在 capability 到期或被显式 revoke 前，owner 保证 request 若携带匹配的 $\kappa$，则 $x$ 仍可在 bounded memory 内执行 rollback。

### 消息类型

1. `CAP_QUERY(source, owner, candidates, epoch)`；
2. `CAP_GRANT(owner, source, κ, slack, expiry)`；
3. `CAP_DENY(owner, source, candidate, reason)`；
4. `ROLLBACK_REQUEST(source, owner, κ, blockers)`；
5. `ROLLBACK_ACK(owner, source, κ, popped)`；
6. `CAP_REVOKE(owner, source, κ, reason)`；
7. `CAP_EXPIRE(κ)`。

### Owner 端状态

- bounded local trail；
- issued capabilities；
- pinned checkpoints；
- slot-generation counters；
- capability credits；
- pending revoke/ack queue。

### Source 端状态

- capability cache；
- capability versions/expiry；
- pending queries；
- rejected/revoked targets；
- route priority over currently valid capabilities。

---

## 6. 必须证明的 invariants

### Safety 1 — No hidden cross-agent reads

source 的 route decision 只能读取：

- source-local state；
- received immutable messages；
- public static problem metadata。

任何 direct read of `agents[target].trail`、target cursor、target pending queue 或 target private register 都计为 protocol violation。

### Safety 2 — Capability soundness

若 owner 接受携带未过期 capability $\kappa$ 的 rollback request，则对应 checkpoint 必须仍在 owner 的 declared $R$ memory 内。

### Safety 3 — Version safety

request version 与 owner slot generation 不一致时，request 必须在 mutation 前 fail closed；旧 capability 不能作用于复用后的 slot。

### Safety 4 — Memory conservation

pinned + unpinned recovery state 不得超过 $R$。Pinning 是 memory reservation，不是免费增加 memory。

### Safety 5 — Communication conservation

每个 query、grant、deny、revoke、request 和 ack 都进入 lifecycle accounting；不能把 capability discovery 当免费 read。

### Liveness — Bounded response

在 channel 未饱和且 owner 仍运行时，每个 capability query/request 必须在冻结 horizon 内 grant/deny/ack/revoke。

### Priority acyclicity

capability 不能绕过原有 global acyclic recovery priority，否则 lease dependency 可能形成死锁。

---

## 7. 三个可投稿的理论目标

### Theorem A — Local-information impossibility

没有 owner message/shared directory 时，source-local policy 无法同时保证 maximal rollback utilization 与 zero invalid requests。

价值：说明 recoverability communication 不是 implementation detail，而是 information-theoretic necessity。

### Theorem B — Lease safety

如果：

1. owner 在 capability 生命周期内 pin 对应 checkpoint；
2. rollback request 携带 owner-issued version；
3. eviction 前先 revoke；
4. message handler linearizable；

则 accepted rollback 的 out-of-window execution 和 stale-version mutation 均为零。

### Theorem C — Charged break-even boundary

令 capability protocol overhead 为 $\Gamma_\kappa$，failure probability 为 $q_\kappa$：

$$
E[W_\kappa]=(1-q_\kappa)W_{s,\kappa}+q_\kappa B+\Gamma_\kappa.
$$

相对 monolith 的 break-even 条件变为：

$$
q_\kappa<q^*_\kappa=
\frac{W_m-W_{s,\kappa}-\Gamma_\kappa}{B-W_{s,\kappa}}.
$$

这把当前 empirical $q^*$ 从事后评价升级为 protocol design constraint：lease/query overhead 太大时，即使 failure 降为零也可能不值得。

---

## 8. 实验必须区分的 controls

1. `perfect_directory`：当前 shared-read upper bound；
2. `unfiltered_deepest`：旧 NACK-cascade policy；
3. `periodic_advertisement`：低通信但 stale；
4. `query_then_route`：准确但增加 round trip，不 pin；
5. `versioned_capability_no_pin`：版本安全但可能 revoke；
6. `rollback_lease_pinned`：proposed safety protocol；
7. `random_valid_capability`：matched capability availability，random priority；
8. `no_cross`；
9. `centralized_factorized`；
10. `equal_memory_monolith`。

必须 sweep：

- $R\in\{4,8,16\}$；
- low/high coupling；
- message delay $\Delta\in\{0,1,2,4,8\}$；
- lease TTL；
- channel cap；
- capability credits/pinned fraction。

主要 estimands：

- solve；
- failure-penalized aggregate work；
- wall-clock/critical path；
- capability messages/tokens；
- pinned-memory occupancy；
- stale grants/revocations；
- invalid requests；
- $q$ 与 charged $q^*_\kappa$。

---

## 9. Falsifiable gate ladder

### D0 — No-free-read audit

- instrument every agent-state read；
- source cannot inspect target private trail；
- local replicas/messages only；
- deterministic replay and lifecycle conservation pass。

### D1 — Protocol safety

- accepted out-of-window rollback = 0；
- stale-version mutation = 0；
- memory never exceeds $R$；
- no capability lifecycle leak。

### D2 — Development value

Against query-only, periodic advertisement, and random-valid capability controls：

- solve non-inferior；
- charged expected work lower by at least 10%；
- benefit survives at least two delay levels and both coupling levels。

### D3 — Independent confirmation

- new zero-overlap SAT and graph pools；
- equal-memory solve NI；
- charged work advantage with paired-bootstrap upper bound；
- observed $q_\kappa<q^*_\kappa$；
- no reliance on perfect-directory arm。

### D4 — Real distributed execution

Only after D3：

- separate processes/local heaps；
- injected or real network delay；
- no shared mutable Python objects；
- actual bytes, latency, hardware-seconds reported。

---

## 10. 第二个更高风险 idea：Recoverability-Aware Checkpoint Cache

当前 $R$-window 是 recency policy：保留最近 $R$ 个 checkpoints。

更深的问题是：

> 在同样的 $R$ 下，owner 应保留哪些 checkpoints，才能最大化未来 cross-agent recoverability？

可将 local recovery memory 视为 checkpoint cache：

- key：assignment/checkpoint version；
- request：cross-agent rollback demand；
- miss：target evicted/NACK；
- pin：active capability lease；
- replacement：checkpoint retention policy。

候选 policies：

1. recency window；
2. conflict-frequency；
3. separator-centrality；
4. lease-demand LFU；
5. risk-budgeted retention；
6. learned semantic retention；
7. development-only oracle upper bound。

潜在贡献是把 reversible memory、multi-agent coordination 和 cache replacement 统一为一个 **recoverability cache** 问题。但 cache replacement、checkpointing 和 nogood retention 都有丰富先例，因此必须证明新颖性来自：

- owner-local bounded rollback semantics；
- capability-consistent eviction；
- failure-tail objective；
- equal-total-memory controls；
- cross-substrate independent evidence。

---

## 11. q* 如何从 evaluation 变成 controller

第三个方向是 **risk-budgeted capability admission**。

系统维护 remaining failure budget：

$$
\mathcal B_t=q^*_\kappa-\widehat q_t.
$$

若某个 lease/route 的 estimated hazard、staleness 或 pin opportunity cost 会使 $\widehat q_{t+1}$ 超过 boundary，则：

- 拒绝 speculative factorization；
- 切换 query/lease mode；
- 或 fallback 到 equal-memory monolith。

单纯 risk selector/portfolio 是 classical，novelty 只能来自 capability protocol 与可证明 resource boundary 的结合。它应排在 PCR/RCL 之后，而不是先训练另一个 classifier。

---

## 12. LLM 在哪里才可能非平凡？

Qwen 不应被用于复述“从 valid targets 选最大 order index”。这是 deterministic rule，没有 research headroom。

只有在下面的任务中，LLM 才可能有非平凡角色：

> 在 $R$ 个 retention slots 和有限 capability credits 下，根据未结构化语义依赖预测哪些 checkpoints 值得保留、advertise 或 pin。

必须比较：

- recency；
- conflict frequency；
- separator-centrality；
- random；
- symbolic learned model；
- oracle upper bound；
- Qwen。

并完整收费：calls、tokens、latency、invalid decisions、extra retention 和 fallback。

如果 Qwen 不能超过这些 symbolic cache policies，就删除 LLM contribution，保留 capability protocol。

---

## 13. 文献边界

直接 classical predecessors：

- Yokoo et al., distributed CSP / asynchronous backtracking；
- Ginsberg, *Dynamic Backtracking*, JAIR 1993, DOI `10.1613/jair.1`；
- Chen & van Beek, *Conflict-Directed Backjumping Revisited*, JAIR 2001, DOI `10.1613/jair.788`；
- Gershman et al., *BnB-ADOPT*, JAIR 2010, DOI `10.1613/jair.2849`；
- Petcu & Faltings, *MB-DPOP*, 2007；
- Fioretto et al., DCOP survey, JAIR 2018, DOI `10.1613/jair.5565`；
- Gray & Cheriton, *Leases*, 1989, DOI `10.1145/74851.74870`。

这些工作意味着：

- distributed search、priority、nogoods、bounded memory 和 leases 分别都不是新概念；
- potential novelty 必须来自它们在 **bounded rollback executability** 上的形式化组合与 tail-risk law；
- 本轮仅是 targeted metadata audit，不足以支持标题或摘要中的“novel algorithm”。

在投稿前必须做 full-text review：

1. bounded-memory ABT/DCOP；
2. distributed checkpoint/recovery protocols；
3. leases/capabilities/cache coherence；
4. nogood retention and deletion；
5. risk-sensitive algorithm portfolios；
6. 2024–2026 multi-agent LLM communication/resource papers。

本轮 targeted search 没有发现与“owner-issued versioned rollback capability + bounded recovery pinning + charged tail-risk boundary”完全相同的直接条目，但这不是 novelty proof。

---

## 14. 推荐优先级

| 方向 | Novelty potential | 可证伪性 | 实现风险 | 推荐 |
|---|---:|---:|---:|---:|
| Proof-Carrying Rollback / capability leases | 高 | 高 | 中 | **第一优先** |
| Recoverability-aware checkpoint cache | 高 | 高 | 中–高 | 第二优先 |
| Risk-budgeted capability admission | 中–高 | 中 | 高 | 第三优先 |
| 再做 Qwen target routing | 低 | 高 | 中 | 不推荐 |
| 追加同分布样本修 SAT CP 0.0018 gap | 低 | 低 | 低 | 不推荐 |
| 只做更多 substrates | 中 | 高 | 中 | protocol 完成后再做 |

---

## 15. 推荐的新 paper framing

### 当前可写版本

**Capacity Before Priority: Controlling Tail Risk in Bounded Factorized Search**

贡献：cross-substrate empirical mechanism + equal-resource evaluation discipline。

### 更 novel 的目标版本

**Proof-Carrying Rollback: Recovery Capabilities for Bounded Multi-Agent Search**

目标贡献：

1. source-local impossibility result；
2. owner-issued rollback capability protocol；
3. lease safety/memory theorems；
4. charged break-even law；
5. perfect-directory、query、advertisement、lease controls；
6. SAT/graph independent confirmation；
7. real process-separated execution。

这条线真正回答了：

> multi-agent 的提升不来自 agent identity，而来自在信息局部、memory bounded、communication charged 的条件下，如何可靠地证明并保持 cross-agent recovery action 可执行。

---

## 16. 单一下一步

不要启动 Qwen，也不要追加同分布样本。

下一步应冻结 **Recovery Capability Protocol v1**：

1. 明确 local/private/public state；
2. 禁止所有 cross-agent direct reads；
3. 定义 capability/version/expiry/pin/revoke lifecycle；
4. 证明 safety 与 memory bound；
5. 在已暴露 pools 做 protocol development；
6. 只有在 charged overhead 下仍低于 break-even，才生成新 confirmatory pools。
