class AppState:
    def __init__(self):
        self.current_station: dict | None = None
        self.is_muted: bool = False
        self.volume: int = 70
