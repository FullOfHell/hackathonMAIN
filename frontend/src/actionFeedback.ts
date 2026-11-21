import { createContext, useContext } from 'react'

export type ActionResult = 'success' | 'error'
export const ActionFeedback = createContext<(result: ActionResult, message: string) => void>(() => {})
export const useActionFeedback = () => useContext(ActionFeedback)

export const feedbackDuration = 7000
export const BeforeSend = createContext<(label: string) => Promise<boolean>>(() => Promise.resolve(false))
export const useBeforeSend = () => useContext(BeforeSend)
