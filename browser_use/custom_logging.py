import json
import logging
from typing import Any

# Centralized prefixes
DECISION_PREFIX = "DEBUG_LLM_DECISION "
DECISION_PREFIX_TEXT = "DEBUG_LLM_DECISION_TEXT_INPUT "
BROWSER_DIMS_PREFIX = "Browser_dimensions"
SELECTOR_PREFIX = "DEBUG_SELECTOR_MAP"


def cdp_calls_snippet(calls: list[dict]) -> str:
    lines = ["# Execute via CDP"]
    for entry in calls or []:
        try:
            domain_method, params = next(iter(entry.items()))
            # Pretty-print params to match expected multi-line formatting
            params_json = json.dumps(params, ensure_ascii=False, indent=2)
            # This yields:
            # await cdp_session.cdp_client.send.DOM.method({
            #   "key": "value"
            # })
            lines.append(f"await cdp_session.cdp_client.send.{domain_method}({params_json})")
        except Exception:
            lines.append(f"# {entry!r}")
    return "\n".join(lines)


def build_selector_map_for_log(selector_map: dict[int, Any], max_items: int = 200) -> str | None:
    """
    Pretty-printed selector-map for DOM indexing transparency.
    Ensures the returned string starts with the SELECTOR_PREFIX so filters match.
    """
    try:
        if not selector_map:
            return None
        items = sorted(selector_map.items(), key=lambda kv: kv[0])
        total = len(items)
        limited = items[: max_items if max_items and max_items > 0 else total]

        lines: list[str] = []
        lines.append(f"{SELECTOR_PREFIX} selector_map: dict[int, EnhancedDOMTreeNode] = {{")
        for idx, node in limited:
            try:
                element_index = getattr(node, "element_index", None)
                backend_node_id = getattr(node, "backend_node_id", None)
                node_id = getattr(node, "node_id", None)
                session_id = getattr(node, "session_id", None)
                target_id = getattr(node, "target_id", None)
                tag_name = getattr(node, "tag_name", None)
                frame_id = getattr(node, "frame_id", None)
                attributes = getattr(node, "attributes", {}) or {}
                lines.append(f"  {idx}: EnhancedDOMTreeNode(")
                lines.append(f"    element_index={element_index},")
                lines.append(f"    backend_node_id={backend_node_id},")
                lines.append(f"    node_id={node_id},")
                lines.append(f'    session_id="{session_id}",')
                lines.append(f'    target_id="{target_id}",')
                lines.append(f'    tag_name="{tag_name}",')
                lines.append(f'    frame_id="{frame_id}",')
                lines.append(f"    attributes={json.dumps(attributes, ensure_ascii=False)},")
                lines.append("  ),")
            except Exception:
                # Fallback to raw repr
                lines.append(f"  {idx}: {repr(node)},")
        if total > len(limited):
            lines.append(f"  ... (truncated; total {total} elements)")
        lines.append("}")
        return "\n".join(lines)
    except Exception:
        return None


def log_debug_llm_decision(structured_output: Any, selector_map_str: str | None = None) -> None:
    """
    Emit DEBUG_LLM_DECISION with structured output and optional mapping.
    Also emits DEBUG_SELECTOR_MAP line when selector_map_str is provided.
    """
    try:
        decisions_logger = logging.getLogger("browser_use.llm.decisions")
        browser_logger = logging.getLogger("browser_use")

        actions = getattr(structured_output, "action", []) or []
        payload = {
            "text_format_sent_to_llm": None,  # optional: caller may add separately if needed
            "structured_llm_output": {
                "thinking": getattr(structured_output, "thinking", None),
                "action": [
                    a.model_dump(exclude_unset=True) if hasattr(a, "model_dump") else str(a)
                    for a in actions
                ],
            },
        }
        if selector_map_str:
            payload["index_to_dom_node_mapping"] = selector_map_str

        message = DECISION_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2)
        decisions_logger.debug(message)

        # Emit selector map as standalone searchable line
        if selector_map_str:
            mapping_logger = logging.getLogger("browser_use.dom.mapping")
            mapping_logger.debug(selector_map_str)
    except Exception as e:
        logging.getLogger("browser_use").debug(f"[CUSTOM_LOG] Failed to log debug LLM decision: {e}")


