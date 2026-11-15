import { getToken } from '@/utils/auth'
import request from '@/utils/request'

export function getConversationsApi(params, signal) {
  return request({ url: '/api/ai/conversations', method: 'get', params, signal })
}

export function getConversationMessagesApi(id, params, signal) {
  return request({ url: `/api/ai/conversations/${id}/messages`, method: 'get', params, signal })
}

export function deleteConversationApi(id, signal) {
  return request({ url: `/api/ai/conversations/${id}`, method: 'delete', signal })
}

export async function chatStreamApi(data, onEvent, { signal } = {}) {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  const response = await fetch(`${baseUrl}/api/ai/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${getToken()}`
    },
    body: JSON.stringify(data),
    signal
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const error = new Error(
      response.status === 401 ? '登录已失效，请重新登录' : body?.message || '聊天请求失败'
    )
    error.status = response.status
    throw error
  }
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('聊天接口返回异常，请刷新记录后重试')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let terminal = false

  const dispatch = (frame) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
    if (!data) return
    const event = JSON.parse(data)
    onEvent(event)
    terminal = event.type === 'done' || event.type === 'error'
  }

  try {
    while (!terminal) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let boundary
      while (!terminal && (boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index)
        buffer = buffer.slice(boundary.index + boundary[0].length)
        dispatch(frame)
      }
      if (done) {
        if (!terminal && buffer.trim()) dispatch(buffer)
        if (!terminal) throw new Error('回复连接已中断，请刷新记录确认保存结果')
        break
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
