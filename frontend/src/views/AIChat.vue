<template>
  <section class="ai-page">
    <header class="chat-header">
      <div class="chat-heading">
        <span class="assistant-mark">AI</span>
        <div>
          <h1>AI 实验室助手</h1>
          <p>查规则、找资源，让预约更简单</p>
        </div>
      </div>
      <span class="confirm-badge"><span></span>核对后再提交</span>
    </header>

    <div ref="listRef" class="chat-messages" role="log" aria-label="对话记录" aria-live="polite">
      <div class="chat-inner">
        <article
          v-for="(item, index) in messages"
          :key="index"
          class="message-row"
          :class="{ 'is-user': item.role === 'user' }"
        >
          <div class="message-avatar" aria-hidden="true">
            {{ item.role === 'user' ? '我' : 'AI' }}
          </div>
          <div class="message-column">
            <div class="message-meta">
              <span>{{ item.role === 'user' ? '你' : '实验室助手' }}</span>
              <span v-if="item.role === 'assistant' && item.status" class="message-status">
                <i></i>{{ item.status }}
              </span>
            </div>
            <div class="message-bubble">
              <details v-if="item.role === 'assistant' && item.steps?.length" class="tool-details">
                <summary>
                  处理过程 <span>{{ item.steps.length }} 条记录</span>
                </summary>
                <div class="tool-records">
                  <div v-for="(step, i) in item.steps" :key="i">{{ step }}</div>
                </div>
              </details>
              <div class="message-markdown" v-html="parseMarkdown(item.content)"></div>
              <ReservationDraftCard
                v-for="draft in item.drafts || []"
                :key="draft.draft_id"
                :draft="draft"
                @confirmed="handleReservationConfirmed"
                @cancelled="handleDraftCancelled"
              />
            </div>
          </div>
        </article>

        <div v-if="messages.length === 1" class="suggestions">
          <span>试着问问</span>
          <button
            v-for="question in suggestions"
            :key="question"
            type="button"
            @click="fillSuggestion(question)"
          >
            {{ question }} <span aria-hidden="true">↗</span>
          </button>
        </div>
      </div>
    </div>

    <footer class="composer-area">
      <div class="composer">
        <el-input
          ref="composerInput"
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="例如：帮我找一个明天下午开放的实验室"
          aria-label="输入消息"
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.stop
        />
        <div class="composer-bar">
          <span>先核对确认单，再提交预约</span>
          <el-button
            type="primary"
            class="send-button"
            :disabled="!input.trim()"
            :loading="loading"
            @click="handleSend"
          >
            发送 <span class="send-arrow" aria-hidden="true">↗</span>
          </el-button>
        </div>
      </div>
      <p class="keyboard-hint">Enter 发送 <span>·</span> Shift + Enter 换行</p>
    </footer>
  </section>
</template>

