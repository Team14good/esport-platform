"""notifications 的資料表、schema 與列舉。"""

from enum import StrEnum


class DeliveryStatus(StrEnum):
    """Email 寄送狀態：待寄、已寄出、失敗。"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
