# Custom Logging Changes Documentation

This document outlines all the custom logging changes implemented in the browser-use project to enhance debugging and observability.

## Overview

Custom logging functionality has been added across multiple components to provide better visibility into:
- LLM decision-making processes with structured output
- DOM element selector mappings 
- CDP (Chrome DevTools Protocol) calls
- Browser viewport/screen metrics
- User action execution flows

## 1. New Custom Logging Module

**File**: `browser_use/custom_logging.py` (New file - 414 lines)

### Key Functions:

#### 1.1 `log_debug_llm_decision(structured_output, selector_map_str=None)`
- **Purpose**: Logs LLM decisions with structured output and optional DOM selector mapping
- **Lines**: 74-106
- **Emits**: `DEBUG_LLM_DECISION` prefixed JSON with thinking, actions, and DOM mappings

#### 1.2 `log_debug_llm_decision_cdp(calls)`  
- **Purpose**: Logs CDP calls with generated Python code snippets
- **Lines**: 108-123
- **Emits**: `DEBUG_LLM_DECISION_TEXT_INPUT` with CDP calls and executable Python code

#### 1.3 `log_browser_dimensions(browser_session)`
- **Purpose**: Logs comprehensive browser viewport and screen metrics
- **Lines**: 126-159
- **Emits**: `Browser_dimensions` JSON with window dimensions, device pixel ratio, screen info

#### 1.4 `build_selector_map_for_log(selector_map, max_items=200)`
- **Purpose**: Creates pretty-printed selector map for DOM indexing transparency
- **Lines**: 29-71
- **Returns**: Formatted string with `DEBUG_SELECTOR_MAP` prefix

#### 1.5 `log_action_cdp_calls(action_name, params, browser_session, click_metadata=None)`
- **Purpose**: Synthesizes CDP calls for various browser actions
- **Lines**: 204-414
- **Supports**: search, go_to_url, click_element_by_index, input_text, scroll, send_keys, etc.

## 2. Tools Service Integration

**File**: `browser_use/tools/service.py`

### Import Changes:
```python
# Line 16
from browser_use.custom_logging import log_action_cdp_calls
```

### Function Call Integration:
Custom logging calls have been added to all major action handlers:

- **Line 154**: `log_action_cdp_calls("search", params.model_dump(), browser_session)`
- **Line 174**: `log_action_cdp_calls("go_to_url", params.model_dump(), browser_session)`  
- **Line 218**: `log_action_cdp_calls("go_back", {}, browser_session)`
- **Line 269**: `log_action_cdp_calls("click_element_by_index", params.model_dump(), browser_session, click_metadata)`
- **Line 339**: `log_action_cdp_calls("input_text", params.model_dump(), browser_session)`
- **Line 507**: `log_action_cdp_calls("upload_file_to_element", params.model_dump(), browser_session)`
- **Line 531**: `log_action_cdp_calls("switch_tab", params.model_dump(), browser_session)`
- **Line 556**: `log_action_cdp_calls("close_tab", params.model_dump(), browser_session)`
- **Line 819**: `log_action_cdp_calls("scroll", params.model_dump(), browser_session)`
- **Line 840**: `log_action_cdp_calls("send_keys", params.model_dump(), browser_session)`
- **Line 862**: `log_action_cdp_calls("scroll_to_text", {"text": text}, browser_session)`
- **Line 898**: `log_action_cdp_calls("get_dropdown_options", params.model_dump(), browser_session)`
- **Line 927**: `log_action_cdp_calls("select_dropdown_option", params.model_dump(), browser_session)`
- **Line 1072**: `log_action_cdp_calls("execute_js", {"code": code}, browser_session)`

## 3. Watchdog Integration  

**File**: `browser_use/browser/watchdogs/default_action_watchdog.py`

### Import Changes:
```python
# Lines 25-27
from browser_use.custom_logging import (
    log_abspos_focus_click as cl_log_abspos_focus_click,
)
```

### Function Call Integration:
- **Line 1047**: `cl_log_abspos_focus_click(cdp_session.target_id, element_node.backend_node_id, center_x, center_y, modifiers=0)`

This logs absolute position click events with target ID, backend node ID, and coordinates.

## 4. Agent Service Integration

**File**: `browser_use/agent/service.py`

### Import Changes:
```python
# Lines 63-67  
from browser_use.custom_logging import (
    build_selector_map_for_log as cl_build_selector_map_for_log,
    log_debug_llm_decision as cl_log_debug_llm_decision,
    log_browser_dimensions as cl_log_browser_dimensions,
)
```

### Function Call Integration:

