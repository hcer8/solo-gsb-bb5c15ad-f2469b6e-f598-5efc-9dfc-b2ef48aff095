"""最小费用最大流评审分配求解器。

图结构：
    源点 -> 稿件节点      容量 = 该稿剩余所需评审数，费用 0
    稿件 -> 评审人        容量 = 1，费用 = 主题不匹配惩罚（冲突/已锁定对不建边）
    评审人 -> 汇点        拆成单位容量的边，第 k 条边费用为负载的凸边际成本，
                          已锁定占用计入 k 的起点，从而参与负载均衡

目标：先保证流量最大（尽可能完整分配），在最大流中使总费用最小。
由于总分配数固定（最大流），最小化评审人负载的平方和等价于最小化负载方差，
即惩罚负载偏差。
"""

from collections import deque


class MinCostMaxFlow:
    def __init__(self, n):
        self.n = n
        self.graph = [[] for _ in range(n)]  # 边: [to, cap, cost, 反向边下标]

    def add_edge(self, fr, to, cap, cost):
        fwd = [to, cap, cost, len(self.graph[to])]
        rev = [fr, 0, -cost, len(self.graph[fr])]
        self.graph[fr].append(fwd)
        self.graph[to].append(rev)
        return len(self.graph[fr]) - 1  # 返回正向边下标，便于回读流量

    def min_cost_max_flow(self, s, t):
        """SPFA 逐最短增广路，返回 (最大流, 最小费用)。"""
        n = self.n
        INF = float("inf")
        flow = cost = 0
        while True:
            dist = [INF] * n
            inq = [False] * n
            prev_v = [-1] * n
            prev_e = [-1] * n
            dist[s] = 0
            q = deque([s])
            inq[s] = True
            while q:
                v = q.popleft()
                inq[v] = False
                for i, e in enumerate(self.graph[v]):
                    if e[1] > 0 and dist[e[0]] > dist[v] + e[2]:
                        dist[e[0]] = dist[v] + e[2]
                        prev_v[e[0]] = v
                        prev_e[e[0]] = i
                        if not inq[e[0]]:
                            q.append(e[0])
                            inq[e[0]] = True
            if dist[t] == INF:
                break
            d = INF
            v = t
            while v != s:
                d = min(d, self.graph[prev_v[v]][prev_e[v]][1])
                v = prev_v[v]
            flow += d
            cost += d * dist[t]
            v = t
            while v != s:
                e = self.graph[prev_v[v]][prev_e[v]]
                e[1] -= d
                self.graph[v][e[3]][1] += d
                v = prev_v[v]
        return flow, cost


def topic_mismatch_cost(paper_topics, reviewer_topics, penalty):
    """主题不匹配费用：完全不匹配取满惩罚，全部匹配为 0，按重合度线性插值。"""
    if not paper_topics:
        return 0
    overlap = len(set(paper_topics) & set(reviewer_topics))
    return round(penalty * (1 - overlap / len(paper_topics)))


