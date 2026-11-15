<template>
  <section class="ai-page">
    <aside class="history-sidebar" :class="{ 'is-open': historyOpen }" aria-label="历史会话">
      <div class="history-heading">
        <span>我的会话</span>
        <button type="button" :disabled="busy || listLoading" @click="refreshConversations()">
          刷新
        </button>
      </div>
      <button class="new-chat-button" type="button" :disabled="busy" @click="startNewConversation">
        ＋ 新建会话
      </button>
      <p v-if="listError" class="history-error" role="alert">{{ listError }}</p>
      <p v-if="!conversations.length && !listLoading && !listError" class="history-empty">
        发送第一条消息，开始新的对话
      </p>
      <nav class="conversation-list" aria-label="选择会话">
        <div
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation-row"
          :class="{ active: currentConversationId === conversation.id }"
        >
          <button
            type="button"
            class="conversation-select"
            :disabled="busy"
            :aria-current="currentConversationId === conversation.id ? 'true' : undefined"
            @click="selectConversation(conversation.id)"
          >
            <span class="conversation-title">{{ conversation.title }}</span>
            <span class="conversation-time">{{ formatTime(conversation.update_time) }}</span>
          </button>
          <button
            type="button"
            class="conversation-delete"
            :aria-label="`删除会话：${conversation.title}`"
            :disabled="busy"
            @click="deleteConversation(conversation)"
          >
            ×
          </button>
        </div>
      </nav>
      <button
        v-if="conversations.length < conversationTotal"
        class="history-more"
        type="button"
        :disabled="busy || listLoading"
        @click="refreshConversations(true)"
      >
        加载更多会话
      </button>
      <p v-if="listLoading" class="history-empty" role="status">正在加载会话…</p>
    </aside>
    <button
      v-if="historyOpen"
      type="button"
      class="history-backdrop"
      aria-label="关闭历史会话"
      @click="historyOpen = false"
    ></button>
    <div class="chat-workspace">
      <header class="chat-header">
        <div class="chat-heading">
          <button
            type="button"
            class="history-toggle"
            :aria-expanded="historyOpen"
            @click="historyOpen = !historyOpen"
          >
            会话
          </button>
          <span class="assistant-mark">AI</span>
          <div>
            <h1>AI 实验室助手</h1>
            <p>{{ currentTitle }}</p>
          </div>
        </div>
        <span class="confirm-badge"><span></span>核对后再提交</span>
      </header>

      <div v-if="restoredHistory" class="history-notice">
        历史会话暂不恢复预约卡片。未确认的预约请重新生成确认单，已提交的预约可到预约记录查看。
      </div>
      <div v-if="historyError || syncRequired" class="chat-warning" role="alert">
        <span>{{ historyError || '本次回复的保存结果尚未确认，请刷新记录后继续。' }}</span>
        <button type="button" :disabled="busy" @click="reloadRecords">刷新记录</button>
      </div>
      <div ref="listRef" class="chat-messages" role="log" aria-label="对话记录" aria-live="polite">
        <div class="chat-inner">
          <button
            v-if="hasOlderMessages"
            class="older-messages"
            type="button"
            :disabled="busy"
            @click="loadOlderMessages"
          >
            查看更早消息
          </button>
          <p v-if="initializing || historyLoading" class="history-empty" role="status">
            正在加载记录…
          </p>
          <article
            v-for="item in messages"
            :key="item.key"
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
                <details
                  v-if="item.role === 'assistant' && item.steps?.length"
                  class="tool-details"
                >
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
                  @confirmed="handleReservationConfirmed($event, item)"
                  @cancelled="handleDraftCancelled($event, item)"
                />
                <p v-if="item.notice" class="operation-notice" role="status">{{ item.notice }}</p>
                <p v-if="item.error" class="message-error" role="alert">{{ item.error }}</p>
              </div>
            </div>
          </article>

          <div v-if="!currentConversationId && historyReady" class="suggestions">
            <span>试着问问</span>
            <button
              v-for="question in suggestions"
              :key="question"
              type="button"
              :disabled="busy"
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
            :disabled="!canCompose"
            :maxlength="2000"
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
              :disabled="!canCompose || !input.trim()"
              :loading="loading"
              @click="handleSend"
            >
              发送 <span class="send-arrow" aria-hidden="true">↗</span>
            </el-button>
          </div>
        </div>
        <p class="keyboard-hint">Enter 发送 <span>·</span> Shift + Enter 换行</p>
      </footer>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify' // 过滤危险的 HTML，防止 XSS 攻击
