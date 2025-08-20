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
    };
    answer_data: {
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

    const initialData: ExerciseFormData = JSON.parse(exerciseDataScript.textContent || '{}');

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
    

    const ExerciseFormApp = defineComponent({
        data() {
            return {
                exercise: initialData,
                loading: false,
                error: null as string | null
            };
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
