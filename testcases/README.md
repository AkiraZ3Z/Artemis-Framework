# Artemis Framework 测试用例指南

本目录存放 YAML 格式的测试用例。每个文件定义一个测试用例，包含基本信息、配置、步骤、验证及变量提取等。

---

## 一、用例结构概览

一个典型的 YAML 用例文件结构如下：

```yaml
testcase:
  id: "TC_EXAMPLE_001"           # 必填，唯一标识
  name: "示例用例"               # 必填，用例名称
  description: "演示用例结构"    # 可选
  module: "example"              # 所属模块
  priority: "medium"             # high / medium / low
  tags: ["smoke", "api"]         # 标签列表
  author: "your-name"
  version: "1.0.0"
  status: "ready"                # draft / ready / disabled / deprecated
  
  config:                        # 用例级配置（会覆盖全局配置）
    base_url: "https://jsonplaceholder.typicode.com"
    services:                    # 需要自动注册的服务（可选）
      notes:
        class: "testmodule.operation.ReqRes_Notes.notes_service.NotesService"
        params:
          base_url: "https://reqres.in/api"
          public_key: "${ENV.REQRES_PUBLIC_KEY}"
  
  setup:                         # 前置步骤（可选）
    - action: "api.call"
      params:
        method: "POST"
        url: "/login"
  
  steps:                         # 核心测试步骤（必填，至少一个）
    - name: "获取用户列表"
      action: "api.call"         # 支持 api.call / assert / wait / variable.set / mail.fetch 等
      params:
        method: "GET"
        url: "${config.base_url}/users"
      validate:                  # 断言列表（可选）
        - actual: "${response.status_code}"
          expected: 200
          operator: "equal"
        - actual: "len(${response.body})"
          expected: 0
          operator: "greater_than"
      save:                      # 提取变量（可选）
        first_user_id: "${response[0].id}"
  
  teardown:                      # 后置清理步骤（可选）
    - action: "api.call"
      params:
        method: "DELETE"
        url: "/cleanup"
```

---

## 二、步骤详解

### 2.1 步骤字段

| 字段 | 说明 |
|------|------|
| `name` | 步骤名称，用于日志和报告 |
| `action` | 动作类型，框架会根据该字段寻找对应的处理器 |
| `params` | 步骤参数，随动作不同而不同 |
| `validate` | 断言规则列表 |
| `save` | 从响应中提取并保存变量到上下文 |
| `retry_times` | 步骤失败时重试次数（默认 0） |
| `retry_interval` | 重试间隔秒数（默认 1.0） |
| `timeout` | 步骤超时秒数（可选） |
| `skip` | 是否跳过该步骤（true/false） |
| `skip_reason` | 跳过原因说明 |

### 2.2 常用动作

| 动作关键字 | 功能 | 处理器 |
|-----------|------|--------|
| `api.call` 或 `api.xxx` | 调用 API 服务 | `APICallHandler` |
| `assert` | 执行断言 | `AssertionHandler` |
| `variable.set` | 设置上下文变量 | `VariableSetHandler` |
| `wait` | 等待指定秒数 | `WaitHandler` |
| `mail.fetch` | 从邮箱获取验证码 | `MailFetchHandler` |
| `sql.execute` | 执行 SQL（预留） | `SQLExecuteHandler` |

> 自定义处理器可通过 `TestExecutor.register_handler` 注册。

### 2.3 变量引用

支持 `${变量名}` 以及嵌套路径 `${response.data[0].id}`，还支持以下内置变量：

| 变量 | 含义 |
|------|------|
| `${config.xxx}` | 用例配置中的值 |
| `${ENV.VAR_NAME}` | 操作系统环境变量 |
| `${RANDOM.string}` | 随机 8 位字符串 |
| `${RANDOM.int}` | 随机整数 |
| `${TIMESTAMP}` | 当前时间戳 |
| `${UUID}` | UUID |

---

## 三、多格式示例对照

下面以同一个步骤为例，展示 **YAML、JSON、Python 字典** 三种表示方式。

### 3.1 YAML（推荐）

```yaml
steps:
  - name: "获取用户列表"
    action: "api.call"
    params:
      method: "GET"
      url: "${config.base_url}/users"
    validate:
      - actual: "${response.status_code}"
        expected: 200
        operator: "equal"
      - actual: "len(${response.body})"
        expected: 0
        operator: "greater_than"
    save:
      first_user_id: "${response[0].id}"
```

### 3.2 JSON（等价的 JSON 表示）

```json
{
  "steps": [
    {
      "name": "获取用户列表",
      "action": "api.call",
      "params": {
        "method": "GET",
        "url": "${config.base_url}/users"
      },
      "validate": [
        {
          "actual": "${response.status_code}",
          "expected": 200,
          "operator": "equal"
        },
        {
          "actual": "len(${response.body})",
          "expected": 0,
          "operator": "greater_than"
        }
      ],
      "save": {
        "first_user_id": "${response[0].id}"
      }
    }
  ]
}
```

### 3.3 Python 数据结构（`TestCaseLoader` 内部解析结果）

```python
steps = [
    {
        "name": "获取用户列表",
        "action": "api.call",
        "params": {
            "method": "GET",
            "url": "${config.base_url}/users"
        },
        "validate": [
            {"actual": "${response.status_code}", "expected": 200, "operator": "equal"},
            {"actual": "len(${response.body})", "expected": 0, "operator": "greater_than"}
        ],
        "save": {
            "first_user_id": "${response[0].id}"
        }
    }
]
```

无论哪种格式，最终都会被 `TestCaseLoader` 解析为统一的 `TestCase` 和 `TestStep` 对象。

---

## 四、使用脚手架快速生成用例

我们提供了一个交互式命令行工具 `build_testcase.py`，可以引导你一步步填写信息，自动生成符合规范的 YAML 用例文件。

**使用方法：**

```bash
# 直接运行脚手架
python build_testcase.py

# 或者通过 run.py 的 --new 参数
python run.py --new
```

工具会依次询问：
- 用例基本信息（ID、名称、模块、优先级等）
- 步骤详情（动作、参数、验证条件、变量提取）
- 是否添加上下文（setup / teardown）

完成后会在指定目录（默认 `testcases/`）下生成 `{用例ID}.yaml` 文件，你可以直接使用 `run.py -t <文件>` 执行它。

---

## 五、运行用例

生成或用编辑器编写好 YAML 后，使用以下命令执行：

```bash
# 执行单个用例
python run.py -t testcases/TC_EXAMPLE_001.yaml

# 执行整个目录
python run.py -d testcases/ -r

# 指定任务名称和日志级别
python run.py --task-name "回归测试" --log-level DEBUG -t testcases/login.yaml
```

执行后会在 `reports/` 下生成 HTML 报告，可用浏览器直接打开查看。

---

## 六、注意事项

- 敏感信息（如密码、Token）请使用 `${ENV.XXX}` 引用环境变量，不要硬编码在 YAML 中。
- 用例 ID 必须唯一，建议采用 `模块_功能_编号` 命名，如 `USER_LOGIN_001`。
- 验证规则中的 `operator` 支持 `equal`、`not_equal`、`greater_than`、`contains`、`matches` 等十余种操作符，详见 `AssertionOperator` 枚举。
- 若需要调用邮件获取验证码，请确保在用例配置或环境变量中提供邮箱地址和授权码，并保证 IMAP 服务已开启。
- 更多高级功能（如服务自动注册、数据驱动）请参阅框架文档或 `config/global_config.yaml` 中的注释。

---
