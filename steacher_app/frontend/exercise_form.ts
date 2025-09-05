import { createApp, defineComponent } from 'vue';

interface TestCase {
    description: string;
    test_code: string;
    expected_output: string;
}

interface ExerciseFormData {
    pk: number | null;
    title_i18n: Record<string, string>;
    order: number;
    description_i18n: Record<string, string>;
    question_i18n: Record<string, string>;
    exercise_type: string;
    exercise_data: {
        db?: string;
        answer_template?: string;
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
    const courseName: string = typeof (rawData as any).course_name === 'string' ? (rawData as any).course_name : '';
    const courseDescription: string = typeof (rawData as any).course_description === 'string' ? (rawData as any).course_description : '';

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
        (initialData as any).exercise_data = {};
    }
    if (!(initialData as any).title_i18n) (initialData as any).title_i18n = {};
    if (!(initialData as any).description_i18n) (initialData as any).description_i18n = {};
    if (!(initialData as any).question_i18n) (initialData as any).question_i18n = {};
    

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
                uiLang: 'en' as 'en' | 'fr' | 'de',
                lastSyncedEnSumByLang: { fr: 0, de: 0 } as Record<'fr'|'de', number>,
                course_name: courseName,
                course_description: courseDescription,
            };
        },
        watch: {
            'exercise.exercise_type'(newType, oldType) {
                // When switching to SQL, ensure the db property exists.
                if (newType === 'sql') {
                    if (!this.exercise.exercise_data) {
                        this.exercise.exercise_data = { question_i18n: {}, db: '' } as any;
                    } else if (this.exercise.exercise_data.db === undefined) {
                        this.exercise.exercise_data.db = '';
                    }
                }
                // Ensure answer_template key exists for supported types
                if (['python','sql','scala','open_question'].includes(newType)) {
                    if (!this.exercise.exercise_data) {
                        this.exercise.exercise_data = {} as any;
                    }
                    if (this.exercise.exercise_data.answer_template === undefined) {
                        this.exercise.exercise_data.answer_template = '';
                    }
                }
            }
        },
        computed: {
            pageTitle(): string {
                const title = this.exercise.title_i18n?.['en'] || this.exercise.title_i18n?.['fr'] || this.exercise.title_i18n?.['de'] || '';
                return this.exercise.pk ? `Edit Exercise: ${title}` : 'Create New Exercise';
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
        mounted() {
            // Initialize per-language sync baseline to current EN content
            try {
                const currentSum = (this as any).computeEnSum();
                (this as any).lastSyncedEnSumByLang.fr = currentSum;
                (this as any).lastSyncedEnSumByLang.de = currentSum;
            } catch (_) {}
        },
        methods: {
            deepClone<T>(obj: T): T {
                return JSON.parse(JSON.stringify(obj));
            },
            asciiSum(s: string): number {
                let total = 0;
                for (let i = 0; i < s.length; i++) total += s.charCodeAt(i);
                return total >>> 0;
            },
            computeEnSum(): number {
                const enTitle = this.exercise.title_i18n?.['en'] || '';
                const enDesc = this.exercise.description_i18n?.['en'] || '';
                const enQ = this.exercise.question_i18n?.['en'] || '';
                return this.asciiSum(enTitle + enDesc + enQ);
            },
            langEmpty(lang: 'en'|'fr'|'de'): boolean {
                const t = (this.exercise.title_i18n?.[lang] || '').trim();
                const d = (this.exercise.description_i18n?.[lang] || '').trim();
                const q = (this.exercise.question_i18n?.[lang] || '').trim();
                return !t || !d || !q;
            },
            langStale(lang: 'fr'|'de'): boolean {
                const currentSum = this.computeEnSum();
                return currentSum !== this.lastSyncedEnSumByLang[lang];
            },
            markSynced(lang: 'fr'|'de') {
                this.lastSyncedEnSumByLang[lang] = this.computeEnSum();
            },
            getCsrfToken(): string | null {
                const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                return csrfTokenElement ? csrfTokenElement.value : null;
            },
            buildErrorMessage(result: any, status: number): string {
                let errorMessage = result?.message || `Server error: ${status}`;
                if (result?.details) {
                    errorMessage += '\n\nDetails:\n';
                    result.details.forEach((detail: any) => {
                        errorMessage += `- ${detail.description}\n`;
                        errorMessage += `  - Expected: ${detail.expected_output}\n`;
                        errorMessage += `  - Got: ${detail.actual_output}\n`;
                    });
                }
                return errorMessage;
            },
            async performSave(redirectOnSuccess: boolean) {
                this.loading = true;
                this.error = null;

                try {
                    // Save-time warning: missing/stale translations
                    const missing: string[] = [];
                    const stale: string[] = [];
                    (['fr','de'] as const).forEach((lang) => {
                        if (this.langEmpty(lang)) missing.push(lang.toUpperCase());
                        if (this.langStale(lang)) stale.push(lang.toUpperCase());
                    });
                    if (missing.length || stale.length) {
                        const msg = `Translations\nMissing: ${missing.join(', ') || 'none'}\nStale: ${stale.join(', ') || 'none'}\n\nProceed to save?`;
                        const proceed = window.confirm(msg);
                        if (!proceed) {
                            this.loading = false;
                            return;
                        }
                    }

                    const csrfToken = this.getCsrfToken();
                    if (!csrfToken) {
                        this.error = 'CSRF token not found!';
                        this.loading = false;
                        return;
                    }
                    const teacherPath = window.location.pathname.replace(/^\/exercises\//, '/teachers/');
                    const response = await fetch(teacherPath, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken,
                        },
                        body: JSON.stringify(this.exercise),
                    });

                    const result = await response.json();
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(this.buildErrorMessage(result, response.status));
                    }

                    const savedPk: number | null = result.exercise_pk ?? null;
                    if (!this.exercise.pk && savedPk) {
                        this.exercise.pk = savedPk;
                        if (this.course_pk != null) {
                            const newPath = `/exercises/courses/${this.course_pk}/edit_exercise/${savedPk}/`;
                            window.history.replaceState(null, '', newPath);
                        }
                    }

                    if (redirectOnSuccess) {
                        const targetId: number | null = savedPk ?? this.exercise.pk ?? null;
                        if (targetId != null) {
                            window.location.href = `/exercises/${targetId}/`;
                        }
                    }
                } catch (err: any) {
                    this.error = err.message || String(err);
                } finally {
                    this.loading = false;
                }
            },
            async translateLanguage(targetLang: 'fr'|'de') {
                this.assistantError = null;
                this.sending = true;
                const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                if (!csrfTokenElement) {
                    this.assistantError = 'CSRF token not found!';
                    this.sending = false;
                    return;
                }
                try {
                    console.log('[translate_i18n] sending single target', targetLang);
                    const response = await fetch('/teachers/ai/translate_i18n/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfTokenElement.value,
                        },
                        body: JSON.stringify({
                            source_lang: 'en',
                            targets: [targetLang],
                            fields: {
                                title: this.exercise.title_i18n?.['en'] || '',
                                description: this.exercise.description_i18n?.['en'] || '',
                                question: this.exercise.question_i18n?.['en'] || '',
                            },
                            course_context: { name: this.course_name, description: this.course_description },
                        }),
                    });
                    const result = await response.json();
                    console.log('[translate_i18n] response', result);
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(result.message || `Server error: ${response.status}`);
                    }
                    const translations = (result.translations || {})[targetLang] || {};
                    if (translations.title !== undefined) this.exercise.title_i18n[targetLang] = translations.title;
                    if (translations.description !== undefined) this.exercise.description_i18n[targetLang] = translations.description;
                    if (translations.question !== undefined) this.exercise.question_i18n[targetLang] = translations.question;
                    this.lastSyncedEnSumByLang[targetLang] = this.computeEnSum();
                } catch (err: any) {
                    this.assistantError = err.message || String(err);
                } finally {
                    this.sending = false;
                }
            },
            async translateMissingOrStale() {
                const targets: ('fr'|'de')[] = [];
                (['fr','de'] as const).forEach((lang) => {
                    if (this.langEmpty(lang) || this.langStale(lang)) targets.push(lang);
                });
                if (targets.length === 0) return;
                this.assistantError = null;
                this.sending = true;
                const csrfTokenElement = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
                if (!csrfTokenElement) {
                    this.assistantError = 'CSRF token not found!';
                    this.sending = false;
                    return;
                }
                try {
                    console.log('[translate_i18n] sending batch', targets);
                    const response = await fetch('/teachers/ai/translate_i18n/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfTokenElement.value,
                        },
                        body: JSON.stringify({
                            source_lang: 'en',
                            targets,
                            fields: {
                                title: this.exercise.title_i18n?.['en'] || '',
                                description: this.exercise.description_i18n?.['en'] || '',
                                question: this.exercise.question_i18n?.['en'] || '',
                            },
                            course_context: { name: this.course_name, description: this.course_description },
                        }),
                    });
                    const result = await response.json();
                    console.log('[translate_i18n] batch response', result);
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(result.message || `Server error: ${response.status}`);
                    }
                    const translations = result.translations || {};
                    (targets as string[]).forEach((lang) => {
                        const t = translations[lang] || {};
                        if (t.title !== undefined) this.exercise.title_i18n[lang] = t.title;
                        if (t.description !== undefined) this.exercise.description_i18n[lang] = t.description;
                        if (t.question !== undefined) this.exercise.question_i18n[lang] = t.question;
                        this.lastSyncedEnSumByLang[lang as 'fr'|'de'] = this.computeEnSum();
                    });
                } catch (err: any) {
                    this.assistantError = err.message || String(err);
                } finally {
                    this.sending = false;
                }
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
                    const response = await fetch('/teachers/ai/authoring_assistant/', {
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
            async saveExercise() { return this.performSave(true); },
            async saveAndContinue() { return this.performSave(false); }
        }
    });

    const app = createApp(ExerciseFormApp);
    app.config.compilerOptions.delimiters = ['[[', ']]'];
    app.mount('#exercise-form-app');
});
