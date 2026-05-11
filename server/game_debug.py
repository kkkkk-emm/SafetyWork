def debug_print(enabled: bool, message: str) -> None:
    """在调试开关启用时输出 debug_print 相关日志。"""
    if enabled:
        print(message)
