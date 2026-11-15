const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Vue = require('vue')
const { parse, compileScript } = require('@vue/compiler-sfc')
const { compile } = require('@vue/compiler-dom')
const babel = require('@babel/parser')

// Compile the real components and exercise their events without a browser or new dependencies.
function loadComponent(relativePath, modules) {
  const filename = path.resolve(__dirname, '..', relativePath)
  const { descriptor, errors } = parse(fs.readFileSync(filename, 'utf8'), { filename })
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: relativePath })
  let code = script.content
  const imports = babel
    .parse(code, { sourceType: 'module' })
    .program.body.filter((node) => node.type === 'ImportDeclaration')
  for (const node of imports.reverse()) code = code.slice(0, node.start) + code.slice(node.end)
  const entries = Object.entries(script.imports)
  const values = entries.map(([, binding]) => {
    const module = binding.source === 'vue' ? Vue : modules[binding.source]
    assert(module, `Missing test module: ${binding.source}`)
    return module[binding.imported]
  })
  const component = new Function(
    ...entries.map(([name]) => name),
    code.replace('export default', 'return')
  )(...values)
  const template = compile(descriptor.template.content, {
    mode: 'function',
    prefixIdentifiers: true,
    bindingMetadata: script.bindings
  })
  component.render = new Function('Vue', template.code)(Vue)
  return component
}

function element(type, text = '') {
  return { type, text, props: {}, children: [], parent: null }
}
function detach(node) {
  if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  node.parent = null
}
const renderer = Vue.createRenderer({
  createElement: element,
  createText: (text) => element('#text', text),
  createComment: (text) => element('#comment', text),
  setText: (node, text) => {
    node.text = text
  },
  setElementText: (node, text) => {
    node.text = text
    node.children = []
  },
  patchProp: (node, name, oldValue, value) => {
    node.props[name] = value
  },
  insert(node, parent, anchor) {
    detach(node)
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(node)
    else parent.children.splice(index, 0, node)
    node.parent = parent
  },
  remove: detach,
  parentNode: (node) => node.parent,
  nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1] || null
})
const components = {
  ElCard: {
    setup(props, { slots }) {
      return () => Vue.h('section', [slots.header?.(), slots.default?.()])
    }
  },
  ElTag: {
    setup:
      (props, { slots }) =>
      () =>
        Vue.h('span', slots.default?.())
  },
  ElAlert: { props: ['title'], setup: (props) => () => Vue.h('p', props.title) },
  ElInput: { setup: () => () => Vue.h('textarea') },
  ElButton: {
    props: ['disabled', 'loading'],
    emits: ['click'],
    setup:
      (props, { slots, emit }) =>
      () =>
        Vue.h(
          'button',
          {
            disabled: props.disabled || props.loading,
            onClick: () => emit('click')
          },
          slots.default?.()
        )
  }
}
function mount(t, component, props = {}) {
  const app = renderer.createApp(component, props)
  for (const [name, stub] of Object.entries(components)) app.component(name, stub)
  const root = element('root')
  const vm = app.mount(root)
  t.after(() => app.unmount())
  return { root, state: vm.$.setupState, unmount: () => app.unmount() }
}
function text(node) {
  return node.type === '#comment' ? '' : node.text + node.children.map(text).join('')
}
function findButton(node, label) {
  if (node.type === 'button' && text(node).trim() === label) return node
  for (const child of node.children) {
    const found = findButton(child, label)
    if (found) return found
  }
}
const flush = async () => {
  await Vue.nextTick()
  await new Promise(setImmediate)
  await Vue.nextTick()
}
function clock(t) {
  let now = Date.parse('2099-01-01T08:00:00Z')
  const timers = new Map()
  let nextId = 0
  t.mock.method(Date, 'now', () => now)
  t.mock.method(globalThis, 'setInterval', (callback) => {
    timers.set(++nextId, callback)
    return nextId
  })
  t.mock.method(globalThis, 'clearInterval', (id) => timers.delete(id))
  return {
    advance(ms) {
      now += ms
      for (const callback of timers.values()) callback()
    }
  }
}
function draft(overrides = {}) {
  return {
    ok: true,
    draft_id: 3,
    status: 'pending',
    lab_id: 1,
    lab_name: '测试实验室',
    equipment_id: null,
    date: '2099-01-02',
    start_time: '09:00',
    end_time: '10:00',
    remark: '课程实验',
    expires_at: new Date(Date.now() + 600000).toISOString(),
    confirmation_token: 'private-confirmation-token',
    ...overrides
  }
}
function cardComponent(api, cancelApi = async () => assert.fail('Unexpected cancel request')) {
  return loadComponent('src/components/ReservationDraftCard.vue', {
    '@/api/reservation': {
      confirmReservationDraftApi: api,
      cancelReservationDraftApi: cancelApi
    }
  })
}

