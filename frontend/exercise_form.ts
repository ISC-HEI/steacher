import { createApp, defineComponent } from 'vue';

interface TestCase {
    description: string;
    test_code: string;
    expected_output: string;
}

interface ExerciseFormData {
    pk: number | null;
    title: string;
    order: number;
    description: string;
    exercise_type: string;
    exercise_data: {
        question: string;
        db?: string;
    };
    answer_data: {
        expected_result?: string;
        additional_context?: string;
        unit_tests: {
            setup_code: string;
            test_cases: TestCase[];
            timeout_seconds: number;
        };
        correct_answers: { answer: string; explanation: string; }[];
        hints: string[];
    };
}

document.addEventListener('DOMContentLoaded', function() {
    const appElement = document.getElementById('exercise-form-app');
    const exerciseDataScript = document.getElementById('exercise-form-data');

    if (!appElement || !exerciseDataScript) {
        console.error('Required elements not found!');
        return;
    }

    const rawData: any = JSON.parse(exerciseDataScript.textContent || '{}');
    const initialData: ExerciseFormData = rawData as ExerciseFormData;
    const availableSqlAssets: string[] = Array.isArray(rawData.available_sql_assets) ? rawData.available_sql_assets : [];
    const coursePk: number | null = typeof rawData.course_pk === 'number' ? rawData.course_pk : null;

    // Ensure the nested structure for unit tests exists, especially for new exercises.
    if (!initialData.answer_data) {
        initialData.answer_data = { unit_tests: { setup_code: '', test_cases: [], timeout_seconds: 10 }, correct_answers: [], hints: [] };
    }
    if (!initialData.answer_data.unit_tests) {
        initialData.answer_data.unit_tests = { setup_code: '', test_cases: [], timeout_seconds: 10 };
    }
     if (!initialData.answer_data.unit_tests.test_cases) {
        initialData.answer_data.unit_tests.test_cases = [];
    }
    if (!initialData.answer_data.correct_answers) {
        initialData.answer_data.correct_answers = [];
    }
    if (!initialData.answer_data.hints) {
        initialData.answer_data.hints = [];
    }
    if (!initialData.exercise_data) {
        initialData.exercise_data = { question: '' };
    }
    

    const ExerciseFormApp = defineComponent({
        data() {
            return {
                exercise: initialData,
                available_sql_assets: availableSqlAssets,
                loading: false,
                error: null as string | null,
                // Assistant state (ephemeral, desktop only)
                messages: [] as { role: 'user' | 'assistant'; content: string }[],
                draftMessage: '',
                sending: false,
                assistantError: null as string | null,
                lastAppliedSnapshot: null as ExerciseFormData | null,
                course_pk: coursePk,
            };
        },
        watch: {
            'exercise.exercise_type'(newType, oldType) {
                // When switching to SQL, ensure the db property exists.
                if (newType === 'sql') {
                    if (!this.exercise.exercise_data) {
                        this.exercise.exercise_data = { question: '', db: '' };
                    } else if (this.exercise.exercise_data.db === undefined) {
                        this.exercise.exercise_data.db = '';
                    }
                }
            }
        },
        computed: {
            pageTitle(): string {
                return this.exercise.pk ? `Edit Exercise: ${this.exercise.title}` : 'Create New Exercise';
            },
            hints_text: {
                get(): string {
                    return this.exercise.answer_data.hints.join('\\n');
                },
                set(value: string) {
                    this.exercise.answer_data.hints = value.split('\\n');
                }
            }
        },
        methods: {
            deepClone<T>(obj: T): T {
                return JSON.parse(JSON.stringify(obj));
            },
            addTestCase() {
                this.exercise.answer_data.unit_tests.test_cases.push({
                    description: '',
                    test_code: '',
                    expected_output: ''
                });
            },
            removeTestCase(index: number) {
                this.exercise.answer_data.unit_tests.test_cases.splice(index, 1);
            },
            addCorrectAnswer() {
                this.exercise.answer_data.correct_answers.push({ answer: '', explanation: '' });
            },
            removeCorrectAnswer(index: number) {
                this.exercise.answer_data.correct_answers.splice(index, 1);
            },
            async sendAssistantMessage() {
                if (!this.draftMessage.trim() || this.sending) return;
                this.assistantError = null;
                this.sending = true;

                const userMsg = { role: 'user' as const, content: this.draftMessage };
                this.messages.push(userMsg);
                this.draftMessage = '';

                const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                if (!csrfTokenElement) {
                    this.assistantError = 'CSRF token not found!';
                    this.sending = false;
                    return;
                }

                try {
                    const response = await fetch('/exercises/ai/authoring_assistant/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfTokenElement.value,
                        },
                        body: JSON.stringify({
                            exercise: this.exercise,
                            messages: this.messages,
                            context: { course_pk: this.course_pk },
                        }),
                    });

                    const result = await response.json();
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(result.message || `Server error: ${response.status}`);
                    }

                    const assistant_message: string = result.assistant_message || '';
                    const updated_exercise: ExerciseFormData = result.updated_exercise || this.exercise;

                    this.lastAppliedSnapshot = this.deepClone(this.exercise);
                    this.exercise = this.deepClone(updated_exercise);

                    if (assistant_message) {
                        this.messages.push({ role: 'assistant', content: assistant_message });
                    }
                } catch (err: any) {
                    this.assistantError = err.message || String(err);
                } finally {
                    this.sending = false;
                }
            },
            undoLastAIEdit() {
                if (!this.lastAppliedSnapshot) return;
                this.exercise = this.deepClone(this.lastAppliedSnapshot);
                this.lastAppliedSnapshot = null;
            },
            async saveExercise() {
                this.loading = true;
                this.error = null;

                const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                if (!csrfTokenElement) {
                    this.error = 'CSRF token not found!';
                    this.loading = false;
                    return;
                }

                try {
                    const response = await fetch(window.location.pathname, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfTokenElement.value,
                        },
                        body: JSON.stringify(this.exercise),
                    });

                    if (!response.ok) {
                        const result = await response.json();
                        let errorMessage = result.message || `Server error: ${response.status}`;
                        if (result.details) {
                            errorMessage += '\\n\\nDetails:\\n';
                            result.details.forEach((detail: any) => {
                                errorMessage += `- ${detail.description}\\n`;
                                errorMessage += `  - Expected: ${detail.expected_output}\\n`;
                                errorMessage += `  - Got: ${detail.actual_output}\\n`;
                            });
                        }
                        throw new Error(errorMessage);
                    }

                    const result = await response.json();
                    if (result.status === 'success') {
                        window.location.href = (appElement.querySelector('a.is-light') as HTMLAnchorElement).href;
                    } else {
                        throw new Error(result.message || 'Failed to save the exercise.');
                    }
                } catch (err: any) {
                    this.error = err.message;
                } finally {
                    this.loading = false;
                }
            }
        }
    });

    const app = createApp(ExerciseFormApp);
    app.config.compilerOptions.delimiters = ['[[', ']]'];
    app.mount('#exercise-form-app');
});
