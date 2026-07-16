<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'chat'">
      <path d="M21 12a8 8 0 0 1-8 8H6l-4 2 1.3-4.4A9 9 0 1 1 21 12Z" />
      <path d="M8 12h.01M12 12h.01M16 12h.01" />
    </template>
    <template v-else-if="name === 'agents'">
      <rect x="4" y="7" width="16" height="13" rx="4" />
      <path d="M9 12h.01M15 12h.01M9 16h6M12 7V4M9 4h6" />
    </template>
    <template v-else-if="name === 'database'">
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </template>
    <template v-else-if="name === 'plug'">
      <path d="m8 12 4 4M15 5l4 4M14 6l-3.5 3.5a3.5 3.5 0 0 0 0 5l.5.5a3.5 3.5 0 0 0 5 0l3.5-3.5M9.5 14.5 4 20" />
    </template>
    <template v-else-if="name === 'sparkles'">
      <path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3ZM5 14l.8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8L5 14ZM19 13l.8 2.2 2.2.8-2.2.8L19 19l-.8-2.2L16 16l2.2-.8L19 13Z" />
    </template>
    <template v-else-if="name === 'server'">
      <rect x="3" y="4" width="18" height="6" rx="2" />
      <rect x="3" y="14" width="18" height="6" rx="2" />
      <path d="M7 7h.01M7 17h.01M11 7h6M11 17h6" />
    </template>
    <template v-else-if="name === 'plus'">
      <path d="M12 5v14M5 12h14" />
    </template>
    <template v-else-if="name === 'search'">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </template>
    <template v-else-if="name === 'upload'">
      <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />
    </template>
    <template v-else-if="name === 'download'">
      <path d="M12 4v12M7 11l5 5 5-5M4 20h16" />
    </template>
    <template v-else-if="name === 'trash'">
      <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5" />
    </template>
    <template v-else-if="name === 'edit'">
      <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
    </template>
    <template v-else-if="name === 'send'">
      <path d="m22 2-7 20-4-9-9-4ZM22 2 11 13" />
    </template>
    <template v-else-if="name === 'stop'">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </template>
    <template v-else-if="name === 'close'">
      <path d="m6 6 12 12M18 6 6 18" />
    </template>
    <template v-else-if="name === 'check'">
      <path d="m5 12 4 4L19 6" />
    </template>
    <template v-else-if="name === 'alert'">
      <path d="M10.3 3.7 2.6 17a2 2 0 0 0 1.8 3h15.2a2 2 0 0 0 1.8-3L13.7 3.7a2 2 0 0 0-3.4 0ZM12 9v4M12 17h.01" />
    </template>
    <template v-else-if="name === 'refresh'">
      <path d="M20 7v5h-5M4 17v-5h5M6.1 9A7 7 0 0 1 18.5 7.5L20 12M4 12l1.5 4.5A7 7 0 0 0 17.9 15" />
    </template>
    <template v-else-if="name === 'menu'">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </template>
    <template v-else-if="name === 'chevron'">
      <path d="m9 18 6-6-6-6" />
    </template>
    <template v-else-if="name === 'file'">
      <path d="M6 2h8l4 4v16H6ZM14 2v5h5M9 13h6M9 17h5" />
    </template>
    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </template>
    <template v-else-if="name === 'activity'">
      <path d="M3 12h4l2-7 4 14 2-7h6" />
    </template>
    <template v-else-if="name === 'copy'">
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8h.01M11 12h1v4h1" />
    </template>
  </svg>
</template>
