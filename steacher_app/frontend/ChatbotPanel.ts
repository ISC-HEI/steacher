import { marked } from 'marked';
import DOMPurify from 'dompurify';
import confetti from 'canvas-confetti';
import { getCsrfToken } from './utils.js';
import { defineComponent } from "vue";
import katex from 'katex';

interface ProcessedMessage {
    cleanedContent: string;
    thoughts?: string[];
    debug_fields?: {
        transcript: string;
        error_desc: string;
        help_text: string;
        ambiguities: string;
    };
    _isNew?: boolean;
    [key: string]: any;
}

interface ChatbotPanelData {
    question: string;
    internalMessages: any[];
    pathwayLoading: boolean;
    pathwayData: any;
    showCompletionModal: boolean;
    showJumpToLatest: boolean;
    nextMessageId: number;
    isDarkMode: boolean;
    solutionUnlocked: boolean;
    _submissionsCount: number;
    showImageModal: boolean;
    modalImageUrl: string | null;
    activeDebugTabs: { [messageId: number]: string };
}

export const ChatbotPanel = defineComponent({
  props: {
    loading: {  // used to disable the question input field while loading
      type: Boolean,
      default: false,
    },
    attemptId: {
        type: Number,
        default: null,
    },
    // We need to know if there's a next exercise to determine
    // whether to show the course completion celebration.
    nextExerciseUrl: {
        type: String,
        default: '',
    },
    solutionUnlockedInitial: {
        type: Boolean,
        default: false,
    },
    confettiAlreadyShown: {
        type: Boolean,
        default: false,
    },
    exercise: {
        type: Object,
        default: () => null,
    }
  },
  // language=HTML
  template: `
    <div id="chatbot" ref="chatContainer">
      <div class="chat-content" ref="messagesContainer">
        <!-- Chatbot Content. A list of messages exchanged between the user and the assistant. -->
        <div>
          <template v-for="(message, index) in processedMessages">
            <div v-if="message.role === 'user' && (message.content || (message.images && message.images.length > 0))"
                 class="box content mb-3 user-message"
                 :key="'user-' + index">
              <!-- Create collapsible for all user messages with action metadata -->
              <template v-if="message.metadata && message.metadata.action">
                <details class="collapsible-message">
                  <summary v-html="getMessageSummary(message)"></summary>
                  <div class="mt-2">
                    <div v-if="message.content" v-html="renderMarkdown(message.content)"></div>
                    <div v-if="message.images && message.images.length > 0" class="mt-3" style="display: flex; flex-direction: column; gap: 0.75rem;">
                      <div v-for="(img, imgIdx) in message.images" 
                           :key="imgIdx"
                           style="width: 100%; max-width: 100%; cursor: pointer;"
                           @click="openImageModal('/exercises/image/' + img.image_token)">
                        <img :src="'/exercises/image/' + img.image_token" 
                             alt="User uploaded image"
                             style="width: 100%; max-width: 100%; height: auto; border: 1px solid #e6e6e6; border-radius: 4px; background: #fff;" />
                      </div>
                    </div>
                  </div>
                </details>
              </template>
              <!-- Messages without action metadata (shouldn't happen, but fallback) -->
              <template v-else>
                <div v-html="renderMarkdown(message.content)"></div>
              </template>
            </div>

            <template v-if="message.role === 'assistant'">
                <div v-if="message.cleanedContent"
                     class="box content mb-3 assistant-message"
                     :class="{ 'message-new': message._isNew }"
                     :key="'assistant-content-' + index"
                     style="position: relative;">
                    
                    <!-- AI Reasoning Process (thoughts) - only shown to teachers -->
                    <details v-if="message.thoughts && message.thoughts.length > 0" class="mb-3" style="border-bottom: 1px solid #e0e0e0; padding-bottom: 0.75rem;">
                        <summary style="cursor: pointer; font-weight: 600; color: #7a7a7a; font-size: 0.85rem;">
                            <span class="icon is-small"><i class="fas fa-brain"></i></span>
                            AI Reasoning Process ({{ message.thoughts.length }} thought{{ message.thoughts.length !== 1 ? 's' : '' }})
                        </summary>
                        <p class="is-size-6 mt-2">(only shown to teachers)</p>
                        <div class="box mt-2 has-background-light" style="font-size: 0.85rem;">
                            <div v-for="(thought, tIndex) in message.thoughts" :key="tIndex" class="mb-2">
                                <p class="has-text-grey-dark" style="white-space: pre-wrap;">{{ thought }}</p>
                                <hr v-if="tIndex < message.thoughts.length - 1" class="my-2">
                            </div>
                        </div>
                    </details>
                    
                    <!-- Debug Fields Tabs - only shown to teachers -->
                    <div v-if="message.debug_fields" class="mb-3" style="border-bottom: 1px solid #e0e0e0; padding-bottom: 0.75rem;">
                        <p class="is-size-6 mb-2 has-text-grey">
                            <span class="icon is-small"><i class="fas fa-bug"></i></span>
                            Debug Information (only shown to teachers)
                        </p>
                        <div class="tabs is-small">
                            <ul>
                                <li :class="{ 'is-active': getActiveDebugTab(message._id) === 'help_text' }">
                                    <a @click="setActiveDebugTab(message._id, 'help_text')">Help Text</a>
                                </li>
                                <li :class="{ 'is-active': getActiveDebugTab(message._id) === 'transcript' }">
                                    <a @click="setActiveDebugTab(message._id, 'transcript')">Transcript</a>
                                </li>
                                <li :class="{ 'is-active': getActiveDebugTab(message._id) === 'error_desc' }">
                                    <a @click="setActiveDebugTab(message._id, 'error_desc')">Error Description</a>
                                </li>
                                <li :class="{ 'is-active': getActiveDebugTab(message._id) === 'ambiguities' }">
                                    <a @click="setActiveDebugTab(message._id, 'ambiguities')">Ambiguities</a>
                                </li>
                            </ul>
                        </div>
                        <div class="box mt-2 has-background-light" 
                             :style="{
                                 'font-size': '0.85rem', 
                                 'min-height': '60px',
                                 'overflow-x': getActiveDebugTab(message._id) === 'transcript' ? 'auto' : 'visible',
                                 'white-space': getActiveDebugTab(message._id) === 'transcript' ? 'pre' : 'pre-wrap'
                             }">
                            <div v-if="getDebugTabContent(message, getActiveDebugTab(message._id))" 
                                 v-html="renderMarkdown(getDebugTabContent(message, getActiveDebugTab(message._id)))">
                            </div>
                            <div v-else class="has-text-grey-light">
                                No data available
                            </div>
                        </div>
                    </div>
                    
                    <div v-html="renderMarkdown(message.cleanedContent)"></div>
                    
                    <div class="thumbs-container" v-if="message.trace_id">
                        <button
                            class="button is-small is-white"
                            :class="{ 'selected': message._rating === 'ok' }"
                            title="Helpful"
                            @click="rateTrace(message.trace_id, true, message._id)"
                            :disabled="loading || pathwayLoading || !!message._rated">
                            <span class="icon is-small"><i :class="message._rating === 'ok' ? 'fas fa-thumbs-up' : 'far fa-thumbs-up'"></i></span>
                        </button>
                        <button
                            class="button is-small is-white"
                            :class="{ 'selected': message._rating === 'not_ok' }"
                            title="Not helpful"
                            @click="rateTrace(message.trace_id, false, message._id)"
                            :disabled="loading || pathwayLoading || !!message._rated">
                            <span class="icon is-small"><i :class="message._rating === 'not_ok' ? 'fas fa-thumbs-down' : 'far fa-thumbs-down'"></i></span>
                        </button>
                    </div>
                </div>
            </template>
          </template>
        </div>

        <!-- Pathway Recommendation UI (scrolls with messages) -->
        <article v-if="pathwayLoading" class="message" :class="isDarkMode ? 'is-dark' : 'is-info is-light'">
          <div class="message-body">
            <div class="typing-indicator" aria-label="Assistant is thinking">
              <span class="dot" style="--ti-delay: 0ms;"></span>
              <span class="dot" style="--ti-delay: 150ms;"></span>
              <span class="dot" style="--ti-delay: 300ms;"></span>
              <span class="helper-text">Recommending next exercise... Hold on!</span>
            </div>
          </div>
        </article>

        <section v-if="pathwayData" class="mb-4">
          <!-- Performance Feedback -->
          <article class="message mb-4" :class="isDarkMode ? 'is-dark' : 'is-success is-light'">
            <div class="message-header">
              <p>Performance Feedback</p>
            </div>
            <div class="message-body">
              <p v-if="pathwayData.performance_feedback.what_went_well">
                <strong>What Went Well:</strong> {{ pathwayData.performance_feedback.what_went_well }}
              </p>
              <p v-if="pathwayData.performance_feedback.key_learnings">
                <strong>Key Learnings:</strong> {{ pathwayData.performance_feedback.key_learnings }}
              </p>
            </div>
          </article>

          <!-- Main Recommendation -->
          <div :class="['card', 'mb-4', isDarkMode ? 'has-background-dark has-text-light' : '']">
            <div class="card-content">
              <h3 class="title is-5">Recommended Next Step</h3>
              <p><strong><a :href="getExerciseUrl(pathwayData.main_recommendation.exercise_id)">{{ pathwayData.main_recommendation.title }}</a></strong></p>
              <p class="is-size-7"><em>{{ pathwayData.main_recommendation.what_it_is_about }}</em></p>
              <p class="is-size-7 has-text-weight-semibold">{{ pathwayData.main_recommendation.why_you_should_do_it }}</p>
              <a :href="getExerciseUrl(pathwayData.main_recommendation.exercise_id)" class="button is-primary is-fullwidth mt-2">Start This Exercise</a>
            </div>
          </div>

          <!-- Alternatives -->
          <template v-if="pathwayData.alternatives.length > 0">
            <h3 class="title is-5">Other exercises to explore</h3>
            <div class="mt-3">
              <div v-for="alt in pathwayData.alternatives" :key="alt.exercise_id" :class="['card', 'mb-3', isDarkMode ? 'has-background-dark has-text-light' : '']">
                <div class="card-content">
                  <p><strong><a :href="getExerciseUrl(alt.exercise_id)">{{ alt.title }}</a></strong></p>
                  <p class="is-size-7"><em>{{ alt.what_it_is_about }}</em></p>
                  <p class="is-size-7 has-text-weight-semibold">{{ alt.why_you_should_do_it }}</p>
                  <a :href="getExerciseUrl(alt.exercise_id)" class="button is-success is-light is-fullwidth is-small mt-2">Try this one</a>
                </div>
              </div>
            </div>
          </template>
        </section>

        <!-- Typing indicator (while waiting for AI) - scrolls with content -->
        <div v-if="loading" style="margin-bottom: 0.75rem;">
          <div class="typing-indicator" aria-label="Assistant is thinking">
            <span class="dot" style="--ti-delay: 0ms;"></span>
            <span class="dot" style="--ti-delay: 150ms;"></span>
            <span class="dot" style="--ti-delay: 300ms;"></span>
            <span class="helper-text">Generating feedback...</span>
          </div>
        </div>

        <!-- Jump to latest button -->
        <button v-if="showJumpToLatest"
                class="button is-light is-small jump-to-latest"
                title="Jump to latest"
                @click="handleJumpToLatest">
          <span class="icon"><i class="fas fa-angle-down"></i></span>
        </button>
      </div>

      <!-- Input area -->
      <div class="field has-addons mt-3">
        <!-- Single Input Field -->
        <p class="control is-expanded">
          <textarea
              class="textarea"
              v-model="question"
              placeholder="(Shift+Enter for newline)"
              rows="1"
              :disabled="loading || pathwayLoading || pathwayData"
              @keydown="handleKeydown"
              @input="autosizeTextarea"
              style="resize: none; max-height: 40vh"
          ></textarea>
        </p>

        <!-- Ask Question Button -->
        <p class="control">
          <button class="button is-info" @click="askQuestion" :disabled="loading || pathwayLoading || pathwayData">
            <span class="icon">
              <i class="fas fa-question-circle"></i>
            </span>
            <span>Ask Question</span>
          </button>
        </p>
      </div>

       <!-- Course Completion Modal -->
        <div class="modal" :class="{ 'is-active': showCompletionModal }">
          <div class="modal-background" @click="showCompletionModal = false"></div>
          <div class="modal-content has-text-centered" style="position: relative;">
            <button
                aria-label="close"
                @click="showCompletionModal = false"
                style="position: absolute; top: 0.5rem; right: 0.5rem; border: none; background: transparent; color: black; cursor: pointer;"
                title="Close"
            >
                <span class="icon is-large"><i class="fas fa-times"></i></span>
            </button>
            <div class="box">
                <p class="is-size-1">🏆 🎉 🥳</p>
                <h2 class="title">Course Complete!</h2>
                <p class="subtitle">Congratulations on finishing all the exercises in this course!</p>
                <a href="/exercises/dashboard/" class="button is-primary">Back to Dashboard</a>
            </div>
          </div>
        </div>

        <!-- Image Enlarge Modal -->
        <div class="modal" :class="{ 'is-active': showImageModal }">
          <div class="modal-background" @click="showImageModal = false"></div>
          <div class="modal-content" style="max-width: 90vw; max-height: 90vh; display: flex; align-items: center; justify-content: center;">
            <img v-if="modalImageUrl" 
                 :src="modalImageUrl" 
                 alt="Enlarged image" 
                 @click="showImageModal = false"
                 style="max-width: 100%; max-height: 90vh; object-fit: contain; cursor: pointer;" />
          </div>
          <button class="modal-close is-large" aria-label="close" @click="showImageModal = false"></button>
        </div>

    </div>
  `,
  data(): ChatbotPanelData {
    return {
      question: '',
      internalMessages: [], // Panel-managed messages when no external messages are provided
      pathwayLoading: false,
      pathwayData: null,
      showCompletionModal: false,
      showJumpToLatest: false,
      nextMessageId: 0,
      isDarkMode: typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)').matches : false,
      solutionUnlocked: false,
      _submissionsCount: 0,
      showImageModal: false,
      modalImageUrl: null,
      activeDebugTabs: {},
    };
  },
  computed: {
    processedMessages(): ProcessedMessage[] {
      return this.internalMessages.map(message => {
        if (message.role === 'assistant') {
          // Handle backward compatibility for assistant messages
          if (message.debug_fields && typeof message.debug_fields === 'object') {
            // New format - use debug_fields.help_text as default content
            return {
              ...message,
              cleanedContent: message.debug_fields.help_text || '',
              debug_fields: message.debug_fields
            };
          } else {
            // Fallback to old format
            return {
              ...message,
              cleanedContent: message.content || '',
              debug_fields: null
            };
          }
        } else {
          // Non-assistant messages - no changes needed
          return { ...message, cleanedContent: message.content || '' };
        }
      });
    }
  },
  mounted(this: any) {
    this.$nextTick(() => {
      const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
      if (messagesEl) {
        messagesEl.addEventListener('scroll', this.onMessagesScroll, { passive: true });
        // Delay scroll to ensure messages are rendered in the DOM
        // A second nextTick ensures the message content has been painted
        this.$nextTick(() => {
          this.scrollToBottom();
        });
      }
    });
    // Initialize unlocked state from server-provided prop
    this.solutionUnlocked = !!this.$props.solutionUnlockedInitial;
    // Notify parent of initial state so it can show/hide the button in editors
    try { this.$emit('solution-unlocked', this.solutionUnlocked); } catch (_) { /* noop */ }
  },
  watch: {
    loading(this: any, newVal: boolean) {
      // When loading indicator appears, scroll if user is near bottom
      if (newVal) {
        this.$nextTick(() => {
          const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
          if (!messagesEl) return;
          if (this.isNearBottom(messagesEl)) {
            this.scrollToBottom();
          }
        });
      }
    },
    processedMessages: {
      handler(this: any) {
        // After messages update, auto-scroll only if user is near bottom
        this.$nextTick(() => {
          const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
          if (!messagesEl) return;
          if (this.isNearBottom(messagesEl)) {
            this.scrollToBottom();
          } else {
            this.showJumpToLatest = true;
          }
        });
      },
      deep: true
    },
    pathwayLoading(this: any) {
      // Keep scroll behavior consistent when the loading indicator appears/disappears
      this.$nextTick(() => {
        const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
        if (!messagesEl) return;
        if (this.isNearBottom(messagesEl)) {
          this.scrollToBottom();
        } else {
          this.showJumpToLatest = true;
        }
      });
    },
    pathwayData(this: any) {
      // When recommendations load, optionally stick to bottom
      this.$nextTick(() => {
        const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
        if (!messagesEl) return;
        if (this.isNearBottom(messagesEl)) {
          this.scrollToBottom();
        } else {
          this.showJumpToLatest = true;
        }
      });
    }
  },
  methods: {
    clearMessages(this: any) {
      this.internalMessages = [];
      this.showJumpToLatest = false;
      this.$nextTick(() => this.scrollToBottom());
    },
    
    // Debug tab methods
    getActiveDebugTab(this: any, messageId: number): string {
      return this.activeDebugTabs[messageId] || 'help_text';
    },
    
    setActiveDebugTab(this: any, messageId: number, tabName: string) {
      this.activeDebugTabs = { ...this.activeDebugTabs, [messageId]: tabName };
    },
    
    getDebugTabContent(this: any, message: any, tabName: string): string {
      if (!message.debug_fields) return '';
      const content = message.debug_fields[tabName];
      return content || '';
    },
    
    displayMessage(message: any) {
        // Check if user is near bottom BEFORE adding the message
        const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
        const wasNearBottom = messagesEl ? this.isNearBottom(messagesEl) : true;
        
        const isComplete = message.role === 'assistant' && message.content.includes('<exercise_completed>');
        const isSolutionReveal = message.role === 'assistant' && message.content.includes('<solution_revealed>');

        // Always clean tags from the assistant message before displaying it
        const messageToDisplay = (message.role === 'assistant')
            ? { ...message, content: (message.content || '').replace('<exercise_completed>', '').replace('<solution_revealed>', '').trim() }
            : message;

        // Assign a unique ID and mark as new (for animation) for assistant messages
        const messageWithId = { 
            ...messageToDisplay, 
            _id: this.nextMessageId++,
            _isNew: message.role === 'assistant' // Only animate assistant messages
        };
        this.internalMessages.push(messageWithId);
        
        // Remove the _isNew flag after animation completes (300ms)
        if (messageWithId._isNew) {
            setTimeout(() => {
                messageWithId._isNew = false;
            }, 350);
        }
        
        // If user was near bottom, scroll after DOM updates
        if (wasNearBottom) {
            this.$nextTick(() => {
                this.scrollToBottom();
            });
        }

        // Track qualifying submissions from user messages to unlock spoiler button
        try {
            if (messageWithId.role === 'user') {
                const meta = (messageWithId.metadata || {});
                const action = (meta.action || '').trim();
                if (action === 'run_submission' || action === 'submit_answer') {
                    this._submissionsCount += 1;
                    if (!this.solutionUnlocked && this._submissionsCount >= 5) {
                        this.solutionUnlocked = true;
                        try { this.$emit('solution-unlocked', true); } catch (_) { /* noop */ }
                    }
                }
            }
        } catch (_) { /* noop */ }

        if (isComplete) {
            if (this.pathwayData || this.pathwayLoading) {
                return; // A recommendation is already loaded/loading. Do not fire confetti or re-trigger.
            }

            // If we reach here, it's the first time processing completion.
            // Fire confetti and log for debugging.
            if (!isSolutionReveal && !this.confettiAlreadyShown) {
                console.log('Exercise complete: Firing confetti! 🎊');
                confetti({ particleCount: 200, spread: 150, origin: { y: 0.6 } });
            } else if (this.confettiAlreadyShown) {
                console.log('Exercise complete: confetti already shown by exercise component.');
            } else {
                console.log('Exercise complete (solution revealed): confetti suppressed.');
            }

            // Trigger pathway logic, TODO disabled for now
            //if (this.nextExerciseUrl) {
            //    this.fetchPathwayRecommendation();
            //} else {
                // This is the last exercise, show celebration
                // disabled for now this.showCompletionModal = true;
            //}
        }
    },

    async rateTrace(traceId: number, isOk: boolean, messageId: number) {
        try {
            // Optimistic UI update. We must replace the object in the array for Vue's
            // reactivity to reliably detect the change.
            if (messageId !== undefined) {
                const index = this.internalMessages.findIndex(m => m._id === messageId);
                if (index !== -1) {
                    const updatedMessage = {
                        ...this.internalMessages[index],
                        _rating: isOk ? 'ok' : 'not_ok',
                        _rated: true,
                    };
                    this.internalMessages.splice(index, 1, updatedMessage);
                }
            }

            const resp = await fetch('/exercises/api/trace-eval/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ trace_id: traceId, result: isOk ? 'ok' : 'not_ok' })
            });
            if (!resp.ok) {
                console.warn('Trace eval failed', await resp.text());
                // Optional: Rollback UI change on failure here if needed
                return;
            }
        } catch (e) {
            console.warn('Trace eval error', e);
        }
    },

    displayRecommendation(pathwayData: any) {
        // Public method to show pre-existing pathway data on page load
        if (pathwayData) {
            this.pathwayData = pathwayData;
        }
    },

    async fetchPathwayRecommendation() {
        if (!this.attemptId) {
            return; // Not available in generic chat contexts
        }
        this.pathwayLoading = true;
        try {
            const response = await fetch(`/exercises/api/attempts/${this.attemptId}/recommend_pathway/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
            });
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            const result = await response.json();
            if (result.status === 'success') {
                this.pathwayData = result.data;
            } else {
                console.error('Failed to get pathway recommendation:', result.message);
            }
        } catch (error) {
            console.error('Error fetching pathway recommendation:', error);
        } finally {
            this.pathwayLoading = false;
        }
    },

    getExerciseUrl(exerciseId: number) {
        return `/exercises/${exerciseId}/`;
    },

    onMessagesScroll(this: any) {
      const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
      if (!messagesEl) return;
      this.showJumpToLatest = !this.isNearBottom(messagesEl);
    },

    isNearBottom(container: HTMLElement, threshold = 80) {
      const distanceFromBottom = container.scrollHeight - (container.scrollTop + container.clientHeight);
      return distanceFromBottom <= threshold;
    },

    scrollToBottom(this: any) {
      const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
      if (!messagesEl) return;
      messagesEl.scrollTop = messagesEl.scrollHeight;
      this.showJumpToLatest = false;
    },

    handleJumpToLatest(this: any) {
      this.scrollToBottom();
    },

    autosizeTextarea(event: Event) {
      const textarea = event.target as HTMLTextAreaElement;
      // Reset height to auto to ensure the textarea shrinks when text is deleted
      textarea.style.height = 'auto';
      // Set the height to the scroll height to fit the content
      textarea.style.height = `${textarea.scrollHeight}px`;
    },

    openImageModal(this: any, imageUrl: string) {
      this.modalImageUrl = imageUrl;
      this.showImageModal = true;
    },

    getMessageSummary(this: any, message: any) {
        // Generate summary text for collapsible user messages
        if (!message.metadata || !message.metadata.action) {
            return 'User message';
        }

        const { action, question } = message.metadata;

        if (action === 'ask_hint') {
            return '<span class="icon ml-3"><i class="fas fa-lightbulb"></i></span> Hint requested';
        }
        else if (action === 'ask_question') {
            // Show the actual question text with icon
            const questionText = question || 'Question asked';
            return '<span class="icon ml-3"><i class="fas fa-question-circle"></i></span> ' + questionText;
        }
        else if (action === 'run_submission' || action === 'reveal_solution') {
            return '<span class="icon ml-3"><i class="fas fa-code"></i></span> Code submitted to AI tutor';
        }
        else if (action === 'submit_answer') {
            return '<span class="icon ml-3"><i class="fas fa-comment-dots"></i></span> Answer submitted';
        }

        return 'User message';
    },

    // Deprecated: Option buttons removed; no special parsing needed.

    formatUserMessage(message: any) {
        // Display the user messages differently depending on the action. Add icons to the messages.
        if (!message.metadata || !message.metadata.action) {
            return message.content;
        }

        const { action, code, question, error_message } = message.metadata;

        if (action === 'ask_hint') {
            return '<span class="icon"><i class="fas fa-lightbulb"></i></span> _Hint requested_';
        }

        else if (action === 'ask_question') {
            return '<span class="icon"><i class="fas fa-question-circle"></i></span> ' + (question || 'Question asked');
        }

        else if (action === 'run_submission' || action === 'reveal_solution') {
            // Collapsible block for any submission (Python/SQL)
            let detailsContent = message.content || '';
            if (!detailsContent && code) {
                const errorSection = error_message ? `\n\nError:\n\n\`${error_message}\`` : '';
                detailsContent = `\n\n\`\`\`\n${code}\n\`\`\`\n${errorSection}`;
            }
            const renderedDetailsContent = this.renderMarkdown(detailsContent);
            return `
<details class="collapsible-message">
  <summary><span class="icon ml-3"><i class="fas fa-code"></i></span> Code submitted to AI tutor</summary>
  <div class="mt-2">${renderedDetailsContent}</div>
  </details>`;
        }

        else if (action === 'submit_answer') {
            // This is now handled in the template to include images
            // Return content as-is for rendering there
            return message.content;
        }

        return message.content; // Fallback
    },
    askQuestion(this: any) {
      // Emit an event to the parent component
      if (this.question.trim()) {
        const userQuestion = this.question.trim();
        this.$emit('question-asked', userQuestion);

        // Clear the input field after asking the question
        this.question = '';

        // Reset textarea height on next tick after clearing the content
        this.$nextTick(() => {
          const textarea = this.$el.querySelector('textarea');
          if (textarea) {
            textarea.style.height = 'auto';
          }
        });
      }
    },
    handleKeydown(this: any, event: KeyboardEvent) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        this.askQuestion();
      }
      // If Shift+Enter, let the default behavior insert a newline
    },
    renderMarkdown(this: any, content: string) {
      if (!content) return '';
      // Sanitize the content to prevent XSS attacks, then parse Markdown
      let html = DOMPurify.sanitize(marked.parse(content) as string);

      if (this.exercise.allow_image_upload){
        // If the exercise allows images (means it's a math exercise)
        // Then process KaTeX math expressions
        // Handle display math ($$...$$)
        html = html.replace(/\$\$([^$]+)\$\$/g, (match, math) => {
            try {
                return katex.renderToString(math, { 
                    displayMode: true,
                    strict: 'error', // Fail on bad input
                    trust: false // Don't allow \href, etc.
                });
            } catch (e) {
                console.error('KaTeX display math error:', e);
                return match;
            }
        });

        // Handle inline math ($...$) - be careful not to match $$ patterns
        html = html.replace(/(?<!\$)\$([^$\n]+)\$(?!\$)/g, (match, math) => {
            try {
                return katex.renderToString(math, { 
                    displayMode: false,
                    strict: 'error', // Fail on bad input
                    trust: false // Don't allow \href, etc.
                });
            } catch (e) {
                console.error('KaTeX inline math error:', e);
                return match;
            }
        });
      }

      return html;
    }
  }
}); 