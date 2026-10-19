# Research Methodology: Intelligent Forgetting in Agentic AI

## 1. Problem Formulation & Motivation

In agentic systems, memory is typically handled via one of two extremes:
1. **Unbounded Accumulation (Retain All)**: Every interaction, scratchpad log, and user utterance is appended. Over time, prompt context size explodes, retrieval vector search slows down, cost increases linearly, and irrelevant or outdated memories contaminate reasoning.
2. **Naive Pruning (FIFO / LRU)**: Oldest memories are dropped regardless of value. This causes catastrophic amnesia: critical instructions, user preferences, and permanent architectural constraints given early in an interaction are permanently lost.

**Intelligent Forgetting** formulates memory curation as a multi-criteria optimization problem: maximize the retention of high-utility, non-redundant, and critical knowledge while bounding the working memory context below capacity limits.

---

## 2. Mathematical Formulation

Let memory item $m \in \mathcal{M}$ possess attributes:
- Base importance: $I(m) \in [0, 1]$
- Last accessed timestamp: $t_{\text{access}}(m)$
- Total access count: $f(m) \in \mathbb{N}_0$
- Content token sequence: $\mathcal{T}(m)$
- Protection predicate: $P(m) \in \{0, 1\}$ where $P(m) = 1$ if $m.\text{is\_pinned} \lor m.\text{is\_critical} \lor m.\text{permanent}$.

Given current evaluation timestamp $t$ and task context query $q$:

### 2.1 Component Factors

#### A. Intrinsic Importance Factor
$$S_{\text{imp}}(m) = \text{clamp}(I(m), 0.0, 1.0)$$

#### B. Temporal Recency Factor (Exponential Decay)
Let elapsed hours $\Delta t = \max\left(0, \frac{t - t_{\text{access}}(m)}{3600}\right)$ and half-life parameter $t_{\text{half}} > 0$:
$$S_{\text{rec}}(m, t) = 2^{-\frac{\Delta t}{t_{\text{half}}}}$$
- At $\Delta t = 0 \implies S_{\text{rec}} = 1.0$
- At $\Delta t = t_{\text{half}} \implies S_{\text{rec}} = 0.5$
- As $\Delta t \to \infty \implies S_{\text{rec}} \to 0.0$

#### C. Access Frequency Factor (Logarithmic Saturation)
To reward proven utility without allowing early high-frequency memories to dominate indefinitely:
$$S_{\text{freq}}(m) = \min\left(1.0, \frac{\ln(1 + f(m))}{\ln(1 + K_{\text{sat}})}\right)$$
Where $K_{\text{sat}}$ is the saturation threshold (default: $10.0$).

#### D. Task Relevance Factor
Let token sets be $\mathcal{T}_m = \text{tokens}(m.\text{content})$ and $\mathcal{T}_q = \text{tokens}(q)$.
$$J(\mathcal{T}_m, \mathcal{T}_q) = \frac{|\mathcal{T}_m \cap \mathcal{T}_q|}{|\mathcal{T}_m \cup \mathcal{T}_q|}$$
$$\text{Overlap}(\mathcal{T}_m, \mathcal{T}_q) = \frac{|\mathcal{T}_m \cap \mathcal{T}_q|}{|\mathcal{T}_q|}$$
$$S_{\text{rel}}(m, q) = 0.6 \cdot \text{Overlap} + 0.4 \cdot J$$
If $q = \emptyset$, $S_{\text{rel}}(m, \emptyset) = 0.5$ (neutral prior).

#### E. Redundancy Factor
Given active candidate memory set $\mathcal{M}_{\text{active}}$:
$$S_{\text{red}}(m, \mathcal{M}_{\text{active}}) = \max_{m' \in \mathcal{M}_{\text{active}} \setminus \{m\}} J(\mathcal{T}_m, \mathcal{T}_{m'})$$

---

### 2.2 Composite Retention Score

$$S(m, q, t) = \text{clamp}\left(w_{\text{imp}} S_{\text{imp}} + w_{\text{rec}} S_{\text{rec}} + w_{\text{freq}} S_{\text{freq}} + w_{\text{rel}} S_{\text{rel}} - w_{\text{red}} S_{\text{red}}, 0.0, 1.0\right)$$