function chatComponent(apis = {}, options = {}) {
  return loadComponent('src/views/AIChat.vue', {
    '@/api/ai': {
      getConversationsApi: async () => ({ code: 200, data: { list: [], total: 0 } }),
      getConversationMessagesApi: async () => ({ code: 200, data: { list: [], total: 0 } }),
      deleteConversationApi: async () => assert.fail('Unexpected deletion'),
      chatStreamApi: async () => assert.fail('Unexpected chat request'),
      ...apis
    },
    '@/components/ReservationDraftCard.vue': {
      default: options.card || cardComponent(async () => assert.fail('Unexpected confirmation'))
    },
    marked: { marked: { setOptions() {}, parse: (value) => value } },
    dompurify: { default: { sanitize: (value) => value } },
    'element-plus': {
      ElMessage: { error: options.onError || ((message) => assert.fail(message)) },
      ElMessageBox: { confirm: options.confirm || (async () => assert.fail('Unexpected dialog')) }
    }
  })
}

test('card submits only on click, blocks duplicate clicks, and emits confirmed once', async (t) => {
  clock(t)
  const calls = [],
    confirmed = []
  let resolve
  const component = cardComponent((id, body) => {
    calls.push({ id, body })
    return new Promise((done) => {
      resolve = done
    })
  })
  const { root } = mount(t, component, {
    draft: draft(),
    onConfirmed: (value) => confirmed.push(value)
  })
  assert.equal(calls.length, 0)
  assert(!text(root).includes('private-confirmation-token'))
  const button = findButton(root, '确认预约')
  button.props.onClick()
  button.props.onClick()
  await flush()
  assert.equal(calls.length, 1)
  assert.equal(button.props.disabled, true)
  assert.equal(calls[0].id, 3)
  assert.equal(calls[0].body.confirmation_token, 'private-confirmation-token')
  resolve({ code: 200, data: { reservation_id: 14 } })
  await flush()
  assert.deepEqual(confirmed, [{ draftId: 3, reservationId: 14 }])
  assert(text(root).includes('预约 #14 已提交'))
  assert.equal(findButton(root, '确认预约'), undefined)
  button.props.onClick()
  assert.equal(calls.length, 1)
})

test('lost response can retry after expiry using the same idempotency key', async (t) => {
  const time = clock(t)
  const calls = []
  const component = cardComponent(async (id, body) => {
    calls.push(body)
    if (calls.length === 1) throw new Error('Network Error')
    return { code: 200, data: { reservation_id: 14 } }
  })
  const { root } = mount(t, component, { draft: draft() })
  findButton(root, '确认预约').props.onClick()
  await flush()
  time.advance(601000)
  await flush()
  const retry = findButton(root, '重试确认')
  assert.equal(retry.props.disabled, false)
  retry.props.onClick()
  await flush()
  assert.equal(calls.length, 2)
  assert.equal(calls[0].idempotency_key, calls[1].idempotency_key)
  assert(text(root).includes('预约 #14 已提交'))
})

test('expired untouched card and HTTP-200 business rejection cannot create a booking', async (t) => {
  clock(t)
  let calls = 0
  const component = cardComponent(async () => {
    calls++
    return { code: 409, message: '确认单已过期，请重新生成', data: null }
  })
  const old = mount(t, component, {
    draft: draft({ expires_at: new Date(Date.now() - 1000).toISOString() })
  })
  assert.equal(findButton(old.root, '确认预约').props.disabled, true)
  findButton(old.root, '确认预约').props.onClick()
  assert.equal(calls, 0)
  const active = mount(t, component, { draft: draft() })
  findButton(active.root, '确认预约').props.onClick()
  await flush()
  assert.equal(calls, 1)
  assert(text(active.root).includes('确认单已过期，请重新生成'))
  assert.equal(findButton(active.root, '确认预约').props.disabled, true)
  assert.equal(active.state.confirmed, false)
})

