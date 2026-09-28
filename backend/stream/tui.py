import asyncio
import logging
from logging.handlers import RotatingFileHandler
import psutil
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Header, Footer, RichLog
from textual.reactive import reactive
import hypercorn.asyncio
from hypercorn.config import Config

from state import app_state
from api import app as quart_app

# Custom logger for the TUI
class TUILogHandler(logging.Handler):
    """Custom logging handler to send logs to the TUI."""
    def __init__(self, tui_app):
        super().__init__()
        self.tui_app: App = tui_app
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))


    def emit(self, record):
        log_entry = self.format(record)
        try:
            loop = asyncio.get_running_loop()
            # 將寫入動作安全地丟進原本的 event loop 尾端
            loop.call_soon(self.tui_app.write_log, log_entry)
        except RuntimeError:
            # 如果真的在不同的 thread (例如 asyncio.to_thread 背景)，才用 call_from_thread
            self.tui_app.call_from_thread(self.tui_app.write_log, log_entry)


# Custom Panel to display application state
class HardwarePanel(Static):
    """Panel to display hardware usage."""
    cpu = reactive(0.0)
    ram = reactive(0.0)
    ram_total = reactive(0.0)

    def on_mount(self):
        self.set_interval(1.0, self.update_stats)

    def update_stats(self):
        self.cpu = psutil.cpu_percent()
        self.ram = psutil.virtual_memory().used / (1024 ** 3)
        self.ram_total = psutil.virtual_memory().total / (1024 ** 3)
    
    def render(self):
        return (
            f"CPU Usage: {self.cpu} %\n\n"
            f"Memory Usage: {self.ram:.2f} / {self.ram_total:.2f} GB"
        )
    
class DataPanel(Static):
    """Panel to display current session and client count."""

    def on_mount(self):
        self.set_interval(1.0, self.refresh)

    def _format_time(self, dt: datetime | None) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "N/A"
    
    def render(self):
        s = app_state
        return (
            f"Current Session: {s.current_session}\n"
            f"Last WSS Update: {self._format_time(s.last_wss_update)}\n"
            f"Last Path Time: {self._format_time(s.last_path_time)}\n"
            f"Connected Clients: {s.client_count}"
        )

class APIDashboard(App):
    
    CSS = """
    Screen {
        layout: horizontal;
    }
    
    #left_column {
        width: 40%;
        height: 100%;
        border-right: solid green;
    }
    
    #right_column {
        width: 60%;
        height: 100%;
    }
    
    HardwarePanel {
        height: 30%;
        border: solid dodgerblue;
        padding: 1 2;
        content-align: left middle;
        border-title-color: cyan;
    }

    DataPanel {
        height: 70%;
        border: solid dodgerblue;
        padding: 1 2;
        content-align: left middle;
    }
    """

    BINDINGS = [("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            with Vertical(id="left_column"):
                hw = HardwarePanel()
                hw.border_title = "Hardware Usage"
                yield hw

                da = DataPanel()
                da.border_title = "Application State"
                yield da

            with Vertical(id="right_column"):
                self.log_view = RichLog(id="log_view", highlight=True, wrap=True, markup=True)
                yield self.log_view

        yield Footer()

    async def run_server(self):
        """Run the Quart server in the background."""
        config = Config()
        config.bind = ["127.0.0.1:5000"]
        
        root_logger = logging.getLogger()
        config.accesslog = root_logger
        config.errorlog = root_logger

        class IgnoreAppPutFilter(logging.Filter):
            def filter(self, record):
                if record.exc_info:
                    exc_type, exc_value, exc_tb = record.exc_info
                    if exc_value and "'HTTPStream' object has no attribute 'app_put'" in str(exc_value):
                        return False
                return True
                
        root_logger.addFilter(IgnoreAppPutFilter())

        try:
            await hypercorn.asyncio.serve(quart_app, config)
        except Exception as e:
            self.write_log(f"Error running server: {e}")


    async def on_mount(self) -> None:
        """Start the Quart server and set up logging when the TUI mounts."""

        # Logger setup
        root_logger = logging.getLogger()
        root_logger.addHandler(TUILogHandler(self))
        root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, logging.StreamHandler)]

        file_handler = RotatingFileHandler(
            'app.log', 
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=3,          # 3 backup files
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s'
        ))
        root_logger.addHandler(file_handler)

        self.server_task = asyncio.create_task(self.run_server())
        self.write_log("✅ Dashboard and API server started !")

    def write_log(self, message: str) -> None:
        """Write a log message to the TUI."""
        self.log_view.write(message)

    def action_quit_app(self) -> None:
        """Action to quit the application."""
        if hasattr(self, 'server_task'):
            self.server_task.cancel()
        self.exit()

if __name__ == "__main__":
    app = APIDashboard()
    app.run()