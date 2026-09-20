# 民用日程展开 API（Civil Schedule Expansion API）

基于 **FastAPI + 标准库 zoneinfo** 的日程展开服务：给定 IANA 时区、日期区间、星期集合与本地时刻，按指定的夏令时策略展开为具体实例。服务通过 **UTC 往返校验** 区分正常时刻、跳时（不存在时刻）与叠时（重复时刻），输出去重且按 UTC 稳定排序的实例列表，每个实例包含本地时间、UTC 偏移、UTC 时间与决策原因。

## 快速启动（单条命令）

```bash
docker compose up --build
```

依赖（FastAPI、uvicorn、tzdata 时区数据库）在镜像构建阶段安装完毕，容器启动即可用，无需任何额外步骤。

- 服务地址： <http://localhost:8000>
- 交互式文档（Swagger UI）： <http://localhost:8000/docs>
- 健康检查： <http://localhost:8000/health>

## 配置

无需环境变量。唯一可调整项为端口映射：修改 `docker-compose.yml` 中的 `ports`（默认 `8000:8000`，冒号左侧为宿主机端口）。IANA 时区数据由 `tzdata` pip 包提供，不依赖宿主机操作系统的时区库。

## API

### `POST /expand`

请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `timezone` | string | IANA 时区名，如 `America/New_York` |
| `start_date` / `end_date` | date | 日期区间（含两端），跨度不得超过 366 天 |
| `weekdays` | int[] | 星期集合，`0`=周一 … `6`=周日，至少 1 个 |
| `local_time` | string | 本地时刻，如 `02:30` |
| `gap_strategy` | enum | 不存在时刻策略：`skip`（默认，跳过）/ `shift_forward`（按跳变差值前移） |
| `fold_strategy` | enum | 重复时刻策略：`first`（默认，取第一次）/ `second`（取第二次）/ `both`（两次都保留） |

策略语义：

- **跳时（gap，春季拨快）**：本地时刻不存在。`shift_forward` 将该时刻按跳变差值前移——例如纽约 `2024-03-10 02:30` 不存在（02:00 直接跳到 03:00，差值 1 小时），前移后落在 `03:30 -04:00`。
- **叠时（fold，秋季拨回）**：本地时刻发生两次。`first` 取 UTC 较早的一次，`second` 取 UTC 较晚的一次，`both` 两次都生成。

响应：`200 OK`

```json
{
  "timezone": "America/New_York",
  "count": 2,
  "instances": [
    {"local": "2024-11-03T01:30:00", "offset": "-04:00", "utc": "2024-11-03T05:30:00Z", "reason": "fold_first"},
    {"local": "2024-11-03T01:30:00", "offset": "-05:00", "utc": "2024-11-03T06:30:00Z", "reason": "fold_second"}
  ]
}
```

`reason` 取值：`normal`（正常）、`gap_shift_forward`（跳时已前移）、`fold_first` / `fold_second`（叠时的第一/第二次）。实例按 UTC 稳定排序并按 UTC 去重。

### 示例

```bash
curl -X POST http://localhost:8000/expand \
  -H 'Content-Type: application/json' \
  -d '{
        "timezone": "America/New_York",
        "start_date": "2024-11-03",
        "end_date": "2024-11-03",
        "weekdays": [6],
        "local_time": "01:30",
        "gap_strategy": "shift_forward",
        "fold_strategy": "both"
      }'
```

### 错误（422）

以下情况返回 `422 Unprocessable Entity`（响应体含具体原因）：

- 非法的 IANA 时区名；
- `end_date` 早于 `start_date`（区间逆序）；
- 区间跨度超过 366 天；
- 其他请求校验失败（星期越界、策略枚举非法、字段缺失等）。

## 本地开发与测试

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload   # 开发模式，监听 8000 端口
pytest                          # 运行测试
```

## 项目结构

```
app/
  core.py      # UTC 往返分类（normal/gap/fold）与展开、去重、稳定排序
  schemas.py   # 请求/响应模型与 422 校验
  main.py      # FastAPI 入口：POST /expand、GET /health
tests/test_expand.py
Dockerfile
docker-compose.yml
requirements.txt / requirements-dev.txt
```
