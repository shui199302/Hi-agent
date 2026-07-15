import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StatusBadge from './StatusBadge.vue'

describe('StatusBadge', () => {
  it('translates healthy states and applies a positive tone', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'healthy' } })
    expect(wrapper.text()).toContain('健康')
    expect(wrapper.classes()).toContain('status-positive')
    wrapper.unmount()
  })

  it('allows an explicit user-facing label', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'running', label: '正在生成' } })
    expect(wrapper.text()).toContain('正在生成')
    expect(wrapper.classes()).toContain('status-progress')
    wrapper.unmount()
  })
})
