class GsRequestError(RuntimeError):

    def __init__(self, error_code: str) -> None:
        """保存 GsRequestError.__init__ 相关的 GS 业务错误码。"""
        super().__init__(error_code)
        self.error_code = error_code
