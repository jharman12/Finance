# Interaction Design & User Flows

This document details specific user interactions, state transitions, and best UX patterns for your multi-feature AI assistant.

---

## 1. Main Navigation Flow

### Sidebar Navigation Behavior

```
User launches app
    ↓
┌─────────────────────────────────────────┐
│ MainWindow displays with:                │
│ • Left Sidebar (160px wide)              │
│ • Finance Tab active (default)           │
│ • Right Status Panel visible             │
│ • Status bar shows "Ready"               │
└─────────────────────────────────────────┘
    ↓
┌─ User clicks Sidebar Feature Button ─┐
│ (e.g., "📅 Calendar")                 │
└───────────────────────────────────────┘
    ↓
Sidebar Button Updates:
    • Current button: background=white, foreground=#2196F3
    • Previous button: background=transparent
    ↓
Tab Widget Updates:
    • Tab 0 (Finance) → Tab 1 (Calendar)
    ↓
Content Animates In (QStackedWidget or tab switch)
    ↓
Status Bar updates context (if needed)
```

### Keyboard Navigation

```
Ctrl+1  →  Switch to Finance Tab
Ctrl+2  →  Switch to Calendar Tab
Ctrl+3  →  Switch to To-Do Tab
Ctrl+4  →  Switch to Shopping Tab
Ctrl+?  →  Show Help/Shortcuts
Tab     →  Navigate between interactive elements
Enter   →  Activate focused button/trigger action
Esc     →  Close dialog/return to previous state
```

---

## 2. Voice Input Interaction Flow

### State Machine: Voice Processing

```
                        ┌─ User Speaks ─┐
                        ↓                ↓
                   ┌─LISTENING─┐    ┌─SILENT─┐
                   │ ●🎤 Yellow│    │● Ready │
                   └─────┬─────┘    └────────┘
                         │
            Voice detected for 2+ seconds
                         │
                    ┌────▼────┐
                    │PROCESSING│
                    │●⚙ Blue   │
                    │Wave animation
                    └────┬─────┘
                         │
         ┌─ Speech Complete ─┬─ Error ─┐
         ↓                   ↓         ↓
    ┌─ASR─┐          ┌─ERROR─┐    [Timeout]
    │Parse│          │●⚠ Red │   Retry or
    └──┬──┘          │Error  │    Cancel
       │             └───────┘
       │
       ├─ Speech Recognized ─┐
       │                     ↓
       │              ┌─AGENT_PROCESSING─┐
       │              │●⚙ Blue             │
       │              │"Analyzing..."      │
       │              └────┬───────────────┘
       │                   │
       │        ┌─ Agent Complete ─┐
       │        ↓                   ↓
       │    ┌─READY─┐         ┌─ERROR─┐
       │    │●✓Green│         │●⚠ Red │
       │    │"Ready"│         │Error  │
       │    └───────┘         └───────┘
       │
       ├─ No Speech (Timeout)
       ↓
    ┌─TIMEOUT─┐
    │●⚠ Yellow│
    │"No input"
    └─────────┘
```

### Voice Indicator CSS States

```css
/* Ready State */
indicator {
    color: #4CAF50;  /* Green */
    content: "●";
    animation: none;
}
status_text { content: "🎤 Ready"; }
waveform { display: none; }

/* Listening State */
indicator {
    color: #FFC107;  /* Yellow */
    animation: pulse 0.5s infinite;
}
status_text { content: "🎤 Listening..."; }
waveform {
    display: block;
    animation: wave 0.1s steps(1);
    content: "▁ ▂ ▃ ▄ ▅ ▄ ▃ ▂";
}

/* Processing State */
indicator {
    color: #2196F3;  /* Blue */
    animation: pulse 0.5s infinite;
}
status_text { content: "⚙ Processing..."; }
waveform {
    display: block;
    animation: wave 0.1s steps(1);
}

/* Error State */
indicator {
    color: #f44336;  /* Red */
    animation: none;
}
status_text { content: "⚠ Error"; }
waveform { display: none; }
```