#### 4.1 DEBUG_SELECTOR_MAP Logging
- **Line 710**: `self._last_selector_map_str = cl_build_selector_map_for_log(browser_state_summary.dom_state.selector_map)`
- **Purpose**: Builds selector map string during step preparation for later use in LLM decision logging

#### 4.2 LLM Decision Logging  
- **Line 1209**: `cl_log_debug_llm_decision(parsed, selector_map_str=self._last_selector_map_str)`
- **Purpose**: Logs LLM decisions with structured output and DOM selector map after getting model output

#### 4.3 Browser Dimensions Logging
- **Line 1777**: `await cl_log_browser_dimensions(self.browser_session)`  
- **Purpose**: Logs browser viewport/screen metrics during action execution

## 5. Logging Prefixes and Format

The custom logging system uses standardized prefixes for easy filtering:

- `DEBUG_LLM_DECISION`: LLM decision outputs with actions and thinking
- `DEBUG_LLM_DECISION_TEXT_INPUT`: CDP calls with Python code snippets  
- `DEBUG_SELECTOR_MAP`: DOM element selector mappings
- `Browser_dimensions`: Browser viewport and screen metrics

## 6. Benefits

1. **Enhanced Debugging**: Detailed logs of LLM decisions and browser interactions
2. **Reproducibility**: CDP calls logged with executable Python code
3. **DOM Transparency**: Clear mapping between element indices and actual DOM elements
4. **Performance Monitoring**: Browser metrics for viewport and screen analysis
5. **Action Traceability**: Complete audit trail of all browser actions with parameters

## 7. Usage

The logging system automatically activates when actions are executed. Logs can be filtered using the prefixes:

```bash
# Filter LLM decisions
grep "DEBUG_LLM_DECISION" logs/agent.log

# Filter DOM selector mappings  
grep "DEBUG_SELECTOR_MAP" logs/agent.log

# Filter browser dimensions
grep "Browser_dimensions" logs/agent.log
```

## 8. Test Files and Examples

### 8.1 SafeX Test (`test_safex.py`)

**File**: `examples/test_safex.py`

A comprehensive test file that demonstrates the custom logging functionality with structured logging to CSV and JSON formats.

**Features:**
- Generates run-specific UUID for log organization
- Creates both full and filtered logs
- Extracts Python CDP snippets automatically
- Supports multiple log formats (CSV, JSON, JSONL)

**Command to run:**
```bash
uv run python examples/test_safex.py
```

### 8.2 CDP Replay (`cdp_replay.py`)

**File**: `examples/cdp_replay.py` 

A CDP replay system that can execute recorded browser actions from the Python snippets generated by the logging system.

**Features:**
- Loads CDP commands from extracted Python snippet files
- Executes commands in sequence with proper error handling
- Fixes CDP code structure automatically
- Supports comprehensive browser automation replay

**Command to run:**
```bash
python examples/cdp_replay.py logs/a94d0e4c38a34fa492f3b71ae2cacbe9_python_snippets.py
```

## 9. Environment Setup

### Activate Environment
```bash
source browser-use/bin/activate.fish
```

## 10. Log Storage Directory

All logs are stored in the `logs/` directory at the project root with the following structure:

### Log File Types:

1. **Normal Logs**: `logs/{run_uuid}.csv` and `logs/{run_uuid}.json`
   - Contains all logging output from the browser-use execution
   - Includes debug messages, info logs, errors, and custom logging entries

2. **Filtered Logs**: `logs/{run_uuid}.filtered.csv` and `logs/{run_uuid}.filtered.json`
   - Contains only decision-making and observability logs
   - Filters for: DEBUG_LLM_DECISION, DEBUG_LLM_DECISION_TEXT_INPUT, Browser_dimensions, DEBUG_SELECTOR_MAP
   - Ideal for analyzing agent decision flows

3. **Python Snippets**: `logs/{run_uuid}_python_snippets.py`
   - Extracted executable Python CDP commands from the filtered logs
   - Ready-to-use format for replay via `cdp_replay.py`
   - Contains normalized CDP calls as structured data

### Example Log Files:
```
logs/
├── a94d0e4c38a34fa492f3b71ae2cacbe9.csv              # Full logs (CSV)
├── a94d0e4c38a34fa492f3b71ae2cacbe9.json             # Full logs (JSON)
├── a94d0e4c38a34fa492f3b71ae2cacbe9.filtered.csv     # Filtered logs (CSV) 
├── a94d0e4c38a34fa492f3b71ae2cacbe9.filtered.json    # Filtered logs (JSON)
└── a94d0e4c38a34fa492f3b71ae2cacbe9_python_snippets.py # Extracted CDP commands
```

This comprehensive logging system provides unprecedented visibility into browser-use agent execution, making debugging and analysis significantly easier while enabling powerful replay capabilities for testing and automation workflows.
