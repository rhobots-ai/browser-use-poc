import asyncio
import os
import sys
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime

# Allow running from repo without install
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

# Enable debug observability spans and detailed logging
os.environ.setdefault("LMNR_LOGGING_LEVEL", "debug")
# Enable verbose CDP logging (handled by logging_config.setup_logging)
# os.environ.setdefault("CDP_LOGGING_LEVEL", "DEBUG")

from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI
from browser_use.logging_config import setup_logging
from browser_use.custom_logging import (
    DECISION_PREFIX,
    DECISION_PREFIX_TEXT,
    BROWSER_DIMS_PREFIX,
    SELECTOR_PREFIX,
)

# Set Browser-Use logging level to DEBUG and route logs to stderr (so stdout stays clean JSON)
setup_logging(stream=sys.stderr, log_level="debug", force_setup=True)


# ---------- File logging (CSV + JSON) helpers ----------

CSV_HEADERS = ["timestamp", "level", "name", "run_id", "task_id", "session_id", "message", "pathname", "lineno"]


class LogContextFilter(logging.Filter):
    """Injects run_id, task_id, session_id into every record."""

    def __init__(self, run_id: str, session_id: str | None = None, task_id: str | None = None):
        super().__init__()
        self.run_id = run_id
        self.session_id = session_id or ""
        self.task_id = task_id or ""

    def set_session_id(self, session_id: str | None) -> None:
        self.session_id = session_id or ""

    def set_task_id(self, task_id: str | None) -> None:
        self.task_id = task_id or ""

    def filter(self, record: logging.LogRecord) -> bool:
        # Always stamp values on the record so formatters can rely on them
        record.run_id = getattr(record, "run_id", self.run_id)
        record.session_id = getattr(record, "session_id", self.session_id)
        record.task_id = getattr(record, "task_id", self.task_id)
        return True


class DecisionOnlyFilter(logging.Filter):
    """
    Allows only decision/observability lines while preserving order.
    - By logger name: browser_use.llm.decisions, browser_use.dom.mapping
    - By message prefix: DEBUG_LLM_DECISION, DEBUG_LLM_DECISION_TEXT_INPUT, Browser_dimensions, DEBUG_SELECTOR_MAP
    """
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.name in ("browser_use.llm.decisions", "browser_use.dom.mapping"):
                return True
            msg = record.getMessage()
            return (
                isinstance(msg, str)
                and (
                    msg.startswith(DECISION_PREFIX)
                    or msg.startswith(DECISION_PREFIX_TEXT)
                    or msg.startswith(BROWSER_DIMS_PREFIX)
                    or msg.startswith(SELECTOR_PREFIX)
                )
            )
        except Exception:
            return False


class CsvFormatter(logging.Formatter):
    """CSV formatter for logs using a fixed header set."""

    def __init__(self):
        super().__init__()

    @staticmethod
    def _q(value) -> str:
        s = "" if value is None else str(value)
        s = s.replace('"', '""').replace("\n", " ").replace("\r", " ")
        return f'"{s}"'

    def format(self, record: logging.LogRecord) -> str:
        # ISO 8601 with local timezone offset (e.g. 2025-09-23T11:32:59+0530)
        ts = datetime.fromtimestamp(record.created).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        msg = record.getMessage()
        row = [
            ts,
            record.levelname,
            record.name,
            getattr(record, "run_id", ""),
            getattr(record, "task_id", ""),
            getattr(record, "session_id", ""),
            msg,
            getattr(record, "pathname", ""),
            getattr(record, "lineno", ""),
        ]
        return ",".join(self._q(v) for v in row)


class JsonlFormatter(logging.Formatter):
    """JSON lines formatter (one JSON object per line) with the same fields as CSV."""

    def __init__(self):
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        payload = {
            "timestamp": ts,
            "level": record.levelname,
            "name": record.name,
            "run_id": getattr(record, "run_id", ""),
            "task_id": getattr(record, "task_id", ""),
            "session_id": getattr(record, "session_id", ""),
            "message": record.getMessage(),
            "pathname": getattr(record, "pathname", ""),
            "lineno": getattr(record, "lineno", 0),
        }
        return json.dumps(payload, ensure_ascii=False)


