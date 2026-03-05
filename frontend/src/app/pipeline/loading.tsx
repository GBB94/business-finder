export default function PipelineLoading() {
  return (
    <div className="p-6">
      <div className="mb-6 h-8 w-32 animate-pulse rounded bg-gray-800" />
      <div className="flex gap-4 overflow-x-auto pb-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="w-64 shrink-0 rounded-lg border border-gray-800 bg-gray-900/50"
          >
            <div className="border-b border-gray-800 px-3 py-2">
              <div className="h-4 w-20 animate-pulse rounded bg-gray-800" />
            </div>
            <div className="space-y-2 p-2">
              {Array.from({ length: 2 }).map((_, j) => (
                <div
                  key={j}
                  className="h-20 animate-pulse rounded-lg bg-gray-800/50"
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
