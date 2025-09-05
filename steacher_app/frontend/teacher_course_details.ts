import { createApp, defineComponent, onMounted, reactive } from 'vue';
import { csrfFetch } from './utils.js';

// Sortable is provided globally via CDN in base template
declare const Sortable: any;

function getCsrfToken(): string {
    const input = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]!) : '';
}

const TeacherCourseApp = defineComponent({
    setup() {
        const state = reactive({
            moduleVisible: {} as Record<string, boolean>,
            moduleExpanded: {} as Record<string, boolean>,
            exerciseVisible: {} as Record<string, boolean>
        });

        const send = async (url: string, body: any) => {
            const res = await csrfFetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body)
            });
            let data: any = null;
            try { data = await res.json(); } catch {}
            if (!res.ok || (data && data.status && data.status !== 'success')) {
                const message = (data && data.message) ? data.message : res.statusText;
                throw new Error(message);
            }
            return data;
        };

        onMounted(() => {
            const modulesList = document.getElementById('modules-list');
            // Initialize reactive visibility state from DOM
            document.querySelectorAll<HTMLElement>('[data-role="module-visibility-icon"]').forEach(icon => {
                const cardEl = icon.closest('.card') as HTMLElement | null;
                const moduleId = (cardEl?.querySelector('[data-module-id]')?.getAttribute('data-module-id')) || cardEl?.getAttribute('data-id');
                if (!moduleId) return;
                const current = icon.getAttribute('data-visible') === 'true';
                state.moduleVisible[moduleId] = current;
                // default expanded
                if (state.moduleExpanded[moduleId] === undefined) state.moduleExpanded[moduleId] = true;
            });
            document.querySelectorAll<HTMLElement>('.list-group-item.sortable-item').forEach(row => {
                const exId = row.getAttribute('data-id');
                if (!exId) return;
                const current = row.getAttribute('data-exercise-visible') === 'true';
                state.exerciseVisible[exId] = current;
            });

            // Initialize Sortable for modules
            if (modulesList) {
                // eslint-disable-next-line no-new
                new Sortable(modulesList, {
                    animation: 150,
                    handle: '.handle',
                    ghostClass: 'sortable-ghost',
                    onEnd: () => {
                        const moduleIds = Array.from(modulesList.querySelectorAll('.sortable-item'))
                            .map(el => (el as HTMLElement).dataset.id);
                        send('/teachers/api/reorder_modules/', { module_ids: moduleIds });
                    }
                });
            }

            // Initialize Sortable for each module's exercise list
            document.querySelectorAll('.exercise-list').forEach(exList => {
                // eslint-disable-next-line no-new
                new Sortable(exList, {
                    animation: 150,
                    handle: '.handle',
                    ghostClass: 'sortable-ghost',
                    onEnd: () => {
                        const exerciseIds = Array.from(exList.querySelectorAll('.sortable-item'))
                            .map(el => (el as HTMLElement).dataset.id);
                        send('/teachers/api/reorder_exercises/', { exercise_ids: exerciseIds });

                        // Update the order numbers in the UI
                        exList.querySelectorAll('.order-number').forEach((el, index) => {
                            el.textContent = `${index + 1}.`;
                        });
                    }
                });
            });

        });

        const toggleModuleExpanded = (moduleId: string) => {
            state.moduleExpanded[moduleId] = !(state.moduleExpanded[moduleId] ?? true);
        };

        const toggleModuleVisibility = async (moduleId: string) => {
            const next = !(state.moduleVisible[moduleId] ?? true);
            const previous = state.moduleVisible[moduleId] ?? true;
            state.moduleVisible[moduleId] = next; // optimistic
            try {
                await send(`/teachers/api/modules/${moduleId}/visibility/`, { visible: next });
            } catch (e) {
                state.moduleVisible[moduleId] = previous; // revert
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };

        const toggleExerciseVisibility = async (exerciseId: string) => {
            const next = !(state.exerciseVisible[exerciseId] ?? true);
            const previous = state.exerciseVisible[exerciseId] ?? true;
            state.exerciseVisible[exerciseId] = next; // optimistic
            try {
                await send(`/teachers/api/exercises/${exerciseId}/visibility/`, { visible: next });
            } catch (e) {
                state.exerciseVisible[exerciseId] = previous; // revert
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };

        return {
            moduleVisible: state.moduleVisible,
            moduleExpanded: state.moduleExpanded,
            exerciseVisible: state.exerciseVisible,
            toggleModuleExpanded,
            toggleModuleVisibility,
            toggleExerciseVisibility
        };
    }
});

document.addEventListener('DOMContentLoaded', () => {
    const appRoot = document.getElementById('teacher-course-app');
    if (appRoot) {
        createApp(TeacherCourseApp).mount('#teacher-course-app');
    }
});


