import { readonly, ref } from 'vue'

export interface Notice {
  id: number
  tone: 'success' | 'error' | 'info'
  message: string
}

const notices = ref<Notice[]>([])
let serial = 0

export const notificationState = readonly(notices)

export function notify(message: string, tone: Notice['tone'] = 'info'): void {
  const id = ++serial
  notices.value.push({ id, tone, message })
  window.setTimeout(() => dismissNotice(id), 4200)
}

export function dismissNotice(id: number): void {
  notices.value = notices.value.filter((item) => item.id !== id)
}
