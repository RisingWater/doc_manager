# 文档管理 API 文档

Base URL：`http://127.0.0.1:8000`

所有接口均以 `/api` 为前缀，返回 JSON（UTF-8）。列表接口的分页字段：`page` 从 1 开始，`page_size` 最大 100。

---

## 1. 文档查询（分类筛选 + 模糊查找）

```
GET /api/documents
```

### Query 参数（均可选）

| 参数 | 类型 | 说明 |
|---|---|---|
| `years` | 逗号分隔字符串 | 年份，多值如 `2022,2023` |
| `subjects` | 逗号分隔字符串 | 科目，如 `数学,语文` |
| `cities` | 逗号分隔字符串 | 地市，如 `福州市,厦门市` |
| `exams` | 逗号分隔字符串 | 考试，如 `一检,中考` |
| `paper_type` | 逗号分隔字符串 | 试卷/答案：`试卷`、`答案`、`试卷+答案` |
| `classified` | 字符串 | `yes`=已分类，`no`=未分类，空=全部 |
| `q` | 字符串 | 模糊搜索关键字，匹配文件名/路径/所有分类字段，如 `q=中考数学` |
| `sort` | 字符串 | `mtime_desc`(默认) / `mtime_asc` / `name_asc` / `name_desc` |
| `page` | 整数 | 页码，默认 1 |
| `page_size` | 整数 | 每页数量，默认 20，最大 100 |

多值筛选之间是 AND 关系，同一参数内多个值是 OR（IN）关系。

### 响应

```json
{
  "total": 753,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "path": "D:\\yuqiao\\九年级\\乔宝卷子\\...\\三明化学卷面·2021-2022学年初三一检.pdf",
      "file_name": "三明化学卷面·2021-2022学年初三一检.pdf",
      "ext": "pdf",
      "size": 1234567,
      "mtime": "2026-09-02T23:45:21",
      "rel_dir": "22-24一检、二检卷\\...",
      "year": "2022",
      "subject": "化学",
      "city": "三明市",
      "exam": "一检",
      "paper_type": "试卷",
      "is_classified": true,
      "missing_dims": []
    }
  ]
}
```

`missing_dims`：未分类时缺失的维度，取值 `year` / `subject` / `city` / `exam`。

### 示例

```
# 筛选 2023 年 + 数学，搜索关键字"答案"
GET /api/documents?years=2023&subjects=数学&paper_type=答案&q=厦门&page=1&page_size=50

# 只看未分类的文件
GET /api/documents?classified=no
```

> 中文参数直接使用 UTF-8 URL 编码即可（如 `%E6%95%B0%E5%AD%A6` = 数学）。

---

## 2. 筛选项可选值

```
GET /api/meta/options
```

返回各维度现有的取值及数量，可直接用于构建筛选下拉：

```json
{
  "years":       [{ "value": "2025", "count": 40 }, { "value": "2024", "count": 144 }],
  "subjects":    [{ "value": "数学", "count": 100 }],
  "cities":      [{ "value": "福州市", "count": 86 }],
  "exams":       [{ "value": "一检", "count": 92 }],
  "paper_types": [{ "value": "试卷", "count": 328 }, { "value": "答案", "count": 219 }, { "value": "试卷+答案", "count": 206 }],
  "total": 753,
  "classified": 752
}
```

---

## 3. 下载文档

```
GET /api/documents/{id}/download
```

- `id` 为查询接口返回的文档 id。
- 成功返回文件流，`Content-Disposition` 带 UTF-8 编码的原始文件名（RFC 5987），可直接另存。
- 文档记录不存在或磁盘文件已删除返回 404（`{"detail": "..."}`）。

```bash
curl -OJ "http://127.0.0.1:8000/api/documents/1/download"
```

---

## 4. 上传文档

```
POST /api/upload
Content-Type: multipart/form-data
```

### 表单字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | 文件 | 是 | 要上传的文档 |
| `year` | 字符串 | 否 | 年份，如 `2026` |
| `subject` | 字符串 | 否 | 科目，如 `数学` |
| `city` | 字符串 | 否 | 地市，如 `福州市` |
| `exam` | 字符串 | 否 | 考试，如 `一检` |
| `root_dir` | 字符串 | 否 | 保存目录，必须是 docs.json 中配置的目录；留空默认 `uploads` |

- 文件保存为 `root_dir/年份/科目/地市/考试/文件名`（未填的分类不建目录层）。
- 同名文件自动追加 `(1)`、`(2)`… 后缀。
- 保存后立即写入数据库，无需等待扫描。
- 可用 `GET /api/dirs` 获取可配置的目录列表。

### 响应

```json
{ "ok": true, "id": 612, "path": "D:\\wangxu\\work\\doc_manager\\uploads\\2026\\数学\\中考\\test.pdf", "file_name": "test.pdf" }
```

错误：400 文件名/分类值不合法或目录未配置，500 磁盘写入失败。

### 示例

```bash
curl -X POST "http://127.0.0.1:8000/api/upload" \
  -F "file=@试卷.pdf" \
  -F "year=2026" \
  -F "subject=数学" \
  -F "city=福州市" \
  -F "exam=一检"
```

---

## 附：其他相关接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/scan` | POST | 触发扫描（已扫过的文件跳过，仅补新文件并重新分类）。扫描中重复调用返回 409 |
| `/api/scan/status` | GET | 当前是否在扫描 + 最近一次扫描日志（发现/新增/跳过/更新数） |
| `/api/scan/logs` | GET | 扫描历史，参数 `limit` 默认 20 |
| `/api/dirs` | GET | docs.json 配置的目录及是否存在 |
| `/api/meta/options` | GET | 见第 2 节 |
