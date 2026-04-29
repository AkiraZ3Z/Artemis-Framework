#!/usr/bin/env python3
"""
Artemis Framework - 测试用例脚手架工具
交互式生成 YAML 格式的测试用例，降低手动编写门槛
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# 确保能导入项目内模块（如果需要从配置读取默认路径等，可保留）
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 如果有特殊需要，可以使用框架内定义的状态等，但为简单独立，这里不强行依赖
try:
    from core.testcase_loader import TestCaseStatus, StepAction
except ImportError:
    # 若框架未安装，则使用简单字符串列表
    TestCaseStatus = type('Enum', (), {'DRAFT': 'draft', 'READY': 'ready', 'DISABLED': 'disabled', 'DEPRECATED': 'deprecated'})
    StepAction = type('Enum', (), {
        'API_CALL': 'api.call',
        'SQL_EXECUTE': 'sql.execute',
        'FILE_OPERATION': 'file.operation',
        'COMMAND': 'command',
        'WAIT': 'wait',
        'ASSERT': 'assert',
        'VARIABLE_SET': 'variable.set',
        'CUSTOM': 'custom'
    })


def ask(prompt: str, default: Optional[str] = None, required: bool = True) -> str:
    """询问用户输入，支持默认值和必填检查"""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    while True:
        answer = input(prompt).strip()
        if not answer:
            if default:
                return default
            if required:
                print("⚠️ 此项为必填，请输入内容。")
                continue
            else:
                return ""
        return answer


def ask_yes_no(prompt: str, default: Optional[bool] = None) -> bool:
    """询问是/否，返回布尔值"""
    if default is True:
        suffix = " [Y/n]"
    elif default is False:
        suffix = " [y/N]"
    else:
        suffix = " [y/n]"
    while True:
        ans = input(prompt + suffix).strip().lower()
        if ans in ('y', 'yes'):
            return True
        elif ans in ('n', 'no'):
            return False
        elif ans == '' and default is not None:
            return default
        else:
            print("请输入 y 或 n")


def ask_list(prompt: str, default: Optional[List] = None) -> List[str]:
    """询问用户输入列表（逗号分隔）"""
    if default:
        prompt = f"{prompt} [逗号分隔，默认: {','.join(default)}]: "
    else:
        prompt = f"{prompt} [逗号分隔，回车跳过]: "
    ans = input(prompt).strip()
    if not ans:
        return default or []
    return [item.strip() for item in ans.split(',') if item.strip()]


def ask_dict(prompt: str) -> Dict[str, Any]:
    """询问用户输入字典 (key: value) 每行一个，空行结束"""
    print(f"{prompt} (每行 key: value，空行结束):")
    result = {}
    while True:
        line = input("  > ").strip()
        if not line:
            break
        if ':' not in line:
            print("格式错误，请使用 key: value")
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip()
        # 尝试转换 value 为原始类型
        if value.lower() == 'true':
            value = True
        elif value.lower() == 'false':
            value = False
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        result[key] = value
    return result


def collect_testcase_info() -> Dict[str, Any]:
    """收集测试用例的基本信息"""
    print("\n" + "="*50)
    print("📋 测试用例基本信息")
    print("="*50)

    case_id = ask("用例ID (如 TC_LOGIN_001)")
    name = ask("用例名称", default=f"{case_id}_测试")
    description = ask("用例描述", default="", required=False)
    module = ask("所属模块", default="general")
    priority = ask("优先级 (high/medium/low)", default="medium")
    tags = ask_list("标签", default=["smoke"])
    author = ask("作者", default="Artemis")
    version = ask("版本", default="1.0.0")
    status = ask("状态", default="ready", required=False)

    return {
        "id": case_id,
        "name": name,
        "description": description,
        "module": module,
        "priority": priority,
        "tags": tags,
        "author": author,
        "version": version,
        "status": status,
    }


def collect_step(index: int) -> Dict[str, Any]:
    """收集一个测试步骤的信息"""
    print(f"\n➡️ 步骤 {index}")
    name = ask("步骤名称", default=f"step_{index}")
    print("常用动作: api.call | sql.execute | file.operation | command | wait | assert | variable.set | custom")
    action = ask("动作")
    params = ask_dict("请求参数 (如 url: /login, method: POST)")
    validate = []
    if ask_yes_no("是否添加验证条件？", default=False):
        print("请输入验证条件，每行一条，格式: actual,expected,operator (空行结束)")
        while True:
            line = input("  > ").strip()
            if not line:
                break
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 2:
                print("至少需要 actual 和 expected，请重试")
                continue
            actual = parts[0]
            expected = parts[1]
            operator = parts[2] if len(parts) > 2 else 'equal'
            validate.append({
                "actual": actual,
                "expected": expected,
                "operator": operator
            })
    save = {}
    if ask_yes_no("是否保存响应变量？", default=False):
        print("请输入变量名和提取路径，格式: var_name: response.path (空行结束)")
        while True:
            line = input("  > ").strip()
            if not line:
                break
            if ':' not in line:
                print("格式错误，请使用 var_name: path")
                continue
            var_name, _, extractor = line.partition(':')
            save[var_name.strip()] = extractor.strip()
    retry_times = int(ask("重试次数", default="0", required=False) or "0")
    retry_interval = float(ask("重试间隔(秒)", default="1.0", required=False) or "1.0")
    timeout = ask("超时时间(秒, 回车不限制)", default="", required=False)
    skip = ask_yes_no("是否跳过此步骤？", default=False)
    skip_reason = ""
    if skip:
        skip_reason = ask("跳过原因", default="临时跳过")

    return {
        "name": name,
        "action": action,
        "params": params,
        "validate": validate,
        "save": save,
        "retry_times": retry_times,
        "retry_interval": retry_interval,
        "timeout": float(timeout) if timeout else None,
        "skip": skip,
        "skip_reason": skip_reason,
    }


def collect_setup_teardown(section: str) -> List[Dict[str, Any]]:
    """收集 setup 或 teardown 动作列表"""
    items = []
    print(f"\n📌 {section} 配置")
    if not ask_yes_no(f"是否添加 {section} 步骤？", default=False):
        return items
    i = 1
    while True:
        print(f"\n⚙️ {section} 步骤 {i}")
        action = ask("动作")
        params = ask_dict("参数")
        items.append({"action": action, "params": params})
        i += 1
        if not ask_yes_no(f"继续添加 {section} 步骤？", default=False):
            break
    return items


def build_yaml(data: Dict[str, Any]) -> str:
    """将数据转换为 YAML 字符串"""
    return yaml.dump(
        {"testcase": data},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
    )


def main():
    print("\n🧪 Artemis Framework - 测试用例脚手架")
    print("按照提示输入信息，将自动生成 YAML 用例文件\n")

    # 收集基本信息
    case_data = collect_testcase_info()

    # 收集 setup
    case_data["setup"] = collect_setup_teardown("Setup")

    # 收集步骤
    steps = []
    print("\n📝 测试步骤")
    i = 1
    while True:
        step = collect_step(i)
        steps.append(step)
        i += 1
        if not ask_yes_no("是否继续添加步骤？", default=False):
            break
    case_data["steps"] = steps

    # 收集 teardown
    case_data["teardown"] = collect_setup_teardown("Teardown")

    # 确定保存路径
    default_dir = Path("testcases")
    output_dir = ask("保存目录", default=str(default_dir))
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{case_data['id']}.yaml"
    filepath = os.path.join(output_dir, filename)

    # 确认覆盖
    if os.path.exists(filepath):
        if not ask_yes_no(f"文件 {filepath} 已存在，是否覆盖？", default=False):
            print("❌ 操作取消")
            return

    # 写出文件
    yaml_content = build_yaml(case_data)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print(f"\n✅ 测试用例已生成: {filepath}")
    print("可以运行 `python run.py -t {}` 来执行它".format(filepath))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，退出。")
        sys.exit(1)