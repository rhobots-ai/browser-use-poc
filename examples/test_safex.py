import asyncio
import os
import sys
import json

# Allow running from repo without install
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI


async def main():
    llm = ChatOpenAI(model="gpt-4.1-mini")

    profile = BrowserProfile(
        headless=False,  # set to False if you want to watch the browser
        # allowed_domains=["*.google.com", "*.github.com", "github.com", "www.google.com"],
    )
    session = BrowserSession(browser_profile=profile)

    # --- Task describing the flow explicitly ---
    task = (
        "Open https://angularformadd.netlify.app/, add a new routes and pricing and submit the form and close the browser"
    )

    try:
        agent = Agent(task=task, llm=llm, browser_session=session)
        history = await agent.run(max_steps=15)

        # Build and print structured JSON trace similar to the requested schema
        def _parse_json_value(value):
            try:
                return json.loads(value) if isinstance(value, str) else value
            except Exception:
                return value

        trace_obj = agent.get_trace_object()
        t = trace_obj.get("trace", {}) or {}
        td = trace_obj.get("trace_details", {}) or {}

        # Normalize action history to a list of action names per step (to match example schema)
        action_history_raw = _parse_json_value(t.get("action_history_truncated"))
        def _step_to_names(step):
            if step is None:
                return None
            names = []
            for action in step:
                if isinstance(action, dict) and len(action) > 0:
                    names.append(next(iter(action.keys())))
                else:
                    names.append(str(action))
            return names
        action_history_names = [_step_to_names(step) for step in action_history_raw] if action_history_raw else None

        output = {
            "trace": {
                "model": t.get("model"),
                "task_id": t.get("task_id"),
                "task_truncated": t.get("task_truncated"),
                "action_history_truncated": action_history_names,
                "action_errors": _parse_json_value(t.get("action_errors")),
                "urls": _parse_json_value(t.get("urls")),
                "self_report_completed": t.get("self_report_completed"),
                "self_report_success": t.get("self_report_success"),
                "duration": t.get("duration"),
                "steps_taken": t.get("steps_taken"),
            },
            "trace_details": {
                "task": td.get("task"),
                "final_result_response": td.get("final_result_response"),
                "complete_history": _parse_json_value(td.get("complete_history")),
            },
        }
        print(json.dumps(output, ensure_ascii=False))
    finally:
        # Always cleanup browser
        try:
            await session.kill()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