import {
  chatStreamApi,
  getConversationsApi,
  getConversationMessagesApi,
  deleteConversationApi
} from '@/api/ai'
import ReservationDraftCard from '@/components/ReservationDraftCard.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const welcome = () => [
  {
    key: 'welcome',
    role: 'assistant',
    content:
      '你好，我是实验室预约助手。可以问规则和开放实验室，也可以让我生成预约确认单，核对卡片并点击「确认预约」后提交。'
  }
]
const messages = ref(welcome())
const input = ref('')
const loading = ref(false)
const listRef = ref()
const composerInput = ref()
const conversations = ref([])
const conversationTotal = ref(0)
const currentConversationId = ref(null)
const initializing = ref(true)
const listLoading = ref(false)
const historyLoading = ref(false)
const deleting = ref(false)
const historyReady = ref(false)
const historyOpen = ref(false)
const restoredHistory = ref(false)
const syncRequired = ref(false)
const listError = ref('')
const historyError = ref('')
const historyTotal = ref(0)
const messagePage = ref(1)
const pageSize = 50
const busy = computed(
  () => initializing.value || loading.value || historyLoading.value || deleting.value
)
const canCompose = computed(
  () => historyReady.value && !busy.value && !syncRequired.value && !historyError.value
)
const hasOlderMessages = computed(() => messagePage.value * pageSize < historyTotal.value)
const currentTitle = computed(
  () =>
    conversations.value.find((item) => item.id === currentConversationId.value)?.title ||
    '查规则、找资源，让预约更简单'
)
const lifecycleController = new AbortController()
let streamController
let disposed = false
let listVersion = 0
let conversationPage = 1
let localSequence = 0

const resultData = (response) => {
  if (response?.code !== 200) throw new Error(response?.message || '读取会话失败')
  return response.data
}
const toMessage = (message) => ({
  key: `message-${message.id}`,
  id: message.id,
  role: message.role,
  content: message.content,
  status: '',
  steps: [],
  drafts: []
})
const formatTime = (value) =>
  String(value || '')
    .replace('T', ' ')
    .slice(5, 16)

const refreshConversations = async (append = false) => {
  const version = ++listVersion
  listLoading.value = true
  listError.value = ''
  const page = append ? conversationPage + 1 : 1
  try {
    const data = resultData(
      await getConversationsApi({ page, page_size: 20 }, lifecycleController.signal)
    )
    if (disposed || version !== listVersion) return false
    const previousIds = new Set(conversations.value.map((item) => item.id))
    conversations.value = append
      ? [...conversations.value, ...data.list.filter((item) => !previousIds.has(item.id))]
      : data.list
    conversationPage = page
    conversationTotal.value = data.total
    return true
  } catch (error) {
    if (!disposed && version === listVersion)
      listError.value = error.message || '加载会话失败，请刷新重试'
    return false
  } finally {
    if (version === listVersion) listLoading.value = false
  }
}

const loadConversation = async (id) => {
  historyLoading.value = true
  historyReady.value = false
  historyError.value = ''
  try {
    const data = resultData(
      await getConversationMessagesApi(
        id,
        { page: 1, page_size: pageSize },
        lifecycleController.signal
      )
    )
    if (disposed) return
    currentConversationId.value = id
    messages.value = data.list.length ? data.list.map(toMessage) : welcome()
    historyTotal.value = data.total
    messagePage.value = 1
    restoredHistory.value = true
    syncRequired.value = false
    historyReady.value = true
    input.value = ''
    historyOpen.value = false
    scrollToBottom()
  } catch (error) {
    if (!disposed) historyError.value = error.message || '加载消息失败，请刷新重试'
  } finally {
    historyLoading.value = false
  }
}

const selectConversation = async (id) => {
  if (busy.value) return
  if (
    id === currentConversationId.value &&
    !syncRequired.value &&
    historyReady.value &&
    !historyError.value
  ) {
    historyOpen.value = false
    return
  }
  await loadConversation(id)
}

const startNewConversation = () => {
  if (busy.value) return
  currentConversationId.value = null
  messages.value = welcome()
  input.value = ''
  historyTotal.value = 0
  messagePage.value = 1
  restoredHistory.value = false
  syncRequired.value = false
  historyError.value = ''
  historyReady.value = true
  historyOpen.value = false
}

const reloadRecords = async () => {
  if (busy.value) return
  initializing.value = true
  try {
    if (!(await refreshConversations())) return
    const id = currentConversationId.value || conversations.value[0]?.id
    if (id) await loadConversation(id)
    else {
      initializing.value = false
      startNewConversation()
    }
  } finally {
    initializing.value = false
  }
}

