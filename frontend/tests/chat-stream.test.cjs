const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function loadApi(fetch, request = () => {}) {
  const filename = path.resolve(__dirname, '../src/api/ai.js')
  const source = fs
    .readFileSync(filename, 'utf8')
    .replace(/^import .*$/gm, '')
    .replaceAll('import.meta.env.VITE_API_BASE_URL', "''")
    .replaceAll('export ', '')
  return new Function(
    'fetch',
    'getToken',
    'request',
    source +
      '\nreturn { chatStreamApi, getConversationsApi, getConversationMessagesApi, deleteConversationApi }'
  )(fetch, () => 'fixture-bearer', request)
}

function streamResponse(parts) {
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const part of parts) controller.enqueue(part)
        controller.close()
      }
    }),
    { headers: { 'content-type': 'text/event-stream' } }
  )
}

test('SSE handles split UTF-8 and CRLF frames, using the single-message request', async () => {
  let sent
  const wire = [
    { type: 'conversation', conversation_id: 12 },
    { type: 'token', content: '中文回复' },
    { type: 'done', conversation_id: 12, message_id: 2 }
  ]
    .map((event) => `data: ${JSON.stringify(event)}\r\n\r\n`)
    .join('')
  const bytes = new TextEncoder().encode(wire)
  const api = loadApi(async (url, options) => {
    sent = { url, options }
    return streamResponse(Array.from(bytes, (byte) => new Uint8Array([byte])))
  })
  const events = []
  const controller = new AbortController()
  await api.chatStreamApi(
    { conversation_id: null, message: '你好' },
    (event) => events.push(event),
    { signal: controller.signal }
  )
  assert.deepEqual(
    events.map((event) => event.type),
    ['conversation', 'token', 'done']
  )
  assert.equal(events[1].content, '中文回复')
  assert.deepEqual(JSON.parse(sent.options.body), { conversation_id: null, message: '你好' })
  assert.equal(sent.options.headers.Authorization, 'Bearer fixture-bearer')
  assert.equal(sent.options.signal, controller.signal)
})

test('HTTP errors preserve the status and server explanation', async () => {
  const api = loadApi(
    async () => new Response(JSON.stringify({ message: '会话不存在' }), { status: 404 })
  )
  await assert.rejects(
    api.chatStreamApi({ message: 'hi' }, () => {}),
    (error) => error.status === 404 && error.message === '会话不存在'
  )
})

test('EOF without a terminal event and malformed frames cannot silently succeed', async () => {
  const encoder = new TextEncoder()
  for (const wire of ['data: {"type":"token","content":"partial"}\n\n', 'data: not-json\n\n']) {
    const api = loadApi(async () => streamResponse([encoder.encode(wire)]))
    await assert.rejects(api.chatStreamApi({ message: 'hi' }, () => {}))
  }
})

test('callback errors propagate, and an explicit error event ends the stream', async () => {
  const encoder = new TextEncoder()
  const api = loadApi(async () =>
    streamResponse([encoder.encode('data: {"type":"error","message":"failed"}\n\n')])
  )
  await assert.rejects(
    api.chatStreamApi({}, () => {
      throw new Error('callback failed')
    }),
    /callback failed/
  )
  const events = []
  await api.chatStreamApi({}, (event) => events.push(event))
  assert.equal(events[0].message, 'failed')
})

test('conversation API wrappers pass pagination, IDs, and cancellation to request', async () => {
  const calls = []
  const api = loadApi(
    () => assert.fail('Unexpected fetch'),
    (options) => calls.push(options)
  )
  const signal = new AbortController().signal
  api.getConversationsApi({ page: 2, page_size: 20 }, signal)
  api.getConversationMessagesApi(12, { page: 1, page_size: 50 }, signal)
  api.deleteConversationApi(12, signal)
  assert.deepEqual(
    calls.map((call) => [call.method, call.url]),
    [
      ['get', '/api/ai/conversations'],
      ['get', '/api/ai/conversations/12/messages'],
      ['delete', '/api/ai/conversations/12']
    ]
  )
  assert.equal(calls[0].params.page, 2)
  assert(calls.every((call) => call.signal === signal))
})
