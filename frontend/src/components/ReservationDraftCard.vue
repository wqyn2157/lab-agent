<template>
  <el-card
    class="reservation-draft"
    :class="{ 'is-confirmed': confirmed, 'is-cancelled': cancelled }"
    shadow="never"
  >
    <template #header>
      <div class="draft-heading">
        <div class="draft-title">
          <span class="draft-symbol" aria-hidden="true">约</span><strong>预约确认单</strong>
        </div>
        <el-tag :type="confirmed ? 'success' : canConfirm ? 'warning' : 'info'">
          {{ statusLabel }}
        </el-tag>
      </div>
    </template>

    <dl class="draft-details">
      <dt>实验室</dt>
      <dd>{{ draft.lab_name || `实验室 ${draft.lab_id}` }}</dd>
      <template v-if="draft.equipment_id != null">
        <dt>设备</dt>
        <dd>{{ draft.equipment_name || `设备 ${draft.equipment_id}` }}</dd>
      </template>
      <dt>日期</dt>
      <dd>{{ draft.date }}</dd>
      <dt>时间</dt>
      <dd>{{ draft.start_time }} 至 {{ draft.end_time }}</dd>
      <template v-if="draft.remark">
        <dt>备注</dt>
        <dd>{{ draft.remark }}</dd>
      </template>
    </dl>

    <el-alert
      v-if="confirmed"
      :title="`预约 #${reservationId} 已提交，等待管理员审核。`"
      type="success"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="cancelled"
      title="待确认单已取消，未创建预约。"
      type="info"
      :closable="false"
      show-icon
    />
    <template v-else>
      <p class="draft-expiry">有效期至：{{ draft.expires_at.replace('T', ' ') }}</p>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
        class="draft-error"
      />
      <p v-if="expired && !uncertain && !cancelUncertain" class="draft-expiry">
        确认单已过期，请重新生成。
      </p>
      <div class="draft-actions">
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!canConfirm || submitting || cancelling"
          @click="handleConfirm"
        >
          {{ uncertain ? '重试确认' : '确认预约' }}
        </el-button>
        <el-button
          :loading="cancelling"
          :disabled="!canCancel || submitting || cancelling"
          @click="handleCancel"
        >
          {{ cancelUncertain ? '重试取消' : '取消' }}
        </el-button>
      </div>
    </template>
  </el-card>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { confirmReservationDraftApi, cancelReservationDraftApi } from '@/api/reservation'

const props = defineProps({
  draft: { type: Object, required: true }
})
const emit = defineEmits(['confirmed', 'cancelled'])

// 一张卡片只生成一次，网络失败后的重试继续使用这个键。
const idempotencyKey = crypto.randomUUID()
const submitting = ref(false)
const cancelling = ref(false)
const reservationId = ref(null)
const error = ref('')
const uncertain = ref(false)
const cancelUncertain = ref(false)
const closedStatus = ref(null)
const unavailable = ref(false)
const now = ref(Date.now())
let timer

const confirmed = computed(() => reservationId.value !== null)
const cancelled = computed(() => closedStatus.value === 'cancelled')
const expired = computed(
  () => closedStatus.value === 'expired' || now.value >= new Date(props.draft.expires_at).getTime()
)
// 首次确认可能已经成功；即使过期，也允许用原幂等键重试核实结果。
const canConfirm = computed(
  () =>
    !confirmed.value &&
    !cancelled.value &&
    !cancelUncertain.value &&
    !unavailable.value &&
    (!expired.value || uncertain.value)
)
const canCancel = computed(
  () =>
    !confirmed.value &&
    !cancelled.value &&
    !uncertain.value &&
    !unavailable.value &&
    (!expired.value || cancelUncertain.value)
)
const statusLabel = computed(() => {
  if (confirmed.value) return '已提交'
  if (cancelled.value) return '已取消'
  if (submitting.value) return '提交中'
  if (cancelling.value) return '取消中'
  if (uncertain.value) return '结果待核实'
  if (cancelUncertain.value) return '取消结果待核实'
  if (expired.value) return '已过期'
  if (unavailable.value) return '无法确认'
  return '待确认'
})

onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onUnmounted(() => clearInterval(timer))

