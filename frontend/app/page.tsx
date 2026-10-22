const principles = [
  { name: "Grounded", text: "Every finding cites a brand rule or an approved fact." },
  { name: "Explainable", text: "Plain-language reasons, evidence quotes and confidence." },
  { name: "Human-controlled", text: "AI suggests. People decide, and every decision is logged." },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center gap-10 px-6 py-16">
      <header>
        <h1 className="text-5xl font-bold tracking-tight">Preflight</h1>
        <p className="mt-3 text-xl text-navy-700">Content cleared before it goes live.</p>
      </header>
      <ul className="grid gap-4 sm:grid-cols-3">
        {principles.map((p) => (
          <li key={p.name} className="rounded-xl border border-navy-100 bg-navy-50 p-5">
            <h2 className="font-semibold text-teal-700">{p.name}</h2>
            <p className="mt-1 text-sm">{p.text}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
