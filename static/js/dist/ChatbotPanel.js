import { marked } from 'marked';
import DOMPurify from 'dompurify';
export const ChatbotPanel = {
    props: {
        initialQuestion: {
            type: String,
            default: ''
        }
    },
    // language=HTML
    template: `
    <div id="chatbot">
      <!-- Initial Question -->
      <div v-if="initialQuestion"
           v-html="initialQuestion"
           ref="initialQuestionMessage"
           class="box mb-3 assistant-message"></div>
      <!-- Chatbot Content -->
      <div>
        <template v-for="(message, index) in chatMessages">
          <div v-if="message.role === 'user' && message.question !== ''"
               v-html="message.question"
               class="box mb-3 user-message"
               :key="'user-' + index"></div>
          <div v-if="message.role === 'assistant'"
               v-html="renderMarkdown(message.content)"
               class="box mb-3 assistant-message"
               :key="'assistant-' + index"></div>
        </template>
      </div>

      <!-- Section for Question Input and Hint Button -->
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
          <button class="button is-info" @click="askQuestion" :disabled="loading">Ask Question</button>
        </p>
      </div>

    </div>
  `,
    data() {
        return {
            chatMessages: [],
            question: '',
            loading: false,
        };
    },
    mounted() {
        if (this.initialQuestion && this.$refs.initialQuestionMessage) {
            const el = this.$refs.initialQuestionMessage;
            el.classList.add('highlight-question');
            setTimeout(() => {
                el.classList.remove('highlight-question');
            }, 4000); // Remove after 4 seconds (duration of animation)
        }
    },
    methods: {
        askQuestion() {
            // Placeholder for sending question to backend
            if (this.question.trim()) {
                this.chatMessages.push({ role: 'user', question: this.question });
                // In a real app, you would make an API call here.
                // For now, we'll just simulate a response.
                this.loading = true;
                setTimeout(() => {
                    this.chatMessages.push({ role: 'assistant', content: 'This is a simulated response.' });
                    this.loading = false;
                }, 1000);
                this.question = '';
            }
        },
        renderMarkdown(content) {
            if (!content)
                return '';
            // Sanitize the content to prevent XSS attacks, then parse Markdown
            return DOMPurify.sanitize(marked.parse(content));
        }
    }
};
