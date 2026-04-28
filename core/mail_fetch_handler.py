"""
Artemis Framework - 邮箱验证码获取步骤处理器
配合 mail_fetcher 工具，可在 YAML 步骤中通过 action: mail.fetch 自动拉取验证码
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING

from .testcase_executor import TestStatus, StepHandler, TestStep, ExecutionContext

if TYPE_CHECKING:
    from .logger import CaseLogger

from .tools.mail_fetcher import MailFetcher


class MailFetchHandler(StepHandler):
    """邮件验证码获取处理器"""

    def can_handle(self, action: str) -> bool:
        return action == "mail.fetch"

    def execute(self, step: TestStep, context: ExecutionContext,
                case_logger: Optional["CaseLogger"] = None) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        try:
            # 解析参数（支持变量引用）
            params = step.params
            email_addr = params.get("email_address") or context.get_variable("email_address")
            auth_code = params.get("auth_code") or context.get_variable("auth_code")
            timeout = params.get("timeout", 120)
            sender_filter = params.get("sender_filter", "ReqRes")

            if not email_addr or not auth_code:
                return TestStatus.ERROR, None, {}, "缺少邮箱地址或授权码"

            fetcher = MailFetcher(email_addr, auth_code, logger=case_logger)
            code = fetcher.fetch_verification_code(sender_filter=sender_filter,
                                                   timeout_seconds=timeout)
            if code:
                # 保存到上下文和步骤结果中
                saved = {"verification_code": code}
                context.set_variable("verification_code", code)
                return TestStatus.PASS, code, saved, None
            else:
                return TestStatus.FAIL, None, {}, "在超时时间内未获取到验证码"

        except Exception as e:
            error_msg = f"邮件获取异常: {str(e)}"
            if case_logger:
                case_logger.error(error_msg)
            return TestStatus.ERROR, None, {}, error_msg