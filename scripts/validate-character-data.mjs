#!/usr/bin/env node

/**
 * 角色数据校验脚本
 *
 * 支持两种模式：
 *   1. 校验 src/content/characters/*.json 源文件（优先）
 *   2. 若源文件不存在，回退到校验 src/data/characters.json
 *
 * 同时校验与 characterVisuals.json、i18n/characters.ts 的一致性。
 *
 * 用法：
 *   node scripts/validate-character-data.mjs
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

// ── 合法值集合 ──────────────────────────────────────────────────────────────

const VALID_MBTI = new Set([
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP',
])

const VALID_ARCHETYPES = new Set([
  'luminous-lead',
  'icebound-observer',
  'oathbound-captain',
  'trickster-orbit',
  'gentle-healer',
  'shadow-strategist',
  'chaos-spark',
  'moonlit-guardian',
])

const VALID_DIMENSIONS = new Set([
  'expression', 'temperature', 'judgement', 'order', 'agency', 'aura',
])

const VALID_LOCALES = new Set(['zh-CN', 'zh-TW', 'en', 'ja'])

const VALID_PERSONA_BASIS_TYPES = new Set(['canon', 'fandom-impression'])
const VALID_CONFIDENCE = new Set(['high', 'medium', 'low'])

// ── 工具函数 ────────────────────────────────────────────────────────────────

let errorCount = 0
let warningCount = 0

function error(msg) {
  console.error(`  ✗ ${msg}`)
  errorCount++
}

function warn(msg) {
  console.warn(`  ⚠ ${msg}`)
  warningCount++
}

function loadJSON(path) {
  const raw = readFileSync(resolve(ROOT, path), 'utf-8')
  return JSON.parse(raw)
}

// ── i18n 解析 ───────────────────────────────────────────────────────────────

function extractI18nBlock(varName) {
  const content = readFileSync(resolve(ROOT, 'src/i18n/characters.ts'), 'utf-8')
  const lines = content.split('\n')
  const result = {}

  let started = false
  let currentKey = null
  let currentEntries = {}

  for (const line of lines) {
    if (!started && line.includes(`const ${varName}`)) {
      started = true
      continue
    }
    if (!started) continue

    const keyMatch = line.match(/^\s*['"]([^'"]+)['"]\s*:\s*\{|^\s*([^\s'"{:]+)\s*:\s*\{/)
    if (keyMatch) {
      if (currentKey && Object.keys(currentEntries).length > 0) {
        result[currentKey] = currentEntries
      }
      currentKey = keyMatch[1] || keyMatch[2]
      currentEntries = {}
      continue
    }

    if (currentKey) {
      const localeMatch = line.match(/^\s*['"]?(zh-CN|zh-TW|en|ja)['"]?\s*:\s*['"]([^']*?)['"]/)
      if (localeMatch) {
        currentEntries[localeMatch[1]] = localeMatch[2]
      }
    }

    if (line.trim() === '},' || line.trim() === '}') {
      if (currentKey && Object.keys(currentEntries).length > 0) {
        result[currentKey] = currentEntries
      }
      currentKey = null
      currentEntries = {}
      if (line.trim() === '}') break
    }
  }

  return result
}

// ── 角色校验 ────────────────────────────────────────────────────────────────

function validateCharacter(char, prefix) {
  // 必填字段
  const requiredFields = ['id', 'name', 'series', 'matchCode', 'code', 'archetypeId', 'tags', 'note', 'vector']
  for (const field of requiredFields) {
    if (!char[field]) {
      error(`${prefix} 缺少必填字段: ${field}`)
    }
  }

  if (!char.id) return

  // matchCode 合法
  if (char.matchCode && !VALID_MBTI.has(char.matchCode)) {
    error(`${prefix} matchCode 不合法: ${char.matchCode}`)
  }

  // matchCodeFlex 合法
  if (Array.isArray(char.matchCodeFlex)) {
    for (const code of char.matchCodeFlex) {
      if (!VALID_MBTI.has(code)) {
        error(`${prefix} matchCodeFlex 条目不合法: ${code}`)
      }
    }
  }

  // archetypeId 合法
  if (char.archetypeId && !VALID_ARCHETYPES.has(char.archetypeId)) {
    error(`${prefix} archetypeId 不合法: ${char.archetypeId}`)
  }

  // vector 校验
  if (char.vector) {
    const vecKeys = Object.keys(char.vector)
    const missingDims = [...VALID_DIMENSIONS].filter(d => !vecKeys.includes(d))
    if (missingDims.length > 0) {
      error(`${prefix} vector 缺少维度: ${missingDims.join(', ')}`)
    }
    for (const [dim, val] of Object.entries(char.vector)) {
      if (!VALID_DIMENSIONS.has(dim)) {
        warn(`${prefix} vector 含未知维度: ${dim}`)
      }
      if (typeof val !== 'number' || val < -1 || val > 1) {
        error(`${prefix} vector.${dim} 值越界: ${val}（应在 [-1, 1]）`)
      }
    }
  }

  // matchWeight
  if (char.matchWeight !== undefined) {
    if (typeof char.matchWeight !== 'number' || char.matchWeight <= 0) {
      error(`${prefix} matchWeight 应为正数，当前: ${char.matchWeight}`)
    }
  }

  // personaBasis
  if (char.personaBasis) {
    if (!VALID_PERSONA_BASIS_TYPES.has(char.personaBasis.type)) {
      error(`${prefix} personaBasis.type 不合法: ${char.personaBasis.type}`)
    }
    if (!VALID_CONFIDENCE.has(char.personaBasis.confidence)) {
      error(`${prefix} personaBasis.confidence 不合法: ${char.personaBasis.confidence}`)
    }
    if (!char.personaBasis.label || !char.personaBasis.summary) {
      error(`${prefix} personaBasis 缺少 label 或 summary`)
    }
  }

  // signature
  if (char.signature?.uniqueAxes) {
    for (const dim of Object.keys(char.signature.uniqueAxes)) {
      if (!VALID_DIMENSIONS.has(dim)) {
        warn(`${prefix} signature.uniqueAxes 含未知维度: ${dim}`)
      }
    }
  }

  if (char.signature?.questionAffinity) {
    for (const qa of char.signature.questionAffinity) {
      if (!qa.questionId) {
        error(`${prefix} signature.questionAffinity 条目缺少 questionId`)
      }
      if (!['agree', 'disagree', 'neutral'].includes(qa.expected)) {
        error(`${prefix} signature.questionAffinity.expected 不合法: ${qa.expected}`)
      }
    }
  }

  // tags
  if (Array.isArray(char.tags) && char.tags.length === 0) {
    warn(`${prefix} tags 为空数组`)
  }
}

// ── 主逻辑 ──────────────────────────────────────────────────────────────────

function main() {
  console.log('\n📋 ACGTI 角色数据校验\n')

  const SOURCE_DIR = resolve(ROOT, 'src/content/characters')

  // 加载 visuals 和 i18n
  const visuals = loadJSON('src/data/characterVisuals.json')
  const nameI18n = extractI18nBlock('characterNameI18n')
  const seriesI18n = extractI18nBlock('seriesI18n')
  const visualIds = new Set(Object.keys(visuals))

  let characters = []
  let mode = ''

  // 优先从 src/content/characters/ 读取
  if (existsSync(SOURCE_DIR)) {
    const files = readdirSync(SOURCE_DIR).filter(f => f.endsWith('.json'))
    if (files.length > 0) {
      mode = 'source'
      for (const file of files) {
        const entry = JSON.parse(readFileSync(resolve(SOURCE_DIR, file), 'utf-8'))
        characters.push({ ...entry.meta, _visual: entry.visual, _i18n: entry.i18n })
      }
    }
  }

  // 回退到 src/data/characters.json
  if (mode !== 'source') {
    mode = 'legacy'
    characters = loadJSON('src/data/characters.json')
  }

  const characterIds = new Set()
  const characterCodes = new Map()
  const characterNames = new Map()

  console.log(`  模式: ${mode === 'source' ? '源文件 (src/content/characters/)' : '聚合文件 (src/data/characters.json)'}`)
  console.log(`  角色总数: ${characters.length}`)
  console.log(`  Visual 条目: ${visualIds.size}`)
  console.log(`  i18n 名称条目: ${Object.keys(nameI18n).length}`)
  console.log()

  for (const char of characters) {
    const prefix = `[${char.id || '???'}]`

    validateCharacter(char, prefix)

    if (!char.id) continue

    // id 唯一性
    if (characterIds.has(char.id)) {
      error(`${prefix} id 重复: ${char.id}`)
    }
    characterIds.add(char.id)

    // code 唯一性
    if (char.code) {
      if (characterCodes.has(char.code)) {
        error(`${prefix} code 重复: ${char.code}（与 ${characterCodes.get(char.code)} 冲突）`)
      }
      characterCodes.set(char.code, char.id)
    }

    // name 唯一性
    if (char.name) {
      if (characterNames.has(char.name)) {
        warn(`${prefix} name 重复: ${char.name}（与 ${characterNames.get(char.name)} 相同）`)
      }
      characterNames.set(char.name, char.id)
    }

    // visual 校验
    if (mode === 'source' && char._visual) {
      const v = char._visual
      if (!v.image) error(`${prefix} visual 缺少 image`)
      if (!v.accent) error(`${prefix} visual 缺少 accent`)
      if (v.accent && !/^#[0-9a-fA-F]{3,8}$/.test(v.accent)) {
        error(`${prefix} visual.accent 格式不合法: ${v.accent}`)
      }
    } else {
      if (!visualIds.has(char.id)) {
        warn(`${prefix} 在 characterVisuals.json 中无对应条目`)
      } else {
        const v = visuals[char.id]
        if (!v.image) error(`${prefix} visual 缺少 image`)
        if (!v.accent) error(`${prefix} visual 缺少 accent`)
        if (v.accent && !/^#[0-9a-fA-F]{3,8}$/.test(v.accent)) {
          error(`${prefix} visual.accent 格式不合法: ${v.accent}`)
        }
      }
    }

    // i18n 校验
    if (mode === 'source' && char._i18n) {
      if (!char._i18n.name || Object.keys(char._i18n.name).length === 0) {
        warn(`${prefix} 源文件中缺少 i18n.name 翻译`)
      }
      // title/note/tags 翻译完整性
      for (const locale of ['zh-TW', 'en', 'ja']) {
        const localeData = char._i18n[locale]
        if (!localeData) {
          warn(`${prefix} 源文件中缺少 i18n.${locale} 翻译（title/note/tags）`)
        } else {
          if (!localeData.title) warn(`${prefix} 源文件中缺少 i18n.${locale}.title`)
          if (!localeData.note) warn(`${prefix} 源文件中缺少 i18n.${locale}.note`)
          if (!localeData.tags) warn(`${prefix} 源文件中缺少 i18n.${locale}.tags`)
        }
      }
    } else {
      if (!nameI18n[char.id]) {
        warn(`${prefix} 在 i18n/characters.ts 中无名称翻译`)
      }
    }
  }

  // 孤儿检测（仅 legacy 模式）
  if (mode === 'legacy') {
    for (const vid of visualIds) {
      if (!characterIds.has(vid)) {
        warn(`characterVisuals.json 中有孤儿条目: ${vid}（无对应角色）`)
      }
    }
    for (const iid of Object.keys(nameI18n)) {
      if (!characterIds.has(iid)) {
        warn(`i18n/characters.ts 中有孤儿条目: ${iid}（无对应角色）`)
      }
    }
  }

  // 汇总
  console.log()
  console.log('──────────────────────────────')
  if (errorCount === 0 && warningCount === 0) {
    console.log('✓ 所有校验通过，数据一致。')
  } else {
    console.log(`  错误: ${errorCount}`)
    console.log(`  警告: ${warningCount}`)
    if (errorCount > 0) {
      console.log('\n✗ 存在错误，请修复后重新校验。')
      process.exit(1)
    } else {
      console.log('\n⚠ 仅有警告，可以继续，但建议检查。')
    }
  }
  console.log()
}

main()
