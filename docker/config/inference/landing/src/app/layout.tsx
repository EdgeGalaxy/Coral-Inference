import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { ConfigProvider } from '@/providers/config-provider'
import { QueryProvider } from '@/providers/query-provider'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Coral Inference Dashboard',
  description: 'Real-time inference pipeline monitoring and control dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <ConfigProvider>
          <QueryProvider>
            <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
              {children}
            </div>
          </QueryProvider>
        </ConfigProvider>
      </body>
    </html>
  )
}
