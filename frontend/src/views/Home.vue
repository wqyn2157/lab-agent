<template>
  <div class="home-page">
    <section class="welcome-card">
      <div class="welcome-content">
        <div>
          <p class="eyebrow">你的实验室工作台</p>
          <div class="welcome-heading">
            你好，{{ userInfo?.name || '同学' }}
            <span class="role-badge">{{ roleLabel }}</span>
          </div>
          <div class="welcome-description">
            查看开放资源，安排实验时间。预约和问题，都可以从这里开始。
          </div>
        </div>
        <el-button type="primary" size="large" @click="$router.push('/manager/ai-chat')">
          <el-icon class="button-icon"><ChatDotRound /></el-icon>打开 AI 助手
        </el-button>
      </div>
    </section>

    <div class="stats-grid">
      <article class="stat-card" v-for="item in statCards" :key="item.label">
        <div>
          <p class="stat-label">{{ item.label }}</p>
          <p class="stat-value">{{ item.value }}</p>
          <p class="stat-description">{{ item.description }}</p>
        </div>
        <span class="stat-icon"
          ><el-icon><component :is="item.icon" /></el-icon
        ></span>
      </article>
    </div>

    <section class="content-panel">
      <div class="section-heading">
        <h2>从这里开始</h2>
        <span>找到资源，再安排你的实验</span>
      </div>
      <div class="features-grid">
        <article class="feature-item" v-for="item in features" :key="item.title">
          <span class="feature-icon"
            ><el-icon><component :is="item.icon" /></el-icon
          ></span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.desc }}</p>
        </article>
      </div>
    </section>

    <section class="content-panel">
      <div class="section-heading">
        <h2>快捷入口</h2>
        <span>常用功能，一步到达</span>
      </div>
      <div class="shortcuts-grid">
        <button
          v-for="item in shortcuts"
          :key="item.path"
          type="button"
          class="shortcut-item"
          @click="$router.push(item.path)"
        >
          <span>{{ item.label }}</span
          ><el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useUser } from '@/utils/user'
import { getLabPageList } from '@/api/lab'
import { getReservationPageList } from '@/api/reservation'

const { userInfo } = useUser()

const labTotal = ref('-')
const reservationTotal = ref('-')

const roleLabel = computed(() => (userInfo.value?.role === 'admin' ? '管理员' : '学生'))

const statCards = computed(() => [
  {
    label: '开放实验室',
    value: labTotal.value,
    description: '发现可用的实验空间',
    icon: 'OfficeBuilding'
  },
  {
    label: userInfo.value?.role === 'admin' ? '预约记录' : '我的预约',
    value: reservationTotal.value,
    description: '随时查看预约与审核进度',
    icon: 'Tickets'
  },
  {
    label: '智能预约助手',
    value: 'AI',
    description: '查规则、找资源、生成确认单',
    icon: 'ChatDotRound'
  }
])

const features = [
  {
    title: '浏览实验室与设备',
    icon: 'OfficeBuilding',
    desc: '查看开放时间和设备信息，找到适合本次实验的资源。'
  },
  {
    title: '有问题，先问助手',
    icon: 'ChatDotRound',
    desc: '预约规则、安全规范和开放时间，直接用日常语言提问。'
  },
  {
    title: '核对信息后再提交',
    icon: 'CircleCheck',
    desc: '助手先生成确认单，核对资源和时间，点击确认后提交审核。'
  }
]

const shortcuts = computed(() => {
  const list = [{ label: 'AI 智能助手', path: '/manager/ai-chat' }]
  if (userInfo.value?.role === 'student') {
    list.push(
      { label: '实验室列表', path: '/manager/lablist' },
      { label: '我的预约', path: '/manager/my-reservation' }
    )
  }
  if (userInfo.value?.role === 'admin') {
    list.push(
      { label: '预约审核', path: '/manager/audit-reservation' },
      { label: '实验室管理', path: '/manager/lab' },
      { label: '设备管理', path: '/manager/equipment' },
      { label: '用户管理', path: '/manager/user' }
    )
  }
  return list
})

