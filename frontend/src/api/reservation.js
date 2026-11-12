import request from '@/utils/request'

/**
 * 创建预约
 */
export function createReservationApi(data) {
  return request({
    url: '/api/reservation',
    method: 'post',
    data
  })
}

/**
 * 确认 AI 生成的待确认单；同一次确认重试时保持幂等键不变。
 */
export function confirmReservationDraftApi(draftId, data) {
  return request({
    url: `/api/reservation/drafts/${draftId}/confirm`,
    method: 'post',
    data
  })
}

export function cancelReservationDraftApi(draftId, data) {
  return request({
    url: `/api/reservation/drafts/${draftId}/cancel`,
    method: 'post',
    data
  })
}

/**
 * 查询预约记录
 */
export function getReservationPageList(params) {
  return request({
    url: '/api/reservation/list',
    method: 'get',
    params
  })
}

/**
 * 取消预约
 */
export function cancelReservationApi(id) {
  return request({
    url: `/api/reservation/${id}/cancel`,
    method: 'put'
  })
}

/**
 * 审核预约
 */
export function auditReservationApi(id, status) {
  return request({
    url: `/api/reservation/${id}/audit`,
    method: 'put',
    data: { status }
  })
}
