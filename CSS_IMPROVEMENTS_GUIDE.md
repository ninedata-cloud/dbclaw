# CSS Improvements Visual Guide

## 🎨 Color Palette

### Primary Colors
```
Blue:   #2f81f7  ████  Primary actions, active states
Purple: #a371f7  ████  AI assistant identity
Cyan:   #39d2c0  ████  Tool call indicators
Green:  #3fb950  ████  Success states
Red:    #f85149  ████  Danger/error states
Yellow: #d29922  ████  Warning states
```

### Background Colors
```
Primary:   #0f1117  ████  Main background
Secondary: #161b22  ████  Sidebar, panels
Card:      #1c2333  ████  Cards, bubbles
Hover:     #252d3d  ████  Hover states
Input:     #0d1117  ████  Input fields
```

## 📐 Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│ Header (56px)                                           │
│ [Datasource] [Model] [KB] [Tool Safety]                │
├──────────┬──────────────────────────────┬──────────────┤
│          │                              │              │
│ Sessions │  Chat Messages               │ Tool Panel   │
│ (280px)  │  (flex: 1)                   │ (400px)      │
│          │                              │              │
│ [+ New]  │  ┌────────────────────────┐  │ [Activity]   │
│          │  │ User Message           │  │              │
│ Session1 │  └────────────────────────┘  │ ┌──────────┐ │
│ Session2 │                              │ │ Tool 1   │ │
│ Session3 │  ┌────────────────────────┐  │ └──────────┘ │
│          │  │ Assistant Message      │  │              │
│          │  └────────────────────────┘  │ ┌──────────┐ │
│          │                              │ │ Tool 2   │ │
│          │  ┌────────────────────────┐  │ └──────────┘ │
│          │  │ Tool Call Card         │  │              │
│          │  └────────────────────────┘  │              │
│          │                              │              │
│          ├──────────────────────────────┤              │
│          │ [📎] [Input...] [Send] [⬜] │              │
└──────────┴──────────────────────────────┴──────────────┘
```

## 🎭 Animation Timeline

### Message Appearance (0.3s)
```
0ms    ─────────────────────────────────────> 300ms
       ↓                                      ↓
       opacity: 0                             opacity: 1
       translateY(12px)                       translateY(0)
       
       [Invisible, below]  ──────────>  [Visible, in place]
```

### Button Hover (0.2s)
```
0ms    ─────────────────────> 200ms
       ↓                      ↓
       scale(1)               scale(1.05)
       shadow: 0 1px 3px      shadow: 0 4px 12px
       
       [Normal]  ──────>  [Enlarged, glowing]
```

### Tool Status Pulse (2s, infinite)
```
0ms    ────────> 1000ms ────────> 2000ms ────────> (repeat)
       ↓          ↓               ↓
       opacity: 1 opacity: 0.6    opacity: 1
       
       [Bright] ──> [Dim] ──> [Bright] ──> ...
```

## 🎯 Interactive States

### Session Item States
```
Normal:    background: transparent
           border-left: none

Hover:     background: var(--bg-hover)
           transform: translateX(2px)
           border-left: none

Active:    background: var(--accent-blue)
           color: white
           border-left: 3px solid var(--accent-blue)
           height: 60%
```

### Input Field States
```
Normal:    border: 1px solid var(--border-color)
           background: var(--bg-input)

Hover:     border: 1px solid var(--border-light)

Focus:     border: 1px solid var(--accent-blue)
           box-shadow: 0 0 0 3px rgba(47,129,247,0.1)
```

### Button States
```
Normal:    background: var(--accent-blue)
           transform: scale(1)
           shadow: none

Hover:     background: var(--accent-blue-hover)
           transform: scale(1.05)
           shadow: 0 4px 12px rgba(47,129,247,0.3)

Active:    transform: scale(0.98)

Disabled:  opacity: 0.5
           cursor: not-allowed