const handleConfirm = async () => {
  now.value = Date.now()
  if (submitting.value || cancelling.value || !canConfirm.value) return

  submitting.value = true
  error.value = ''

  try {
    const res = await confirmReservationDraftApi(props.draft.draft_id, {
      confirmation_token: props.draft.confirmation_token,
      idempotency_key: idempotencyKey
    })

    // 项目的业务错误也可能使用 HTTP 200，需要检查响应里的 code。
    if (res.code !== 200) {
      error.value = res.message || '确认失败，请稍后重试。'
      uncertain.value = false
      unavailable.value = [403, 404, 409, 422].includes(res.code)
      return
    }

    if (!Number.isInteger(res.data?.reservation_id)) {
      throw new Error('确认接口未返回预约编号')
    }

    reservationId.value = res.data.reservation_id
    uncertain.value = false
    clearInterval(timer)
    emit('confirmed', {
      draftId: props.draft.draft_id,
      reservationId: reservationId.value
    })
  } catch (err) {
    const status = err.response?.status || err.code
    unavailable.value = [400, 401, 403, 404, 409, 422].includes(status)
    uncertain.value = !unavailable.value
    error.value = uncertain.value
      ? '未收到确认结果，请点击“重试确认”核实，请勿重复生成确认单。'
      : err.response?.data?.message || err.message || '确认失败，请重新生成确认单。'
  } finally {
    submitting.value = false
    now.value = Date.now()
  }
}

const handleCancel = async () => {
  now.value = Date.now()
  if (submitting.value || cancelling.value || !canCancel.value) return

  cancelling.value = true
  error.value = ''

  try {
    const res = await cancelReservationDraftApi(props.draft.draft_id, {
      confirmation_token: props.draft.confirmation_token
    })

    if (res.code !== 200) {
      error.value = res.message || '取消失败，请稍后重试。'
      cancelUncertain.value = false
      unavailable.value = [403, 404, 409, 422].includes(res.code)
      return
    }

    if (!['cancelled', 'expired'].includes(res.data?.status)) {
      throw new Error('取消接口未返回有效状态')
    }

    closedStatus.value = res.data.status
    cancelUncertain.value = false
    clearInterval(timer)
    emit('cancelled', {
      draftId: props.draft.draft_id,
      status: closedStatus.value
    })
  } catch (err) {
    const status = err.response?.status || err.code
    unavailable.value = [400, 401, 403, 404, 409, 422].includes(status)
    cancelUncertain.value = !unavailable.value
    error.value = cancelUncertain.value
      ? '未收到取消结果，请点击“重试取消”核实。'
      : err.response?.data?.message || err.message || '取消失败，请稍后重试。'
  } finally {
    cancelling.value = false
    now.value = Date.now()
  }
}
</script>

<style scoped>
.reservation-draft {
  margin-top: 15px;
  width: 360px;
  max-width: 100%;
  --el-card-border-color: #dce5fb;
  --el-card-border-radius: 12px;
  background: linear-gradient(150deg, #f7f9ff, #fff 65%);
}
.reservation-draft :deep(.el-card__header) {
  padding: 14px 17px;
  border-bottom-color: #e9eef9;
}
.reservation-draft :deep(.el-card__body) {
  padding: 17px;
}
.reservation-draft.is-confirmed {
  --el-card-border-color: #d9ece5;
  background: #fbfefc;
}
.reservation-draft.is-cancelled {
  --el-card-border-color: #e6eaf2;
  background: #fcfdff;
}
.draft-title {
  display: flex;
  align-items: center;
  gap: 9px;
}
.draft-title strong {
  font-size: 13px;
  font-weight: 600;
  color: #536989;
}
.draft-symbol {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  color: #6c89dc;
  background: #eaf0ff;
  font-size: 12px;
  font-weight: 600;
}
.draft-actions {
  display: flex;
  gap: 9px;
  margin-top: 13px;
}
.draft-actions .el-button {
  flex: 1;
  margin: 0;
  height: 34px;
  font-size: 12px;
}
.draft-heading :deep(.el-tag) {
  font-size: 10px;
  border-radius: 5px;
}
.reservation-draft :deep(.el-alert) {
  margin-top: 14px;
  border-radius: 8px;
}
.reservation-draft :deep(.el-alert__title) {
  font-size: 11px;
  line-height: 1.8;
}
.draft-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.draft-details {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
  font-size: 12px;
}
.draft-details dt,
.draft-expiry {
  color: #9ba7ba;
}
.draft-details dd {
  margin: 0;
  color: #5c6c86;
  overflow-wrap: anywhere;
}
.draft-expiry {
  margin-top: 14px;
  font-size: 10px;
}
.draft-error {
  margin-bottom: 12px;
}
</style>
