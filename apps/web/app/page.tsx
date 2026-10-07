export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-8 py-20">
      <p className="mb-4 text-sm uppercase tracking-[0.3em] text-amber-300">Project foundation</p>
      <h1 className="text-5xl font-semibold tracking-tight">RE <span className="text-zinc-400">/ Realm Engine</span></h1>
      <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-300">
        The world is being prepared. The web app, API, data store, and local AI runtime are ready to connect.
      </p>
      <div className="mt-10 grid gap-3 sm:grid-cols-3">
        {["Web · Next.js", "API · FastAPI", "AI · Ollama"].map((item) => (
          <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-sm text-zinc-200" key={item}>{item}</div>
        ))}
      </div>
    </main>
  );
}