def log_debug_llm_decision_cdp(calls: list[dict]) -> None:
    """
    Emit DEBUG_LLM_DECISION_TEXT_INPUT with CDP calls and python_code snippet.
    """
    try:
        decisions_logger = logging.getLogger("browser_use.llm.decisions")
        browser_logger = logging.getLogger("browser_use")

        payload = {
            "final_cdp_call_executed": calls or [],
            "python_code": cdp_calls_snippet(calls or []),
        }
        message = DECISION_PREFIX_TEXT + json.dumps(payload, ensure_ascii=False, indent=2)
        decisions_logger.debug(message)
    except Exception as e:
        logging.getLogger("browser_use").debug(f"[CUSTOM_LOG] Failed to log debug LLM decision CDP: {e}")


async def log_browser_dimensions(browser_session: Any) -> None:
    """
    Emit Browser_dimensions JSON string to map viewport and screen metrics.
    """
    try:
        decisions_logger = logging.getLogger("browser_use.llm.decisions")
        browser_logger = logging.getLogger("browser_use")

        # Avoid changing focus: get or reuse session without forcing focus switch
        cdp_session = await browser_session.get_or_create_cdp_session(target_id=None, focus=False)
        js = (
            "JSON.stringify({"
            "innerWidth: window.innerWidth,"
            "innerHeight: window.innerHeight,"
            "outerWidth: window.outerWidth,"
            "outerHeight: window.outerHeight,"
            "devicePixelRatio: window.devicePixelRatio,"
            "screenWidth: screen.width,"
            "screenHeight: screen.height,"
            "availWidth: screen.availWidth,"
            "availHeight: screen.availHeight,"
            "visualViewportWidth: (window.visualViewport && window.visualViewport.width) || null,"
            "visualViewportHeight: (window.visualViewport && window.visualViewport.height) || null"
            "})"
        )
        res = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": js}, session_id=cdp_session.session_id
        )
        val = (res.get("result", {}) or {}).get("value")
        if isinstance(val, str):
            message = BROWSER_DIMS_PREFIX + " " + val
            decisions_logger.debug(message)
    except Exception as e:
        logging.getLogger("browser_use").debug(f"[CUSTOM_LOG] Failed to log browser dimensions: {e}")


def log_abspos_focus_click(
    target_id: str,
    backend_node_id: int,
    center_x: float,
    center_y: float,
    modifiers: int = 0,
) -> None:
    """
    Emit a fixed-format CDP payload for absolute_position click focusing that matches the expected DEBUG_LLM_DECISION_TEXT_INPUT format.
    This is logging-only and does not affect runtime behavior.
    """
    try:
        calls: list[dict] = [
            {"Target.activateTarget": {"targetId": target_id}},
            {"Target.activateTarget": {"targetId": target_id}},
            {"DOM.getContentQuads": {"backendNodeId": backend_node_id}},
            {"DOM.scrollIntoViewIfNeeded": {"backendNodeId": backend_node_id}},
            {"Input.dispatchMouseEvent": {"type": "mouseMoved", "x": center_x, "y": center_y}},
            {
                "Input.dispatchMouseEvent": {
                    "type": "mousePressed",
                    "x": center_x,
                    "y": center_y,
                    "button": "left",
                    "clickCount": 1,
                    "modifiers": modifiers,
                }
            },
            {
                "Input.dispatchMouseEvent": {
                    "type": "mouseReleased",
                    "x": center_x,
                    "y": center_y,
                    "button": "left",
                    "clickCount": 1,
                    "modifiers": modifiers,
                }
            },
        ]
        log_debug_llm_decision_cdp(calls)
    except Exception as e:
        logging.getLogger("browser_use").debug(f"[CUSTOM_LOG] Failed to log abspos focus click: {e}")


