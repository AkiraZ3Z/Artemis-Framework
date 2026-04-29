<h1 align="center">Artemis Framework</h1>

<p align="center">
  一个现代化、模块化、数据驱动的自动化测试框架，支持 API 测试、邮件验证、全流程业务场景。
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> •
  <a href="#-特性">特性</a> •
  <a href="#-目录结构">目录结构</a> •
  <a href="#-使用指南">使用指南</a> •
  <a href="#-测试用例">测试用例</a> •
  <a href="#-报告">报告</a> •
  <a href="#-配置">配置</a> •
  <a href="#-联系">联系</a>
</p>

---

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone <你的仓库地址>
cd Artemis-Framework

# 2. 安装依赖（推荐使用虚拟环境）
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Linux/Mac
pip install -r requirements.txt

# 3. 设置环境变量（必须）
# Windows PowerShell 示例
$env:QQ_EMAIL = "your_email@qq.com"
$env:QQ_AUTH_CODE = "your_qq_imap_auth_code"
$env:REQRES_PUBLIC_KEY = "your_reqres_public_key"

# 4. 运行示例测试
python run.py -t testcases/reqres_notes/test_reqres_notes_full.yaml
```

---

## ✨ 特性

- **YAML 驱动** – 测试用例使用可读的 YAML 编写，无代码基础即可维护
- **模块化架构** – 日志 / 目录 / 加载器 / 执行器 / 报告完全解耦
- **服务自动注册** – 在测试用例中声明服务，执行时自动注入
- **邮件验证码提取** – 内置 IMAP 邮件抓取处理器，支持真实邮箱验证
- **强大的断言引擎** – 支持嵌套 JSON 路径、`len()` 函数、十余种操作符
- **丰富的变量系统** – 支持环境变量、随机值、时间戳、上下文变量
- **多格式报告** – 实时生成可交互的 HTML 报告，支持导出 JSON / CSV
- **交互式脚手架** – `build_testcase.py` 或 `python run.py --new` 快速生成 YAML 模板
- **多环境配置** – 通过 `config/global_config.yaml` 与 `environments` 段落支持多套环境

---

## 📂 目录结构

```
Artemis-Framework/
├── run.py                  # 主运行入口（支持命令行参数）
├── build_testcase.py       # 测试用例脚手架
├── requirements.txt
├── README.md
├── config/
│   ├── global_config.yaml  # 全局配置文件（环境、日志、报告等）
│   └── config_loader.py
├── core/                   # 框架核心
│   ├── __init__.py
│   ├── id_generator.py     # 会话ID生成
│   ├── logdir_manager.py   # 目录管理
│   ├── logger.py           # 日志系统（任务/用例分层）
│   ├── json_path.py        # JSON 路径解析器
│   ├── testcase_loader.py  # YAML 加载 & 变量解析
│   ├── testcase_executor.py # 用例执行器 & 步骤处理器
│   ├── mail_fetch_handler.py # 邮箱验证码提取处理器
│   └── tools/
│       └── mail_fetcher.py # IMAP 邮件工具
├── testmodule/
│   ├── api_test/
│   │   └── base_client.py  # HTTP 客户端（重试、日志、钩子）
│   └── operation/
│       └── ReqRes_Notes/
│           └── notes_service.py # ReqRes 业务服务
├── reporters/              # 报告模块
│   ├── html_reporter.py
│   ├── allure_reporter.py
│   └── report_manager.py
└── testcases/              # 存放测试用例（YAML）
    ├── README.md           # 用例编写指南
    └── reqres_notes/
        ├── test_reqres_notes_full.yaml
        └── fetch_code_only.yaml
```

---

## 📘 使用指南

### 命令行参数

```bash
python run.py [选项]

选项：
  -c, --config        配置文件路径 (默认: config/global_config.yaml)
  --env               运行环境 (dev/test/staging/prod)
  --task-name         任务名称，用于报告标识
  --session-id        指定 session_id，不指定则自动生成
  --log-level         日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
  --no-console-log    禁止控制台输出
  --dry-run           只加载用例，不执行
  -t, --testcase      指定测试用例文件（可多次使用）
  -d, --test-dir      指定测试用例目录（可多次使用）
  -s, --suite         指定测试套件文件（可多次使用）
  -r, --recursive     递归加载目录
  --new               交互式创建新用例
  --version           显示版本
```

### 常用示例

```bash
# 运行默认目录下所有用例
python run.py

# 指定任务名称和日志级别
python run.py --task-name "回归测试" --log-level DEBUG

# 运行单个文件
python run.py -t testcases/reqres_notes/test_reqres_notes_full.yaml

# 只加载不执行（检验用例格式）
python run.py -d testcases/ -r --dry-run

# 生成新用例
python run.py --new
```

---

## 🧪 测试用例

测试用例采用 YAML 格式，一个简单的例子：

```yaml
testcase:
  id: "DEMO_001"
  name: "演示用例"
  steps:
    - name: "获取示例用户"
      action: "api.call"
      params:
        method: "GET"
        url: "https://jsonplaceholder.typicode.com/users/1"
      validate:
        - actual: "${response.status_code}"
          expected: 200
          operator: "equal"
```

更多编写规范请阅读 `testcases/README.md`。  
使用 **脚手架** 可快速生成用例模板。

---

## 📊 报告

执行后会自动在 `reports/<任务目录>/html/` 下生成 HTML 报告，内含：

- 总览统计（通过率、用例分布）
- 每个用例的执行步骤、耗时、错误详情
- 步骤的输入参数与保存的变量
- 所有 API 响应均保存为 JSON 文件，可用于调试

直接在浏览器中打开 `test_report_*.html` 即可查看。

---

## ⚙️ 配置

框架全局配置位于 `config/global_config.yaml`。  
支持多环境切换：通过 `--env staging` 或设置环境变量 `ARTEMIS_ENVIRONMENT=staging`。  
敏感信息（密码、Token）请务必使用环境变量，格式为 `${ENV.VAR_NAME}`。

---

## ❓ 常见问题

**Q：如何调试用例？**  
A：使用 `--log-level DEBUG` 运行，可在终端或日志文件中看到详细的变量值、请求/响应详情。

**Q：邮件提取失败？**  
A：确认 `QQ_EMAIL`、`QQ_AUTH_CODE` 环境变量正确，QQ 邮箱需开启 IMAP 服务并使用授权码。

**Q：能否并发执行？**  
A：Windows 下受限于 multiprocessing，建议使用 `--task-name` 区分任务后分别运行。

**Q：如何添加自定义步骤处理器？**  
A：编写继承 `StepHandler` 的类，并在 `TestExecutor` 中注册即可。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。  
本项目由 **[Akira]** 创建和维护。

## 📄 许可

MIT License © 2026 Akira

---