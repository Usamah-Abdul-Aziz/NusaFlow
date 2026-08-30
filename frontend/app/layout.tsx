import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'NusaFlow — Supply Chain Control Tower',
  description: 'Monitor inventory, shipments, risks, forecasts, and simulate supply scenarios.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