const loadOlderMessages = async () => {
  if (busy.value || !hasOlderMessages.value) return
  historyLoading.value = true
  const oldestId = Math.min(...messages.value.filter((item) => item.id).map((item) => item.id))
  const element = listRef.value
  const previousHeight = element?.scrollHeight || 0
  const previousTop = element?.scrollTop || 0
  try {
    // New turns can shift offset pages; only prepend rows older than the visible oldest message.
    while (true) {
      const page = messagePage.value + 1
      const data = resultData(
        await getConversationMessagesApi(
          currentConversationId.value,
          { page, page_size: pageSize },
          lifecycleController.signal
        )
      )
      if (disposed) return
      messagePage.value = page
      historyTotal.value = data.total
      const older = data.list.filter((item) => item.id < oldestId).map(toMessage)
      if (older.length) messages.value.unshift(...older)
      if (older.length || page * pageSize >= data.total) break
    }
    await nextTick()
    if (element) element.scrollTop = previousTop + element.scrollHeight - previousHeight
  } catch (error) {
    if (!disposed) ElMessage.error(error.message || '加载更早消息失败')
  } finally {
    historyLoading.value = false
  }
}

const deleteConversation = async (conversation) => {
  if (busy.value) return
  deleting.value = true
  try {
    await ElMessageBox.confirm(
      `删除「${conversation.title}」及其中的聊天记录？预约记录不会删除。`,
      '删除会话',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    resultData(await deleteConversationApi(conversation.id, lifecycleController.signal))
    if (disposed) return
    if (currentConversationId.value === conversation.id) {
      deleting.value = false
      startNewConversation()
    }
    await refreshConversations()
  } catch (error) {
    if (!disposed && error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.message || '删除结果尚未确认，请刷新会话列表核对')
    }
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  try {
    if (!(await refreshConversations()) || disposed) return
    if (conversations.value.length) await loadConversation(conversations.value[0].id)
    else historyReady.value = true
  } finally {
    initializing.value = false
  }
})
onBeforeUnmount(() => {
  disposed = true
  streamController?.abort()
  lifecycleController.abort()
})
const suggestions = ['有哪些开放的实验室？', '预约需要提前多久？', '帮我查看预约记录']
const fillSuggestion = (question) => {
  if (!canCompose.value) return
  input.value = question
  composerInput.value?.focus()
}

const scrollToBottom = () => {
  nextTick(() => {
    const elem = listRef.value
    if (elem) elem.scrollTop = elem.scrollHeight
  })
}

const handleReservationConfirmed = ({ reservationId }, message) => {
  message.notice = `预约 #${reservationId} 已提交，等待管理员审核。`
  scrollToBottom()
}

const handleDraftCancelled = ({ draftId, status }, message) => {
  message.notice = `待确认单 #${draftId} ${status === 'expired' ? '已过期' : '已取消'}，未创建预约。`
  scrollToBottom()
}

