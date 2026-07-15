class DomainError(Exception):
    """领域异常基类，用于区分业务错误和系统错误。"""


class NotFoundError(DomainError):
    """请求的业务对象不存在，或者当前用户无权查看该对象。"""


class AuthenticationError(DomainError):
    """Mall 登录态缺失或已失效。"""


class PermissionDeniedError(DomainError):
    """当前 Mall 用户无权执行该操作。"""
