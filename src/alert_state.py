"""
OpenInk Alert State Manager
===========================
管理即时通知 / 紧急提醒的状态、有效时间与哈希标识。
"""

import time


class AlertState:
    def __init__(self):
        self.active: bool = False
        self.title: str = ""
        self.text: str = ""
        self.sender: str = ""
        self.duration_min: int = 15
        self.created_at: float = 0
        self.expire_at: float = 0

    def set_alert(self, title: str, text: str, sender: str = "OpenInk", duration_min: int = 15):
        self.active = True
        self.title = title
        self.text = text
        self.sender = sender
        self.duration_min = duration_min
        self.created_at = time.time()
        self.expire_at = self.created_at + duration_min * 60

    def dismiss(self):
        self.active = False

    def is_expired(self) -> bool:
        if not self.active:
            return True
        return time.time() >= self.expire_at


alert_state = AlertState()
