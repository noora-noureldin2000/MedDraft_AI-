---
name: agent-browser
description: Fast headless browser automation CLI and workflow for web navigation, structured data extraction, form filling, accessibility snapshot analysis (@refs), JS execution, screenshot/PDF capture, and web UI interaction. Use when automating web interactions, navigating dynamic websites, scraping academic portals, extracting tables/data from web pages, testing web UIs, or running end-to-end browser tasks.
---

# Browser Automation with agent-browser

`agent-browser` is a fast browser automation CLI (Rust-based with Node.js fallback) designed for AI agents to navigate, click, type, and snapshot web pages via structured commands and accessibility reference IDs (`@e1`, `@e2`, etc.).

## Installation & Setup

### Via npm (Recommended)

```bash
npm install -g agent-browser
agent-browser install
agent-browser install --with-deps
```

### From Source

```bash
git clone https://github.com/vercel-labs/agent-browser
cd agent-browser
pnpm install
pnpm build
agent-browser install
```

## Quick Start & Core Workflow

```bash
agent-browser open <url>        # 1. Navigate to page
agent-browser snapshot -i       # 2. Get interactive elements with refs (@e1, @e2...)
agent-browser click @e1         # 3. Click element by ref
agent-browser fill @e2 "text"   # 4. Fill input by ref
agent-browser close             # 5. Close browser session
```

### Standard Loop

1. **Navigate**: `agent-browser open <url>`
2. **Snapshot**: `agent-browser snapshot -i` (returns indexed element references like `@e1`, `@e2`)
3. **Interact**: Target elements using refs from the snapshot (`click @e1`, `fill @e2 "query"`, etc.)
4. **Re-snapshot**: Snapshot again after navigation, AJAX updates, or DOM changes (refs update on page reload)

---

## Command Reference

### 1. Navigation

```bash
agent-browser open <url>      # Navigate to URL
agent-browser back            # Go back
agent-browser forward         # Go forward
agent-browser reload          # Reload current page
agent-browser close           # Close browser session
```

### 2. Snapshot & Page Inspection

```bash
agent-browser snapshot            # Full accessibility tree
agent-browser snapshot -i         # Interactive elements only (Recommended)
agent-browser snapshot -c         # Compact output
agent-browser snapshot -d 3       # Limit depth to 3 levels
agent-browser snapshot -s "#main" # Scope snapshot to CSS selector
agent-browser snapshot -i --json  # Machine-readable JSON output
```

### 3. Interactions (Targeting `@refs` from Snapshot)

```bash
agent-browser click @e1           # Click element
agent-browser dblclick @e1        # Double-click element
agent-browser focus @e1           # Focus element
agent-browser fill @e2 "text"     # Clear existing value and type new text
agent-browser type @e2 "text"     # Type without clearing existing value
agent-browser press Enter         # Press single key
agent-browser press Control+a     # Key combinations
agent-browser keydown Shift       # Hold key down
agent-browser keyup Shift         # Release key
agent-browser hover @e1           # Hover over element
agent-browser check @e1           # Check checkbox/radio
agent-browser uncheck @e1         # Uncheck checkbox
agent-browser select @e1 "value"  # Select dropdown option
agent-browser scroll down 500     # Scroll page by pixels
agent-browser scrollintoview @e1  # Scroll element into viewport
agent-browser drag @e1 @e2        # Drag and drop between elements
agent-browser upload @e1 file.pdf # Upload file to input
```

### 4. Data Extraction & Information Retrieval

```bash
agent-browser get text @e1        # Get inner text of element
agent-browser get html @e1        # Get inner HTML
agent-browser get value @e1       # Get form input value
agent-browser get attr @e1 href   # Get specific HTML attribute
agent-browser get title           # Get page title
agent-browser get url             # Get current active URL
agent-browser get count ".item"   # Count matching elements
agent-browser get box @e1         # Get bounding box coordinates
```

### 5. Element State Checking

```bash
agent-browser is visible @e1      # Verify element visibility
agent-browser is enabled @e1      # Verify element is interactive
agent-browser is checked @e1      # Verify checkbox/radio state
```

### 6. Screenshots & Media Capture

```bash
agent-browser screenshot          # Screenshot to stdout
agent-browser screenshot path.png # Save screenshot to file
agent-browser screenshot --full   # Capture full-page screenshot
agent-browser pdf output.pdf      # Save current page as PDF
agent-browser record start ./demo.webm # Start recording video
agent-browser record stop              # Stop and save recording
```