```

## 📏 Spacing System

### Padding Scale
```
xs:  4px   ▪
sm:  8px   ▪▪
md:  12px  ▪▪▪
lg:  16px  ▪▪▪▪
xl:  20px  ▪▪▪▪▪
2xl: 24px  ▪▪▪▪▪▪
```

### Gap Scale
```
xs:  4px   ▪
sm:  8px   ▪▪
md:  12px  ▪▪▪
lg:  16px  ▪▪▪▪
xl:  20px  ▪▪▪▪▪
```

### Border Radius
```
sm:  6px   ╭─╮
md:  8px   ╭──╮
lg:  12px  ╭───╮
full: 50%  ●
```

## 🔤 Typography

### Font Families
```
Sans:  'Inter', -apple-system, BlinkMacSystemFont, sans-serif
Mono:  'JetBrains Mono', 'Fira Code', monospace
```

### Font Sizes
```
11px  ▪  Tool status, labels
12px  ▪▪  Code, tool content
13px  ▪▪▪  Form controls, session items
14px  ▪▪▪▪  Body text, messages
16px  ▪▪▪▪▪  Headings
18px  ▪▪▪▪▪▪  Page titles
```

### Font Weights
```
400  Normal text
500  Medium emphasis
600  Strong emphasis, headings
700  Extra strong (rarely used)
```

## 🎬 Transition Curves

### Standard Ease
```
transition: all 0.2s ease;

0%   ────────────────────────> 100%
     ╱                          
    ╱                           
   ╱                            
  ╱                             
 ╱                              
╱                               
[Slow start, slow end]
```

### Cubic Bezier (0.4, 0, 0.2, 1)
```
transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

0%   ────────────────────────> 100%
     ╱                          
    ╱                           
   ╱                            
  ╱                             
 ╱                              
╱                               
[Smooth acceleration, quick deceleration]
```

## 🎨 Shadow Layers

### Elevation System
```
Level 1 (sm):  0 1px 3px rgba(0,0,0,0.2)
               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁

Level 2 (md):  0 2px 8px rgba(0,0,0,0.3)
               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁

Level 3 (lg):  0 4px 12px rgba(47,129,247,0.3)
               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
               ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
```

## 📱 Responsive Behavior

### Desktop (>1200px)
```
┌────────┬──────────────┬────────┐
│Sessions│   Messages   │  Tools │
│ 280px  │   flex: 1    │ 400px  │
└────────┴──────────────┴────────┘
```

### Tablet (768px - 1200px)
```
┌────────┬──────────────┬────────┐
│Sessions│   Messages   │  Tools │
│ 280px  │   flex: 1    │ 320px  │
└────────┴──────────────┴────────┘
```

### Mobile (<768px)
```
┌────────┬──────────────┐
│Sessions│   Messages   │
│ 280px  │   flex: 1    │
└────────┴──────────────┘
         │ Tools (overlay)
         └──────────────┘
```

## 🎯 Key CSS Selectors

### High Priority
```css
.session-item.active::before     /* Active indicator */
.chat-message                     /* Message animation */
.chat-tool-call                   /* Tool card styling */
.chat-input:focus                 /* Input focus state */
```

### Medium Priority
```css
.chat-avatar                      /* Avatar styling */
.chat-tool-status.running         /* Running animation */
.chat-send-btn:hover              /* Button hover */
```

### Low Priority
```css
.empty-state                      /* Empty state */
.badge                            /* Status badges */
```

## 🔧 Customization Examples

### Change Primary Color
```css
:root {
    --accent-blue: #your-color;
    --accent-blue-hover: #your-hover-color;
}
```

### Adjust Animation Speed
```css
.chat-message {
    animation: slideIn 0.5s ease; /* Slower */
}
```

### Modify Panel Width
```css
#tool-execution-panel {
    width: 500px; /* Wider */
}
```

### Custom Tool Status
```css
.chat-tool-status.custom {
    color: #your-color;
    background: rgba(your-rgb, 0.1);
}
```

## 📊 Performance Metrics

### Target Metrics
```
Animation FPS:        60fps
First Paint:          < 100ms
Interaction Ready:    < 200ms
Smooth Scrolling:     60fps
Memory Usage:         < 50MB
```

### Optimization Techniques
```
✓ Use transform instead of position
✓ Use opacity instead of visibility
✓ Minimize repaints and reflows
✓ Use will-change sparingly
✓ Debounce scroll events
```

---

**Note**: This guide provides visual representations of the CSS improvements. Actual implementation details are in `diagnosis.css`.
