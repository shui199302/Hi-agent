export const SETTINGS_SECTION_IDS = ['mcp', 'skills', 'models', 'prompts', 'digital-human'] as const
export type SettingsSectionId = (typeof SETTINGS_SECTION_IDS)[number]
export const SETTINGS_DEFAULT_SECTION: SettingsSectionId = 'models'

export function hashSegments(): string[] {
  return window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
}

export function navigateTo(path: string): void {
  window.location.hash = path.startsWith('/') ? path : `/${path}`
}

export function isSettingsSection(value: string | undefined): value is SettingsSectionId {
  return SETTINGS_SECTION_IDS.some((item) => item === value)
}
