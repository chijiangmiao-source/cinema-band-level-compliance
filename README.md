# 影院放映厅声级评估服务

老影院更换扬声器后，用八个倍频带声压级评估放映厅是否过响。纯后端服务：
Python 3.12 + FastAPI + Pydantic，通过 multipart 上传 CSV 与允许总声级，
按 A 计权合成总声级并给出合规裁决。**不做固定响应**：所有结果均由输入实时计算。

## 计算规则

- 频带（Hz）：63、125、250、500、1000、2000、4000、8000
- A 计权修正（dB）：-26.2、-16.1、-8.6、-3.2、0.0、1.2、1.0、-1.1
- 每行计权级：`L_i + A_i`（十进制精确相加）
- 总声级：`10 × log10( Σ 10^((L_i+A_i)/10) )`
- 裁决：**始终以未舍入总值**与限值比较，`<=` 为 `COMPLIANT`，否则 `NON_COMPLIANT`
- 展示：总值四舍五入（half-up）到 0.01 dB，仅用于展示，不参与裁决
- 频带列表：按计权后线性能量贡献 `10^((L_i+A_i)/10)` 降序；贡献相同按频率升序

## 输入契约

`POST /api/v1/assessments`（`multipart/form-data`）

| 字段 | 规则 |
| --- | --- |
| `file` | UTF-8 CSV，≤ 64 KiB（65536 字节）。首行必须精确为 `frequency_hz,level_db`；随后 8 个频带各有且仅有一行（顺序不限）；声级为 `[0.00, 140.00]` 内的有限普通十进制数；任何位置出现空行（含首行）均整份拒绝 |
| `limit` | 允许总声级：0–140 dB 的普通十进制数，最多两位小数；NaN、无穷、科学计数法等其他表示一律拒绝 |

任一表头、编码、大小、频带或数值规则失败，**整份拒绝**并返回结构化错误：

```json
{ "error": { "code": "INVALID_LIMIT", "message": "...", "details": { "value": "1e2" } } }
```

| HTTP | code | 含义 |
| --- | --- | --- |
| 413 | `FILE_TOO_LARGE` | CSV 超过 64 KiB |
| 422 | `MISSING_FILE` / `MISSING_LIMIT` | 缺少 multipart 字段 |
| 422 | `INVALID_LIMIT` | 限值格式或范围非法 |
| 422 | `INVALID_ENCODING` | 非 UTF-8 编码 |
| 422 | `INVALID_HEADER` | 首行不是精确的 `frequency_hz,level_db` |
| 422 | `INVALID_ROW_COUNT` | 数据行数不是 8 |
| 422 | `INVALID_FIELD_COUNT` | 某行字段数不是 2 |
| 422 | `INVALID_FREQUENCY` / `UNKNOWN_FREQUENCY` | 频率非法 / 不在 8 个倍频带内 |
| 422 | `DUPLICATE_FREQUENCY` / `MISSING_FREQUENCY` | 频带重复 / 缺失 |
| 422 | `INVALID_LEVEL` | 声级非法（非有限普通十进制或越界） |
| 422 | `INVALID_REQUEST` | multipart 请求本身畸形 |

成功响应示例：

```json
{
  "total_db": 93.21,
  "limit_db": 95.0,
  "verdict": "COMPLIANT",
  "bands": [
    { "frequency_hz": 1000, "level_db": 90.0, "a_weight_db": 0.0,
      "weighted_level_db": 90.0, "energy": 1000000000.0 }
  ]
}
```

## 运行（Docker Compose）

```bash
docker compose up --build          # 默认宿主端口 8000
API_PORT=9000 docker compose up    # 用 API_PORT 覆盖宿主端口
```

容器内服务固定监听 8000，`API_PORT` 只改宿主映射端口。
交互式文档：`http://localhost:8000/docs`，健康检查：`GET /healthz`。

调用示例：

```bash
curl -X POST "http://localhost:8000/api/v1/assessments" \
  -F "file=@bands.csv;type=text/csv" \
  -F "limit=95.00"
```

`bands.csv` 示例：

```csv
frequency_hz,level_db
63,80
125,78
250,85
500,88
1000,90
2000,86
4000,82
8000,75
```

## 本地开发与测试

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                 # 119 个用例：合法计算、临界裁决、整文件校验
uvicorn app.main:app --reload
```

测试中的期望值一律按规范公式现算（`tests/helpers.py`），不断言任何固定响应。

## 结构

```
app/
  main.py        # FastAPI 入口、路由、异常处理
  csv_parser.py  # CSV 大小/编码/表头/频带/数值整份校验
  validation.py  # 限值格式校验
  acoustics.py   # A 计权、能量合成、裁决、展示舍入
  service.py     # 评估编排与频带排序
  models.py      # Pydantic 响应模型
  errors.py      # 结构化错误
tests/           # pytest：声学核心、CSV 校验、端到端 API
Dockerfile       # python:3.12-slim
docker-compose.yml
```