def _ensure_logs_dir() -> Path:
    # Create repo-root logs/ folder: examples/.. = repo root
    repo_root = Path(__file__).resolve().parent.parent
    logs_dir = repo_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _write_csv_header_once(csv_path: Path) -> None:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        csv_path.write_text(",".join(CSV_HEADERS) + "\n", encoding="utf-8")


def setup_run_file_logging(run_uuid: str, session_id: str | None = None) -> tuple[LogContextFilter, Path, Path]:
    """Create CSV and JSONL handlers bound to a run UUID, return the filter and file paths."""
    logs_dir = _ensure_logs_dir()
    csv_path = logs_dir / f"{run_uuid}.csv"
    json_path = logs_dir / f"{run_uuid}.json"

    _write_csv_header_once(csv_path)

    csv_handler = logging.FileHandler(csv_path, encoding="utf-8")
    csv_handler.setLevel(logging.DEBUG)
    csv_handler.setFormatter(CsvFormatter())

    jsonl_handler = logging.FileHandler(json_path, encoding="utf-8")
    jsonl_handler.setLevel(logging.DEBUG)
    jsonl_handler.setFormatter(JsonlFormatter())

    ctx_filter = LogContextFilter(run_id=run_uuid, session_id=session_id)
    csv_handler.addFilter(ctx_filter)
    jsonl_handler.addFilter(ctx_filter)

    # Attach to key loggers used by the project
    for logger_name in ("browser_use", "bubus"):
        lg = logging.getLogger(logger_name)
        lg.addHandler(csv_handler)
        lg.addHandler(jsonl_handler)

    return ctx_filter, csv_path, json_path


def setup_filtered_run_file_logging(run_uuid: str, session_id: str | None = None) -> tuple[LogContextFilter, Path, Path]:
    """
    Create FILTERED CSV and JSONL handlers bound to a run UUID (order-preserving, real-time).
    """
    logs_dir = _ensure_logs_dir()
    csv_path = logs_dir / f"{run_uuid}.filtered.csv"
    json_path = logs_dir / f"{run_uuid}.filtered.json"

    # filtered CSV uses same header schema as full CSV
    _write_csv_header_once(csv_path)

    # Handlers
    csv_handler = logging.FileHandler(csv_path, encoding="utf-8")
    csv_handler.setLevel(logging.DEBUG)
    csv_handler.setFormatter(CsvFormatter())

    jsonl_handler = logging.FileHandler(json_path, encoding="utf-8")
    jsonl_handler.setLevel(logging.DEBUG)
    jsonl_handler.setFormatter(JsonlFormatter())

    # Filters: context + decision-only
    ctx_filter = LogContextFilter(run_id=run_uuid, session_id=session_id)
    dec_filter = DecisionOnlyFilter()
    csv_handler.addFilter(ctx_filter)
    csv_handler.addFilter(dec_filter)
    jsonl_handler.addFilter(ctx_filter)
    jsonl_handler.addFilter(dec_filter)

    # Attach to all loggers but disable propagation for child loggers to prevent duplicates
    for logger_name in ("browser_use", "bubus", "browser_use.llm.decisions", "browser_use.dom.mapping"):
        lg = logging.getLogger(logger_name)
        lg.addHandler(csv_handler)
        lg.addHandler(jsonl_handler)
        
        # Disable propagation for child loggers to prevent duplicate logs
        if "." in logger_name:  # This identifies child loggers
            lg.propagate = False

    return ctx_filter, csv_path, json_path


