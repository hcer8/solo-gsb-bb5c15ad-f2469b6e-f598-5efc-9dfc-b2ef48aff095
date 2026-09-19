# 匿名评审分配系统

基于 **Python + FastAPI + SQLite + 原生前端** 的稿件–评审人自动分配 Web 应用。
后端使用**最小费用最大流**生成完整分配：冲突边绝不建边，费用同时惩罚主题不匹配与评审负载偏差；容量不足时返回未满足稿件及可复核原因。支持锁定少量既有分配后重新求解。

## 快速开始（单条命令）

```bash
docker compose up --build
```

该命令自动完成依赖安装与 SQLite 数据库初始化（应用启动时自动建表，无需手动迁移）。

- **访问地址：http://localhost:8000**
- API 文档（Swagger UI）：http://localhost:8000/docs
- 端口：**8000**（宿主机映射，可在 `docker-compose.yml` 中修改）

停止：`docker compose down`（数据保存在名为 `review_data` 的卷中）。

### 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

同样访问 http://localhost:8000 ，数据库文件默认创建于 `data/review_assign.db`（可用环境变量 `DB_PATH` 覆盖）。

## 使用流程

1. **稿件管理**：录入稿件标题、主题（逗号分隔）、每稿所需评审数。
2. **评审人管理**：录入姓名、擅长主题、个人容量上限。
3. **冲突管理**：登记作者冲突的「稿件–评审人」对，求解时绝不使用这些边。
4. **分配求解**：
   - 可调参数：主题不匹配惩罚、负载均衡权重。
   - 点击「求解分配」生成结果；未满足稿件会列出缺口与可复核原因。
   - 在结果表中勾选「锁定」后再次求解：锁定分配被保留，占用对应容量并参与负载计算。
   - 「载入示例数据」可一键填充演示数据。

## 算法说明

建图（源点 → 稿件 → 评审人 → 汇点）：

| 边 | 容量 | 费用 |
|---|---|---|
| 源点 → 稿件 | 该稿剩余所需评审数 | 0 |
| 稿件 → 评审人 | 1（冲突对、已锁定对不建边） | 主题不匹配惩罚：按主题重合度在 `0 ~ mismatch_penalty` 间线性插值 |
| 评审人 → 汇点 | 拆成单位容量边 | 第 k 份负载的凸边际费用 `load_weight·(2k−1)`，即总费用为负载平方和 |

采用 SPFA 逐最短增广路求得**最小费用最大流**：先保证分配数最大（尽可能完整满足），再在最大流中使总费用最小。由于总分配数固定，最小化负载平方和等价于最小化负载方差，从而惩罚评审负载偏差。

**锁定重解**：锁定的分配从稿件需求与评审人容量中预先扣除，且评审人→汇点的边际费用从锁定负载之后开始累计，因此锁定任务照常参与负载均衡。

**容量不足诊断**：对每篇未满足稿件给出可复核原因——无合格评审人（全部冲突）/ 合格评审人剩余容量耗尽 / 全局容量竞争，并附合格评审人数与剩余容量数值。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/state` | 获取全部数据（稿件/评审人/冲突/分配） |
| POST / DELETE | `/api/papers[/{id}]` | 稿件增删 |
| POST / DELETE | `/api/reviewers[/{id}]` | 评审人增删 |
| POST / DELETE | `/api/conflicts[/{id}]` | 冲突登记/移除 |
| POST | `/api/solve` | 求解（参数：`mismatch_penalty`、`load_weight`） |
| POST | `/api/assignments/{id}/lock` | 锁定/解锁单条分配 |
| DELETE | `/api/assignments` | 清除未锁定分配（`?locked=true` 全部清除） |
| POST | `/api/seed` / `/api/reset` | 载入示例 / 清空全部 |

## 目录结构

```
app/
├── main.py        # FastAPI 应用与 API 路由
├── solver.py      # 最小费用最大流求解器与未满足诊断
├── database.py    # SQLite 连接与建表
├── schemas.py     # Pydantic 请求模型
└── static/        # 原生前端（index.html / app.js / style.css）
Dockerfile
docker-compose.yml
requirements.txt
```
