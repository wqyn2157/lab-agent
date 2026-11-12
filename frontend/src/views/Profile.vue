<template>
  <div class="profile-page">
    <header class="profile-page-heading">
      <p>账户设置</p>
      <h1>个人信息</h1>
      <span>完善个人资料，让大家更好地认识你</span>
    </header>

    <div class="profile-grid" v-loading="loading">
      <aside class="identity-card">
        <div class="identity-top">
          <el-upload
            class="avatar-uploader"
            :http-request="handleFileUpload"
            :show-file-list="false"
            accept="image/jpeg,image/png,image/gif,image/webp"
            :before-upload="beforeAvatarUpload"
          >
            <img
              v-if="form.avatar"
              :src="'/uploads/' + form.avatar"
              class="profile-avatar"
              alt="当前头像"
            />
            <span v-else class="avatar-fallback">{{ form.name?.slice(0, 1) || '用' }}</span>
            <span class="avatar-edit">更换头像</span>
          </el-upload>
          <h2>{{ form.name || '用户' }}</h2>
          <span class="identity-role">{{ roleLabel }}</span>
          <p class="identity-account">{{ form.username }}</p>
        </div>
        <div class="avatar-guidance">
          <strong>点击头像即可更换</strong>
          <p>支持 JPG、PNG、GIF、WebP</p>
          <p>图片大小不超过 2 MB</p>
        </div>
        <div class="identity-note">
          <el-icon><Lock /></el-icon>
          <span>账号与角色由系统管理</span>
        </div>
      </aside>

      <section class="profile-form-card">
        <div class="form-card-heading">
          <span class="form-heading-icon"
            ><el-icon><User /></el-icon
          ></span>
          <div>
            <h2>基本资料</h2>
            <p>更新你的显示名称与联系方式</p>
          </div>
        </div>
        <el-form
          ref="formRef"
          :rules="rules"
          :model="form"
          label-position="top"
          class="profile-form"
        >
          <div class="form-grid">
            <el-form-item label="账号">
              <el-input disabled v-model="form.username" />
            </el-form-item>
            <el-form-item label="角色">
              <el-input disabled :model-value="roleLabel" />
            </el-form-item>
            <el-form-item label="显示名称" prop="name" class="full-width">
              <el-input v-model="form.name" placeholder="请输入你的名称" />
              <p class="field-hint">用于页面展示和预约记录</p>
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="form.email" placeholder="请输入邮箱地址" />
            </el-form-item>
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" placeholder="请输入手机号码" />
            </el-form-item>
          </div>
          <div class="profile-form-footer">
            <span>头像和资料修改后，记得保存</span>
            <el-button
              type="primary"
              size="large"
              :loading="submitting"
              :disabled="loading"
              @click="handleSubmit"
            >
              保存修改
            </el-button>
          </div>
        </el-form>
      </section>
    </div>
  </div>
</template>

<script setup>
import { getUserInfo, updateUserInfo } from '@/api/user'
import { uploadFileApi } from '@/api/file'
import { ref, reactive, onMounted, computed } from 'vue'
import { useUser } from '@/utils/user'
import { ElMessage } from 'element-plus'

const { updateUser } = useUser()

const loading = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive({
  username: '',
  name: '',
  role: '',
  email: '',
  phone: '',
  avatar: ''
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式错误', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式错误', trigger: 'blur' }]
}

const roleLabel = computed(() => {
  return form.role === 'admin' ? '管理员' : form.role === 'student' ? '学生' : '未知角色'
})

const beforeAvatarUpload = (file) => {
  const imageTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
  if (!imageTypes.includes(file.type)) {
    ElMessage.error('只能上传图片')
    return false
  }
  if (file.size / 1024 / 1024 > 2) {
    ElMessage.error('上传图片大小不能超过2M')
    return false
  }
  return true
}

const handleFileUpload = async ({ file }) => {
  try {
    const res = await uploadFileApi(file)
    if (res.code === 200) {
      form.avatar = res.data?.disk_name
    }
  } catch {}
}

const loadUserInfo = async () => {
  loading.value = true
  try {
    const res = await getUserInfo()
    if (res.code === 200) {
      Object.assign(form, res.data)
    }
  } finally {
    loading.value = false
  }
}

// 发送请求更新用户信息
const handleSubmit = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const res = await updateUserInfo(form)
    if (res.code === 200) {
      updateUser(res.data)
      ElMessage.success('更新成功')
    }
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadUserInfo()
})
</script>

