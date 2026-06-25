import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Worker } from 'node:worker_threads'
import os from 'node:os'

import { createFastProbabilitySimulator } from './probability-simulation-fast-engine.mjs'
import questions from '../src/data/questions.json' with { type: 'json' }
import archetypes from '../src/data/archetypes.json' with { type: 'json' }
import characters from '../src/data/characters.json' with { type: 'json' }
import questionDimensionWeights from '../src/data/questionDimensionWeights.json' with { type: 'json' }

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const outputPath = path.join(root, 'src/data/characterProbabilities.json')
const cliArgs = process.argv.slice(2)
const positionalArgs = cliArgs.filter((arg) => !arg.startsWith('--'))

const answerScale = [-3, -2, -1, 0, 1, 2, 3]
const seed = Number(positionalArgs[0] ?? 20260411)
const runs = Number(positionalArgs[1] ?? 200000)
const shouldWrite = cliArgs.includes('--write')
const singleThread = cliArgs.includes('--single-thread')
const threadsArg = cliArgs.find((arg) => arg.startsWith('--threads='))
const requestedWorkers = threadsArg ? Number(threadsArg.split('=')[1]) : null
const defaultWorkers = Math.min(os.availableParallelism?.() ?? os.cpus().length, 8, runs)
const numWorkers = singleThread ? 1 : Math.max(1, Math.min(requestedWorkers ?? defaultWorkers, runs))
const useMultithread = numWorkers > 1
const questionsPerRun = questions.length
const simulator = createFastProbabilitySimulator({
  questions,
  archetypes,
  characters,
  questionDimensionWeights,
})
const characterIds = simulator.characterIds

function roundProbability(value) {
  if (value >= 0.01) {
    return Number(value.toFixed(4))
  }

  if (value >= 0.0001) {
    return Number(value.toFixed(6))
  }

  return Number(value.toPrecision(8))
}

function buildRoundedProbabilities(weightEntries, runCount) {
  const sortedEntries = [...weightEntries]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], 'en'))

  const roundedEntries = sortedEntries.map(([id, accumulatedWeight]) => [
    id,
    roundProbability((accumulatedWeight / runCount) * 100),
  ])

  const roundedTotal = roundedEntries.reduce((sum, [, value]) => sum + value, 0)
  const roundingDelta = Number((100 - roundedTotal).toFixed(8))

  if (roundedEntries.length && roundingDelta !== 0) {
    roundedEntries[0][1] = Number((roundedEntries[0][1] + roundingDelta).toFixed(8))
  }

  return Object.fromEntries(roundedEntries)
}

function createEmptyTotals() {
  return new Array(characterIds.length).fill(0)
}

function accumulateSimulationResult(result, winnerCounts, probabilityWeights) {
  if (result.winnerIndex >= 0) {
    winnerCounts[result.winnerIndex] += 1
  }

  for (let index = 0; index < characterIds.length; index += 1) {
    probabilityWeights[index] += result.weights[index]
  }
}

function totalsToMap(totals) {
  return new Map(characterIds.map((id, index) => [id, totals[index]]))
}

function runSingleThread() {
  const winnerCounts = createEmptyTotals()
  const probabilityWeights = createEmptyTotals()
  const answers = new Array(questionsPerRun)
  let rngState = seed >>> 0

  for (let index = 0; index < runs; index += 1) {
    for (let q = 0; q < questionsPerRun; q += 1) {
      rngState = (rngState * 1664525 + 1013904223) >>> 0
      answers[q] = answerScale[Math.floor((rngState / 0x100000000) * answerScale.length)]
    }

    const result = simulator.run(answers)
    accumulateSimulationResult(result, winnerCounts, probabilityWeights)
  }

  return {
    winnerCounts: totalsToMap(winnerCounts),
    probabilityWeights: totalsToMap(probabilityWeights),
  }
}

async function runSimulation() {
  let result

  if (useMultithread) {
    console.log(`Running ${runs} simulations across ${numWorkers} workers (deterministic)...`)

    const workers = []
    const runsPerWorker = Math.floor(runs / numWorkers)

    for (let i = 0; i < numWorkers; i++) {
      const startIndex = i * runsPerWorker
      const workerRuns = i === numWorkers - 1 ? runs - runsPerWorker * (numWorkers - 1) : runsPerWorker

      const worker = new Worker(path.join(__dirname, 'probability-simulation-worker.mjs'), {
        workerData: {
          startIndex,
          runs: workerRuns,
          mainSeed: seed,
          questionsPerRun,
        },
      })

      workers.push(new Promise((resolve, reject) => {
        worker.on('message', resolve)
        worker.on('error', reject)
        worker.on('exit', (code) => {
          if (code !== 0) {
            reject(new Error(`Worker stopped with exit code ${code}`))
          }
        })
      }))
    }

    const results = await Promise.all(workers)

    const totalWinnerCounts = createEmptyTotals()
    const totalProbabilityWeights = createEmptyTotals()

    for (const res of results) {
      for (let index = 0; index < characterIds.length; index += 1) {
        totalWinnerCounts[index] += res.winnerCounts[index] ?? 0
        totalProbabilityWeights[index] += res.probabilityWeights[index] ?? 0
      }
    }

    result = {
      winnerCounts: totalsToMap(totalWinnerCounts),
      probabilityWeights: totalsToMap(totalProbabilityWeights),
    }
  } else {
    console.log(`Running ${runs} simulations (single thread, deterministic)...`)
    result = runSingleThread()
  }

  const { winnerCounts, probabilityWeights } = result
  const probabilities = buildRoundedProbabilities(probabilityWeights.entries(), runs)

  const entries = [...probabilityWeights.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([id, accumulatedWeight]) => ({
      id,
      displayWeight: accumulatedWeight,
      displayProbability: probabilities[id],
      winnerCount: winnerCounts.get(id) ?? 0,
      probability: probabilities[id],
    }))

  const payload = {
    seed,
    runs,
    method: 'softmax-score-share',
    probabilities,
    entries,
  }

  if (shouldWrite) {
    fs.writeFileSync(
      outputPath,
      JSON.stringify({
        seed,
        runs,
        method: 'softmax-score-share',
        probabilities,
      }, null, 2) + '\n',
    )
    console.log(`Updated ${path.relative(root, outputPath)} with ${runs} runs (seed=${seed}).`)
  } else {
    console.log(JSON.stringify(payload, null, 2))
  }
}

runSimulation().catch(console.error)
