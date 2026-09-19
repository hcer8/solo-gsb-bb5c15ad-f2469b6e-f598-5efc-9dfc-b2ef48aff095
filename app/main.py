import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import get_conn, init_db, load_state
from .schemas import ConflictIn, LockIn, PaperIn, ReviewerIn, SolveParams
from .solver import solve_assignment

app = FastAPI(title="匿名评审分配系统", version="1.0.0")


@app.on_event("startup")
def startup():
    init_db()


# ---------------- 稿件 ----------------

@app.get("/api/state")
def get_state():
    with get_conn() as conn:
        papers, reviewers, conflicts, _ = load_state(conn)
        conflict_rows = [dict(r) for r in conn.execute(
            """SELECT c.id, c.paper_id, c.reviewer_id, p.title AS paper_title,
                      rv.name AS reviewer_name
               FROM conflicts c
               JOIN papers p ON p.id = c.paper_id
               JOIN reviewers rv ON rv.id = c.reviewer_id
               ORDER BY c.id""")]
        assignments = [dict(r) for r in conn.execute(
            """SELECT a.id, a.paper_id, a.reviewer_id, a.locked, a.run_id,
                      p.title AS paper_title, rv.name AS reviewer_name
               FROM assignments a
               JOIN papers p ON p.id = a.paper_id
               JOIN reviewers rv ON rv.id = a.reviewer_id
               ORDER BY a.paper_id, a.id""")]
    return {
        "papers": papers,
        "reviewers": reviewers,
        "conflicts": conflict_rows,
        "assignments": assignments,
    }


@app.post("/api/papers", status_code=201)
def create_paper(paper: PaperIn):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO papers (title, topics, required_reviews) VALUES (?, ?, ?)",
            (paper.title, json.dumps(paper.topics, ensure_ascii=False),
             paper.required_reviews))
        return {"id": cur.lastrowid}


@app.delete("/api/papers/{paper_id}")
def delete_paper(paper_id: int):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "稿件不存在")
    return {"ok": True}


# ---------------- 评审人 ----------------

@app.post("/api/reviewers", status_code=201)
def create_reviewer(reviewer: ReviewerIn):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reviewers (name, topics, capacity) VALUES (?, ?, ?)",
            (reviewer.name, json.dumps(reviewer.topics, ensure_ascii=False),
             reviewer.capacity))
        return {"id": cur.lastrowid}


@app.delete("/api/reviewers/{reviewer_id}")
def delete_reviewer(reviewer_id: int):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM reviewers WHERE id = ?", (reviewer_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "评审人不存在")
    return {"ok": True}


# ---------------- 冲突 ----------------

@app.post("/api/conflicts", status_code=201)
def create_conflict(conflict: ConflictIn):
    with get_conn() as conn:
        _check_exists(conn, conflict.paper_id, conflict.reviewer_id)
        try:
            cur = conn.execute(
                "INSERT INTO conflicts (paper_id, reviewer_id) VALUES (?, ?)",
                (conflict.paper_id, conflict.reviewer_id))
        except Exception:
            raise HTTPException(409, "该冲突记录已存在")
        return {"id": cur.lastrowid}


@app.delete("/api/conflicts/{conflict_id}")
def delete_conflict(conflict_id: int):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM conflicts WHERE id = ?", (conflict_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "冲突记录不存在")
    return {"ok": True}


def _check_exists(conn, paper_id, reviewer_id):
    if not conn.execute("SELECT 1 FROM papers WHERE id = ?", (paper_id,)).fetchone():
        raise HTTPException(404, "稿件不存在")
    if not conn.execute("SELECT 1 FROM reviewers WHERE id = ?", (reviewer_id,)).fetchone():
        raise HTTPException(404, "评审人不存在")


# ---------------- 求解与分配 ----------------

@app.post("/api/solve")
def solve(params: SolveParams):
    with get_conn() as conn:
        papers, reviewers, conflicts, locked = load_state(conn)
        if not papers or not reviewers:
            raise HTTPException(400, "请先录入稿件和评审人")
        result = solve_assignment(
            papers, reviewers, conflicts, locked,
            mismatch_penalty=params.mismatch_penalty,
            load_weight=params.load_weight)
        # 保留锁定分配，清除旧的未锁定分配，写入新结果
        conn.execute("DELETE FROM assignments WHERE locked = 0")
        run_id = (conn.execute("SELECT COALESCE(MAX(run_id), 0) FROM assignments")
                  .fetchone()[0] or 0) + 1
        for a in result["assignments"]:
            conn.execute(
                "INSERT OR IGNORE INTO assignments (paper_id, reviewer_id, locked, run_id)"
                " VALUES (?, ?, 0, ?)",
                (a["paper_id"], a["reviewer_id"], run_id))
    result["run_id"] = run_id
    return result


@app.post("/api/assignments/{assignment_id}/lock")
def toggle_lock(assignment_id: int, body: LockIn):
    with get_conn() as conn:
        cur = conn.execute("UPDATE assignments SET locked = ? WHERE id = ?",
                           (1 if body.locked else 0, assignment_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "分配记录不存在")
    return {"ok": True}


@app.delete("/api/assignments")
def clear_assignments(locked: bool = False):
    """清除分配结果。默认仅清除未锁定的；locked=true 时连锁定一起清除。"""
    with get_conn() as conn:
        if locked:
            conn.execute("DELETE FROM assignments")
        else:
            conn.execute("DELETE FROM assignments WHERE locked = 0")
    return {"ok": True}


# ---------------- 示例数据与重置 ----------------

@app.post("/api/seed")
def seed():
    demo_papers = [
        ("基于深度学习的图像分割", ["计算机视觉", "深度学习"], 2),
        ("大语言模型对齐方法综述", ["自然语言处理", "深度学习"], 2),
        ("分布式事务一致性协议优化", ["数据库", "分布式系统"], 2),
        ("零知识证明在区块链中的应用", ["安全", "密码学"], 2),
        ("图神经网络推荐系统", ["机器学习", "图挖掘"], 3),
    ]
    demo_reviewers = [
        ("张伟", ["计算机视觉", "机器学习"], 3),
        ("李娜", ["自然语言处理", "深度学习"], 3),
        ("王强", ["数据库", "分布式系统"], 2),
        ("赵敏", ["安全", "密码学"], 2),
        ("陈杰", ["机器学习", "图挖掘"], 2),
        ("刘洋", ["深度学习", "计算机视觉"], 2),
    ]
    demo_conflicts = [(1, 1), (3, 3), (5, 5)]
    with get_conn() as conn:
        for title, topics, req in demo_papers:
            conn.execute("INSERT INTO papers (title, topics, required_reviews)"
                         " VALUES (?, ?, ?)",
                         (title, json.dumps(topics, ensure_ascii=False), req))
        for name, topics, cap in demo_reviewers:
            conn.execute("INSERT INTO reviewers (name, topics, capacity)"
                         " VALUES (?, ?, ?)",
                         (name, json.dumps(topics, ensure_ascii=False), cap))
        for pid, rid in demo_conflicts:
            conn.execute("INSERT OR IGNORE INTO conflicts (paper_id, reviewer_id)"
                         " VALUES (?, ?)", (pid, rid))
    return {"ok": True}


@app.post("/api/reset")
def reset():
    with get_conn() as conn:
        for table in ("assignments", "conflicts", "papers", "reviewers"):
            conn.execute(f"DELETE FROM {table}")
    return {"ok": True}


# ---------------- 静态前端 ----------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse("app/static/index.html")


app.mount("/static", StaticFiles(directory="app/static"), name="static")
