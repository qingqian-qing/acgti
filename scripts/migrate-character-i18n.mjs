#!/usr/bin/env node

/**
 * 从 main 分支的 messages.ts 中提取角色翻译数据，写入角色源文件
 */

import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

const SOURCE_DIR = resolve(ROOT, 'src/content/characters')
const MESSAGES_PATH = resolve(ROOT, 'src/i18n/messages.ts')

/**
 * 从 messages.ts 提取所有 locale 的角色翻译块
 * 返回格式: { 'zh-TW': { 'hatsune-miku': { title, tags, note } }, ... }
 */
function extractCharacterMessages(filePath) {
  const content = readFileSync(filePath, 'utf-8')
  const lines = content.split('\n')

  const result = {}
  let currentLocale = null
  let currentCharId = null
  let currentCharData = {}
  let currentField = null
  let currentFieldValue = ''
  let inCharBlock = false
  let braceDepth = 0

  // Locale start detection
  const localeStartRegex = /^  (zh-CN|zh-TW|en|ja):\s*\{/

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Detect locale start
    const localeMatch = line.match(localeStartRegex)
    if (localeMatch) {
      // Save previous character
      if (currentLocale && currentCharId && Object.keys(currentCharData).length > 0) {
        if (!result[currentLocale]) result[currentLocale] = {}
        result[currentLocale][currentCharId] = currentCharData
      }
      currentLocale = localeMatch[1]
      currentCharId = null
      inCharBlock = false
      braceDepth = 0
      continue
    }

    if (!currentLocale) continue

    // Detect character block start: 'some-id': {
    const charMatch = trimmed.match(/^'([a-z][a-z0-9-]*)':\s*\{$/)
    if (charMatch && !inCharBlock) {
      // This could be a character block or something else
      // We'll check if it has title/tags/note fields
      currentCharId = charMatch[1]
      currentCharData = {}
      currentField = null
      braceDepth = 1
      inCharBlock = true
      continue
    }

    if (!inCharBlock) continue

    // Track braces
    braceDepth += (line.match(/\{/g) || []).length
    braceDepth -= (line.match(/\}/g) || []).length

    // Field detection within character block
    if (braceDepth >= 1) {
      // title: 'xxx' or title: "xxx"
      const titleMatch = trimmed.match(/^title:\s*'(.*)',?$/)
      if (titleMatch) {
        currentCharData.title = titleMatch[1]
        continue
      }

      // note: 'xxx' (may be multi-line)
      const noteMatch = trimmed.match(/^note:\s*'(.*)',?$/)
      if (noteMatch) {
        currentCharData.note = noteMatch[1]
        continue
      }

      // tags: ['xxx', 'yyy']
      const tagsMatch = trimmed.match(/^tags:\s*\[(.*)\],?$/)
      if (tagsMatch) {
        const tags = []
        const tagRegex = /'([^']*)'/g
        let tm
        while ((tm = tagsMatch[1].matchAll ? tagsMatch[1].matchAll(tagRegex) : [])[0]) {
          // Manual matchAll fallback
        }
        // Simpler approach
        const tagStr = tagsMatch[1]
        const tagParts = tagStr.split(',').map(s => s.trim().replace(/^'|'$/g, ''))
        currentCharData.tags = tagParts
        continue
      }

      // Multi-line array for tags
      if (trimmed.startsWith('tags: [')) {
        const partial = trimmed.replace(/^tags:\s*\[/, '')
        if (trimmed.endsWith('],')) {
          // Single line but might have complex content
          const tagStr = partial.replace(/\],?$/, '')
          const tagParts = tagStr.split(',').map(s => s.trim().replace(/^'|'$/g, ''))
          currentCharData.tags = tagParts
        }
        continue
      }

      // Array element (for multi-line tags)
      if (trimmed.startsWith("'") && !trimmed.includes(':')) {
        // Could be a tag element
        if (!currentCharData._rawTags) currentCharData._rawTags = []
        const tagVal = trimmed.replace(/^'|',$/g, '').replace(/'$/, '')
        currentCharData._rawTags.push(tagVal)
        continue
      }
    }

    // Block closed
    if (braceDepth <= 0) {
      inCharBlock = false

      // If we collected raw tags, combine them
      if (currentCharData._rawTags) {
        if (!currentCharData.tags) currentCharData.tags = currentCharData._rawTags
        delete currentCharData._rawTags
      }

      // Only save if it has at least one character field (title/note/tags)
      if (currentCharId && (currentCharData.title || currentCharData.note || currentCharData.tags)) {
        if (!result[currentLocale]) result[currentLocale] = {}
        result[currentLocale][currentCharId] = { ...currentCharData }
      }

      currentCharId = null
      currentCharData = {}
      currentField = null
    }
  }

  // Save last entry
  if (currentLocale && currentCharId && (currentCharData.title || currentCharData.note || currentCharData.tags)) {
    if (!result[currentLocale]) result[currentLocale] = {}
    result[currentLocale][currentCharId] = { ...currentCharData }
  }

  return result
}

function main() {
  console.log('\n📦 从 messages.ts 提取角色翻译数据\n')

  const charMessages = extractCharacterMessages(MESSAGES_PATH)

  // Also try from main branch if available
  try {
    const { execSync } = await import('child_process')
  } catch {}

  // Stats
  for (const locale of ['zh-TW', 'en', 'ja']) {
    const count = charMessages[locale] ? Object.keys(charMessages[locale]).length : 0
    console.log(`  ${locale}: ${count} 个角色翻译`)
  }

  // Merge into source files
  const files = readdirSync(SOURCE_DIR).filter(f => f.endsWith('.json'))
  let updated = 0

  for (const file of files) {
    const filePath = resolve(SOURCE_DIR, file)
    const entry = JSON.parse(readFileSync(filePath, 'utf-8'))
    const id = entry.meta?.id
    if (!id) continue

    let changed = false
    if (!entry.i18n) entry.i18n = {}

    for (const locale of ['zh-TW', 'en', 'ja']) {
      const charData = charMessages[locale]?.[id]
      if (!charData) continue

      if (charData.title || charData.note || charData.tags) {
        if (!entry.i18n[locale]) entry.i18n[locale] = {}
        if (charData.title) entry.i18n[locale].title = charData.title
        if (charData.note) entry.i18n[locale].note = charData.note
        if (charData.tags) entry.i18n[locale].tags = charData.tags
        changed = true
      }
    }

    if (changed) {
      writeFileSync(filePath, JSON.stringify(entry, null, 2) + '\n', 'utf-8')
      updated++
    }
  }

  console.log(`\n  ✓ 更新了 ${updated} 个角色源文件\n`)
}

main()
