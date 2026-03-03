import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  message: string
  type: ToastType
}

interface ToastContextType {
  toast: (message: string, type?: ToastType) => void
}

const ToastContext = createContext<ToastContextType>({ toast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

let nextId = 0

const BORDER_COLORS: Record<ToastType, string> = {
  success: '#16a34a',
  error: '#dc2626',
  info: '#2563eb',
}

const AUTO_DISMISS_MS = 4000

function ToastMessage({ item, onRemove }: { item: ToastItem; onRemove: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onRemove(item.id), AUTO_DISMISS_MS)
    return () => clearTimeout(timer)
  }, [item.id, onRemove])

  return (
    <div
      className="flex items-start gap-3 px-4 py-3 min-w-[280px] max-w-[400px] relative overflow-hidden"
      style={{
        background: '#ffffff',
        borderLeft: `3px solid ${BORDER_COLORS[item.type]}`,
        boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
      }}
    >
      <p className="text-sm flex-1" style={{ color: '#111827' }}>{item.message}</p>
      <button
        onClick={() => onRemove(item.id)}
        className="flex-shrink-0 p-0.5 transition-colors"
        style={{ color: '#9ca3af' }}
        onMouseEnter={e => (e.currentTarget.style.color = '#6b7280')}
        onMouseLeave={e => (e.currentTarget.style.color = '#9ca3af')}
      >
        <X size={14} />
      </button>
      <div
        className="absolute bottom-0 left-0 h-0.5"
        style={{
          background: BORDER_COLORS[item.type],
          animation: `toast-progress ${AUTO_DISMISS_MS}ms linear forwards`,
        }}
      />
    </div>
  )
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++nextId
    setToasts(prev => [...prev, { id, message, type }])
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {createPortal(
        <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
          {toasts.map(item => (
            <ToastMessage key={item.id} item={item} onRemove={removeToast} />
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}