---

## 3. Device Management Flow

### Device Discovery & Pairing

```
User clicks "📱 Devices" or "+" Add Device
    ↓
┌────────────────────────────────────┐
│ DevicePairingDialog opens          │
│ • Title: "Pair Remote Voice Device"│
│ • Size: 500x400                    │
│ • Modal: yes                       │
└────────────────────────────────────┘
    ↓
┌─ Discovery Phase ────────────────────────────────┐
│ Label: "Searching for available devices... 🔍"   │
│ Empty list (animated loader)                     │
│ "Pair Selected Device" button: DISABLED          │
└──────────────────────────────────────┬───────────┘
   Zeroconf discovers devices (5-10s)
                 ↓
        Device entries appear:
        ☐ Device-A (Ready)      [Signal: -45dBm]
        ☐ Device-B (Ready)      [Signal: -67dBm]
        ☐ Device-C (Low Battery) [Signal: -85dBm]
                 ↓
    User selects device (checkbox)
                 ↓
    "Pair Selected Device" button: ENABLED
                 ↓
    User clicks "Pair Selected Device"
                 ↓
┌─ Pairing Phase ──────────────────────────────────┐
│ Dialog shows:                                    │
│ "Enter Code on Device or Confirm Here"           │
│ ┌──────────────────────────────────────────────┐ │
│ │ Enter Pairing Code: [123456         ]        │ │
│ │                                              │ │
│ │ Or tap 'Confirm' on device                   │ │
│ │ ☐ Confirm on Device                          │ │
│ │                                              │ │
│ │ Timeout: 120 seconds ⏱                      │ │
│ └──────────────────────────────────────────────┘ │
│                                                   │
│ [Cancel] [Pair]                                   │
└───────────────────────────┬──────────────────────┘
           ↓
    ┌─ Device confirms ─┐
    │  Pairing success  │
    └────────┬──────────┘
             ↓
┌─ Success Phase ──────────────────────────────────┐
│ ✓ Device Paired Successfully!                     │
│ Device Name: [Remote Speaker         ]           │
│ Device ID: a1b2c3d4-e5f6-...                     │
│ Last Seen: Just now                              │
│ Battery: 85%                                     │
│ Signal: -45dBm (Strong)                          │
│                                                   │
│ [Done]                                            │
└──────────────────────────────────────────────────┘
             ↓
    Dialog closes
             ↓
    Device appears in Status Panel:
    ┌──────────────────────────┐
    │ ● Device-A               │ ← Green (online)
    │ Status: online           │
    │ Battery: 85%             │
    │ Signal: -45dBm           │
    │             [⋮] menu     │
    └──────────────────────────┘
```

### Device Status Panel Interactions

```
┌─ Right Status Panel ────────────────────────┐
│ Connected Devices                           │
├─────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────┐│
│ │ ● Device-A (Online)                   [⋮]││
│ │ Status: online • Battery: 85%           ││
│ └──────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────┐│
│ │ ● Device-B (Online)                   [⋮]││
│ │ Status: online • Battery: 92%           ││
│ └──────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────┐│
│ │ ◐ Device-C (Idle)                    [⋮] ││
│ │ Status: idle • Battery: 12%             ││
│ └──────────────────────────────────────────┘│
│                                              │
│ [+ Add Device]                               │
├─────────────────────────────────────────────┤
│ AI Agent Status                              │
│ ✓ Ready                                      │
│ Response time: 0.8s (avg)                    │
└─────────────────────────────────────────────┘
```

#### Device Menu Actions

```
User clicks [⋮] on device
    ↓
Context menu appears:
    ├─ Test Connection
    │   └─ Sends ping, shows latency
    ├─ Rename Device...
    │   └─ Dialog to rename
    ├─ View Details
    │   └─ Shows full device info (IP, MAC, etc.)
    ├─ (separator)
    └─ Unpair Device
        └─ Confirmation dialog
```

