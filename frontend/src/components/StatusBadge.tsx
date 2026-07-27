const COLORS: Record<string, string> = {
  active: 'bg-slate-200 text-slate-700',
  running_tools: 'bg-blue-100 text-blue-700 animate-pulse',
  running: 'bg-blue-100 text-blue-700 animate-pulse',
  comparing: 'bg-violet-100 text-violet-700 animate-pulse',
  completed: 'bg-emerald-100 text-emerald-700',
  partial: 'bg-teal-100 text-teal-700',
  not_found: 'bg-amber-100 text-amber-700',
  blocked: 'bg-orange-100 text-orange-700',
  canceled: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-700',
};

export default function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] ?? 'bg-slate-200 text-slate-700';
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {status.replace('_', ' ')}
    </span>
  );
}
