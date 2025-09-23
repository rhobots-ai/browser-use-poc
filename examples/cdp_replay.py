"""
Complete CDP replay test using browser-use internal functions and imports.

This script demonstrates how to parse comprehensive JSON data containing multiple
Python CDP commands and execute them sequentially using browser-use's BrowserSession 
and CDP client functionality.

To run this:
1. Ensure Chrome is running with remote debugging: 
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
2. Run: python test_cdp_complete.py <json_data_file.py>
   Example: uv python test_cdp_complete.py ../../logs/ca9bd18150884cfea0ba3c50e5c285b1_python_code.py
"""

import asyncio
import json
import os
import sys
import re
import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

# Add the project root to Python path to import browser_use
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from browser_use.browser import BrowserSession, BrowserProfile
from browser_use.browser.events import BrowserStartEvent


async def execute_dynamic_cdp_code(browser_session, cdp_session, python_code: str, step_index: int):
    """Execute Python CDP code dynamically with proper context."""
    print(f"🔧 Step {step_index + 1}: Executing dynamic code...")
    print(f"Code preview: {python_code[:100]}{'...' if len(python_code) > 100 else ''}")
    
    # Create execution context with necessary variables
    mock_self = SimpleNamespace()
    mock_self.agent_focus = browser_session.agent_focus
    mock_self.browser_session = browser_session
    
    exec_globals = {
        '__builtins__': __builtins__,
        'self': mock_self,
        'cdp_session': cdp_session,
        'asyncio': asyncio,
    }
    
    # Compile and execute the code
    try:
        # For async code, we need to wrap it in an async function and call it
        wrapped_code = f"""
async def _dynamic_exec():
{chr(10).join('    ' + line for line in python_code.split(chr(10)))}

# Execute the wrapped function
import asyncio
_result = asyncio.create_task(_dynamic_exec())
"""
        
        compiled_code = compile(wrapped_code, f'<dynamic_code_step_{step_index}>', 'exec')
        
        # Execute the code
        exec(compiled_code, exec_globals, exec_globals)
        
        # Wait for the async task to complete
        await exec_globals['_result']
        print(f"✅ Step {step_index + 1}: Dynamic code executed successfully")
        
    except Exception as e:
        print(f"❌ Step {step_index + 1}: Error executing dynamic code: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        raise


def fix_cdp_code_structure(python_code: str, current_target_id: str, session_id: str) -> str:
    """Fix CDP code to use proper params structure and current target/session IDs."""
    
    # Replace all hardcoded target IDs with current one (handle both single and double quotes)
    fixed_code = re.sub(r'"targetId": "[^"]*"', f'"targetId": "{current_target_id}"', python_code)
    fixed_code = re.sub(r"'targetId': '[^']*'", f"'targetId': '{current_target_id}'", fixed_code)
    
    # Fix Input commands to include required coordinates
    # Add default x=400, y=300 if missing coordinates for mouse events
    
    # Fix Input.dispatchMouseEvent commands (mouseWheel, etc.)
    if 'Input.dispatchMouseEvent' in fixed_code:
        # For mouseWheel events that are missing x,y coordinates
        if 'mouseWheel' in fixed_code and '"x":' not in fixed_code and "'x':" not in fixed_code:
            fixed_code = re.sub(
                r'(Input\.dispatchMouseEvent\(\{[^}]*)"type":\s*"mouseWheel"([^}]*)\}',
                r'\1"type": "mouseWheel", "x": 400, "y": 300\2}',
                fixed_code
            )
            fixed_code = re.sub(
                r"(Input\.dispatchMouseEvent\(\{[^}]*)'type':\s*'mouseWheel'([^}]*)\}",
                r"\1'type': 'mouseWheel', 'x': 400, 'y': 300\2}",
                fixed_code
            )
        
        # For mouseWheel events that are missing deltaX (but have deltaY)
        if 'mouseWheel' in fixed_code and '"deltaX":' not in fixed_code and "'deltaX':" not in fixed_code:
            fixed_code = re.sub(
                r'(Input\.dispatchMouseEvent\(\{[^}]*"type":\s*"mouseWheel"[^}]*)"deltaY":\s*([^,}]+)([^}]*)\}',
                r'\1"deltaX": 0, "deltaY": \2\3}',
                fixed_code
            )
            fixed_code = re.sub(
                r"(Input\.dispatchMouseEvent\(\{[^}]*'type':\s*'mouseWheel'[^}]*)'deltaY':\s*([^,}]+)([^}]*)\}",
                r"\1'deltaX': 0, 'deltaY': \2\3}",
                fixed_code
            )
    
    # Fix different CDP call patterns to use proper params structure
    
    # Pattern 1: self.agent_focus.cdp_client.send.* calls (handle both {} and {'...'} patterns)
    fixed_code = re.sub(
        r'await self\.agent_focus\.cdp_client\.send\.([A-Za-z]+)\.([A-Za-z]+)\((\{[^}]+\})\)',
        lambda m: f'await self.agent_focus.cdp_client.send.{m.group(1)}.{m.group(2)}(params={m.group(3)}, session_id="{session_id}")' 
                 if m.group(1) not in ['Target', 'Browser'] else f'await self.agent_focus.cdp_client.send.{m.group(1)}.{m.group(2)}(params={m.group(3)})',
        fixed_code
    )
    
    # Pattern 2: self.browser_session.agent_focus.cdp_client.send.* calls  
    fixed_code = re.sub(
        r'await self\.browser_session\.agent_focus\.cdp_client\.send\.([A-Za-z]+)\.([A-Za-z]+)\((\{[^}]*\})\)',
        lambda m: f'await self.browser_session.agent_focus.cdp_client.send.{m.group(1)}.{m.group(2)}(params={m.group(3)}, session_id="{session_id}")' 
                 if m.group(1) not in ['Target', 'Browser'] else f'await self.browser_session.agent_focus.cdp_client.send.{m.group(1)}.{m.group(2)}(params={m.group(3)})',
        fixed_code
    )
    
    # Pattern 3: cdp_session.cdp_client.send.* calls
    fixed_code = re.sub(
        r'await cdp_session\.cdp_client\.send\.([A-Za-z]+)\.([A-Za-z]+)\((\{[^}]+\})\)',
        lambda m: f'await cdp_session.cdp_client.send.{m.group(1)}.{m.group(2)}(params={m.group(3)}, session_id=cdp_session.session_id)' 
                 if m.group(1) not in ['Target', 'Browser'] else f'await cdp_session.cdp_client.send.{m.group(1)}.{m.group(2)}(params={m.group(3)})',
        fixed_code
    )
    
    return fixed_code


def load_json_data_from_file(file_path: str):
    """Load JSON data from a Python file containing json_data variable."""
    try:
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        print(f"📂 Loading JSON data from: {file_path}")
        
        # Load the module dynamically
        spec = importlib.util.spec_from_file_location("json_data_module", file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Get the json_data variable
        if not hasattr(module, 'json_data'):
            raise AttributeError(f"No 'json_data' variable found in {file_path}")
        
        json_data = module.json_data
        print(f"✅ Loaded {len(json_data)} CDP command sequences from file")
        
        return json_data
        
    except Exception as e:
        print(f"❌ Error loading JSON data from file: {str(e)}")
        raise


async def test_complete_cdp_execution(json_data_file: str = None):
    """Execute complete CDP command sequence by parsing JSON array and running code dynamically."""
    print("🚀 Starting complete CDP test with comprehensive JSON data...")
    
    # Load JSON data from file or use default
    if json_data_file:
        json_data = load_json_data_from_file(json_data_file)
    else:
        print("⚠️ No JSON data file provided, using default minimal data")
        # Minimal default data for testing
        json_data = [
            {
                "python_code": """# Execute via CDP
await self.agent_focus.cdp_client.send.Target.activateTarget({
    "targetId": "PLACEHOLDER_TARGET_ID"
})
await self.agent_focus.cdp_client.send.Page.navigate({
    "url": "https://angularformadd.netlify.app/",
    "transitionType": "address_bar"
})"""
            }
        ]
    
    browser_session = None
    
    try:
        # Create browser session with CDP connection
        print("📱 Creating browser session...")
        browser_session = BrowserSession(
            browser_profile=BrowserProfile(
                headless=False,
                is_local=True,
                window_size={"width": 1792, "height": 1024}
            )
        )
        
        # Start the browser session
        print("🔌 Connecting to CDP...")
        await browser_session.event_bus.dispatch(BrowserStartEvent())
        
        # Wait a moment for connection to establish
        await asyncio.sleep(2)
        
        # Get the CDP client from agent_focus
        if not browser_session.agent_focus or not browser_session.agent_focus.cdp_client:
            print("❌ Failed to establish CDP connection")
            return
            
        print("✅ CDP connection established")
        
        # Get or create a proper CDP session with all required domains enabled
        print("\n🔧 Setting up CDP session with all required domains...")
        try:
            # Get the current session and enable all necessary domains
            cdp_session = await browser_session.get_or_create_cdp_session()
            
            # Enable required domains for comprehensive CDP operations
            domains_to_enable = ['Page', 'DOM', 'Input', 'Runtime', 'Emulation']
            for domain in domains_to_enable:
                try:
                    domain_api = getattr(cdp_session.cdp_client.send, domain)
                    await domain_api.enable(session_id=cdp_session.session_id)
                    print(f"✅ {domain} domain enabled")
                except Exception as e:
                    print(f"⚠️ {domain} domain might already be enabled: {e}")
            
            current_target_id = cdp_session.target_id
            session_id = cdp_session.session_id
            print(f"✅ Using CDP session - Target ID: {current_target_id}, Session ID: {session_id}")
            
            # Set exact browser dimensions as specified
            print("🖥️ Setting browser dimensions...")
            try:
                # Set viewport dimensions
                await cdp_session.cdp_client.send.Emulation.setDeviceMetricsOverride(
                    params={
                        "width": 1792,
                        "height": 937,
                        "deviceScaleFactor": 2,
                        "mobile": False,
                        "dontSetVisibleSize": False
                    },
                    session_id=session_id
                )
                
                # Set visual viewport
                await cdp_session.cdp_client.send.Emulation.setVisibleSize(
                    params={
                        "width": 1792,
                        "height": 937
                    },
                    session_id=session_id
                )
                
                print("✅ Browser dimensions set to 1792x937 with devicePixelRatio=2")
                
            except Exception as dim_error:
                print(f"⚠️ Could not set dimensions: {dim_error}")
            
        except Exception as e:
            print(f"⚠️ Could not set up CDP session: {e}")
            # Fallback to agent_focus target
            current_target_id = browser_session.agent_focus.target_id if browser_session.agent_focus else "838C27B27DC3293A865080C27872F7EA"
            session_id = browser_session.agent_focus.session_id if browser_session.agent_focus else ""
            print(f"🔄 Using fallback - Target ID: {current_target_id}, Session ID: {session_id}")
        
        # Execute all CDP command sequences
        print(f"\n🎯 Executing {len(json_data)} CDP command sequences...")
        
        for i, command_data in enumerate(json_data):
            python_code = command_data.get("python_code", "").strip()
            
            # Skip empty commands
            if not python_code or python_code == "# Execute via CDP":
                print(f"⏭️ Step {i + 1}: Skipping empty command")
                continue
            
            print(f"\n📋 Step {i + 1}: Processing CDP commands...")
            
            # Fix the CDP code structure to use proper params and session_id
            fixed_code = fix_cdp_code_structure(python_code, current_target_id, session_id)
            
            print(f"🔧 Step {i + 1}: Code structure updated")
            
            # Execute the CDP commands dynamically
            try:
                await execute_dynamic_cdp_code(browser_session, cdp_session, fixed_code, i)
                
                # Wait between commands to allow for proper execution
                await asyncio.sleep(1)
                # If this step performed a Page.navigate, wait 1.5s before the next step
                inter_step_delay = 1.5 if '.Page.navigate(' in fixed_code else 1
                await asyncio.sleep(inter_step_delay)
                
            except Exception as e:
                print(f"❌ Step {i + 1}: Failed to execute CDP commands: {str(e)}")
                # Continue with next commands instead of stopping
                continue
        
        # Wait for final operations to complete
        print("\n⏳ Waiting for final operations to complete...")
        await asyncio.sleep(3)
        
        print("\n🎉 Complete CDP execution finished!")
        
    except Exception as e:
        print(f"❌ Error in complete CDP test execution: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        
        # Provide helpful troubleshooting info
        if "Connection refused" in str(e) or "connect" in str(e).lower():
            print("\n💡 Troubleshooting tips:")
            print("1. Make sure Chrome is running with debugging enabled:")
            print('   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222')
            print("2. Verify CDP is accessible: http://localhost:9222/json/version")
            print("3. Check if the target ID exists in: http://localhost:9222/json")
        
    finally:
        # Clean up
        if browser_session:
            try:
                print("\n🧹 Cleaning up browser session...")
                await browser_session.kill()
                print("✅ Browser session closed")
            except Exception as cleanup_error:
                print(f"⚠️ Warning during cleanup: {cleanup_error}")


async def main():
    """Main function to run the complete CDP test."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Execute complete CDP command sequence from JSON data file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_cdp_complete.py ../../logs/ca9bd18150884cfea0ba3c50e5c285b1_python_code.py
  python test_cdp_complete.py /path/to/your/json_data_file.py
  python test_cdp_complete.py  # Uses default minimal data
        """
    )
    parser.add_argument(
        'json_file', 
        nargs='?', 
        help='Path to Python file containing json_data variable with CDP commands'
    )
    
    args = parser.parse_args()
    
    # Run the test with the specified file
    await test_complete_cdp_execution(args.json_file)


if __name__ == '__main__':
    asyncio.run(main())