onMounted(async () => {
  try {
    const labRes = await getLabPageList({ page: 1, page_size: 1, status: 1 })
    if (labRes.code === 200) labTotal.value = labRes.data?.total ?? 0
  } catch {
    labTotal.value = '-'
  }
  try {
    const resRes = await getReservationPageList({ page: 1, page_size: 1 })
    if (resRes.code === 200) reservationTotal.value = resRes.data?.total ?? 0
  } catch {
    reservationTotal.value = '-'
  }
})
</script>

<style scoped>
.home-page {
  max-width: 1360px;
  margin: 0 auto;
  display: grid;
  gap: 22px;
}
.welcome-card {
  padding: 29px 32px;
  border: 1px solid #e2e9f7;
  border-radius: 16px;
  background: linear-gradient(115deg, #fff 25%, #eef3ff 100%);
}
.welcome-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
}
.eyebrow {
  color: #5b77c6;
  font-size: 12px;
  letter-spacing: 1px;
  margin-bottom: 12px;
}
.welcome-heading {
  display: flex;
  align-items: center;
  gap: 13px;
  font-size: 27px;
  color: #23324e;
  font-weight: 700;
}
.role-badge {
  padding: 4px 9px;
  border-radius: 6px;
  border: 1px solid #e1e7f2;
  background: #fff;
  font-size: 11px;
  font-weight: 400;
  color: #7c8aa4;
}
.welcome-description {
  margin-top: 11px;
  color: #7b879d;
  font-size: 13px;
  line-height: 1.8;
}
.button-icon {
  margin-right: 7px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.stat-card {
  padding: 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #e6ebf4;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 3px 12px #243e6603;
}
.stat-label {
  font-size: 12px;
  color: #7e8ba2;
}
.stat-value {
  margin-top: 11px;
  color: #253650;
  font-size: 31px;
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.8px;
}
.stat-description {
  margin-top: 10px;
  font-size: 11px;
  color: #99a3b4;
}
.stat-icon,
.feature-icon {
  display: grid;
  place-items: center;
  width: 39px;
  height: 39px;
  border-radius: 11px;
  background: #eef3ff;
  color: #5c7cde;
  font-size: 20px;
  flex-shrink: 0;
}
.stat-card:nth-child(2) .stat-icon {
  color: #54a696;
  background: #edf8f5;
}
.stat-card:nth-child(3) .stat-icon {
  color: #8e7bca;
  background: #f3f0fb;
}
.content-panel {
  padding: 24px 28px;
  background: #fff;
  border: 1px solid #e6ebf4;
  border-radius: 14px;
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 24px;
}
.section-heading h2 {
  font-size: 15px;
  font-weight: 650;
  color: #34435c;
}
.section-heading > span {
  font-size: 11px;
  color: #9aa4b6;
}
.features-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 30px;
}
.feature-icon {
  width: 34px;
  height: 34px;
  font-size: 18px;
  background: #f4f6fb;
  color: #748bb8;
  border-radius: 9px;
}
.feature-item h3 {
  margin-top: 14px;
  color: #43516b;
  font-size: 14px;
  font-weight: 600;
}
.feature-item p {
  margin-top: 8px;
  font-size: 12px;
  color: #8b95a8;
  line-height: 1.9;
}
.shortcuts-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.shortcut-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  font: inherit;
  font-size: 12px;
  color: #64738d;
  background: #f8faff;
  border: 1px solid #edf1f8;
  border-radius: 9px;
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.shortcut-item:hover {
  background: #eef3ff;
  border-color: #dce5fb;
  color: #4166e8;
}
.shortcut-item .el-icon {
  color: #a3b3d2;
}
@media (max-width: 1000px) {
  .welcome-content {
    align-items: flex-start;
  }
  .welcome-description {
    max-width: 340px;
  }
  .stat-card {
    padding: 20px 16px;
  }
  .stat-icon {
    width: 32px;
    height: 32px;
    font-size: 17px;
  }
}
@media (max-width: 700px) {
  .home-page {
    gap: 16px;
  }
  .welcome-card {
    padding: 23px;
  }
  .welcome-content {
    flex-direction: column;
    gap: 18px;
  }
  .welcome-heading {
    font-size: 23px;
  }
  .stats-grid,
  .features-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .stat-card {
    padding: 18px 22px;
  }
  .stat-value {
    font-size: 28px;
  }
  .content-panel {
    padding: 22px;
  }
  .section-heading > span {
    display: none;
  }
  .feature-item {
    padding-bottom: 16px;
  }
  .shortcuts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
