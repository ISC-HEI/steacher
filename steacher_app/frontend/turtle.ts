// Coordinates the turtle exercise runtime with Pyodide-backed Python execution.
// Drives the Vue UI so learners see why their turtle path matches the expected outcome.
import { ChatbotPanel } from './ChatbotPanel.js';
import { CodeMirrorEditor } from './CodeMirrorEditor.js';
import { createApp, defineComponent } from 'vue';
import confetti from 'canvas-confetti';
import type { Exercise } from './utils.js';
import { csrfFetch } from './utils.js';
import { renderMarkdown } from './markdown_utils.js';

interface TurtleState {
    x: number;
    y: number;
    heading: number;  // 0=north, 90=east, 180=south, 270=west
    penDown: boolean;
}

interface TurtleCommand {
    cmd: string;
    value?: number;
    x?: number;
    y?: number;
    degrees?: number;
    lineno?: number;
}

interface PathSegment {
    fromX: number;
    fromY: number;
    toX: number;
    toY: number;
}

interface InstructionLogEntry {
    stepId: number;
    x: number;
    y: number;
    heading: number;
    instruction: string;
    lineno: number | null;
}

interface TurtleDataContext {
    exercise: Exercise;
    userCode: string;
    loadingState: 'idle' | 'pyodide-loading' | 'executing' | 'getting-guidance';
    executionError: string | null;
    worker: Worker | null;
    workerReady: boolean;
    pendingResolvers: { [runId: string]: (value: any) => void };
    executionTimeoutMs: number;
    commands: TurtleCommand[];
    solutionCommands: TurtleCommand[];
    currentTurtleState: TurtleState;
    hasRun: boolean;
    isAnimating: boolean;
    animationCancelled: boolean;
    pathSegments: PathSegment[];
    staticPrefix: string;
    start_timestamp: string;
    instructionLog: InstructionLogEntry[];
    hasWon: boolean;
    confettiShown: boolean;
    animationSpeed: number;  // Slider position (0-9); converted to exponential speed scale (1-30 units/sec)
    currentHighlightedLine: number | null;
}

// Embed the Python helpers so learner code and the shim share one interpreter environment.
const TURTLE_API_PYTHON = `
import inspect
import json

# Internal state
_x = 0.0
_y = 0.0
_heading = 0  # 0=north, 90=east, 180=south, 270=west
_pen_down = True

def _emit(data):
    print(json.dumps(data))

def forward(steps=1):
    """Move turtle forward by given steps."""
    global _x, _y, _heading, _pen_down
    frame = inspect.stack()[1]
    _emit({"cmd": "forward", "value": steps, "lineno": frame.lineno})
    import math
    rad = math.radians(_heading)
    _x += steps * math.sin(rad)
    _y += steps * math.cos(rad)

def turn_left(degrees=90):
    """Turn turtle left by given degrees (default 90)."""
    global _heading
    frame = inspect.stack()[1]
    _emit({"cmd": "turn_left", "degrees": degrees, "lineno": frame.lineno})
    _heading = (_heading - degrees) % 360

def turn_right(degrees=90):
    """Turn turtle right by given degrees (default 90)."""
    global _heading
    frame = inspect.stack()[1]
    _emit({"cmd": "turn_right", "degrees": degrees, "lineno": frame.lineno})
    _heading = (_heading + degrees) % 360

def jump_to(x, y):
    """Teleport turtle to position (x, y)."""
    global _x, _y
    frame = inspect.stack()[1]
    _emit({"cmd": "jump_to", "x": x, "y": y, "lineno": frame.lineno})
    _x = x
    _y = y

def pen_up():
    """Lift pen (stop drawing)."""
    global _pen_down
    frame = inspect.stack()[1]
    _emit({"cmd": "pen_up", "lineno": frame.lineno})
    _pen_down = False

def pen_down():
    """Lower pen (start drawing)."""
    global _pen_down
    frame = inspect.stack()[1]
    _emit({"cmd": "pen_down", "lineno": frame.lineno})
    _pen_down = True

def get_x():
    """Return the turtle's current X position. Does not emit a command."""
    global _x
    return _x

def get_y():
    """Return the turtle's current Y position. Does not emit a command."""
    global _y
    return _y
`;

// Count lines in the preamble so we can adjust line numbers for highlighting
const TURTLE_API_LINE_COUNT = TURTLE_API_PYTHON.split('\n').length - 1 + 1; // -1 for the preamble, +1 for "Inject goal position if present"

const PIXELS_PER_UNIT = 30; // Keeps logical units aligned with a 600px canvas so cells map cleanly to grid lines.

