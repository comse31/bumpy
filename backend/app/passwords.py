"""Хэширование паролей игроков.

Пароли никогда не хранятся в открытом виде: в БД лежат соль, число итераций и
хэш PBKDF2-HMAC-SHA256 (модуль hashlib из стандартной библиотеки — сторонних
зависимостей не нужно).

Параметры итераций берутся из config.yml (api.password_iterations), поэтому
их можно поднять без правки кода: у каждой записи своё значение, старые хэши
продолжают проверяться.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Длина соли в байтах и минимальная длина пароля.
SALT_BYTES = 16
MIN_PASSWORD_LEN = 4
# Верхняя граница длины: ограничивает работу хэширования от «гигантских» тел.
MAX_PASSWORD_LEN = 128
# Разрешённые символы пароля — те же, что в поле ввода игры (латиница, цифры,
# пробел и - _ .), чтобы клиент и сервер не расходились в валидации.
PASSWORD_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " -_."
)


class PasswordError(ValueError):
    """Пароль не соответствует требованиям."""


def validate(password: str) -> str:
    """Проверить пароль и вернуть его без изменений (кроме trim)."""
    if not isinstance(password, str):
        raise PasswordError("пароль должен быть строкой")
    # пробелы по краям не считаем значимыми: их легко набрать случайно
    value = password.strip()
    if len(value) < MIN_PASSWORD_LEN:
        raise PasswordError(f"пароль слишком короткий (минимум {MIN_PASSWORD_LEN} символа)")
    if len(value) > MAX_PASSWORD_LEN:
        raise PasswordError(f"пароль слишком длинный (максимум {MAX_PASSWORD_LEN} символов)")
    if any(ch not in PASSWORD_CHARS for ch in value):
        raise PasswordError("пароль: допустимы латиница, цифры, пробел, точка, дефис и подчёркивание")
    return value


def hash_password(password: str, iterations: int) -> tuple[str, str, int]:
    """Вернуть (hash_hex, salt_hex, iterations) для нового пароля."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex(), salt.hex(), iterations


def verify_password(password: str, hash_hex: str | None, salt_hex: str | None, iterations: int | None) -> bool:
    """Сравнить пароль с сохранённым хэшем за постоянное время.

    False, если хэш/соль отсутствуют (у имени ещё не было пароля) или данные
    повреждены. Сравнение через hmac.compare_digest исключает атаку по времени.
    """
    if not hash_hex or not salt_hex or not iterations:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(digest, expected)