def log_action_cdp_calls(action_name: str, params: dict, browser_session: Any) -> None:
    """
    Synthesize and log CDP calls for a given action.
    This provides a fallback for actions that don't return CDP debug info natively.
    """
    try:
        calls = []
        _params_dict = params if isinstance(params, dict) else {}

        try:
            target_id = (
                browser_session.agent_focus.target_id
                if browser_session and browser_session.agent_focus
                else ""
            )
        except Exception:
            target_id = ""

        if action_name == "search":
            query = _params_dict.get("query")
            search_engine = _params_dict.get("search_engine", "duckduckgo")
            search_urls = {
                'duckduckgo': f'https://duckduckgo.com/?q={query}',
                'google': f'https://www.google.com/search?q={query}&udm=14',
                'bing': f'https://www.bing.com/search?q={query}',
            }
            url_val = search_urls.get(search_engine.lower(), search_urls['duckduckgo'])
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"Page.navigate": {"url": url_val, "transitionType": "address_bar"}},
            ]

        elif action_name == "go_to_url":
            url_val = _params_dict.get("url")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"Page.navigate": {"url": url_val, "transitionType": "address_bar"}},
            ]

        elif action_name == "go_back":
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"Page.goBack": {}},
            ]

        elif action_name == "click_element_by_index":
            index = _params_dict.get("index")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"DOM.getDocument": {}},
                {"DOM.querySelector": {"selector": f'[data-index="{index}"]'}},
                {"Input.dispatchMouseEvent": {"type": "mousePressed", "button": "left", "clickCount": 1}},
                {"Input.dispatchMouseEvent": {"type": "mouseReleased", "button": "left", "clickCount": 1}},
            ]

        elif action_name == "input_text":
            text_val = _params_dict.get("text")
            index = _params_dict.get("index")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"DOM.querySelector": {"selector": f'[data-index="{index}"]'}},
                {"Input.insertText": {"text": text_val}},
            ]

        elif action_name == "upload_file_to_element":
            file_path = _params_dict.get("path")
            index = _params_dict.get("index")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"DOM.querySelector": {"selector": f'[data-index="{index}"]'}},
                {"DOM.setFileInputFiles": {"files": [file_path]}},
            ]

        elif action_name == "switch_tab":
            tab_id = _params_dict.get("tab_id")
            calls = [
                {"Target.activateTarget": {"targetId": tab_id}},
            ]

        elif action_name == "close_tab":
            tab_id = _params_dict.get("tab_id")
            calls = [
                {"Target.closeTarget": {"targetId": tab_id}},
            ]

        elif action_name == "scroll":
            down = _params_dict.get("down", True)
            num_pages = _params_dict.get("num_pages", 1.0)
            frame_element_index = _params_dict.get("frame_element_index")
            scroll_delta = int(num_pages * 1000)  # Approximate pixels
            if not down:
                scroll_delta = -scroll_delta
            
            if frame_element_index:
                calls = [
                    {"Target.activateTarget": {"targetId": target_id}},
                    {"DOM.querySelector": {"selector": f'[data-index="{frame_element_index}"]'}},
                    {"Input.dispatchMouseEvent": {"type": "mouseWheel", "deltaY": scroll_delta}},
                ]
            else:
                calls = [
                    {"Target.activateTarget": {"targetId": target_id}},
                    {"Input.dispatchMouseEvent": {"type": "mouseWheel", "deltaY": scroll_delta}},
                ]

        elif action_name == "send_keys":
            keys_val = _params_dict.get("keys")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"Input.dispatchKeyEvent": {"type": "rawKeyDown", "key": keys_val}},
                {"Input.dispatchKeyEvent": {"type": "keyUp", "key": keys_val}},
            ]

        elif action_name == "scroll_to_text":
            text = _params_dict.get("text")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"Runtime.evaluate": {"expression": f"window.find('{text}')"}},
                {"DOM.scrollIntoViewIfNeeded": {}},
            ]

        elif action_name == "get_dropdown_options":
            index = _params_dict.get("index")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"DOM.querySelector": {"selector": f'[data-index="{index}"]'}},
                {"DOM.getAttributes": {}},
            ]

        elif action_name == "select_dropdown_option":
            index = _params_dict.get("index")
            text = _params_dict.get("text")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"DOM.querySelector": {"selector": f'[data-index="{index}"]'}},
                {"DOM.querySelector": {"selector": f'option[text="{text}"]'}},
                {"Input.dispatchMouseEvent": {"type": "mousePressed", "button": "left", "clickCount": 1}},
                {"Input.dispatchMouseEvent": {"type": "mouseReleased", "button": "left", "clickCount": 1}},
            ]

        elif action_name == "execute_js":
            code = _params_dict.get("code", "")
            calls = [
                {"Target.activateTarget": {"targetId": target_id}},
                {"Runtime.evaluate": {"expression": code, "returnByValue": True, "awaitPromise": True}},
            ]

        if calls:
            # Log with DEBUG_LLM_DECISION prefix instead of DEBUG_LLM_DECISION_TEXT_INPUT
            try:
                decisions_logger = logging.getLogger("browser_use.llm.decisions")
                payload = {
                    "final_cdp_call_executed": calls,
                    "python_code": cdp_calls_snippet(calls),
                }
                message = DECISION_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2)
                decisions_logger.debug(message)
            except Exception as e:
                logging.getLogger("browser_use").debug(f"[CUSTOM_LOG] Failed to log action CDP calls with DEBUG_LLM_DECISION prefix: {e}")

    except Exception as e:
        logging.getLogger("browser_use").debug(f"[CUSTOM_LOG] Failed to log action CDP calls: {e}")