function getCSSVariable(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Wait for templates to hydrate so we can grab server-injected JSON safely.
document.addEventListener('DOMContentLoaded', function() {
    const exerciseDataScript = document.getElementById('exercise-data');
    const appElement = document.getElementById('turtle-exercise-app');

    if (!exerciseDataScript || !appElement) {
        console.error('Required script tags or app element not found!');
        return;
    }
    const exerciseData: Exercise = JSON.parse(exerciseDataScript.textContent || '{}');

    const attemptIdScript = document.getElementById('attempt-id');
    let attemptId: number | null = null;
    if (attemptIdScript && attemptIdScript.textContent) {
        attemptId = JSON.parse(attemptIdScript.textContent);
    }

    const interactionsScript = document.getElementById('interactions-data');
    let initialMessages: any[] = [];
    let lastUserCode = '';
    if (interactionsScript) {
        const logs = JSON.parse(interactionsScript.textContent || '[]') as any[];
        for (let i = logs.length - 1; i >= 0; i--) {
            const log = logs[i];
            if (log.user_submission && log.user_submission.metadata && log.user_submission.metadata.code) {
                lastUserCode = log.user_submission.metadata.code;
                break;
            }
        }
        logs.forEach((log: any) => {
            if (log.user_submission) initialMessages.push(log.user_submission);
            if (log.llm_response) initialMessages.push(log.llm_response);
        });
    }

    const TurtleExerciseApp = defineComponent({
        delimiters: ['[[', ']]'],
        data(): TurtleDataContext {
            const datasetEl = appElement as HTMLElement;
            const staticPrefix = datasetEl?.getAttribute('data-static-prefix') || '/static/';
            const timeoutAttr = datasetEl?.getAttribute('data-execution-timeout');
            const executionTimeoutMs = timeoutAttr ? parseInt(timeoutAttr, 10) : 8000;
            return {
                exercise: exerciseData,
                userCode: lastUserCode || (exerciseData.exercise_data && exerciseData.exercise_data.answer_template) || '',
                loadingState: 'idle',
                executionError: null,
                worker: null,
                workerReady: false,
                pendingResolvers: {},
                executionTimeoutMs,
                commands: [],
                solutionCommands: [],
                currentTurtleState: { x: 0, y: 0, heading: 0, penDown: true },
                hasRun: false,
                isAnimating: false,
                animationCancelled: false,
                pathSegments: [],
                staticPrefix,
                start_timestamp: new Date().toISOString(),
                instructionLog: [{ stepId: 0, x: 0.00, y: 0.00, heading: 0, instruction: '(start position)', lineno: null }],
                hasWon: false,
                confettiShown: false,
                animationSpeed: 2,  // Default slider position (0-9), gives ~2.2 units/sec
                currentHighlightedLine: null
            }
        },

        async mounted() {
            const chatbotPanel = this.$refs.chatbotPanel as any;

            const feedbackScript = document.getElementById('completion-feedback-data');
            if (feedbackScript && feedbackScript.textContent) {
                try {
                    const feedbackData = JSON.parse(feedbackScript.textContent);
                    if (feedbackData && chatbotPanel) {
                        chatbotPanel.displayRecommendation(feedbackData);
                    }
                } catch (e) {
                    console.error("Failed to parse completion feedback data", e);
                }
            }

            if (chatbotPanel) {
                initialMessages.forEach(msg => chatbotPanel.displayMessage(msg));
            }

            await this.startWorker();
            await this.executeSolutionCode();
            this.drawInitialTurtle();

            // Expose for quiz mode
            (window as any).submitAnswer = () => this.submitAnswer();
        },

        methods: {
            getUnitsPerSecond(): number {
                // Exponential scaling from 1 to 200 units/sec across slider positions 0-9
                const minSpeed = 1;
                const maxSpeed = 200;
                const normalized = this.animationSpeed / 9;
                return minSpeed * Math.pow(maxSpeed / minSpeed, normalized);
            },

            renderMarkdown(this: any, content: string) {
                return renderMarkdown(content, false);
            },

            checkBounds(state: TurtleState): boolean {
                const limit = 10.05;
                if (state.x < -limit || state.x > limit || state.y < -limit || state.y > limit) {
                    this.executionError = `Turtle went out of bounds at position (${state.x.toFixed(2)}, ${state.y.toFixed(2)})! Stay within -10 to +10.`;
                    return false;
                }
                return true;
            },

            async startWorker() {
                try {
                    console.log('[turtle] Starting worker...');
                    this.loadingState = 'pyodide-loading';
                    const cacheBust = Date.now();
                    const workerUrl = `${this.staticPrefix}js/dist/python_worker.js?v=${cacheBust}`;
                    console.log('[turtle] Worker URL:', workerUrl);
                    const w = new Worker(workerUrl, { type: 'module' });
                    this.worker = w;

                    // Create a promise that resolves when worker is ready
                    const workerReadyPromise = new Promise<void>((resolve, reject) => {
                        w.onmessage = (evt: MessageEvent) => {
                            const msg = evt.data as any;
                            if (!msg || !msg.type) return;
                            if (msg.type === 'ready') {
                                console.log('[turtle] Worker ready!');
                                this.workerReady = true;
                                this.loadingState = 'idle';
                                resolve();
                                return;
                            }
                            if (msg.type === 'init-error') {
                                console.error('[turtle] Worker init error:', msg.error);
                                this.executionError = 'Failed to initialize Python interpreter: ' + String(msg.error);
                                this.loadingState = 'idle';
                                reject(new Error(msg.error));
                                return;
                            }
                            if (msg.type === 'result') {
                                const { runId } = msg;
                                console.log('[turtle] Worker result for runId:', runId);
                                const resolver = this.pendingResolvers[runId];
                                if (resolver) {
                                    resolver(msg);
                                    delete this.pendingResolvers[runId];
                                }
                                return;
                            }
                        };
                    });

                    const pyodideModuleUrl = `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs?v=${cacheBust}`;
                    const indexURL = `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/`;
                    console.log('[turtle] Sending init message to worker');
                    w.postMessage({ type: 'init', pyodideModuleUrl, indexURL });
                    
                    // Wait for worker to be ready before returning
                    await workerReadyPromise;
                    console.log('[turtle] startWorker completed');
                } catch (error) {
                    console.error('[turtle] Failed to start worker:', error);
                    this.executionError = 'Failed to start Python worker: ' + String(error);
                    this.loadingState = 'idle';
                }
            },

            async executeCode(code: string): Promise<{ success: boolean; stdout?: string; error?: string }> {
                if (!this.worker || !this.workerReady) {
                    console.log('[turtle] Worker not ready');
                    return { success: false, error: 'Python worker not ready yet' };
                }

                console.log('[turtle] Executing code in worker...');
                const runId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
                const resultPromise = new Promise((resolve) => {
                    this.pendingResolvers[runId] = resolve as (value: any) => void;
                }) as Promise<any>;

                this.worker.postMessage({ type: 'run', runId, code });

                let timedOut = false;
                const timeoutHandle = setTimeout(() => {
                    timedOut = true;
                    console.log('[turtle] Execution timed out, terminating worker');
                    try {
                        this.worker?.terminate();
                    } catch (_) { /* noop */ }
                    this.worker = null;
                    this.workerReady = false;
                    const resolver = this.pendingResolvers[runId];
                    if (resolver) {
                        resolver({ success: false, error: `Execution timed out after ${this.executionTimeoutMs / 1000} seconds` });
                    }
                    delete this.pendingResolvers[runId];
                }, this.executionTimeoutMs);

                const msg = await resultPromise.catch((e) => ({ error: String(e), success: false }));
                clearTimeout(timeoutHandle);

                if (timedOut) {
                    return { success: false, error: `Execution timed out after ${this.executionTimeoutMs / 1000} seconds. Your code may contain an infinite loop.` };
                }

                console.log('[turtle] Execution result:', { success: msg.success, stdoutLength: msg.stdout?.length, error: msg.error });
                return msg;
            },

            async executeSolutionCode() {
                console.log('[turtle] executeSolutionCode started');
                if (!this.workerReady || !this.worker) {
                    console.log('[turtle] Worker not ready for solution');
                    return;
                }
                
                const solution = (this.exercise as any).solution_code;
                if (!solution) {
                    console.log('[turtle] No solution provided, skipping solution drawing');
                    return;
                }

                console.log('[turtle] Solution code length:', solution.length);

                try {
                    const fullCode = TURTLE_API_PYTHON + '\n' + solution;
                    const result = await this.executeCode(fullCode);

                    if (!result.success) {
                        console.error('[turtle] Error executing solution:', result.error);
                        return;
                    }

                    console.log('[turtle] Solution stdout:', result.stdout);

                    // Parse turtle commands from stdout
                    const commands: TurtleCommand[] = [];
                    if (result.stdout) {
                        result.stdout.split('\n').forEach(line => {
                            if (line.trim()) {
                                try {
                                    const cmd = JSON.parse(line.trim());
                                    commands.push(cmd);
                                } catch (e) {
                                    console.log('[turtle] Failed to parse line as JSON:', line);
                                }
                            }
                        });
                    }

                    console.log('[turtle] Solution commands parsed:', commands.length, commands);
                    this.solutionCommands = commands;

                    this.drawSolution();
                    console.log('[turtle] Solution drawn');

                } catch (error) {
                    console.error('[turtle] Error executing solution:', error);
                }
            },

            simulateCommands(commands: TurtleCommand[]): TurtleState {
                let state = { x: 0, y: 0, heading: 0, penDown: true };
                commands.forEach(cmd => {
                    if (cmd.cmd === 'forward' && cmd.value) {
                        const rad = (state.heading * Math.PI) / 180;
                        state.x += cmd.value * Math.sin(rad);
                        state.y += cmd.value * Math.cos(rad);
                    } else if (cmd.cmd === 'turn_left' && cmd.degrees) {
                        state.heading = (state.heading - cmd.degrees + 360) % 360;
                    } else if (cmd.cmd === 'turn_right' && cmd.degrees) {
                        state.heading = (state.heading + cmd.degrees) % 360;
                    } else if (cmd.cmd === 'jump_to' && cmd.x !== undefined && cmd.y !== undefined) {
                        state.x = cmd.x;
                        state.y = cmd.y;
                    } else if (cmd.cmd === 'pen_up') {
                        state.penDown = false;
                    } else if (cmd.cmd === 'pen_down') {
                        state.penDown = true;
                    }
                });
                return state;
            },

            extractPathSegments(commands: TurtleCommand[]): PathSegment[] {
                const segments: PathSegment[] = [];
                let state = { x: 0, y: 0, heading: 0, penDown: true };
                
                commands.forEach(cmd => {
                    if (cmd.cmd === 'forward' && cmd.value) {
                        // Break into small segments for accurate path comparison
                        const segmentSize = 0.1;
                        const numSegments = Math.ceil(cmd.value / segmentSize);
                        
                        for (let i = 0; i < numSegments; i++) {
                            const oldX = state.x;
                            const oldY = state.y;
                            const rad = (state.heading * Math.PI) / 180;
                            
                            // Move by segmentSize, or remainder if this is the last segment
                            const distance = (i === numSegments - 1) ? (cmd.value - i * segmentSize) : segmentSize;
                            state.x += distance * Math.sin(rad);
                            state.y += distance * Math.cos(rad);
                            
                            if (state.penDown) {
                                segments.push({ fromX: oldX, fromY: oldY, toX: state.x, toY: state.y });
                            }
                        }
                    } else if (cmd.cmd === 'turn_left' && cmd.degrees) {
                        state.heading = (state.heading - cmd.degrees + 360) % 360;
                    } else if (cmd.cmd === 'turn_right' && cmd.degrees) {
                        state.heading = (state.heading + cmd.degrees) % 360;
                    } else if (cmd.cmd === 'jump_to' && cmd.x !== undefined && cmd.y !== undefined) {
                        state.x = cmd.x;
                        state.y = cmd.y;
                    } else if (cmd.cmd === 'pen_up') {
                        state.penDown = false;
                    } else if (cmd.cmd === 'pen_down') {
                        state.penDown = true;
                    }
                });
                
                return segments;
            },

            normalizeSegment(seg: PathSegment): string {
                const epsilon = 0.1;
                const x1 = Math.round(seg.fromX / epsilon) * epsilon;
                const y1 = Math.round(seg.fromY / epsilon) * epsilon;
                const x2 = Math.round(seg.toX / epsilon) * epsilon;
                const y2 = Math.round(seg.toY / epsilon) * epsilon;
                
                // Normalize direction: always store with smaller coordinate first
                if (x1 < x2 || (x1 === x2 && y1 < y2)) {
                    return `${x1.toFixed(1)},${y1.toFixed(1)}-${x2.toFixed(1)},${y2.toFixed(1)}`;
                } else {
                    return `${x2.toFixed(1)},${y2.toFixed(1)}-${x1.toFixed(1)},${y1.toFixed(1)}`;
                }
            },

            pathsMatch(userSegments: PathSegment[], solutionSegments: PathSegment[]): boolean {
                const userSet = new Set(userSegments.map(seg => this.normalizeSegment(seg)));
                const solutionSet = new Set(solutionSegments.map(seg => this.normalizeSegment(seg)));
                
                if (userSet.size !== solutionSet.size) return false;
                
                for (const seg of solutionSet) {
                    if (!userSet.has(seg)) return false;
                }
                
                return true;
            },

            checkWinCondition(): boolean {
                if (this.solutionCommands.length === 0) {
                    return false;
                }

                const userSegments = this.extractPathSegments(this.commands);
                const solutionSegments = this.extractPathSegments(this.solutionCommands);

                // Compare the path, not just final position, so learners practice sequences not teleports.
                const pathsMatch = this.pathsMatch(userSegments, solutionSegments);

                const solutionFinalState = this.simulateCommands(this.solutionCommands);
                const epsilon = 0.1;
                const positionMatches = 
                    Math.abs(this.currentTurtleState.x - solutionFinalState.x) < epsilon &&
                    Math.abs(this.currentTurtleState.y - solutionFinalState.y) < epsilon;

                return pathsMatch && positionMatches;
            },

            logicalToCanvas(x: number, y: number): { cx: number; cy: number } {
                // Convert logical coords (-10 to +10) to canvas pixels (0 to 600)
                const cx = 300 + x * PIXELS_PER_UNIT;
                const cy = 300 - y * PIXELS_PER_UNIT; // Y inverted for canvas
                return { cx, cy };
            },

            drawSolution() {
                const canvas = this.$refs.solutionCanvas as HTMLCanvasElement;
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                if (!ctx) return;

                ctx.clearRect(0, 0, canvas.width, canvas.height);

                // Draw axis lines first (background)
                this.drawAxisLines(ctx);

                // Draw solution path
                ctx.strokeStyle = getCSSVariable('--accent-muted');
                ctx.lineWidth = 2;
                this.drawPath(ctx, this.solutionCommands);
            },

            drawPath(ctx: CanvasRenderingContext2D, commands: TurtleCommand[]) {
                let state = { x: 0, y: 0, heading: 0, penDown: true };
                
                let canvasPos = this.logicalToCanvas(state.x, state.y);
                ctx.beginPath();
                ctx.moveTo(canvasPos.cx, canvasPos.cy);

                commands.forEach(cmd => {
                    if (cmd.cmd === 'forward' && cmd.value) {
                        const rad = (state.heading * Math.PI) / 180;
                        state.x += cmd.value * Math.sin(rad);
                        state.y += cmd.value * Math.cos(rad);
                        canvasPos = this.logicalToCanvas(state.x, state.y);
                        if (state.penDown) {
                            ctx.lineTo(canvasPos.cx, canvasPos.cy);
                        } else {
                            ctx.moveTo(canvasPos.cx, canvasPos.cy);
                        }
                    } else if (cmd.cmd === 'turn_left' && cmd.degrees) {
                        state.heading = (state.heading - cmd.degrees + 360) % 360;
                    } else if (cmd.cmd === 'turn_right' && cmd.degrees) {
                        state.heading = (state.heading + cmd.degrees) % 360;
                    } else if (cmd.cmd === 'jump_to' && cmd.x !== undefined && cmd.y !== undefined) {
                        state.x = cmd.x;
                        state.y = cmd.y;
                        canvasPos = this.logicalToCanvas(state.x, state.y);
                        ctx.moveTo(canvasPos.cx, canvasPos.cy);
                    } else if (cmd.cmd === 'pen_up') {
                        state.penDown = false;
                    } else if (cmd.cmd === 'pen_down') {
                        state.penDown = true;
                    }
                });

                ctx.stroke();
            },

            drawAxisLines(ctx: CanvasRenderingContext2D) {
                /* Draws the axis lines for the grid */
                
                const centerX = 300;
                const centerY = 300;
                
                ctx.strokeStyle = '#dddddd';
                ctx.lineWidth = 0.1;
                ctx.beginPath();
                
                // Vertical center line
                ctx.moveTo(centerX, 0);
                ctx.lineTo(centerX, 600);
                
                // Horizontal center line
                ctx.moveTo(0, centerY);
                ctx.lineTo(600, centerY);
                
                ctx.stroke();
            },

            drawTurtle(ctx: CanvasRenderingContext2D, x: number, y: number, heading: number, penDown: boolean = true) {
                const pos = this.logicalToCanvas(x, y);
                const radius = 8;
                const color = getCSSVariable('--accent-color');
                
                // Draw circle (outline only)
                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                
                // Use dashed line when pen is up
                if (!penDown) {
                    ctx.setLineDash([4, 4]);
                }
                
                ctx.beginPath();
                ctx.arc(pos.cx, pos.cy, radius, 0, 2 * Math.PI);
                ctx.stroke();
                
                // Reset line dash
                if (!penDown) {
                    ctx.setLineDash([]);
                }

                // Only draw directional triangle when pen is down
                if (penDown) {
                    ctx.save();
                    ctx.translate(pos.cx, pos.cy);
                    ctx.rotate((heading * Math.PI) / 180);
                    
                    const triangleSize = 10;
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.moveTo(0, -radius - triangleSize); // Point outside circle
                    ctx.lineTo(-triangleSize * 0.6, -radius * 0.8); // Left corner at circle edge
                    ctx.lineTo(triangleSize * 0.6, -radius * 0.8); // Right corner at circle edge
                    ctx.closePath();
                    ctx.fill();
                    
                    ctx.restore();
                }
            },

            drawInitialTurtle() {
                const canvas = this.$refs.userCanvas as HTMLCanvasElement;
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                if (!ctx) return;

                ctx.clearRect(0, 0, canvas.width, canvas.height);
                this.drawTurtle(ctx, 0, 0, 0);
            },

            async executeUserCode() {
                console.log('[turtle] executeUserCode started');
                if (!this.workerReady || !this.worker) {
                    this.executionError = 'Python interpreter not ready yet. Please wait...';
                    console.log('[turtle] Worker not ready for user code');
                    return;
                }

                try {
                    this.loadingState = 'executing';
                    this.executionError = null;

                    const fullCode = TURTLE_API_PYTHON + '\n' + this.userCode;
                    console.log('[turtle] User code length:', this.userCode.length);
                    const result = await this.executeCode(fullCode);

                    if (!result.success) {
                        console.error('[turtle] Error executing user code:', result.error);
                        this.executionError = this.cleanPythonError(result.error || 'Unknown error');
                        if (this.executionError.includes('timed out')) {
                            await this.startWorker(); // Restart worker after timeout
                        }
                        return;
                    }

                    console.log('[turtle] User stdout:', result.stdout);

                    // Parse turtle commands from stdout
                    const commands: TurtleCommand[] = [];
                    if (result.stdout) {
                        result.stdout.split('\n').forEach(line => {
                            if (line.trim()) {
                                try {
                                    const cmd = JSON.parse(line.trim());
                                    commands.push(cmd);
                                } catch (e) {
                                    console.log('[turtle] Failed to parse user line as JSON:', line);
                                }
                            }
                        });
                    }

                    console.log('[turtle] User commands parsed:', commands.length, commands);
                    this.commands = commands;
                    this.hasRun = true;
                    
                    await this.animateCommands(commands);

                } catch (error) {
                    console.error('[turtle] Error in executeUserCode:', error);
                    this.executionError = this.cleanPythonError(String(error));
                } finally {
                    this.loadingState = 'idle';
                }
            },

            async animateCommands(commands: TurtleCommand[]) {
                const animationStartTime = performance.now();
               
                const canvas = this.$refs.userCanvas as HTMLCanvasElement;
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                if (!ctx) return;

                ctx.clearRect(0, 0, canvas.width, canvas.height);
                this.isAnimating = true;
                this.animationCancelled = false;
                this.pathSegments = [];

                let state = { x: 0, y: 0, heading: 0, penDown: true };
                this.currentTurtleState = { ...state };
                
                let stepId = 0;

                for (const cmd of commands) {
                    if (this.animationCancelled) break;

                    // Highlight the line being executed
                    if (cmd.lineno) {
                        this.highlightLine(cmd.lineno);
                    }

                    if (cmd.cmd === 'forward' && cmd.value) {
                        await this.animateForward(ctx, state, cmd.value);
                        stepId++;
                        this.instructionLog.push({
                            stepId,
                            x: state.x,
                            y: state.y,
                            heading: state.heading,
                            instruction: `forward(${cmd.value})`,
                            lineno: cmd.lineno ? cmd.lineno - TURTLE_API_LINE_COUNT : null
                        });
                        if (!this.checkBounds(state)) break;
                    } else if (cmd.cmd === 'turn_left' && cmd.degrees) {
                        await this.animateRotation(ctx, state, -cmd.degrees);
                        // animateRotation already updated state.heading
                        this.currentTurtleState = { ...state };
                        stepId++;
                        this.instructionLog.push({
                            stepId,
                            x: state.x,
                            y: state.y,
                            heading: state.heading,
                            instruction: `turn_left(${cmd.degrees})`,
                            lineno: cmd.lineno ? cmd.lineno - TURTLE_API_LINE_COUNT : null
                        });
                    } else if (cmd.cmd === 'turn_right' && cmd.degrees) {
                        await this.animateRotation(ctx, state, cmd.degrees);
                        // animateRotation already updated state.heading
                        this.currentTurtleState = { ...state };
                        stepId++;
                        this.instructionLog.push({
                            stepId,
                            x: state.x,
                            y: state.y,
                            heading: state.heading,
                            instruction: `turn_right(${cmd.degrees})`,
                            lineno: cmd.lineno ? cmd.lineno - TURTLE_API_LINE_COUNT : null
                        });
                    } else if (cmd.cmd === 'jump_to' && cmd.x !== undefined && cmd.y !== undefined) {
                        await this.animateJumpTo(ctx, state, cmd.x, cmd.y);
                        state.x = cmd.x;
                        state.y = cmd.y;
                        this.currentTurtleState = { ...state };
                        stepId++;
                        this.instructionLog.push({
                            stepId,
                            x: state.x,
                            y: state.y,
                            heading: state.heading,
                            instruction: `jump_to(${cmd.x}, ${cmd.y})`,
                            lineno: cmd.lineno ? cmd.lineno - TURTLE_API_LINE_COUNT : null
                        });
                        if (!this.checkBounds(state)) break;
                    } else if (cmd.cmd === 'pen_up') {
                        state.penDown = false;
                    } else if (cmd.cmd === 'pen_down') {
                        state.penDown = true;
                    }
                }

                this.isAnimating = false;
                this.hasRun = false;

                // Clear highlight after animation completes
                this.clearHighlight();

                // Check win condition after animation completes
                if (!this.animationCancelled && this.checkWinCondition()) {
                    this.hasWon = true;
                    if (!this.confettiShown) {
                        console.log('Win condition met: Firing confetti! 🎊');
                        confetti({ particleCount: 200, spread: 150, origin: { y: 0.6 } });
                        this.confettiShown = true;
                    }
                }

                const animationEndTime = performance.now();
                const totalTimeMs = animationEndTime - animationStartTime;
                console.log('[turtle] Animation completed in', totalTimeMs.toFixed(2), 'ms');
            },

            async animateForward(ctx: CanvasRenderingContext2D, state: TurtleState, distance: number) {
                const startX = state.x;
                const startY = state.y;
                const rad = (state.heading * Math.PI) / 180;
                const endX = startX + distance * Math.sin(rad);
                const endY = startY + distance * Math.cos(rad);
                
                const unitsPerSecond = this.getUnitsPerSecond();
                const durationMs = (distance / unitsPerSecond) * 1000;
                
                const startTime = performance.now();
                
                return new Promise<void>((resolve) => {
                    const animate = (currentTime: number) => {
                        if (this.animationCancelled) {
                            // Jump to end position if cancelled
                            state.x = endX;
                            state.y = endY;
                            if (state.penDown) {
                                this.pathSegments.push({ fromX: startX, fromY: startY, toX: endX, toY: endY });
                            }
                            this.currentTurtleState = { ...state };
                            this.redrawCanvas(ctx, state);
                            resolve();
                            return;
                        }
                        
                        const elapsed = currentTime - startTime;
                        const progress = Math.min(elapsed / durationMs, 1.0);
                        
                        const currentX = startX + (endX - startX) * progress;
                        const currentY = startY + (endY - startY) * progress;
                        
                        // Update path segments incrementally for smooth drawing
                        if (state.penDown && progress > 0) {
                            const lastSegment = this.pathSegments[this.pathSegments.length - 1];
                            if (lastSegment && lastSegment.fromX === startX && lastSegment.fromY === startY) {
                                // Update the last segment endpoint
                                lastSegment.toX = currentX;
                                lastSegment.toY = currentY;
                            } else {
                                // Create new segment
                                this.pathSegments.push({ fromX: startX, fromY: startY, toX: currentX, toY: currentY });
                            }
                        }
                        
                        state.x = currentX;
                        state.y = currentY;
                        this.currentTurtleState = { ...state };
                        this.redrawCanvas(ctx, state);
                        
                        if (progress < 1.0) {
                            requestAnimationFrame(animate);
                        } else {
                            resolve();
                        }
                    };
                    
                    requestAnimationFrame(animate);
                });
            },

            redrawCanvas(ctx: CanvasRenderingContext2D, state: TurtleState) {
                ctx.clearRect(0, 0, 600, 600);
                
                // Draw axis lines first (background)
                this.drawAxisLines(ctx);
                
                // Redraw all path segments
                ctx.strokeStyle = getCSSVariable('--accent-color');
                ctx.lineWidth = 2;
                ctx.beginPath();
                this.pathSegments.forEach(seg => {
                    const from = this.logicalToCanvas(seg.fromX, seg.fromY);
                    const to = this.logicalToCanvas(seg.toX, seg.toY);
                    ctx.moveTo(from.cx, from.cy);
                    ctx.lineTo(to.cx, to.cy);
                });
                ctx.stroke();
                
                // Draw turtle at current position
                this.drawTurtle(ctx, state.x, state.y, state.heading, state.penDown);
            },

            async animateRotation(ctx: CanvasRenderingContext2D, state: TurtleState, deltaDegrees: number) {
                const startHeading = state.heading;
                const endHeading = (startHeading + deltaDegrees + 360) % 360;
                
                const unitsPerSecond = this.getUnitsPerSecond();
                const degreesPerSecond = unitsPerSecond * 90; // 90° turn takes same time as moving 1 unit
                const durationMs = (Math.abs(deltaDegrees) / degreesPerSecond) * 1000;
                
                const startTime = performance.now();
                
                return new Promise<void>((resolve) => {
                    const animate = (currentTime: number) => {
                        if (this.animationCancelled) {
                            state.heading = endHeading;
                            this.currentTurtleState = { ...state };
                            this.redrawCanvas(ctx, state);
                            resolve();
                            return;
                        }
                        
                        const elapsed = currentTime - startTime;
                        const progress = Math.min(elapsed / durationMs, 1.0);
                        
                        const currentHeading = (startHeading + deltaDegrees * progress + 360) % 360;
                        state.heading = currentHeading;
                        this.currentTurtleState = { ...state };
                        this.redrawCanvas(ctx, state);
                        
                        if (progress < 1.0) {
                            requestAnimationFrame(animate);
                        } else {
                            resolve();
                        }
                    };
                    
                    requestAnimationFrame(animate);
                });
            },

            async animateJumpTo(ctx: CanvasRenderingContext2D, state: TurtleState, targetX: number, targetY: number) {
                const startX = state.x;
                const startY = state.y;
                const distance = Math.sqrt((targetX - startX) ** 2 + (targetY - startY) ** 2);
                
                const unitsPerSecond = this.getUnitsPerSecond();
                const durationMs = (distance / unitsPerSecond) * 1000;
                
                const startTime = performance.now();
                
                return new Promise<void>((resolve) => {
                    const animate = (currentTime: number) => {
                        if (this.animationCancelled) {
                            state.x = targetX;
                            state.y = targetY;
                            this.currentTurtleState = { ...state };
                            this.redrawCanvas(ctx, state);
                            resolve();
                            return;
                        }
                        
                        const elapsed = currentTime - startTime;
                        const progress = Math.min(elapsed / durationMs, 1.0);
                        
                        state.x = startX + (targetX - startX) * progress;
                        state.y = startY + (targetY - startY) * progress;
                        this.currentTurtleState = { ...state };
                        this.redrawCanvas(ctx, state);
                        
                        if (progress < 1.0) {
                            requestAnimationFrame(animate);
                        } else {
                            resolve();
                        }
                    };
                    
                    requestAnimationFrame(animate);
                });
            },

            delay(ms: number): Promise<void> {
                return new Promise(resolve => setTimeout(resolve, ms));
            },

            async executeUserCodeInstant() {
                // Execute without animation for Submit
                if (!this.workerReady || !this.worker) return;

                try {
                    this.loadingState = 'executing';
                    this.executionError = null;

                    const fullCode = TURTLE_API_PYTHON + '\n' + this.userCode;
                    const result = await this.executeCode(fullCode);

                    if (!result.success) {
                        this.executionError = this.cleanPythonError(result.error || 'Unknown error');
                        if (this.executionError.includes('timed out')) {
                            await this.startWorker(); // Restart worker after timeout
                        }
                        return;
                    }

                    // Parse turtle commands from stdout
                    const commands: TurtleCommand[] = [];
                    if (result.stdout) {
                        result.stdout.split('\n').forEach(line => {
                            try {
                                const cmd = JSON.parse(line.trim());
                                commands.push(cmd);
                            } catch (e) {
                                // Not JSON, ignore
                            }
                        });
                    }

                    this.commands = commands;
                    this.hasRun = true;
                    
                    // Draw instantly
                    const canvas = this.$refs.userCanvas as HTMLCanvasElement;
                    if (!canvas) return;
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return;

                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.strokeStyle = getCSSVariable('--accent-color');
                    ctx.lineWidth = 2;
                    this.drawPath(ctx, commands);

                    this.currentTurtleState = this.simulateCommands(commands);
                    this.drawTurtle(ctx, this.currentTurtleState.x, this.currentTurtleState.y, this.currentTurtleState.heading, this.currentTurtleState.penDown);

                    // Check bounds
                    if (!this.checkBounds(this.currentTurtleState)) {
                        return;
                    }

                    // Check win condition (for Submit without prior Run)
                    if (this.checkWinCondition()) {
                        this.hasWon = true;
                        if (!this.confettiShown) {
                            console.log('Win condition met: Firing confetti! 🎊');
                            confetti({ particleCount: 200, spread: 150, origin: { y: 0.6 } });
                            this.confettiShown = true;
                        }
                    }

                } catch (error) {
                    this.executionError = this.cleanPythonError(String(error));
                } finally {
                    this.loadingState = 'idle';
                }
            },

            resetExercise() {
                // Cancel any ongoing animation
                this.animationCancelled = true;
                this.isAnimating = false;

                // Clear both canvases
                const userCanvas = this.$refs.userCanvas as HTMLCanvasElement;
                const solutionCanvas = this.$refs.solutionCanvas as HTMLCanvasElement;
                
                if (userCanvas) {
                    const ctx = userCanvas.getContext('2d');
                    if (ctx) ctx.clearRect(0, 0, userCanvas.width, userCanvas.height);
                }
                if (solutionCanvas) {
                    const ctx = solutionCanvas.getContext('2d');
                    if (ctx) ctx.clearRect(0, 0, solutionCanvas.width, solutionCanvas.height);
                }

                // Redraw solution
                this.drawSolution();

                // Reset state
                this.currentTurtleState = { x: 0, y: 0, heading: 0, penDown: true };
                this.commands = [];
                this.pathSegments = [];
                this.hasRun = false;
                this.hasWon = false;
                this.confettiShown = false;
                this.instructionLog = [{ stepId: 0, x: 0.00, y: 0.00, heading: 0, instruction: '(start position)', lineno: null }];

                // Show initial turtle
                this.drawInitialTurtle();
            },

            headingToCompass(heading: number): string {
                // 0=N, 90=E, 180=S, 270=W
                const normalized = ((heading % 360) + 360) % 360;
                if (normalized >= 315 || normalized < 45) return 'N';
                if (normalized >= 45 && normalized < 135) return 'E';
                if (normalized >= 135 && normalized < 225) return 'S';
                return 'W';
            },

            async submitAnswer() {
                (window as any).hasAlreadySubmittedThisQuestion = true;

                if (!this.userCode.trim()) {
                    this.executionError = 'Please enter some code';
                    return;
                }

                // Execute code instantly (no animation) for submission
                await this.executeUserCodeInstant();

                // Send to guidance API
                this.loadingState = 'getting-guidance';
                try {
                    const payload = {
                        action: 'run_submission',
                        code: this.userCode,
                        output: null,
                        error_message: this.executionError,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString(),
                        turtle_state: {
                            final_position: { x: this.currentTurtleState.x, y: this.currentTurtleState.y },
                            final_heading: this.currentTurtleState.heading
                        }
                    };

                    const response = await csrfFetch(`/exercises/${this.exercise.id}/attempts/${attemptId}/guidance/`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });

                    if (!response.ok) {
                        throw new Error(`Server error: ${response.statusText}`);
                    }

                    const result = await response.json();
                    const chatbotPanel = this.$refs.chatbotPanel as any;
                    if (!chatbotPanel) return;

                    if (result.user_submission) {
                        chatbotPanel.displayMessage(result.user_submission);
                    }
                    if (result.guidance) {
                        if (result.guidance.includes('<exercise_completed>')) {
                            this.updateStatusIcon();
                        }
                        const assistantMsg: any = { role: 'assistant', content: result.guidance };
                        if (result.assistant_trace_id) assistantMsg.trace_id = result.assistant_trace_id;
                        if (result.thoughts) assistantMsg.thoughts = result.thoughts;
                        chatbotPanel.displayMessage(assistantMsg);
                    }
                } catch (error) {
                    this.executionError = `Error communicating with server: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                    (window as any).hasAlreadySubmittedThisQuestion = false;
                }
            },

            updateStatusIcon() {
                const iconContainer = document.getElementById('exercise-status-icon');
                if (!iconContainer) return;
                const existingIcon = iconContainer.querySelector('i');
                if (existingIcon) {
                    existingIcon.className = 'fas fa-check-circle has-text-success';
                    existingIcon.setAttribute('title', 'Completed');
                } else {
                    iconContainer.innerHTML = '<i class="fas fa-check-circle has-text-success" title="Completed"></i>';
                }
            },

            giveHint() {
                this.getGuidance('ask_hint');
            },

            handleQuestion(question: string) {
                this.getGuidance('ask_question', { question });
            },

            async getGuidance(action: string, details: { question?: string } = {}) {
                this.loadingState = 'getting-guidance';
                try {
                    const payload = {
                        action: action,
                        code: this.userCode,
                        question: details.question || null,
                        start_timestamp: this.start_timestamp,
                        submission_timestamp: new Date().toISOString(),
                    };

                    const response = await csrfFetch(`/exercises/${this.exercise.id}/attempts/${attemptId}/guidance/`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });

                    if (!response.ok) {
                        throw new Error(`Server error: ${response.statusText}`);
                    }

                    const result = await response.json();
                    const chatbotPanel = this.$refs.chatbotPanel as any;
                    if (!chatbotPanel) return;

                    if (result.user_submission) {
                        chatbotPanel.displayMessage(result.user_submission);
                    }
                    if (result.guidance) {
                        const assistantMsg: any = { role: 'assistant', content: result.guidance };
                        if (result.assistant_trace_id) assistantMsg.trace_id = result.assistant_trace_id;
                        if (result.thoughts) assistantMsg.thoughts = result.thoughts;
                        chatbotPanel.displayMessage(assistantMsg);
                    }
                } catch (error) {
                    this.executionError = `Error: ${error}`;
                } finally {
                    this.loadingState = 'idle';
                    this.start_timestamp = new Date().toISOString();
                }
            },

            cleanPythonError(errorMessage: string): string {
                // Find the line matching 'File "<exec>", line N, in <module>' and remove it and everything before
                const lines = errorMessage.split('\n');
                const execLineRegex = /.*File "<exec>", line \d+, in <module>/;
                
                let startIndex = -1;
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    if (line !== undefined && execLineRegex.test(line)) {
                        startIndex = i + 1; // Take everything after this line
                        break;
                    }
                }
                
                if (startIndex !== -1 && startIndex < lines.length) {
                    return lines.slice(startIndex).join('\n').trim();
                }
                
                return errorMessage.trim();
            },

            highlightLine(lineNumber: number) {
                const editorComponent = this.$refs.codeMirrorEditor as any;
                if (!editorComponent) return;
                
                const editor = editorComponent.getEditor();
                if (!editor) return;

                // Adjust line number: Python reports line in combined code (preamble + user code),
                // but editor only shows user code, so subtract preamble lines
                const adjustedLineNumber = lineNumber - TURTLE_API_LINE_COUNT;
                
                // Skip if line is in the preamble or out of range
                if (adjustedLineNumber <= 0 || adjustedLineNumber > editor.state.doc.lines) {
                    return;
                }

                this.currentHighlightedLine = adjustedLineNumber;

                try {
                    // Clear previous highlight first
                    const prevHighlighted = (this as any)._highlightedElement as HTMLElement;
                    if (prevHighlighted) {
                        prevHighlighted.classList.remove('cm-active-line-highlight');
                    }

                    // Use the EditorView DOM API to add a CSS class to the line
                    const line = editor.state.doc.line(adjustedLineNumber);
                    const lineElement = editor.domAtPos(line.from);
                    
                    // Find the line element in the DOM
                    let currentNode = lineElement.node as HTMLElement;
                    while (currentNode && !currentNode.classList?.contains('cm-line')) {
                        currentNode = currentNode.parentElement as HTMLElement;
                    }
                    
                    if (currentNode) {
                        currentNode.classList.add('cm-active-line-highlight');
                        // Store reference for clearing
                        (this as any)._highlightedElement = currentNode;
                    }
                } catch (e) {
                    console.warn('Error highlighting line:', e);
                }
            },

            clearHighlight() {
                this.currentHighlightedLine = null;
                
                // Remove the class from the previously highlighted element
                const highlightedElement = (this as any)._highlightedElement as HTMLElement;
                if (highlightedElement) {
                    highlightedElement.classList.remove('cm-active-line-highlight');
                    (this as any)._highlightedElement = null;
                }
            },
        },

        components: {
            'chatbot-panel': ChatbotPanel,
            'code-mirror-editor': CodeMirrorEditor
        }
    });

    createApp(TurtleExerciseApp).mount('#turtle-exercise-app');
});