test('chat deduplicates cards and sends only the new message and server conversation ID', async (t) => {
  clock(t)
  const requests = []
  let confirmations = 0
  const card = draft()
  const component = chatComponent(
    {
      chatStreamApi: async (data, onEvent) => {
        requests.push(data)
        onEvent({ type: 'conversation', conversation_id: 12 })
        if (requests.length === 1) {
          onEvent({ type: 'reservation_draft', data: card })
          onEvent({ type: 'reservation_draft', data: card })
        }
        onEvent({ type: 'token', content: '请核对确认单。' })
        onEvent({ type: 'done', conversation_id: 12, message_id: 100 + requests.length })
      }
    },
    {
      card: cardComponent(async () => {
        confirmations++
        return { code: 200, data: { reservation_id: 14 } }
      })
    }
  )
  const { root, state } = mount(t, component)
  await flush()
  state.input = '帮我预约'
  await state.handleSend()
  await flush()
  assert.equal(state.messages.at(-1).drafts.length, 1)
  assert.equal(confirmations, 0)
  findButton(root, '确认预约').props.onClick()
  await flush()
  assert.equal(confirmations, 1)
  assert(state.messages.at(-1).notice.includes('预约 #14 已提交'))
  state.input = '查询预约记录'
  await state.handleSend()
  await flush()
  assert.deepEqual(requests, [
    { conversation_id: null, message: '帮我预约' },
    { conversation_id: 12, message: '查询预约记录' }
  ])
  assert(!JSON.stringify(requests).includes('private-confirmation-token'))
})

test('mount restores the latest conversation; generating blocks navigation and duplicate sends', async (t) => {
  const calls = []
  let finish
  const component = chatComponent({
    getConversationsApi: async () => ({
      code: 200,
      data: { list: [{ id: 12, title: '旧会话' }], total: 1 }
    }),
    getConversationMessagesApi: async () => ({
      code: 200,
      data: {
        list: [
          { id: 1, role: 'user', content: '之前的问题' },
          { id: 2, role: 'assistant', content: '之前的回答' }
        ],
        total: 2
      }
    }),
    chatStreamApi: (data, onEvent) => {
      calls.push(data)
      onEvent({ type: 'conversation', conversation_id: 12 })
      return new Promise((resolve) => {
        finish = () => {
          onEvent({ type: 'token', content: '新回答' })
          onEvent({ type: 'done', conversation_id: 12, message_id: 4 })
          resolve()
        }
      })
    }
  })
  const { state } = mount(t, component)
  await flush()
  assert.equal(state.currentConversationId, 12)
  assert.deepEqual(
    state.messages.map((m) => m.content),
    ['之前的问题', '之前的回答']
  )
  state.input = '继续之前的话题'
  const sending = state.handleSend()
  state.input = '重复发送'
  await state.handleSend()
  state.startNewConversation()
  await state.selectConversation(99)
  assert.equal(state.currentConversationId, 12)
  assert.equal(calls.length, 1)
  finish()
  await sending
  assert.deepEqual(calls[0], { conversation_id: 12, message: '继续之前的话题' })
  assert.equal(state.messages.at(-1).content, '新回答')
})