def extract_python_snippets_to_file(filtered_json_path: Path, run_uuid: str) -> Path:
    """
    Extract python_code snippets from filtered JSON logs and create a .py file 
    with the specified format.
    """
    logs_dir = filtered_json_path.parent
    python_snippets_path = logs_dir / f"{run_uuid}_python_snippets.py"
    
    python_snippets = []
    
    try:
        if filtered_json_path.exists():
            with open(filtered_json_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        message = log_entry.get('message', '')
                        
                        # Look for DEBUG_LLM_DECISION or DEBUG_LLM_DECISION_TEXT_INPUT messages
                        if (message.startswith(DECISION_PREFIX) or message.startswith(DECISION_PREFIX_TEXT)):
                            # Extract JSON payload from the message
                            json_start = message.find('{')
                            if json_start != -1:
                                json_payload = message[json_start:]
                                try:
                                    payload_data = json.loads(json_payload)
                                    python_code = payload_data.get('python_code', '')
                                    if python_code and python_code.strip() != "# Execute via CDP":
                                        # Normalize snippet formatting to single-line JSON objects inside calls
                                        def _normalize_snippet(s: str) -> str:
                                            # Collapse common multi-line object patterns to single line
                                            s = s.replace("{\n", "{")
                                            s = s.replace("\n    ", " ")  # 4-space indents
                                            s = s.replace("\n  ", " ")    # 2-space indents
                                            s = s.replace("\n}", "}")
                                            return s

                                        normalized_code = _normalize_snippet(python_code)
                                        python_snippets.append({
                                            "python_code": normalized_code
                                        })
                                except json.JSONDecodeError:
                                    continue
                    except json.JSONDecodeError:
                        continue
        
        # Write the Python file with the extracted snippets in the requested format
        file_lines = ["# Auto-generated list of CDP python snippets per iteration", "json_data = ["]
        
        for i, snippet in enumerate(python_snippets):
            python_code = snippet["python_code"]
            file_lines.append("    {")
            file_lines.append('        "python_code": """' + python_code + '"""')
            if i < len(python_snippets) - 1:
                file_lines.append("    },")
            else:
                file_lines.append("    }")
        
        file_lines.append("]")
        file_lines.append("")  # Empty line at end
        
        file_content = "\n".join(file_lines)
        python_snippets_path.write_text(file_content, encoding='utf-8')
        
    except Exception as e:
        print(f"Warning: Failed to extract python snippets: {e}")
    
    return python_snippets_path


async def main():
    # Generate a UUID for this run and set up file logging
    run_uuid = uuid.uuid4().hex

    llm = ChatOpenAI(model="gpt-4.1-mini")

    profile = BrowserProfile(
        headless=False,  # set to False if you want to watch the browser
        # allowed_domains=["*.google.com", "*.github.com", "github.com", "www.google.com"],
    )
    session = BrowserSession(browser_profile=profile)

    # Initialize CSV/JSON loggers with run_uuid and session.id
    ctx_filter, csv_path, json_path = setup_run_file_logging(run_uuid=run_uuid, session_id=session.id)
    # Initialize FILTERED logs (decision-only), order-preserving
    f_ctx_filter, filtered_csv_path, filtered_json_path = setup_filtered_run_file_logging(run_uuid=run_uuid, session_id=session.id)

    # --- Task describing the flow explicitly ---
    task = (
        "Open https://angularformadd.netlify.app/, add a new routes and pricing and submit the form and close the browser"
    )

    try:
        agent = Agent(task=task, llm=llm, browser_session=session)
        # Update task_id in filter once agent is created
        try:
            ctx_filter.set_task_id(str(getattr(agent, "id", "")))
        except Exception:
            pass

        history = await agent.run(max_steps=15)

    finally:
        # Always cleanup browser
        try:
            await session.kill()
        except Exception:
            pass
        
        # Ensure logs are flushed
        logging.shutdown()
        
        # Extract python snippets from filtered logs and create .py file
        python_snippets_path = extract_python_snippets_to_file(filtered_json_path, run_uuid)
        
        # Print file paths in the same logical sequence as they are logged
        print(str(csv_path))
        print(str(json_path))
        print(str(filtered_csv_path))
        print(str(filtered_json_path))
        print(str(python_snippets_path))


if __name__ == "__main__":
    asyncio.run(main())