---

## 4. Shared vs Personal Item Organization

### Toggle Interaction

```
User in To-Do, Shopping, or Calendar tab

┌─ Top Toolbar ──────────────────────────────┐
│ [👤 Personal] [👥 Shared]                  │
│  ↑ Pressed      ↑ Not pressed              │
└────────────────────────────────────────────┘

When Personal pressed:
    • Background: #E8F5E9 (light green)
    • Text color: #2E7D32 (green)
    • Shows only user's personal items
    • Lists filtered to ownership=false

When Shared pressed:
    • Background: #E3F2FD (light blue)
    • Text color: #1565C0 (blue)
    • Shows household/shared items
    • Lists filtered to ownership=true

User can toggle while viewing:
    • Instant filter update
    • List animates in/out (200ms)
    • Scroll position resets to top
```

### Item Display with Ownership

```
┌─ Personal To-Do Item ─────────────────────┐
│ ☐ Buy groceries            [👤] [✎] [✕]  │
│ ● High Priority                           │
│ Due: Today                                │
└───────────────────────────────────────────┘

┌─ Shared Household Item ───────────────────┐
│ ☐ Fix kitchen tap          [👥] [✎] [✕]  │
│ ● Low Priority                            │
│ Due: Saturday (assigned to Tom)           │
└───────────────────────────────────────────┘

Hover Effects:
    • Item background: #fafafa
    • Edit & Delete buttons appear (if owner)
    • Copy/Share buttons appear (if permitted)
```

---

## 5. Agent Configuration Interaction

### Settings Dialog

```
User clicks "⚙ Agent Config" (Sidebar)
    ↓
┌────────────────────────────────────────────┐
│ AI Agent Configuration Dialog              │
├─ [Finance] [Calendar] [Task] [Other] ──────┤
│                                             │
│ ┌─ Finance Agent Settings ─────────────┐  │
│ │ Description: Expert financial        │  │
│ │ guidance for budgeting...            │  │
│ │                                       │  │
│ │ Model:              [qwen2.5 ▼]      │  │
│ │ Temperature:  ☐──────●────────☐ 0.3 │  │
│ │ Max Context:         [4096]           │  │
│ │ Response Style: [Professional ▼]     │  │
│ │ Risk Profile: [Conservative ▼]       │  │
│ │                                       │  │
│ │ ▼ Advanced Options                    │  │
│ │   □ Enable Explanations               │  │
│ │   □ Show Calculations                │  │
│ │                                       │  │
│ └───────────────────────────────────────┘  │
│                                             │
│ ┌─ Configuration Preview ─────────────────┐│
│ │ Current Configuration:                  ││
│ │                                         ││
│ │ Finance Agent:                          ││
│ │ • Model: qwen2.5:latest                ││
│ │ • Temperature: 0.3 (Focused)           ││
│ │ • Risk: Conservative                   ││
│ │                                         ││
│ │ Calendar Agent:                         ││
│ │ • Model: qwen2.5:latest                ││
│ │ • Auto-Optimize: Enabled               ││
│ └─────────────────────────────────────────┘│
│                                             │
│ [Reset to Defaults] [Test Agent] [Save]    │
└─────────────────────────────────────────────┘
```

### Agent Testing Flow

```
User clicks "Test Agent"
    ↓
┌────────────────────────────────────────────┐
│ Test Agent - Finance Advisor               │
├────────────────────────────────────────────┤
│                                             │
│ Testing with sample prompt...              │
│ ⏳ Loading...                              │
│                                             │
│ Agent Response:                            │
│                                             │
│ "Based on your current financial          │
│ situation, I recommend:                   │
│ 1. Increase emergency fund to 3 months    │
│ 2. Reduce dining expenses by 15%          │
│ 3. Review investment allocation           │
│                                             │
│ Response time: 1.2s                        │
│ Context usage: 45%"                        │
│                                             │
│ ✓ Agent is responding correctly            │
│                                             │
│ [Close]                                     │
└────────────────────────────────────────────┘
```

