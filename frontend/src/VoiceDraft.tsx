import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'

const recordingTypes = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']
const maxSeconds = 30

interface VoiceDraftProps {
  remaining: number
  disabled: boolean
  onAdd: (text: string) => void
}

export function VoiceDraft({ remaining, disabled, onAdd }: VoiceDraftProps) {
  const [enabled, setEnabled] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'permission' | 'recording' | 'ready' | 'sending' | 'review'>('idle')
  const [audio, setAudio] = useState<Blob | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const mounted = useRef(false)
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const take = useRef(0)

  useEffect(() => {
    mounted.current = true
    let active = true
    api.transcriptionStatus().then(
      (status) => { if (active) setEnabled(status.enabled) },
      () => { if (active) setEnabled(false) },
    )
    return () => {
      active = false
      mounted.current = false
      take.current += 1
      window.clearTimeout(timer.current)
      const capture = recorder.current
      recorder.current = null
      if (capture?.state === 'recording') capture.stop()
      stream.current?.getTracks().forEach((track) => track.stop())
      stream.current = null
    }
  }, [])

  async function start() {
    const version = ++take.current
    const mimeType = recordingTypes.find((type) => MediaRecorder.isTypeSupported(type))
    if (!mimeType) {
      setError('This browser cannot make a supported recording. You can type your report.')
      return
    }
    setPhase('permission')
    setError('')
    try {
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!mounted.current || version !== take.current) {
        microphone.getTracks().forEach((track) => track.stop())
        return
      }
      stream.current = microphone
      const capture = new MediaRecorder(microphone, { mimeType })
      const chunks: Blob[] = []
      capture.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data) }
      capture.onstop = () => {
        if (recorder.current !== capture) return
        releaseRecording()
        const clip = new Blob(chunks, { type: capture.mimeType || mimeType })
        if (!clip.size) {
          setError('Nothing was recorded. Try again or type your report.')
          setPhase('idle')
          return
        }
        setAudio(clip)
        setPhase('ready')
      }
      capture.onerror = () => {
        if (recorder.current !== capture) return
        releaseRecording()
        setError('Recording failed. Try again or type your report.')
        setPhase('idle')
      }
      recorder.current = capture
      capture.start()
      timer.current = window.setTimeout(stop, maxSeconds * 1000)
      setPhase('recording')
    } catch {
      if (!mounted.current || version !== take.current) return
      releaseRecording()
      setError('Could not access the microphone. Check permissions or type your report.')
      setPhase('idle')
    }
  }

  function releaseRecording() {
    window.clearTimeout(timer.current)
    recorder.current = null
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
  }

  function stop() {
    if (recorder.current?.state === 'recording') recorder.current.stop()
  }

  function discard() {
    take.current += 1
    const capture = recorder.current
    releaseRecording()
    if (capture?.state === 'recording') capture.stop()
    setAudio(null)
    setText('')
    setError('')
    setPhase('idle')
  }

  async function transcribe() {
    if (!audio) return
    const version = ++take.current
    setPhase('sending')
    setError('')
    try {
      const result = await api.transcribeRecording(audio)
      if (version !== take.current) return
      setText(result.text)
      setAudio(null)
      setPhase('review')
    } catch (failure) {
      if (version !== take.current) return
      setError(failure instanceof Error && failure.name !== 'TimeoutError'
        ? failure.message : 'Transcription timed out. Retry or type your report.')
      setPhase('ready')
    }
  }

  if (!enabled || typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) return null
  const transcript = text.trim()

  return (
    <section className="voice-draft" aria-label="Voice input">
      <p className="muted">Record up to {maxSeconds} seconds. Selecting Transcribe sends the clip to the configured speech-to-text provider.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {phase === 'permission' && <p role="status">Waiting for microphone access…</p>}
      {phase === 'recording' && <p role="status">Recording…</p>}
      {phase === 'sending' && <p role="status">Transcribing recording…</p>}
      {phase === 'review' && <>
        <label htmlFor="voice-transcript">Review transcript</label>
        <textarea id="voice-transcript" rows={3} value={text} onChange={(event) => setText(event.target.value)} />
        {transcript.length > remaining && <p className="error" role="status">Shorten the transcript to fit the report.</p>}
      </>}
      <div className="actions">
        {phase === 'idle' && <button className="secondary" type="button" disabled={disabled || remaining < 1}
          onClick={() => void start()}>Record voice report</button>}
        {phase === 'recording' && <button type="button" onClick={stop}>Stop recording</button>}
        {phase === 'ready' && <button type="button" disabled={disabled} onClick={() => void transcribe()}>
          {error ? 'Retry transcription' : 'Transcribe recording'}
        </button>}
        {phase === 'review' && <button type="button" disabled={disabled || !transcript || transcript.length > remaining}
          onClick={() => { onAdd(transcript); discard() }}>Add transcript to report</button>}
        {phase !== 'idle' && <button className="secondary" type="button" onClick={discard}>
          {phase === 'review' ? 'Discard transcript' : 'Discard recording'}
        </button>}
      </div>
    </section>
  )
}
