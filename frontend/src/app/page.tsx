export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-5xl font-bold tracking-tight mb-4">IdeaScope</h1>
      <p className="text-gray-400 text-lg mb-8 text-center max-w-md">
        Validate business ideas with structured evidence gates, scoring
        frameworks, and automated research.
      </p>
      <a
        href="/pipeline"
        className="rounded-lg bg-indigo-600 px-6 py-3 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
      >
        Open Pipeline
      </a>
    </main>
  );
}