<style scoped>
.profile-page {
  max-width: 1100px;
  margin: 0 auto;
}
.profile-page-heading {
  margin: 4px 0 25px;
}
.profile-page-heading > p {
  font-size: 11px;
  color: #8c9ab2;
  letter-spacing: 1px;
  margin-bottom: 8px;
}
.profile-page-heading h1 {
  color: #2b3b56;
  font-size: 23px;
  font-weight: 650;
}
.profile-page-heading > span {
  display: block;
  margin-top: 9px;
  color: #929eb2;
  font-size: 12px;
}
.profile-grid {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}
.identity-card,
.profile-form-card {
  background: #fff;
  border: 1px solid #e5eaf3;
  border-radius: 15px;
  box-shadow: 0 3px 12px #243e6603;
}
.identity-card {
  overflow: hidden;
}
.identity-top {
  text-align: center;
  padding: 33px 20px 23px;
  background: linear-gradient(180deg, #f2f6ff, #fff 82%);
}
.avatar-uploader {
  display: flex;
  justify-content: center;
}
.avatar-uploader :deep(.el-upload) {
  width: 90px;
  height: 90px;
  border: 4px solid #fff;
  border-radius: 50%;
  position: relative;
  overflow: hidden;
  box-shadow: 0 3px 16px #3f5c9c12;
  transition: box-shadow 0.15s;
}
.avatar-uploader :deep(.el-upload:hover) {
  box-shadow: 0 0 0 3px #e1e9ff;
}
.avatar-uploader :deep(.el-upload:focus-visible) {
  outline: 2px solid #4166e8;
  outline-offset: 3px;
}
.profile-avatar,
.avatar-fallback {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.avatar-fallback {
  display: grid;
  place-items: center;
  background: #e6edff;
  color: #6a87da;
  font-size: 30px;
  font-weight: 600;
}
.avatar-edit {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 5px 0;
  background: #24355299;
  color: #fff;
  font-size: 10px;
  opacity: 0;
  transition: opacity 0.15s;
}
.avatar-uploader :deep(.el-upload:hover) .avatar-edit,
.avatar-uploader :deep(.el-upload:focus-visible) .avatar-edit {
  opacity: 1;
}
.identity-top h2 {
  margin: 17px 0 9px;
  color: #34445f;
  font-size: 19px;
  font-weight: 650;
  overflow-wrap: anywhere;
}
.identity-role {
  display: inline-block;
  padding: 4px 11px;
  border: 1px solid #e2e9fc;
  border-radius: 20px;
  background: #f1f5ff;
  color: #7791ce;
  font-size: 10px;
}
.identity-account {
  margin-top: 12px;
  color: #9aa5b7;
  font-size: 12px;
}
.avatar-guidance {
  padding: 0 18px 25px;
  text-align: center;
  font-size: 10px;
  color: #a2acbc;
  line-height: 1.9;
}
.avatar-guidance strong {
  display: block;
  margin-bottom: 5px;
  color: #7f8ca3;
  font-size: 11px;
  font-weight: 400;
}
.identity-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-top: 1px solid #eef1f6;
  padding: 15px 10px;
  color: #9ca9be;
  font-size: 10px;
  background: #fcfdff;
}
.identity-note .el-icon {
  font-size: 13px;
}
.form-card-heading {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 22px 27px;
  border-bottom: 1px solid #edf1f6;
}
.form-heading-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: #eff4ff;
  color: #8099d8;
  font-size: 18px;
}
.form-card-heading h2 {
  font-size: 14px;
  font-weight: 600;
  color: #4a5b78;
}
.form-card-heading p {
  margin-top: 5px;
  font-size: 11px;
  color: #a0aabb;
}
.profile-form {
  padding: 25px 27px 0;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}
.full-width {
  grid-column: 1 / -1;
}
.profile-form :deep(.el-form-item) {
  margin-bottom: 23px;
  min-width: 0;
}
.profile-form :deep(.el-form-item__label) {
  margin-bottom: 9px;
  color: #687891;
  font-size: 12px;
  line-height: 1.5;
}
.profile-form :deep(.el-input__wrapper) {
  min-height: 39px;
  padding: 0 12px;
  box-shadow: 0 0 0 1px #e2e8f2 inset;
  border-radius: 8px;
}
.profile-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px #8ba6f4 inset,
    0 0 0 3px #f0f4ff;
}
.profile-form :deep(.el-input__inner) {
  color: #5a6b88;
  font-size: 12px;
}
.profile-form :deep(.el-input__inner::placeholder) {
  color: #b1bac9;
}
.profile-form :deep(.el-input.is-disabled .el-input__wrapper) {
  background: #f7f9fc;
  box-shadow: 0 0 0 1px #edf0f6 inset;
}
.profile-form :deep(.el-input.is-disabled .el-input__inner) {
  -webkit-text-fill-color: #97a3b8;
}
.field-hint {
  margin-top: 6px;
  color: #a4afc0;
  font-size: 10px;
  line-height: 1.6;
}
.profile-form-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 3px;
  padding: 21px 0;
  border-top: 1px solid #edf1f6;
}
.profile-form-footer > span {
  font-size: 10px;
  color: #a3aec0;
}
.profile-form-footer .el-button {
  height: 37px;
  padding: 0 20px;
  font-size: 12px;
  border-radius: 8px;
}
@media (max-width: 1000px) {
  .profile-grid {
    grid-template-columns: 210px minmax(0, 1fr);
    gap: 17px;
  }
  .profile-form {
    padding: 22px 20px 0;
  }
  .form-card-heading {
    padding: 20px;
  }
}
@media (max-width: 850px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
  .identity-top {
    padding-top: 26px;
  }
  .avatar-guidance {
    padding-bottom: 20px;
  }
}
@media (max-width: 600px) {
  .profile-page-heading {
    margin-top: 0;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .full-width {
    grid-column: auto;
  }
  .profile-form-footer {
    align-items: stretch;
    flex-direction: column-reverse;
    gap: 12px;
  }
  .profile-form-footer > span {
    text-align: center;
  }
}
</style>