---

## 6. Multi-Calendar Display

### Calendar View Switching

```
┌─ Calendar Tab Toolbar ────────────────────┐
│ View: [Month ▼]  Period: [This Month ▼]  │
│ [📅 Calendars] [🔍 Search...]            │
│                                            │
│ ◄  June 2026  ►                      [Today]
└────────────────────────────────────────────┘

Month View Layout:
┌──────────────────────────────────────────┐
│ Sun  Mon  Tue  Wed  Thu  Fri  Sat         │
├──────────────────────────────────────────┤
│  1    2    3    4    5    6    7          │
│  8    9   10   11   12   13   14          │
│ 15   16   17   18   19   20   21          │
│ 22   23   24   25   26   27   28          │
│ 29   30                                    │
└──────────────────────────────────────────┘

Day cell with events:
┌─ Day 15 ──────────────────┐
│ 15                         │
├────────────────────────────┤
│ ┌────────────────────────┐ │
│ │ 09:00 Team Meeting    │ │  ← Blue (Work)
│ └────────────────────────┘ │
│ ┌────────────────────────┐ │
│ │ 15:00 Dentist         │ │  ← Green (Personal)
│ └────────────────────────┘ │
└────────────────────────────┘

Click on event:
    ↓
Event detail popup or inline editing
```

### Calendar Selection

```
User clicks "📅 Calendars"
    ↓
┌─ Calendar Selector Dropdown ──────────────┐
│ ☑ Personal Calendar                       │
│ ☑ Work Calendar                           │
│ ☑ Family Calendar                         │
│ ☐ Holidays (US)                           │
│ ☐ Birthdays                               │
│ ☑ Shared: Household Meetings              │
│                                            │
│ [Color Legend]                             │
│ ● Personal: #2196F3                       │
│ ● Work: #FF5722                           │
│ ● Family: #4CAF50                         │
└───────────────────────────────────────────┘

Unchecking calendar:
    • Events disappear from view
    • Day cells update immediately
    • No save needed (auto-save)
```

---

## 7. Responsive Behavior

### Desktop Layout (>1200px)

```
┌─────┬─────────────────────────┬─────────┐
│ 160 │                          │  200    │
│  px │     Content Area         │  px     │
│     │     (70-75%)             │         │
│ 200 │                          │ Status  │
│ max │                          │ Panel   │
│  |  │                          │         │
│ Sidebar                         │         │
└─────┴─────────────────────────┴─────────┘
```

### Tablet Layout (800-1200px)

```
┌────┬────────────────────────────────────────┐
│120 │                                         │
│ px │    Content Area                        │
│    │    (80-85%)                            │
│Compact                                      │
│Sidebar                                      │
│    │  Status Panel at bottom or hidden     │
└────┴────────────────────────────────────────┘
```

### Mobile Layout (<800px)

```
┌──────────────────────────────────────────┐
│  Content Area (Full Width)               │
│  (Status panel minimized/hidden)         │
├──────────────────────────────────────────┤
│                                            │
│  Main Content                            │
│                                            │
├──────────────────────────────────────────┤
│ 💰 📅 ✓ 🛒                                │
│ Bottom Navigation Bar (Mobile Friendly)  │
└──────────────────────────────────────────┘
```

### Breakpoint Transitions

```
Window Resized from 1400px → 1000px
    ↓
ResizeEvent triggered
    ↓
Check: if width < 1200px
    ↓
Set Tablet Layout
    • Sidebar: max-width 120px
    • Hide status panel or move to tab
    • Adjust spacing
    ↓
Animation (200ms)
    ↓
New layout displayed
```

---

## 8. Accessibility Keyboard Shortcuts