const handleSend = async () => {
  const text = input.value.trim()
  if (!text || !canCompose.value) return
  if (Array.from(text).length > 2000) {
    ElMessage.error('消息不能超过2000个字符')
    return
  }

  messages.value.push({ key: `local-${++localSequence}`, role: 'user', content: text })
  input.value = ''
  loading.value = true
  scrollToBottom()

  // 必须用 reactive：普通对象 push 后再改字段，视图可能不更新
  const assistant = reactive({
    key: `local-${++localSequence}`,
    role: 'assistant',
    content: '', // 正文：靠 token 一点点拼
    status: '正在思考…', // 当前状态文案
    steps: [], // 过程流水，不进下次 history
    drafts: []
  })
  messages.value.push(assistant)

  const requestConversationId = currentConversationId.value
  streamController = new AbortController()
  let completed = false

  try {
    // 第二个参数是回调：每解析出一条 SSE 事件就进一次
    await chatStreamApi(
      { conversation_id: requestConversationId, message: text },
      (evt) => {
        if (disposed) return
        if (evt.type === 'conversation') {
          if (
            !Number.isInteger(evt.conversation_id) ||
            evt.conversation_id <= 0 ||
            (requestConversationId !== null && evt.conversation_id !== requestConversationId)
          ) {
            throw new Error('会话信息异常，请刷新记录后重试')
          }
          currentConversationId.value = evt.conversation_id
          void refreshConversations()
        } else if (evt.type === 'status') {
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
          if (
            evt.conversation_id !== currentConversationId.value ||
            !Number.isInteger(evt.message_id) ||
            evt.message_id <= 0
          ) {
            throw new Error('回复保存结果异常，请刷新记录核对')
          }
          assistant.id = evt.message_id
          completed = true
          assistant.status = ''
          // 注意：不要在这里再 append 一整段正文，否则会双份
        } else if (evt.type === 'error') {
          throw new Error(evt.message || '回复失败，请刷新记录后重试')
        }
        scrollToBottom()
      },
      { signal: streamController.signal }
    )
    if (!completed) throw new Error('回复未完成，请刷新记录确认保存结果')
  } catch (err) {
    if (disposed) return
    assistant.status = ''
    assistant.error = err.message || '网络异常'
    syncRequired.value = !err.status || err.status >= 500
    if (err.status === 404)
      historyError.value = '该会话已不存在或无法访问，请新建会话或选择其他会话。'
    if (!syncRequired.value && !input.value) input.value = text
    ElMessage.error(err.message || '网络异常')
  } finally {
    loading.value = false
    assistant.status = ''
    if (!disposed) void refreshConversations()
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
  position: relative;
  display: flex;
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
.chat-workspace {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.history-sidebar {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 220px;
  padding: 20px 12px;
  border-right: 1px solid #e8edf5;
  background: #f8faff;
  overflow-y: auto;
}
.history-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 6px 15px;
  color: #526078;
  font-size: 13px;
  font-weight: 600;
}
.history-sidebar button,
.history-toggle,
.chat-warning button,
.older-messages {
  font: inherit;
  cursor: pointer;
}
.history-sidebar button:disabled,
.older-messages:disabled,
.chat-warning button:disabled,
.suggestions button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.history-heading button,
.history-more {
  border: 0;
  background: transparent;
  color: #667eaf;
  font-size: 11px;
}
.new-chat-button {
  flex-shrink: 0;
  width: 100%;
  padding: 10px;
  border: 1px solid #dce5fc;
  border-radius: 9px;
  background: #fff;
  color: #4166e8;
  font-size: 12px !important;
}
.conversation-list {
  margin-top: 13px;
}
.conversation-row {
  display: flex;
  align-items: center;
  margin-bottom: 5px;
  border: 1px solid transparent;
  border-radius: 9px;
}
.conversation-row.active {
  background: #eaf0ff;
  border-color: #dfe7fc;
}
.conversation-row:hover {
  background: #eef3fd;
}
.conversation-select {
  flex: 1;
  min-width: 0;
  padding: 11px 7px 11px 10px;
  border: 0;
  background: transparent;
  text-align: left;
}
.conversation-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #526078;
  font-size: 12px;
}
.conversation-time {
  display: block;
  margin-top: 5px;
  color: #9aa7bc;
  font-size: 10px;
}
.conversation-delete {
  flex-shrink: 0;
  margin-right: 5px;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #98a5bb;
}
.conversation-delete:hover {
  background: #fff0f0;
  color: #c26363;
}
.history-more {
  padding: 12px;
}
.history-empty {
  padding: 15px 7px;
  text-align: center;
  color: #98a5bb;
  font-size: 11px;
  line-height: 1.8;
}
.history-error,
.message-error {
  margin-top: 10px;
  color: #b76557;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.history-notice {
  flex-shrink: 0;
  padding: 9px 24px;
  background: #f5f8ff;
  color: #8695ae;
  font-size: 11px;
  line-height: 1.7;
}
.chat-warning {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 12px;
  padding: 10px 20px;
  background: #fff7e8;
  color: #9d7740;
  font-size: 12px;
}
.chat-warning button,
.older-messages {
  flex-shrink: 0;
  padding: 5px 10px;
  border: 1px solid #e0e6f1;
  border-radius: 7px;
  background: #fff;
  color: #7185a8;
  font-size: 11px;
}
.older-messages {
  display: block;
  margin: 0 auto 20px;
}
.operation-notice {
  margin-top: 10px;
  color: #5b8b74;
  font-size: 12px;
}
.history-toggle,
.history-backdrop {
  display: none;
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
  .history-sidebar {
    position: absolute;
    inset: 0 auto 0 0;
    z-index: 3;
    display: none;
    width: min(260px, 82%);
    box-shadow: 6px 0 24px #243e6614;
  }
  .history-sidebar.is-open {
    display: flex;
  }
  .history-backdrop {
    position: absolute;
    inset: 0;
    z-index: 2;
    display: block;
    border: 0;
    background: #243e6633;
  }
  .history-toggle {
    display: block;
    padding: 7px;
    border: 1px solid #e0e6f1;
    border-radius: 7px;
    color: #7185a8;
    background: #fff;
    font-size: 11px;
  }
  .history-notice {
    padding: 8px 15px;
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