def solve_assignment(papers, reviewers, conflicts, locked,
                     mismatch_penalty=10, load_weight=1):
    """
    papers:    [{id, title, topics, required_reviews}]
    reviewers: [{id, name, topics, capacity}]
    conflicts: {(paper_id, reviewer_id), ...}   作者冲突，绝不建边
    locked:    [{paper_id, reviewer_id}]        锁定分配，占用容量并参与负载
    返回 {assignments, unfulfilled, warnings, stats}
    """
    warnings = []
    conflict_set = set(conflicts)
    locked_pairs = {(l["paper_id"], l["reviewer_id"]) for l in locked}

    locked_by_paper = {}
    locked_by_reviewer = {}
    for l in locked:
        locked_by_paper[l["paper_id"]] = locked_by_paper.get(l["paper_id"], 0) + 1
        locked_by_reviewer[l["reviewer_id"]] = locked_by_reviewer.get(l["reviewer_id"], 0) + 1

    paper_ids = [p["id"] for p in papers]
    reviewer_ids = [r["id"] for r in reviewers]
    p_idx = {pid: i for i, pid in enumerate(paper_ids)}
    r_idx = {rid: i for i, rid in enumerate(reviewer_ids)}

    P, R = len(papers), len(reviewers)
    SRC, SNK = 0, 1 + P + R
    mcmf = MinCostMaxFlow(2 + P + R)

    # 源点 -> 稿件：剩余需求（锁定已占用部分扣除）
    remaining_need = {}
    for p in papers:
        used = locked_by_paper.get(p["id"], 0)
        need = max(0, p["required_reviews"] - used)
        if used > p["required_reviews"]:
            warnings.append(
                f"稿件《{p['title']}》锁定数 {used} 超过所需评审数 {p['required_reviews']}，超出部分仍保留。")
        remaining_need[p["id"]] = need
        if need > 0:
            mcmf.add_edge(SRC, 1 + p_idx[p["id"]], need, 0)

    # 评审人 -> 汇点：单位容量凸费用边，锁定负载计入起点
    remaining_cap = {}
    for r in reviewers:
        used = locked_by_reviewer.get(r["id"], 0)
        cap = max(0, r["capacity"] - used)
        if used > r["capacity"]:
            warnings.append(
                f"评审人 {r['name']} 锁定数 {used} 超过容量 {r['capacity']}，本次不再分配新任务。")
        remaining_cap[r["id"]] = cap
        node = 1 + P + r_idx[r["id"]]
        for k in range(1, cap + 1):
            # 第 (used+k) 份总负载的边际成本 = load_weight * ((used+k)^2 - (used+k-1)^2)
            marginal = load_weight * (2 * (used + k) - 1)
            mcmf.add_edge(node, SNK, 1, marginal)

    # 稿件 -> 评审人：无冲突且未锁定的对才建边
    pair_edges = {}  # (paper_id, reviewer_id) -> (节点, 边下标)
    for p in papers:
        if remaining_need[p["id"]] == 0:
            continue
        p_node = 1 + p_idx[p["id"]]
        for r in reviewers:
            key = (p["id"], r["id"])
            if key in conflict_set or key in locked_pairs:
                continue
            if remaining_cap[r["id"]] == 0:
                continue
            cost = topic_mismatch_cost(p["topics"], r["topics"], mismatch_penalty)
            r_node = 1 + P + r_idx[r["id"]]
            e_idx = mcmf.add_edge(p_node, r_node, 1, cost)
            pair_edges[key] = (p_node, e_idx)

    max_flow, min_cost = mcmf.min_cost_max_flow(SRC, SNK)

    # 回读分配结果：正向边容量从 1 变 0 即被使用
    assignments = []
    new_load = {rid: 0 for rid in reviewer_ids}
    for (pid, rid), (node, e_idx) in pair_edges.items():
        edge = mcmf.graph[node][e_idx]
        if edge[1] == 0:  # 容量耗尽 => 流量为 1
            assignments.append({"paper_id": pid, "reviewer_id": rid})
            new_load[rid] += 1

    # 未满足稿件诊断
    new_by_paper = {}
    for a in assignments:
        new_by_paper[a["paper_id"]] = new_by_paper.get(a["paper_id"], 0) + 1

    reviewer_by_id = {r["id"]: r for r in reviewers}
    unfulfilled = []
    for p in papers:
        got = locked_by_paper.get(p["id"], 0) + new_by_paper.get(p["id"], 0)
        if got >= p["required_reviews"]:
            continue
        shortage = p["required_reviews"] - got
        eligible = [r for r in reviewers
                    if (p["id"], r["id"]) not in conflict_set
                    and (p["id"], r["id"]) not in locked_pairs]
        free_cap = sum(max(0, remaining_cap[r["id"]] - new_load[r["id"]])
                       for r in eligible)
        if not eligible:
            reason = "无可用评审人：所有评审人均与该稿件存在作者冲突（或未录入评审人）。"
        elif free_cap == 0:
            names = "、".join(r["name"] for r in eligible[:5])
            reason = (f"合格评审人 {len(eligible)} 人（{names}）的剩余容量已耗尽，"
                      f"仍缺 {shortage} 份评审。")
        else:
            reason = (f"全局容量竞争：合格评审人剩余容量共 {free_cap}，"
                      f"但受其他稿件需求挤占，仍缺 {shortage} 份评审。")
        unfulfilled.append({
            "paper_id": p["id"],
            "title": p["title"],
            "required": p["required_reviews"],
            "assigned": got,
            "shortage": shortage,
            "eligible_reviewers": len(eligible),
            "eligible_free_capacity": free_cap,
            "reason": reason,
        })

    total_need = sum(max(0, p["required_reviews"] - locked_by_paper.get(p["id"], 0))
                     for p in papers)
    stats = {
        "total_demand": sum(p["required_reviews"] for p in papers),
        "total_capacity": sum(r["capacity"] for r in reviewers),
        "locked": len(locked),
        "new_assignments": len(assignments),
        "max_flow": max_flow,
        "remaining_need": total_need,
        "min_cost": min_cost,
        "fulfilled": len(papers) - len(unfulfilled),
        "unfulfilled_count": len(unfulfilled),
        "reviewer_loads": [
            {"reviewer_id": r["id"], "name": r["name"],
             "load": locked_by_reviewer.get(r["id"], 0) + new_load[r["id"]],
             "capacity": r["capacity"]}
            for r in reviewers
        ],
    }
    return {
        "assignments": assignments,
        "unfulfilled": unfulfilled,
        "warnings": warnings,
        "stats": stats,
    }
