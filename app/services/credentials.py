from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.errors import AppError


class CredentialCipher:
    """Encrypt third-party credentials before they reach SQLite."""

    def __init__(self, secret: str) -> None:
        self._secret = secret.strip()

    @property
    def configured(self) -> bool:
        return len(self._secret) >= 24

    def _fernet(self) -> Fernet:
        if not self.configured:
            raise AppError(
                "CREDENTIAL_STORAGE_NOT_CONFIGURED",
                "服务器尚未配置凭证加密密钥，暂时不能保存个人令牌。",
                status_code=503,
            )
        digest = hashlib.sha256(
            ("yicheng-credential-v1\0" + self._secret).encode("utf-8")
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        value = plaintext.strip()
        if not value:
            raise AppError(
                "EMPTY_CREDENTIAL",
                "个人访问令牌不能为空。",
                status_code=422,
            )
        return self._fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet().decrypt(
                ciphertext.encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise AppError(
                "CREDENTIAL_DECRYPT_FAILED",
                "已保存的杭电助手凭证无法读取，请重新连接。",
                status_code=409,
            ) from exc