```
Global Shortcuts (anywhere in app)
    Ctrl+1          Switch to Finance
    Ctrl+2          Switch to Calendar
    Ctrl+3          Switch to To-Do
    Ctrl+4          Switch to Shopping
    Ctrl+?          Show Help
    Ctrl+K          Global Search
    
    Tab             Focus next element
    Shift+Tab       Focus previous element
    Space           Activate button/toggle
    Enter           Submit form
    Esc             Close dialog/cancel
    
Finance Tab
    Ctrl+T          New transaction
    Ctrl+B          Show budget
    Ctrl+A          Open analytics
    
Calendar Tab
    Ctrl+E          New event
    Ctrl+N          Next month
    Ctrl+P          Previous month
    
To-Do Tab
    Ctrl+N          New task
    Ctrl+F          Filter tasks
    
Shopping Tab
    Ctrl+I          Add item
    Ctrl+C          Clear completed
```

---

## 9. Error & Success Messaging

### Toast Notifications

```
Success (3 second fade):
┌────────────────────────────────────────┐
│ ✓ Device paired successfully           │
│   Device-A is now ready for voice      │
└────────────────────────────────────────┘

Error (Stays until dismissed):
┌────────────────────────────────────────┐
│ ✗ Failed to pair device                │
│   Timeout during pairing process       │
│                                         │
│ [Retry] [Cancel]                       │
└────────────────────────────────────────┘

Info (Informational):
┌────────────────────────────────────────┐
│ ℹ Syncing with remote device...        │
│   This may take a few seconds          │
└────────────────────────────────────────┘
```

### Inline Validation

```
┌─ Add New Task Form ────────────────────────┐
│ Task Title: [                          ]  │
│             ^ Required field              │
│                                            │
│ Priority:   [High ▼]                     │
│                                            │
│ Due Date:   [2026-06-28]                 │
│             ^ Must be future date        │
│                                            │
│ Ownership:  [👤 Personal] [👥 Shared]    │
│                                            │
│ [Save]                                     │
└────────────────────────────────────────────┘

When user clicks Save without title:
    ↓
Input field gets red border
    ↓
Error message: "Task title is required"
    ↓
Focus returns to field
    ↓
User types title
    ↓
Border turns green (validation passes)
    ↓
Save button becomes enabled
```

---

## 10. Animation & Transition Patterns

### Tab Switching Animation

```
User clicks Calendar Tab
    ↓
Finance content: Fade out + Slide left (100ms)
Calendar content: Fade in + Slide right (100ms)
    ↓
Total: 100ms (feels snappy)
```

### Device Status Update

```
Device goes offline
    ↓
Status indicator: Green → Yellow → Red (500ms fade)
Label: "online" → "idle" → "offline" (text update)
    ↓
Device card height reduces if empty state (200ms)
```

### Voice Indicator Animation

```
When listening:
    Waveform cycles: ▁ ▂ ▃ ▄ ▅ ▄ ▃ ▂ (100ms per frame)
    Indicator pulses: opacity 1.0 → 0.5 → 1.0 (500ms)
    
When processing:
    Waveform cycles: ▂ ▃ ▄ ▅ ▆ ▅ ▄ ▃ (100ms per frame)
    Indicator pulses: opacity 1.0 → 0.7 → 1.0 (500ms)
```

---

## Best Practices Summary

✅ **DO**
- Use consistent spacing throughout (4px, 8px, 16px, 24px)
- Provide clear feedback for every user action
- Make interactive elements at least 44x44 pixels (touch-friendly)
- Use color + text for status (not color alone)
- Animate transitions smoothly (100-300ms)
- Show loading states for async operations
- Provide undo/confirmation for destructive actions

❌ **DON'T**
- Use more than 3 colors for main UI (theme consistency)
- Disable buttons without explanation
- Hide important controls in menus
- Show errors without solution suggestions
- Play sounds without user permission
- Use animations longer than 300ms for common actions
- Require perfect input (trim whitespace, suggest corrections)