<script setup>
import { ref, reactive, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify' // 过滤危险的 HTML，防止 XSS 攻击
import { chatStreamApi } from '@/api/ai'
import ReservationDraftCard from '@/components/ReservationDraftCard.vue'
import { ElMessage } from 'element-plus'

const messages = ref([
  {
    role: 'assistant',
    content:
      '你好，我是实验室预约助手。可以问规则和开放实验室，也可以让我生成预约确认单，核对卡片并点击「确认预约」后提交。'
  }
])
const input = ref('')
const loading = ref(false)
const listRef = ref()
const composerInput = ref()
const suggestions = ['有哪些开放的实验室？', '预约需要提前多久？', '帮我查看预约记录']
const fillSuggestion = (question) => {
  input.value = question
  composerInput.value?.focus()
}

const scrollToBottom = () => {
  nextTick(() => {
    const elem = listRef.value
    if (elem) elem.scrollTop = elem.scrollHeight
  })
}

const handleReservationConfirmed = ({ reservationId }) => {
  messages.value.push({
    role: 'assistant',
    content: `预约 #${reservationId} 已提交，等待管理员审核。`
  })
  scrollToBottom()
}

const handleDraftCancelled = ({ draftId, status }) => {
  messages.value.push({
    role: 'assistant',
    content: `待确认单 #${draftId} ${status === 'expired' ? '已过期' : '已取消'}，未创建预约。`
  })
  scrollToBottom()
}

const handleSend = async () => {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  scrollToBottom()

  // 必须用 reactive：普通对象 push 后再改字段，视图可能不更新
  const assistant = reactive({
    role: 'assistant',
    content: '', // 正文：靠 token 一点点拼
    status: '正在思考…', // 当前状态文案
    steps: [], // 过程流水，不进下次 history
    drafts: []
  })
  messages.value.push(assistant)

  const history = messages.value
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .slice(0, -1) // 去掉刚插入的空助手，避免把空 content 送回去
    // 只保留 role/content；status、steps 丢掉
    .map(({ role, content }) => ({ role, content }))

  try {
    // 第二个参数是回调：每解析出一条 SSE 事件就进一次
    await chatStreamApi({ messages: history }, (evt) => {
      if (evt.type === 'status') {
        assistant.status = evt.message || '正在思考…'
      } else if (evt.type === 'tool_start') {
        const label = evt.label || evt.name || '工具'
        assistant.status = `正在${label}…`
        assistant.steps.push(`开始：${label}`)
      } else if (evt.type === 'tool_end') {
        const label = evt.label || evt.name || '工具'
        assistant.status = `${label}完成`
        assistant.steps.push(`完成：${label}`)
        if (evt.preview) {
          assistant.steps.push(`输出结果：${evt.preview}`)
        }
      } else if (evt.type === 'reservation_draft') {
        const draft = evt.data
        if (
          draft?.ok === true &&
          !assistant.drafts.some((item) => item.draft_id === draft.draft_id)
        ) {
          assistant.drafts.push(draft)
        }
      } else if (evt.type === 'token') {
        assistant.content += evt.content || '' // 打字机：追加，不是覆盖
        assistant.status = '' // 开始出字后清掉「正在…」，避免叠在一起
      } else if (evt.type === 'done') {
        assistant.status = ''
        // 注意：不要在这里再 append 一整段正文，否则会双份
      } else if (evt.type === 'error') {
        assistant.status = ''
        if (!assistant.content) {
          assistant.content = evt.message || '请求失败'
        }
        ElMessage.error(evt.message || '请求失败')
      }
      scrollToBottom()
    })
  } catch (err) {
    assistant.status = ''
    if (!assistant.content) {
      assistant.content = err.message || '网络异常'
    }
    ElMessage.error(err.message || '网络异常')
  } finally {
    loading.value = false
    assistant.status = ''
    scrollToBottom()
  }
}

// 将 markdown 字符串转换为安全的 HTML 字符串
const parseMarkdown = (text) => {
  if (!text) return ''
  marked.setOptions({ breaks: true }) // 把 \n 转换成 <br>
  // 使用 marked 解析，然后用 DOMPurify 清理
  const rawHtml = marked.parse(text)
  return DOMPurify.sanitize(rawHtml)
}
</script>

<style scoped>
.ai-page {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 120px);
  min-height: 540px;
  max-height: 1000px;
  max-width: 1360px;
  margin: 0 auto;
  border: 1px solid #e3e9f3;
  border-radius: 16px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 6px 24px #243e6604;
}
.chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 20px 28px;
  border-bottom: 1px solid #edf0f6;
}
.chat-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}
.assistant-mark {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(145deg, #6e8af4, #4166e8);
  font-size: 15px;
  font-weight: 650;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 10px #4166e819;
}
.chat-heading h1 {
  font-size: 17px;
  font-weight: 650;
  color: #293a56;
}
.chat-heading p {
  margin-top: 5px;
  font-size: 11px;
  color: #95a0b2;
}
.confirm-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 20px;
  color: #7e8ca7;
  background: #f5f7fc;
  font-size: 11px;
  white-space: nowrap;
}
.confirm-badge > span {
  width: 5px;
  height: 5px;
  background: #8da4e5;
  border-radius: 50%;
}
.chat-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: #fafbfe;
  scrollbar-width: thin;
  scrollbar-color: #dde4f0 transparent;
}
.chat-inner {
  max-width: 1000px;
  margin: 0 auto;
  padding: 29px 30px;
}
.message-row {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  margin-bottom: 24px;
}
.message-avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  margin-top: 23px;
  border: 1px solid #dfe7fc;
  border-radius: 10px;
  color: #5d7cdc;
  background: #eef3ff;
  font-size: 10px;
  font-weight: 650;
}
.message-column {
  min-width: 0;
  max-width: min(86%, 780px);
}
.message-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 2px 7px;
  color: #929eb2;
  font-size: 10px;
}
.message-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #8a9cbd;
}
.message-status i {
  width: 4px;
  height: 4px;
  background: #8ba3e6;
  border-radius: 50%;
}
.message-bubble {
  padding: 13px 17px;
  border: 1px solid #e8edf5;
  border-radius: 3px 14px 14px;
  color: #526078;
  background: #fff;
  font-size: 13px;
  line-height: 1.85;
  overflow-wrap: anywhere;
  box-shadow: 0 2px 6px #243e6603;
}
.is-user {
  justify-content: flex-end;
}
.is-user .message-avatar {
  order: 2;
  background: #e9edf5;
  border-color: #e3e8f1;
  color: #8491a7;
  font-size: 12px;
}
.is-user .message-meta {
  justify-content: flex-end;
}
.is-user .message-bubble {
  color: #fff;
  border-color: #4166e8;
  background: #4166e8;
  border-radius: 14px 3px 14px 14px;
  box-shadow: none;
}
.message-markdown :deep(p + p) {
  margin-top: 10px;
}
.message-markdown :deep(ul),
.message-markdown :deep(ol) {
  margin: 9px 0;
  padding-left: 21px;
}
.message-markdown :deep(ul) {
  list-style: disc;
}
.message-markdown :deep(ol) {
  list-style: decimal;
}
.message-markdown :deep(li + li) {
  margin-top: 4px;
}
.message-markdown :deep(h1),
.message-markdown :deep(h2),
.message-markdown :deep(h3) {
  margin: 12px 0 6px;
  font-size: 14px;
  color: inherit;
}
.message-markdown :deep(strong) {
  font-weight: 650;
  color: #364761;
}
.message-markdown :deep(a) {
  color: #4166e8;
  text-decoration: underline;
}
.message-markdown :deep(pre) {
  margin: 10px 0;
  padding: 12px;
  background: #f4f6fb;
  border-radius: 8px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.message-markdown :deep(code) {
  padding: 2px 4px;
  border-radius: 4px;
  background: #f2f5fc;
  color: #586d9e;
  font-size: 12px;
}
.message-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
}
.is-user .message-markdown :deep(strong),
.is-user .message-markdown :deep(a) {
  color: #fff;
}
.tool-details {
  margin-bottom: 10px;
  color: #95a0b3;
  font-size: 11px;
}
.tool-details summary {
  cursor: pointer;
  user-select: none;
}
.tool-details summary > span {
  margin-left: 8px;
  color: #adb7c7;
  font-size: 10px;
}
.tool-records {
  max-height: 190px;
  overflow-y: auto;
  margin-top: 9px;
  padding: 9px 11px;
  background: #f7f9fd;
  border-radius: 7px;
  line-height: 1.8;
}
.tool-records > div + div {
  margin-top: 5px;
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: -4px 0 14px 41px;
}
.suggestions > span {
  width: 100%;
  margin-bottom: 2px;
  font-size: 10px;
  color: #a2adbf;
}
.suggestions button {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid #e4eaf5;
  border-radius: 8px;
  background: #fff;
  color: #7b8ba7;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.suggestions button:hover {
  color: #4166e8;
  border-color: #cad7fb;
  background: #f5f8ff;
}
.suggestions button > span {
  color: #a4b4d2;
}
.composer-area {
  flex-shrink: 0;
  padding: 18px 28px 12px;
  border-top: 1px solid #edf0f6;
  background: #fff;
}
.composer {
  max-width: 940px;
  margin: 0 auto;
  border: 1px solid #e0e6f1;
  border-radius: 12px;
  padding: 3px;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.composer:focus-within {
  border-color: #9bb1f6;
  box-shadow: 0 0 0 3px #edf2ff;
}
.composer :deep(.el-textarea__inner) {
  min-height: 56px !important;
  padding: 11px 12px 5px;
  border: 0;
  border-radius: 10px;
  box-shadow: none !important;
  resize: none;
  font: inherit;
  font-size: 13px;
  color: #526078;
  line-height: 1.7;
}
.composer :deep(.el-textarea__inner::placeholder) {
  color: #a8b2c3;
}
.composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 7px 6px 12px;
}
.composer-bar > span {
  color: #a6b0c1;
  font-size: 10px;
}
.send-button {
  height: 32px;
  padding: 0 15px;
  font-size: 12px;
  border-radius: 8px;
}
.send-arrow {
  margin-left: 7px;
  font-size: 15px;
}
.keyboard-hint {
  text-align: center;
  margin-top: 8px;
  font-size: 10px;
  color: #aeb7c6;
}
.keyboard-hint span {
  padding: 0 5px;
}
@media (max-width: 768px) {
  .ai-page {
    height: calc(100dvh - 96px);
    min-height: 460px;
    border-radius: 13px;
  }
  .chat-header {
    padding: 17px;
  }
  .chat-heading h1 {
    font-size: 15px;
  }
  .chat-heading p {
    font-size: 10px;
  }
  .confirm-badge {
    display: none;
  }
  .chat-inner {
    padding: 23px 15px;
  }
  .message-row {
    gap: 8px;
  }
  .message-avatar {
    width: 25px;
    height: 25px;
    border-radius: 8px;
  }
  .message-column {
    max-width: calc(100% - 33px);
  }
  .message-bubble {
    padding: 11px 12px;
  }
  .suggestions {
    margin-left: 33px;
  }
  .composer-area {
    padding: 14px 14px 9px;
  }
  .composer-bar > span {
    font-size: 9px;
  }
}
</style>
