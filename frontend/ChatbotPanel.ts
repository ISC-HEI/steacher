import { marked } from 'marked';
import DOMPurify from 'dompurify';

export const ChatbotPanel = {
  props: {
    initialQuestion: {
      type: String,
      default: ''
    },
    messages: {
      type: Array,
      default: () => []
    },
    loading: {  // used to disable the question input field while loading
      type: Boolean,
      default: false,
    }
  },
  // language=HTML
  template: `
    <div id="chatbot" ref="chatContainer">
      <div class="chat-content">

        <!-- First, we display the initial question of the exercise -->
        <div v-if="initialQuestion"
             v-html="initialQuestion"
             ref="initialQuestionMessage"
             class="box mb-3 assistant-message initial-question"></div>

        <!-- Chatbot Content. A list of messages exchanged between the user and the assistant. -->
        <div>
          <template v-for="(message, index) in messages">
            <div v-if="message.role === 'user' && message.content"
                 v-html="renderMarkdown(formatUserMessage(message))"
                 class="box mb-3 user-message"
                 :key="'user-' + index"></div>
            <div v-if="message.role === 'assistant' && message.content"
                 v-html="renderMarkdown(message.content)"
                 class="box mb-3 assistant-message"
                 :key="'assistant-' + index"></div>
          </template>
        </div>
      </div>

      <!-- Text Input and Button for asking a question. -->
      <div class="field has-addons mt-3">
        <!-- Single Input Field -->
        <p class="control is-expanded">
          <input
              class="input"
              type="text"
              v-model="question"
              placeholder="Enter your question"
              @keyup.enter="askQuestion"
              :disabled="loading"
          />
        </p>

        <!-- Ask Question Button -->
        <p class="control">
          <button class="button is-info" @click="askQuestion" :disabled="loading">
            <span class="icon">
              <i class="fas fa-question-circle"></i>
            </span>
            <span>Ask Question</span>
          </button>
        </p>

      </div>
    </div>
  `,
  data() {
    return {
      question: '',
    };
  },
  mounted(this: any) {
    // Highlight the initial question for 4 seconds
    if (this.initialQuestion && this.$refs.initialQuestionMessage) {
      const el = this.$refs.initialQuestionMessage as HTMLElement;
      el.classList.add('highlight-question');
      setTimeout(() => {
        el.classList.remove('highlight-question');
      }, 4000); // Remove after 4 seconds (duration of animation)
    }
  },
  watch: {
    messages: {
      handler(this: any) {
        // Use nextTick to wait for the DOM to update
        this.$nextTick(() => {
          const container = this.$refs.chatContainer as HTMLElement;
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        });
      },
      deep: true // Watch for changes inside the array
    }
  },
  methods: {
    formatUserMessage(message: any) {
        // Display the user messages differently depending on the action. Add icons to the messages.
        if (!message.metadata || !message.metadata.action) {
            return message.content;
        }

        const { action, code, question, error_message } = message.metadata;

        if (action === 'ask_hint') {
            return '<span class="icon"><i class="fas fa-lightbulb"></i></span> _Hint requested_';
        }

        if (action === 'ask_question') {
            return '<span class="icon"><i class="fas fa-question-circle"></i></span> ' + (question || 'Question asked');
        }

        if (action === 'run_query' && code) {
            let display = '';

            const lines = code.split('\n');
            if (lines.length > 2) {
                display += `\`${lines.slice(0, 2).join('\n')}\n...\n\``;
            } else {
                display += `\`${code}\``;
            }

            if (error_message) {
                display += `<br/>\`${error_message.replace('SQL Error: ', '')}\``;
            }

            return display;
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
      }
    },
    renderMarkdown(this: any, content: string) {
      if (!content) return '';
      // Sanitize the content to prevent XSS attacks, then parse Markdown
      return DOMPurify.sanitize(marked.parse(content) as string);
    }
  }
}; 