test('a fresh page reads stored messages from APIs instead of replaying a request', async (t) => {
  let saved = false
  const requests = []
  const apis = {
    getConversationsApi: async () => ({
      code: 200,
      data: { list: saved ? [{ id: 12, title: '已保存会话' }] : [], total: saved ? 1 : 0 }
    }),
    getConversationMessagesApi: async () => ({
      code: 200,
      data: {
        list: [
          { id: 1, role: 'user', content: 'hello' },
          { id: 2, role: 'assistant', content: 'saved reply' }
        ],
        total: 2
      }
    }),
    chatStreamApi: async (data, onEvent) => {
      requests.push(data)
      saved = true
      onEvent({ type: 'conversation', conversation_id: 12 })
      onEvent({ type: 'token', content: 'saved reply' })
      onEvent({ type: 'done', conversation_id: 12, message_id: 2 })
    }
  }
  const first = mount(t, chatComponent(apis))
  await flush()
  first.state.input = 'hello'
  await first.state.handleSend()
  const refreshed = mount(t, chatComponent(apis))
  await flush()
  assert.equal(refreshed.state.currentConversationId, 12)
  assert.deepEqual(
    refreshed.state.messages.map((m) => m.content),
    ['hello', 'saved reply']
  )
  assert.equal(refreshed.state.restoredHistory, true)
  assert.equal(requests.length, 1)
})

test('loading older messages preserves order and ignores shifted-page overlap', async (t) => {
  const row = (id) => ({ id, role: 'user', content: `message ${id}` })
  const component = chatComponent({
    getConversationsApi: async () => ({
      code: 200,
      data: { list: [{ id: 12, title: '分页会话' }], total: 1 }
    }),
    getConversationMessagesApi: async (id, params) => ({
      code: 200,
      data: {
        list:
          params.page === 1
            ? Array.from({ length: 50 }, (_, i) => row(i + 51))
            : Array.from({ length: 50 }, (_, i) => row(i + 3)),
        total: params.page === 1 ? 100 : 102
      }
    })
  })
  const { state } = mount(t, component)
  await flush()
  const lastMessage = state.messages.at(-1)
  await state.loadOlderMessages()
  assert.deepEqual(
    state.messages.map((m) => m.id),
    Array.from({ length: 98 }, (_, i) => i + 3)
  )
  assert.equal(state.messages.at(-1), lastMessage)
})

test('an interrupted response blocks resend until records are refreshed', async (t) => {
  let requests = 0
  const errors = []
  const component = chatComponent(
    {
      getConversationsApi: async () => ({
        code: 200,
        data: { list: requests ? [{ id: 12, title: '中断会话' }] : [], total: requests ? 1 : 0 }
      }),
      getConversationMessagesApi: async () => ({
        code: 200,
        data: { list: [{ id: 1, role: 'user', content: 'hello' }], total: 1 }
      }),
      chatStreamApi: async (data, onEvent) => {
        requests++
        onEvent({ type: 'conversation', conversation_id: 12 })
        onEvent({ type: 'token', content: '半截回复' })
        throw new Error('连接中断')
      }
    },
    { onError: (message) => errors.push(message) }
  )
  const { state } = mount(t, component)
  await flush()
  state.input = 'hello'
  await state.handleSend()
  assert.equal(state.syncRequired, true)
  assert.equal(state.messages.at(-1).content, '半截回复')
  assert.equal(state.messages.at(-1).error, '连接中断')
  state.input = '不能直接继续'
  await state.handleSend()
  assert.equal(requests, 1)
  await state.reloadRecords()
  assert.equal(state.syncRequired, false)
  assert.deepEqual(
    state.messages.map((m) => m.content),
    ['hello']
  )
  assert.deepEqual(errors, ['连接中断'])
})

test('a failed history load prevents sending with an unverified conversation', async (t) => {
  const component = chatComponent({
    getConversationsApi: async () => ({
      code: 200,
      data: { list: [{ id: 12, title: '旧会话' }], total: 1 }
    }),
    getConversationMessagesApi: async () => {
      throw new Error('读取失败')
    }
  })
  const { state } = mount(t, component)
  await flush()
  assert.equal(state.historyReady, false)
  assert.equal(state.historyError, '读取失败')
  state.input = '不应发送'
  await state.handleSend()
  assert.equal(state.messages.length, 1)
})

test('a deleted conversation cannot keep accepting retries under its old ID', async (t) => {
  let requests = 0
  const component = chatComponent(
    {
      getConversationsApi: async () => ({
        code: 200,
        data: { list: [{ id: 12, title: '旧会话' }], total: 1 }
      }),
      chatStreamApi: async () => {
        requests++
        throw Object.assign(new Error('会话不存在'), { status: 404 })
      }
    },
    { onError() {} }
  )
  const { state } = mount(t, component)
  await flush()
  state.input = 'hello'
  await state.handleSend()
  assert.equal(state.canCompose, false)
  assert(state.historyError.includes('不存在'))
  await state.handleSend()
  assert.equal(requests, 1)
  state.startNewConversation()
  assert.equal(state.currentConversationId, null)
  assert.equal(state.canCompose, true)
})

