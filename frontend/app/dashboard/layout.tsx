import Nav from '@/components/Nav';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Nav />
      {/* min-w-0 is required here: a flex item's default min-width is
          "auto", meaning it refuses to shrink below its content's
          natural width. A wide table on any page would otherwise force
          this whole column (and the fixed-width Nav next to it) wider
          than the viewport instead of scrolling internally. */}
      <div className="min-w-0 flex-1 bg-slate-100">{children}</div>
    </div>
  );
}
