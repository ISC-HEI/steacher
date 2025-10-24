# Turtle Graphics Exercise Type - Implementation Specification

## Overview

This document specifies the implementation of a new "turtle" exercise type for Steacher. The turtle exercise type allows students to write real Python code using [turtle graphics](https://en.wikipedia.org/wiki/Turtle_graphics) commands. Students can use full Python syntax (loops, conditionals, functions, variables) to create drawings on an HTML5 canvas. The code executes client-side via Pyodide, which emits JSON commands that are captured and animated on the canvas.

## Key Features

- **Real Python Execution**: Students write actual Python code with full language capabilities (loops, conditionals, functions)
- **Visual Feedback**: Three-pane layout with code editor, animated canvas, and AI tutor
- **Reference Pattern**: Solution pattern pre-drawn in light gray for visual comparison
- **Animation**: Smooth step-by-step animation of turtle movements with adjustable speed
- **Win Detection**: Automatic path matching to detect when student solution matches the reference
- **Goal Mode**: Optional goal position that students must reach
- **Instruction Log**: Table showing position and heading after each command
- **AI Guidance**: Full integration with Steacher's AI tutor system

## Architecture

### Frontend Components

**File**: `steacher_app/frontend/turtle.ts` 

#### Python API (Embedded in TypeScript)

A large Python API string is injected before user code execution, providing these functions:

- `forward(steps=1)` - Move forward by N steps
- `turn_left(degrees=90)` - Turn left (default 90°)
- `turn_right(degrees=90)` - Turn right (default 90°)
- `jump_to(x, y)` - Teleport to position
- `pen_up()` - Lift pen (stop drawing)
- `pen_down()` - Lower pen (start drawing)
- `at_goal()` - Return True if turtle is at goal position

Each function:
- Emits JSON commands via `print(json.dumps(...))`
- Uses `inspect.stack()` to capture line numbers
- Updates internal state variables (`_x`, `_y`, `_heading`, `_pen_down`)

#### Canvas System

**Coordinate System**:
- Two overlaid 600x600px canvas elements
- Background canvas: solution path (light gray)
- Foreground canvas: user path (blue)
- Logical coordinates: -10 to +10 in both X and Y (20 units total)
- Scale: 1 logical unit = 30 pixels
- Origin (0,0) at canvas center (300, 300)
- Heading: 0° = north (up), 90° = east (right), 180° = south (down), 270° = west (left)
- Y-axis: Canvas Y increases downward, but turtle logic Y increases upward (standard math)

**Turtle Visualization**:
- Non-filled circle outline (8px radius)
- Small filled triangle at edge pointing in heading direction
- Both turtle and path drawn in accent color (CSS variable `--accent-color`)

**Goal Visualization** (optional):
- Filled green circle (6px radius)
- Only shown if solution contains `at_goal()` call
- Position determined by final turtle position after executing solution

#### Animation System

**Speed Control**:
- Slider range: 5-2000 (stored in `animationSpeed`)
- Actual delay calculated as `2005 - animationSpeed`
- Higher slider value = slower animation
- Default: 1500 → ~505ms delay

**Animation Features**:
- Forward movement broken into 0.1-unit increments for smoothness
- Rotation animated over 10 steps
- Jump-to animated over 20 interpolated steps
- Cancellable via Reset button
- Path segments accumulated for win detection

**Run/Reset Button Behavior**:
- Initial: "Run" button (green/primary)
- After Run: Changes to "Reset" button (red/danger)
- Reset: Clears user canvas, resets state, shows initial turtle

#### Win Detection

The first `correct_answers[0].answer` is sent to the frontend as `solution_code` and executed to draw the reference pattern.

The system checks if the student's solution matches the reference by:

1. **Path Matching**: Compares all drawn line segments
   - Segments broken into 0.1-unit increments
   - Normalized with epsilon tolerance (0.1)
   - Direction-independent (line A→B equals B→A)
   - Must match exactly (same segments, same count)

2. **Position Matching**: Compares final position
   - Epsilon tolerance: 0.1 units
   - Checks both X and Y coordinates

3. **Confetti Effect**: Triggers on win (using canvas-confetti library)

#### Key Methods

- `initPyodide()` - Load Pyodide from CDN, set up stdout capture
- `executeSolutionCode()` - Execute solution, detect goal mode, draw reference
- `executeUserCode()` - Execute user code with animation
- `executeUserCodeInstant()` - Execute without animation (for Submit)
- `animateCommands()` - Step-by-step animation with speed control
- `drawPath()` - Render command sequence on canvas
- `drawTurtle()` - Render turtle circle with directional triangle
- `drawGoal()` - Render goal circle (if applicable)
- `checkWinCondition()` - Compare user path to solution
- `submitAnswer()` - Execute code, send to guidance API with turtle state
- `giveHint()` / `handleQuestion()` - Request AI guidance
- `resetExercise()` - Clear state, redraw solution, show initial turtle

### Template

**File**: `steacher_app/templates/exercises/students/turtle.html` 

The template extends `exercises/exercise.html` and provides a three-column grid layout:

#### Left Panel
- Exercise question (rendered Markdown)
- CodeMirror editor (Python mode)
- Control buttons: Run/Reset, Submit, Gimme a Hint
- Animation speed slider
- Error console
- Help box with common turtle commands

#### Middle Panel
- Canvas container with two overlaid canvases
- Instruction log table showing:
  - Instruction executed
  - Position (X, Y)
  - Heading (degrees with tooltip)

#### Right Panel
- ChatbotPanel component for AI tutor

### Styling

**File**: `steacher_app/static/css/style.css` 

All turtle-specific CSS classes prefixed with `turtle-`:


## Known Limitations

1. **No Auto-centering**: If drawing goes off-canvas, it's clipped (KISS approach)
2. **No Grid Lines**: Canvas is blank except for paths (KISS approach)
3. **Single Solution Reference**: Only first correct answer shown as reference
4. **Epsilon Tolerance**: Very precise paths might fail matching (0.1 unit tolerance)
5. **No Step-back**: Cannot undo individual commands during animation