test('done without a valid saved message ID is treated as an unknown outcome', async (t) => {
  const component = chatComponent(
    {
      chatStreamApi: async (data, onEvent) => {
        onEvent({ type: 'conversation', conversation_id: 12 })
        onEvent({ type: 'token', content: 'reply' })
        onEvent({ type: 'done', conversation_id: 12, message_id: 0 })
      }
    },
    { onError() {} }
  )
  const { state } = mount(t, component)
  await flush()
  state.input = 'hello'
  await state.handleSend()
  assert.equal(state.syncRequired, true)
  assert.equal(state.canCompose, false)
})

test('deleting requires confirmation and resets only the active conversation', async (t) => {
  let cancelled = true
  const deleted = []
  const component = chatComponent(
    {
      getConversationsApi: async () => ({
        code: 200,
        data: {
          list: deleted.length ? [] : [{ id: 12, title: '待删除会话' }],
          total: deleted.length ? 0 : 1
        }
      }),
      deleteConversationApi: async (id) => {
        deleted.push(id)
        return { code: 200, data: null }
      }
    },
    {
      confirm: async () => {
        if (cancelled) throw 'cancel'
      }
    }
  )
  const { state } = mount(t, component)
  await flush()
  await state.deleteConversation({ id: 12, title: '待删除会话' })
  assert.deepEqual(deleted, [])
  cancelled = false
  await state.deleteConversation({ id: 12, title: '待删除会话' })
  assert.deepEqual(deleted, [12])
  assert.equal(state.currentConversationId, null)
  assert.equal(state.messages[0].key, 'welcome')
})

test('cancelling blocks confirmation and duplicate cancellation, then closes the card', async (t) => {
  clock(t)
  let resolve
  const calls = [],
    cancelled = []
  const component = cardComponent(
    async () => assert.fail('Confirmation must not run while cancelling'),
    (id, body) => {
      calls.push({ id, body })
      return new Promise((done) => {
        resolve = done
      })
    }
  )
  const { root } = mount(t, component, {
    draft: draft(),
    onCancelled: (result) => cancelled.push(result)
  })
  const confirm = findButton(root, '确认预约')
  const cancel = findButton(root, '取消')
  cancel.props.onClick()
  cancel.props.onClick()
  confirm.props.onClick()
  await flush()
  assert.equal(calls.length, 1)
  assert.deepEqual(calls[0], {
    id: 3,
    body: { confirmation_token: 'private-confirmation-token' }
  })
  assert.equal(confirm.props.disabled, true)
  resolve({ code: 200, data: { draft_id: 3, status: 'cancelled' } })
  await flush()
  assert(text(root).includes('待确认单已取消，未创建预约'))
  assert.equal(findButton(root, '确认预约'), undefined)
  assert.deepEqual(cancelled, [{ draftId: 3, status: 'cancelled' }])
})

test('unknown cancellation blocks confirmation and can retry even after expiry', async (t) => {
  const time = clock(t)
  let calls = 0
  const component = cardComponent(
    async () => assert.fail('Cannot confirm while cancellation result is unknown'),
    async () => {
      calls++
      if (calls === 1) throw new Error('Network Error')
      return { code: 200, data: { draft_id: 3, status: 'cancelled' } }
    }
  )
  const { root } = mount(t, component, { draft: draft() })
  findButton(root, '取消').props.onClick()
  await flush()
  time.advance(601000)
  await flush()
  const confirm = findButton(root, '确认预约')
  assert.equal(confirm.props.disabled, true)
  confirm.props.onClick()
  const retry = findButton(root, '重试取消')
  assert.equal(retry.props.disabled, false)
  retry.props.onClick()
  await flush()
  assert.equal(calls, 2)
  assert(text(root).includes('待确认单已取消，未创建预约'))
})
