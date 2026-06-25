#!/usr/bin/env node

/**
 * 一次性拆分脚本：将聚合数据拆分为每角色一个 JSON 文件
 *
 * 读取：
 *   src/data/characters.json
 *   src/data/characterVisuals.json
 *   src/i18n/characters.ts (characterNameI18n + seriesI18n)
 *
 * 生成：
 *   src/content/characters/<id>.json  (每个角色一个文件)
 *
 * 每个 JSON 文件结构：
 * {
 *   "meta": { ...characters.json 中的字段（排除 image） },
 *   "visual": { image, thumb, accent },
 *   "i18n": { name: { locale: string }, series: { locale: string } }
 * }
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

const CONTENT_DIR = resolve(ROOT, 'src/content/characters')

function loadJSON(path) {
  return JSON.parse(readFileSync(resolve(ROOT, path), 'utf-8'))
}

/**
 * 从 i18n/characters.ts 提取 characterNameI18n 和 seriesI18n
 * 使用逐行解析，避免正则嵌套 { } 匹配问题
 */
function parseI18nFile() {
  const content = readFileSync(resolve(ROOT, 'src/i18n/characters.ts'), 'utf-8')
  const lines = content.split('\n')

  const nameI18n = {}
  const seriesI18n = {}

  extractBlock(lines, 'characterNameI18n', nameI18n)
  extractBlock(lines, 'seriesI18n', seriesI18n)

  return { nameI18n, seriesI18n }
}

/**
 * 逐行解析 TypeScript const 对象块
 * 从 `const <varName>` 开始，匹配到第一个顶层的 `}`
 */
function extractBlock(lines, varName, target) {
  let started = false
  let currentKey = null
  let currentEntries = {}

  for (const line of lines) {
    if (!started && line.includes(`const ${varName}`)) {
      started = true
      continue
    }

    if (!started) continue

    // 检测新条目开头: 'key': {  或  "key": {  或  key: {
    const keyMatch = line.match(/^\s*['"]([^'"]+)['"]\s*:\s*\{|^\s*([^\s'"{:]+)\s*:\s*\{/)
    if (keyMatch) {
      // 如果上一个 key 还没关闭，先保存
      if (currentKey && Object.keys(currentEntries).length > 0) {
        target[currentKey] = currentEntries
      }
      currentKey = keyMatch[1] || keyMatch[2]
      currentEntries = {}
      continue
    }

    // 检测 locale 行: 'zh-CN': '...', 或 en: '...',
    if (currentKey) {
      const localeMatch = line.match(/^\s*['"]?(zh-CN|zh-TW|en|ja)['"]?\s*:\s*['"]([^']*?)['"]/)
      if (localeMatch) {
        currentEntries[localeMatch[1]] = localeMatch[2]
      }
    }

    // 条目关闭 }, 或块关闭 }
    if (line.trim() === '},' || line.trim() === '}') {
      if (currentKey && Object.keys(currentEntries).length > 0) {
        target[currentKey] = currentEntries
      }
      currentKey = null
      currentEntries = {}
      // 顶层的 }（无逗号）= 块结束
      if (line.trim() === '}') {
        break
      }
    }
  }
}

function main() {
  console.log('\n📦 拆分角色数据为独立文件\n')

  const characters = loadJSON('src/data/characters.json')
  const visuals = loadJSON('src/data/characterVisuals.json')
  const { nameI18n, seriesI18n } = parseI18nFile()

  // 确保 target 目录存在
  mkdirSync(CONTENT_DIR, { recursive: true })

  let count = 0
  for (const char of characters) {
    const id = char.id
    if (!id) {
      console.warn(`  ⚠ 跳过无 id 角色: ${char.name}`)
      continue
    }

    const visual = visuals[id] || {}
    const nameLocales = nameI18n[id] || {}
    const seriesLocales = seriesI18n[char.series] || {}

    // 构建 meta（排除 id, image）
    const meta = { ...char }
    delete meta.image  // image 信息由 visual 提供

    const entry = {
      meta,
      visual: {
        image: visual.image || char.image || '',
        thumb: visual.thumb || '',
        accent: visual.accent || '',
      },
      i18n: {
        name: Object.keys(nameLocales).length > 0 ? nameLocales : undefined,
        series: Object.keys(seriesLocales).length > 0 ? seriesLocales : undefined,
      },
    }

    // 清理 undefined 字段
    if (!entry.i18n.name) delete entry.i18n.name
    if (!entry.i18n.series) delete entry.i18n.series

    const filePath = resolve(CONTENT_DIR, `${id}.json`)
    writeFileSync(filePath, JSON.stringify(entry, null, 2) + '\n', 'utf-8')
    count++
  }

  console.log(`  ✓ 已生成 ${count} 个角色文件到 src/content/characters/\n`)
}

main()
