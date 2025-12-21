import { createApp, defineComponent, onMounted, reactive, toRefs } from 'vue';
import { csrfFetch } from './utils.js';

// Sortable is provided globally via CDN in base template
declare const Sortable: any;

// Exercise interface is now exported from utils.ts

const TeacherCourseApp = defineComponent({
    setup() {
        const state = reactive({
            moduleVisible: {} as Record<string, boolean>,
            moduleExpanded: {} as Record<string, boolean>,
            exerciseVisible: {} as Record<string, boolean>,
            showImportModal: false,
            selectedFile: null as File | null,
            selectedFileName: null as string | null,
            importing: false,
            importError: null as string | null,
            importSuccess: null as string | null
        });

        let isReordering = false;

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
            const modulesList = document.getElementById('modules-list') as HTMLElement | null;
            const courseId = (() => {
                const raw = modulesList?.getAttribute('data-course-id');
                const n = raw ? parseInt(raw, 10) : NaN;
                return Number.isFinite(n) ? n : null;
            })();
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
                        const payload: any = { module_ids: moduleIds };
                        if (courseId != null) payload.course_pk = courseId;
                        send('/teachers/api/reorder_modules/', payload);
                    }
                });
            }

            // Initialize Sortable for each module's exercise list
            document.querySelectorAll('.exercise-list').forEach(exList => {
                // eslint-disable-next-line no-new
                new Sortable(exList, {
                    group: 'exercises', // group for cross-module dragging
                    animation: 150,
                    handle: '.handle',
                    ghostClass: 'sortable-ghost',
                    onEnd: async (evt: any) => {
                        // Prevent overlapping saves
                        if (isReordering) {
                            return;
                        }
                        isReordering = true;

                        const toInt = (v: string | undefined | null) => {
                            const n = parseInt(v || '', 10);
                            return Number.isFinite(n) ? n : NaN;
                        };

                        const fromModuleId = toInt(evt.from.dataset.moduleId);
                        const toModuleId = toInt(evt.to.dataset.moduleId);
                        const movedExerciseId = toInt(evt.item.dataset.id);

                        const sourceExerciseIds = Array.from(evt.from.querySelectorAll('.sortable-item'))
                            .map(el => toInt((el as HTMLElement).dataset.id))
                            .filter(n => Number.isFinite(n));
                        const targetExerciseIds = Array.from(evt.to.querySelectorAll('.sortable-item'))
                            .map(el => toInt((el as HTMLElement).dataset.id))
                            .filter(n => Number.isFinite(n));

                        const payload: any = {
                            source_module_id: fromModuleId,
                            target_module_id: toModuleId,
                            source_exercise_ids: sourceExerciseIds,
                            target_exercise_ids: targetExerciseIds,
                            moved_exercise_id: movedExerciseId,
                        };
                        if (courseId != null) payload.course_pk = courseId;

                        const fromInstance = Sortable.get(evt.from);
                        const toInstance = Sortable.get(evt.to);
                        try {
                            fromInstance?.option('disabled', true);
                            toInstance?.option('disabled', true);

                            await send('/teachers/api/reorder_exercises/', payload);

                            // Update UI for empty/non-empty lists
                            if (evt.from !== evt.to) {
                                // Target is no longer empty, remove placeholder if it exists
                                const emptyMsg = evt.to.querySelector('p');
                                if (emptyMsg && emptyMsg.parentElement === evt.to) {
                                    evt.to.removeChild(emptyMsg);
                                }

                                // Source might be empty now, add placeholder if needed
                                if (evt.from.querySelectorAll('.sortable-item').length === 0) {
                                    const p = document.createElement('p');
                                    p.textContent = 'This module does not have any exercises yet.';
                                    evt.from.appendChild(p);
                                }
                            }

                            // Update the order numbers in the UI
                            evt.from.querySelectorAll('.order-number').forEach((el: Element, index: number) => {
                                (el as HTMLElement).textContent = `${index + 1}.`;
                            });
                            if (evt.from !== evt.to) {
                                evt.to.querySelectorAll('.order-number').forEach((el: Element, index: number) => {
                                    (el as HTMLElement).textContent = `${index + 1}.`;
                                });
                            }
                        } catch (e) {
                            // Revert DOM move on error
                            const itemEl = evt.item as HTMLElement;
                            const oldFrom: HTMLElement = evt.from;
                            const oldIndex: number = evt.oldIndex;
                            if (evt.from !== evt.to) {
                                const ref = oldFrom.querySelectorAll('.sortable-item')[oldIndex] || null;
                                oldFrom.insertBefore(itemEl, ref);
                            } else {
                                const ref = oldFrom.querySelectorAll('.sortable-item')[oldIndex] || null;
                                oldFrom.insertBefore(itemEl, ref);
                            }
                            // Restore placeholders after revert
                            if (evt.from !== evt.to) {
                                if (evt.to.querySelectorAll('.sortable-item').length === 0) {
                                    const p = document.createElement('p');
                                    p.textContent = 'This module does not have any exercises yet.';
                                    evt.to.appendChild(p);
                                }
                                const emptyMsg = evt.from.querySelector('p');
                                if (emptyMsg && emptyMsg.parentElement === evt.from) {
                                    evt.from.removeChild(emptyMsg);
                                }
                            }
                            // Update order numbers after revert
                            oldFrom.querySelectorAll('.order-number').forEach((el: Element, index: number) => {
                                (el as HTMLElement).textContent = `${index + 1}.`;
                            });
                            if (evt.from !== evt.to) {
                                evt.to.querySelectorAll('.order-number').forEach((el: Element, index: number) => {
                                    (el as HTMLElement).textContent = `${index + 1}.`;
                                });
                            }
                            // eslint-disable-next-line no-console
                            console.error(e);
                        } finally {
                            fromInstance?.option('disabled', false);
                            toInstance?.option('disabled', false);
                            isReordering = false;
                        }
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
                const modulesList = document.getElementById('modules-list') as HTMLElement | null;
                const rawCourse = modulesList?.getAttribute('data-course-id');
                const courseId = rawCourse ? parseInt(rawCourse, 10) : null;
                const payload: any = { visible: next };
                if (courseId != null) payload.course_pk = courseId;
                await send(`/teachers/api/modules/${moduleId}/visibility/`, payload);
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
                const modulesList = document.getElementById('modules-list') as HTMLElement | null;
                const rawCourse = modulesList?.getAttribute('data-course-id');
                const courseId = rawCourse ? parseInt(rawCourse, 10) : null;
                const payload: any = { visible: next };
                if (courseId != null) payload.course_pk = courseId;
                await send(`/teachers/api/exercises/${exerciseId}/visibility/`, payload);
            } catch (e) {
                state.exerciseVisible[exerciseId] = previous; // revert
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };
        
        const duplicateExercise = async (exerciseId: string) => {
            try {
                const modulesList = document.getElementById('modules-list') as HTMLElement | null;
                const rawCourse = modulesList?.getAttribute('data-course-id');
                const courseId = rawCourse ? parseInt(rawCourse, 10) : null;
                const payload: any = {};
                if (courseId != null) payload.course_pk = courseId;
                await send(`/teachers/api/exercises/${exerciseId}/duplicate/`, payload);
                window.location.reload();
            } catch (e) {
                // eslint-disable-next-line no-alert
                alert(`Failed to duplicate exercise: ${e}`);
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };

        const deleteExercise = async (exerciseId: string) => {
            try {
                // First, get attempt count from backend (GET request)
                const infoResponse = await csrfFetch(`/teachers/api/exercises/${exerciseId}/archive/`, {
                    method: 'GET',
                });
                
                const infoData = await infoResponse.json();
                
                if (!infoResponse.ok || infoData.status === 'error') {
                    throw new Error(infoData.message || 'Failed to get exercise info');
                }
                
                // Build confirmation message
                let message = 'Are you sure you want to delete this exercise? ';
                
                if (infoData.attempt_count > 0) {
                    message += `${infoData.attempt_count} student(s) have submitted work for this exercise. `;
                }
                
                message += 'Student work will be preserved but inaccessible. ' +
                          'Contact the Steacher administrator if you need to restore it later.';
                
                // Show confirmation
                // eslint-disable-next-line no-alert
                const confirmed = window.confirm(message);
                
                if (!confirmed) {
                    return; // User cancelled
                }
                
                // User confirmed - now archive (POST request)
                const archiveResponse = await csrfFetch(`/teachers/api/exercises/${exerciseId}/archive/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                });
                
                const archiveData = await archiveResponse.json();
                
                if (!archiveResponse.ok || archiveData.status === 'error') {
                    throw new Error(archiveData.message || 'Failed to delete exercise');
                }
                
                // Success - reload page
                window.location.reload();
            } catch (e) {
                // eslint-disable-next-line no-alert
                alert(`Failed to delete exercise: ${e}`);
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };

        const archiveModule = async (moduleId: string) => {
            // eslint-disable-next-line no-alert
            const confirmed = window.confirm(
                'Are you sure you want to delete this module? ' +
                'This will hide the module and all its exercises from students. ' +
                'Student work will be preserved but inaccessible. ' +
                'Contact the Steacher administrator if you need to restore it later.'
            );
            
            if (!confirmed) return;
            
            try {
                const response = await csrfFetch(`/teachers/api/modules/${moduleId}/archive/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                });
                
                const data = await response.json();
                
                if (!response.ok || data.status === 'error') {
                    throw new Error(data.message || 'Failed to delete module');
                }
                
                // Reload page to reflect changes
                window.location.reload();
            } catch (e) {
                // eslint-disable-next-line no-alert
                alert(`Failed to delete module: ${e}`);
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };

        const editExercise = (exerciseId: string) => {
            const modulesList = document.getElementById('modules-list') as HTMLElement | null;
            const rawCourse = modulesList?.getAttribute('data-course-id');
            window.location.href = `/teachers/courses/${rawCourse}/edit_exercise/${exerciseId}/`;
        };

        const addModulePrompt = async () => {
            const title = window.prompt('Module title');
            if (title === null) return; // canceled
            const trimmed = (title || '').trim();
            if (!trimmed) return; // empty
            try {
                const modulesList = document.getElementById('modules-list') as HTMLElement | null;
                const rawCourse = modulesList?.getAttribute('data-course-id');
                const courseId = rawCourse ? parseInt(rawCourse, 10) : null;
                const payload: any = { name: trimmed, description: '' };
                if (courseId != null) payload.course_pk = courseId;
                await send('/teachers/api/modules/create/', payload);
                window.location.reload();
            } catch (e: any) {
                // eslint-disable-next-line no-alert
                alert(`Failed to create module: ${e?.message || e}`);
                // eslint-disable-next-line no-console
                console.error(e);
            }
        };

        const handleFileSelect = (event: Event) => {
            const target = event.target as HTMLInputElement;
            const file = target.files?.[0];
            if (file) {
                state.selectedFile = file;
                state.selectedFileName = file.name;
            } else {
                state.selectedFile = null;
                state.selectedFileName = null;
            }
            state.importError = null;
            state.importSuccess = null;
        };

        const submitImport = async () => {
            if (!state.selectedFile) return;
            
            state.importing = true;
            state.importError = null;
            state.importSuccess = null;

            try {
                const modulesList = document.getElementById('modules-list') as HTMLElement | null;
                const rawCourse = modulesList?.getAttribute('data-course-id');
                const courseId = rawCourse ? parseInt(rawCourse, 10) : null;
                
                if (!courseId) {
                    throw new Error('Course ID not found');
                }

                const formData = new FormData();
                formData.append('file', state.selectedFile);

                const response = await csrfFetch(`/teachers/courses/${courseId}/import-module/`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (!response.ok || data.status === 'error') {
                    throw new Error(data.message || 'Import failed');
                }

                state.importSuccess = data.message || 'Module imported successfully';
                
                // Reload page after short delay to show success message
                setTimeout(() => {
                    window.location.reload();
                }, 1500);

            } catch (e: any) {
                state.importError = e?.message || 'Import failed';
                // eslint-disable-next-line no-console
                console.error(e);
            } finally {
                state.importing = false;
            }
        };

        const setShowImportModal = (value: boolean) => {
            state.showImportModal = value;
            if (!value) {
                // Reset state when closing modal
                state.selectedFile = null;
                state.selectedFileName = null;
                state.importError = null;
                state.importSuccess = null;
            }
        };

        return {
            ...toRefs(state),
            toggleModuleExpanded,
            toggleModuleVisibility,
            toggleExerciseVisibility,
            duplicateExercise,
            deleteExercise,
            archiveModule,
            editExercise,
            addModulePrompt,
            handleFileSelect,
            submitImport,
            setShowImportModal
        };
    }
});

document.addEventListener('DOMContentLoaded', () => {
    const appRoot = document.getElementById('teacher-course-app');
    if (appRoot) {
        createApp(TeacherCourseApp).mount('#teacher-course-app');
    }
});