Where normalized weights satisfy:
$$w_{\text{imp}} + w_{\text{rec}} + w_{\text{freq}} + w_{\text{rel}} = 1.0, \quad w_i \ge 0$$
Default hyperparameters:
- $w_{\text{imp}} = 0.35$
- $w_{\text{rec}} = 0.25$
- $w_{\text{freq}} = 0.20$
- $w_{\text{rel}} = 0.20$
- $w_{\text{red}} = 0.15$
- $t_{\text{half}} = 72.0 \text{ hours}$
- $K_{\text{sat}} = 10.0$

---

## 3. Decision Rules & Action Classification

For every active memory $m \in \mathcal{M}_{\text{active}}$:

1. **Safety Rule (Inviolable)**:
   $$\text{If } P(m) = 1 \implies \text{Action}(m) = \text{RETAIN / KEEP}$$
2. **Redundancy & Summarization Rule**:
   $$\text{If } \exists m' \text{ such that } J(\mathcal{T}_m, \mathcal{T}_{m'}) \ge \theta_{\text{sum}} \land P(m) = 0 \land P(m') = 0 \implies \text{Action}(m) = \text{SUMMARIZE / COMPRESS}$$
   Synthesizes a combined summary $\tilde{m}$ with references to source IDs.
3. **Threshold Rules**:
   - If $S(m) < \theta_{\text{forget}} \implies \text{Action}(m) = \text{FORGET / PRUNE}$ (default: $0.25$)
   - Else if $\theta_{\text{forget}} \le S(m) < \theta_{\text{archive}} \implies \text{Action}(m) = \text{ARCHIVE}$ (default: $0.45$)
   - Else $\implies \text{Action}(m) = \text{RETAIN / KEEP}$
4. **Capacity Enforcement Rule**:
   While $|\{m : \text{Action}(m) = \text{RETAIN}\}| > C_{\max}$ or $\text{Tokens}_{\text{active}} > B_{\text{token}}$:
   Prune the non-protected memory with the minimum retention score $S(m)$.

---

## 4. Reinforcement Learning Engine (LinUCB Contextual Bandit)

To transcend static threshold heuristics, the cognitive engine incorporates a genuine **LinUCB Contextual Bandit** reinforcement learning system.

### 4.1 State Space Representation
For each candidate memory $m \in \mathcal{M}$, the system constructs an 8-dimensional normalized feature vector $\mathbf{x} \in [0, 1]^8$:
$$\mathbf{x} = \begin{bmatrix}
S_{\text{imp}}(m) \\
S_{\text{rec}}(m) \\
S_{\text{freq}}(m) \\
S_{\text{rel}}(m) \\
S_{\text{red}}(m) \\
\text{clamp}\left(\frac{\text{Tokens}(m)}{100}, 0, 1\right) \\
\text{clamp}\left(\frac{|\mathcal{M}_{\text{active}}|}{C_{\max}}, 0, 1\right) \\
P(m)
\end{bmatrix}$$

### 4.2 Action Space & Safety Invariant
The action space $\mathcal{A}$ comprises four discrete lifecycle decisions:
$$\mathcal{A} = \{\text{KEEP}, \text{COMPRESS}, \text{ARCHIVE}, \text{PRUNE}\}$$

**Deterministic Safety Mask**:
If $P(m) = 1$ ($m$ is pinned, critical, or permanent), the candidate action space is strictly restricted:
$$\mathcal{A}_{\text{valid}}(m) = \begin{cases} \{\text{KEEP}\}, & \text{if } P(m) = 1 \\ \mathcal{A}, & \text{otherwise} \end{cases}$$
The learned policy is mechanically prohibited from pruning or archiving protected knowledge.

### 4.3 Policy Selection (LinUCB with Ridge Regression)
For each action $a \in \mathcal{A}$, the model maintains a precision matrix $A_a \in \mathbb{R}^{d \times d}$ (initialized to $\mathbf{I}_d$) and response vector $\mathbf{b}_a \in \mathbb{R}^d$ (initialized to $\mathbf{0}$).
Estimated ridge parameter:
$$\hat{\theta}_a = A_a^{-1} \mathbf{b}_a$$
The Upper Confidence Bound (UCB) decision rule selects:
$$a^* = \arg\max_{a \in \mathcal{A}_{\text{valid}}(m)} \left(\mathbf{x}^\top \hat{\theta}_a + \alpha \sqrt{\mathbf{x}^\top A_a^{-1} \mathbf{x}}\right)$$
Where exploration parameter $\alpha > 0$ (default: $0.2$).

### 4.4 Reward Function
The reward signal $R(\mathbf{x}, a) \in [-1.0, 1.0]$ balances information utility against storage/context overhead:
$$R(\mathbf{x}, a) = \begin{cases}
w_{\text{imp}} S_{\text{imp}} + w_{\text{rel}} S_{\text{rel}} - 0.1 \cdot \text{Cost}(m), & \text{if } a = \text{KEEP} \\
0.5 \cdot S_{\text{red}} + 0.3 \cdot (1 - \text{Cost}(m)), & \text{if } a = \text{COMPRESS} \\
0.4 \cdot (1 - S_{\text{rel}}) + 0.3 \cdot (1 - S_{\text{rec}}), & \text{if } a = \text{ARCHIVE} \\
0.5 \cdot (1 - S_{\text{imp}}) + 0.3 \cdot (1 - S_{\text{freq}}) + 0.2 \cdot \text{Cost}(m) - 2.0 \cdot P(m), & \text{if } a = \text{PRUNE}
\end{cases}$$

### 4.5 Recursive Policy Update
Following observation of reward $r$:
$$A_{a^*} \leftarrow A_{a^*} + \mathbf{x}\mathbf{x}^\top, \quad \mathbf{b}_{a^*} \leftarrow \mathbf{b}_{a^*} + r \mathbf{x}$$

---

## 5. Empirical Evaluation & Benchmark Results

### 5.1 Experimental Setup
- **Corpus**: 100 synthetic memory records spanning:
  - 10 Critical User Preferences ($I \ge 0.9$, created 30 days ago)
  - 20 High-frequency Technical Facts ($I = 0.75$, access count 12-16)
  - 30 Ephemeral chatter/scratchpad logs ($I = 0.15$, access count 0)
  - 20 Redundant variations (5 clusters of 4 duplicates each)
  - 20 General task contextual observations
- **Target Working Capacity**: $C_{\max} = 40$ active memories.
- **Evaluation Queries**: 5 representative task queries testing retrieval recall of critical constraints and technical policies.

### 5.2 4-Way Comparative Benchmark Results

| Strategy | Active Memories | Total Tokens | Critical Retention Rate | Retrieval Success Rate | Storage / Token Reduction | Safety Violations | Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline (Retain All)** | 100 | 2,162 | **100.0%** | **80.0%** | 0.0% | **0** | 1,858 ms |
| **Recency-Only (LRU)** | 40 | 898 | **100.0%** | 60.0% | 60.0% | **0** | 3,308 ms |
| **Intelligent Forgetting (Proposed)** | **14** | 2,261 | **100.0%** | **80.0%** | **86.0%** | **0** | 3,776 ms |
| **Reinforcement Learning (LinUCB)** | 50 | 1,132 | **100.0%** | **80.0%** | 50.0% | **0** | 10,547 ms |

### 5.3 Analysis & Discussion
1. **Preservation of Critical Knowledge**: All strategies preserved 100% of critical constraints and pinned user rules. Both Intelligent Forgetting and LinUCB RL achieved **0 safety violations**.
2. **Context Clutter & Redundancy Reduction**: Intelligent Forgetting reduced active memory count from 100 to 14 (an **86% reduction** in active clutter) by summarizing duplicate clusters and archiving low-scoring ephemeral chatter.
3. **Retrieval Precision**: While Recency-Only dropped retrieval accuracy from 80% to 60% by discarding older important facts, both Intelligent Forgetting and LinUCB RL maintained full **80.0% retrieval accuracy**.
4. **Adaptive Policy Learning**: LinUCB learned to balance active token footprint (1,132 tokens vs. 2,162 for baseline) while sustaining 80% retrieval recall.

---

## 6. Limitations & Future Roadmap
- **Production RL Shadow Mode**: LinUCB policies are trained in reproducible offline environments and run in shadow mode before automated promotion to production execution.
- **Fine-Grained Contextual Embeddings**: Future work will evaluate combining Dense Qdrant vector distances directly as a continuous scalar feature in the RL state representation.
- **Hierarchical Clustering**: Expanding pairwise summarization into agglomerative hierarchical memory trees (e.g., Memoria/Generative Agents style).