### 7. Waiting & Synchronization

```bash
agent-browser wait @e1                 # Wait until element appears
agent-browser wait 2000                # Wait duration in ms
agent-browser wait --text "Success"    # Wait for specific text to appear
agent-browser wait --url "/dashboard"  # Wait for URL pattern
agent-browser wait --load networkidle  # Wait for network idle state
agent-browser wait --fn "window.ready" # Wait for custom JS condition
```

### 8. Semantic Locators (Alternative to `@refs`)

```bash
agent-browser find role button click --name "Submit"
agent-browser find text "Sign In" click
agent-browser find label "Email" fill "user@test.com"
agent-browser find first ".item" click
agent-browser find nth 2 "a" text
```

### 9. Browser Settings & Emulation

```bash
agent-browser set viewport 1920 1080      # Set viewport resolution
agent-browser set device "iPhone 14"      # Emulate mobile device
agent-browser set geo 37.7749 -122.4194   # Set geolocation
agent-browser set offline on              # Emulate offline mode
agent-browser set headers '{"X-Key":"v"}' # Set custom HTTP headers
agent-browser set credentials user pass   # HTTP basic authentication
agent-browser set media dark              # Emulate dark color scheme
```

### 10. Cookies, Storage & Authentication State

```bash
agent-browser cookies                     # List all cookies
agent-browser cookies set name value      # Set cookie
agent-browser cookies clear               # Clear cookies
agent-browser storage local               # Dump localStorage
agent-browser storage local key           # Get specific localStorage key
agent-browser storage local set k v       # Set localStorage value
agent-browser storage local clear         # Clear localStorage
agent-browser state save auth.json        # Save full session state (cookies + storage)
agent-browser state load auth.json        # Load saved session state
```

### 11. Network Interception & Request Tracking

```bash
agent-browser network route <url>              # Intercept requests
agent-browser network route <url> --abort      # Block request
agent-browser network route <url> --body '{}'  # Mock response JSON
agent-browser network unroute [url]            # Remove route interceptors
agent-browser network requests                 # View tracked network requests
agent-browser network requests --filter api    # Filter network logs
```

### 12. Multi-Tab, Frames, Dialogs & JS Eval

```bash
agent-browser tab                          # List open tabs
agent-browser tab new [url]                # Open new tab
agent-browser tab 2                        # Switch to tab index 2
agent-browser tab close                    # Close active tab
agent-browser frame "#iframe"              # Switch execution context into iframe
agent-browser frame main                   # Switch back to main document frame
agent-browser dialog accept [text]         # Accept prompt/alert dialog
agent-browser dialog dismiss               # Dismiss dialog
agent-browser eval "document.title"        # Evaluate arbitrary JavaScript
```

---

## Practical Examples

### Example 1: Form Submission & Search Query

```bash
agent-browser open https://scholar.google.com
agent-browser snapshot -i
# Identified input [ref=e1] and search button [ref=e2]
agent-browser fill @e1 "SGLT2 inhibitors renal outcomes"
agent-browser press Enter
agent-browser wait --load networkidle
agent-browser snapshot -i
```

### Example 2: Authenticated Session Reuse

```bash
# First login and persist state:
agent-browser open https://academic-portal.example.com/login
agent-browser snapshot -i
agent-browser fill @e1 "researcher@med.edu"
agent-browser fill @e2 "SecretPass123"
agent-browser click @e3
agent-browser wait --url "/dashboard"
agent-browser state save session.json

# Subsequent automated sessions:
agent-browser state load session.json
agent-browser open https://academic-portal.example.com/dashboard
```

---

## Best Practices & Tips

- **Stable References**: Refs (`@e1`, `@e2`) are created per snapshot. Always re-run `agent-browser snapshot -i` after navigating or triggering actions that modify the DOM.
- **Prefer `fill` over `type`**: `fill` automatically clears existing field values before entering new text, preventing accidental concatenated input.
- **Handling Slow Pages**: Use `agent-browser wait --load networkidle` or `agent-browser wait @ref` before interacting with newly rendered elements.
- **Headless vs Headed Debugging**: Use `--headed` flag when debugging interactive workflows to visually inspect agent browser actions.
