/* Teacher quiz control panel client, now using Vue for reactive state management. */

// @ts-ignore - global Vue from CDN
const { createApp } = (window as any).Vue;

type QuizConfig = {
    cohort_id: number;
    module_id: number;
    exercises: { id: number; title: string; question: string }[];
};

type QuizState = {
    state?: string;
    current_exercise_id?: string;
};

function main() {
    console.log('[quiz_control] boot');
    const configEl = document.getElementById('quiz-config');
    if (!configEl) { console.warn('[quiz_control] no config element'); return; }
    const config: QuizConfig = JSON.parse(configEl.textContent || '{}');
    console.log('[quiz_control] config', config);

    const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + `/ws/quiz/${config.cohort_id}/${config.module_id}/`;
    console.log('[quiz_control] wsUrl', wsUrl);
    const ws = new WebSocket(wsUrl);

    const app = createApp({
        delimiters: ['[[', ']]'],
        data() {
            return {
                presence: 0,
                state: { state: 'not_started' } as QuizState,
                selectedExerciseId: 'gathering' as string,
                countdownDuration: 5,
                countdownEndTime: null as number | null,
                nowTimestamp: Math.floor(Date.now() / 1000),
                resultsData: {
                    correct_count: null,  // bulma: don't set the progress bar value attribute --> display indeterminate progress bar
                    incorrect_count: 0,
                    submissions_count: 0,
                },
            };
        },
        computed: {
            showStartGathering(): boolean {
                const s = (this as any).state.state || 'not_started';
                const show = ['not_started', 'completed'].includes(s);
                return show;
            },
            showStartQuiz(): boolean {
                const s = (this as any).state.state || 'not_started';
                const show = s === 'gathering';
                return show;
            },
            currentExercise(): { id: number; title: string; question: string } | undefined {
                const exId = parseInt((this as any).state.current_exercise_id || '');
                return config.exercises.find(e => e.id === exId);
            },
            currentQuestionHtml(): string {
                const ce = (this as any).currentExercise as { id: number; title: string; question: string } | undefined;
                // Backend already provides question pre-rendered (markdown -> HTML). Use as-is.
                return ce && ce.question ? ce.question : '';
            },
            countdownRemaining(): number | null {
                const endTime = (this as any).countdownEndTime;
                if (endTime === null) return null;
                // Use reactive nowTimestamp to force Vue to re-compute every second
                const now = (this as any).nowTimestamp;
                const remaining = Math.max(0, endTime - now);
                return remaining;
            },
            correctPercent(): number {
                const data = (this as any).resultsData;
                const total = data.submissions_count || 1;
                return Math.round((data.correct_count / total) * 100);
            },
            incorrectPercent(): number {
                const data = (this as any).resultsData;
                const total = data.submissions_count || 1;
                return Math.round((data.incorrect_count / total) * 100);
            },
        },
        methods: {
            send(action: string, payload: any = {}) {
                console.log('[quiz_control] send', action, payload, 'readyState=', ws.readyState);
                if (ws.readyState === WebSocket.OPEN) {
                    try {
                        ws.send(JSON.stringify({ action, payload }));
                        console.log('[quiz_control] sent');
                    } catch (e) {
                        console.error('[quiz_control] send error', e);
                    }
                } else {
                    console.warn('[quiz_control] ws not open, cannot send');
                }
            },
            startGathering() {
                console.log('[quiz_control] startGathering click');
                this.send('start_gathering');
            },
            startQuiz() {
                let exIdStr = (this as any).selectedExerciseId;
                if (exIdStr === 'gathering' || !exIdStr) {
                    exIdStr = config.exercises[0] ? String(config.exercises[0].id) : '';
                }
                const exId = parseInt(exIdStr);
                console.log('[quiz_control] startQuiz click', { exIdStr, exId, wsReady: ws.readyState });
                if (!Number.isNaN(exId)) this.send('start_quiz', { exercise_id: exId });
            },
            startCountdown() {
                const duration = Math.max(5, (this as any).countdownDuration);
                console.log('[quiz_control] startCountdown click', { duration });
                this.send('start_countdown', { duration });
            },
            nextQuestion() {
                // Auto-advance to next exercise in sequence
                const currentExId = parseInt((this as any).state.current_exercise_id || '');
                const currentIndex = config.exercises.findIndex(e => e.id === currentExId);
                const nextIndex = currentIndex + 1;
                
                if (nextIndex < config.exercises.length) {
                    const nextEx = config.exercises[nextIndex];
                    if (nextEx) {
                        console.log('[quiz_control] nextQuestion click - advancing from', currentExId, 'to', nextEx.id);
                        this.send('next_question', { exercise_id: nextEx.id });
                    }
                } else {
                    console.log('[quiz_control] nextQuestion click - no more questions');
                    alert('No more questions. End the quiz or use the dropdown to jump to a specific question.');
                }
            },
            jumpTo() {
                const sel = (this as any).selectedExerciseId;
                console.log('[quiz_control] jumpTo click', { selected: sel });
                if (sel === 'gathering') {
                    this.startGathering();
                } else {
                    this.nextQuestion();
                }
            },
        }
    }).mount('#quiz-control-app');

    ws.addEventListener('open', () => {
        console.log('[quiz_control] ws open');
        (app as any).send('acquire_lock');
        // no teacher presence heartbeat needed
    });

    ws.addEventListener('message', (e) => {
        try {
            const data = JSON.parse(e.data);
            console.log('[quiz_control] ws message raw', data);
            if (data.type === 'quiz_state_update') {
                const raw = data.state || {};
                const nextState = (raw && (raw as any).state) ? raw : { state: 'not_started' };
                (app as any).state = nextState;
                const s = (nextState as any).state || '';
                const ex = (nextState as any).current_exercise_id || '';
                (app as any).presence = (data.presence && data.presence.count) || 0;
                console.log('[quiz_control] state update -> state:', s, 'current_exercise_id:', ex, 'presence:', (app as any).presence);
                
                // Clear countdown if state changes away from display_question
                if (s !== 'display_question') {
                    (app as any).countdownEndTime = null;
                }
            } else if (data.type === 'countdown_start' || data.event === 'countdown_start') {
                // Server broadcasts countdown start
                const endTime = data.countdown_end_time;
                console.log('[quiz_control] countdown_start', { endTime });
                (app as any).countdownEndTime = endTime;
            }
        } catch (err) {
            console.error('[quiz_control] parse message error', err);
        }
    });

    ws.addEventListener('close', (ev) => {
        console.warn('[quiz_control] ws close', ev.code, ev.reason);
    });

    ws.addEventListener('error', (err) => {
        console.error('[quiz_control] ws error', err);
    });

    // Lock heartbeat
    setInterval(() => {
        console.log('[quiz_control] heartbeat tick');
        (app as any).send('lock_heartbeat');
    }, 20000);

    // Countdown display refresh (1 second interval to update remaining time)
    setInterval(() => {
        // Update nowTimestamp every second to trigger countdownRemaining re-computation
        (app as any).nowTimestamp = Math.floor(Date.now() / 1000);
    }, 1000);

    // Results polling (every 2 seconds when in results state)
    let resultsPollingInterval: number | null = null;
    
    function startResultsPolling() {
        if (resultsPollingInterval !== null) return; // Already polling
        
        console.log('[quiz_control] starting results polling');
        resultsPollingInterval = window.setInterval(async () => {
            const currentState = (app as any).state.state;
            if (currentState !== 'results_for_current_question') {
                stopResultsPolling();
                return;
            }
            
            const exId = parseInt((app as any).state.current_exercise_id || '');
            if (isNaN(exId)) return;
            
            try {
                const url = `/teachers/api/quiz/${config.cohort_id}/${config.module_id}/exercises/${exId}/results/`;
                const response = await fetch(url, {
                    method: 'GET',
                    credentials: 'same-origin',
                });
                if (response.ok) {
                    const data = await response.json();
                    console.log('[quiz_control] results data', data);
                    (app as any).resultsData = data;
                }
            } catch (err) {
                console.error('[quiz_control] results polling error', err);
            }
        }, 2000);
    }
    
    function stopResultsPolling() {
        if (resultsPollingInterval !== null) {
            console.log('[quiz_control] stopping results polling');
            clearInterval(resultsPollingInterval);
            resultsPollingInterval = null;
        }
    }
    
    // Watch for state changes to start/stop polling
    let lastState = '';
    setInterval(() => {
        const currentState = (app as any).state.state || '';
        if (currentState !== lastState) {
            console.log('[quiz_control] state changed from', lastState, 'to', currentState);
            lastState = currentState;
            
            if (currentState === 'results_for_current_question') {
                startResultsPolling();
            } else {
                stopResultsPolling();
            }
        }
    }, 500);
}

document.addEventListener('DOMContentLoaded', main);


