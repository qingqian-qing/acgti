import { parentPort, workerData } from 'node:worker_threads'

import { createFastProbabilitySimulator } from './probability-simulation-fast-engine.mjs'
import questions from '../src/data/questions.json' with { type: 'json' }
import archetypes from '../src/data/archetypes.json' with { type: 'json' }
import characters from '../src/data/characters.json' with { type: 'json' }
import questionDimensionWeights from '../src/data/questionDimensionWeights.json' with { type: 'json' }

const LCG_A = 1664525
const LCG_C = 1013904223
const LCG_M = 0x100000000

function geometricSum(a, n, m) {
  if (n === 0) return 0n
  if (n === 1) return 1n

  const aBig = BigInt(a)
  const mBig = BigInt(m)

  if (n % 2 === 0) {
    const half = geometricSum(a, n / 2, m)
    const aPowHalf = powMod(aBig, BigInt(n / 2), mBig)
    return (half * (1n + aPowHalf)) % mBig
  } else {
    const prev = geometricSum(a, n - 1, m)
    const aPowPrev = powMod(aBig, BigInt(n - 1), mBig)
    return (prev + aPowPrev) % mBig
  }
}

function powMod(base, exp, mod) {
  let result = 1n
  base = base % mod
  while (exp > 0n) {
    if (exp & 1n) {
      result = (result * base) % mod
    }
    base = (base * base) % mod
    exp >>= 1n
  }
  return result
}

function getNthState(state0, n) {
  if (n === 0) return state0 >>> 0

  const aBig = BigInt(LCG_A)
  const mBig = BigInt(LCG_M)

  const aPowN = powMod(aBig, BigInt(n), mBig)
  const sumCoef = geometricSum(LCG_A, n, mBig)

  const part1 = (aPowN * BigInt(state0)) % mBig
  const part2 = (BigInt(LCG_C) * sumCoef) % mBig

  return Number((part1 + part2) % mBig)
}

const answerScale = [-3, -2, -1, 0, 1, 2, 3]

const { startIndex, runs, mainSeed, questionsPerRun } = workerData

const initialState = getNthState(mainSeed, startIndex * questionsPerRun)
let rngState = initialState

const simulator = createFastProbabilitySimulator({
  questions,
  archetypes,
  characters,
  questionDimensionWeights,
})
const characterIds = simulator.characterIds
const winnerCounts = new Array(characterIds.length).fill(0)
const probabilityWeights = new Array(characterIds.length).fill(0)
const answers = new Array(questionsPerRun)

for (let i = 0; i < runs; i++) {
  for (let q = 0; q < questionsPerRun; q += 1) {
    rngState = (rngState * LCG_A + LCG_C) >>> 0
    answers[q] = answerScale[Math.floor((rngState / LCG_M) * answerScale.length)]
  }

  const result = simulator.run(answers)
  if (result.winnerIndex >= 0) {
    winnerCounts[result.winnerIndex] += 1
  }

  for (let index = 0; index < characterIds.length; index += 1) {
    probabilityWeights[index] += result.weights[index]
  }
}

parentPort.postMessage({
  winnerCounts,
  probabilityWeights,
})
