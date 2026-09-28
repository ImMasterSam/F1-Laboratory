from datetime import datetime

class AppState:
    def __init__(self):
        self.current_session: str = "Unknown"
        self.last_wss_update: datetime | None = None
        self.last_path_time: datetime | None = None
        self.client_count: int = 0

app_state = AppState()